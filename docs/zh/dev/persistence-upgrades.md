# 持久化升级与迁移

本页是 AstrBot 跨版本处理持久化状态的约定。改动数据库模型、配置键或数据目录结构之前，请先读这一页。

> **状态：已实现。** 每个存储的迁移执行器、ledger、主库重塑与旧库导入都已落地。主库现在是 `data/astrbot.db`，启动时会把旧的 `data/data_v4.db` 导入一次并保留原文件作为备份。

## 目标

AstrBot 使用**保数据的升级**：启动时按有序、有记录的迁移，把每个持久化存储带到当前 schema，不再需要手工删库。重点不是"每个版本发一个脚本"，而是一个确定性、可恢复的启动步骤，保证：

- 存储的当前状态来自存储自身，绝不从文件名或发布号推断；
- 不可能观察到"做了一半"的升级；
- 失败时明确中止启动，而不是静默漂移。

## 为什么不用发布版本号做脚本名

早先"一个版本一个脚本"（`mig_4.28.1to4.28.2.py`）的想法被否决。它回答不了唯一重要的问题——"这个存储已经见过哪些变更？"——对跳版本升级、打过热修复、或运行 fork 构建的用户都不成立。一旦某个版本带多个变更，或变更发生在发布之外，发布号到迁移步的映射就断了。

所有生产级迁移工具在另一点上是一致的：**单调的步骤标识 + 记录已执行内容的 ledger**。

### 现有实现参考

| 系统           | 已应用状态存放                              | 步骤标识              | 回滚                     | 我们采纳的经验                            |
| -------------- | ------------------------------------------- | --------------------- | ------------------------ | ----------------------------------------- |
| Django         | `django_migrations` 表                      | 递增序号 / 图         | 极少用                   | 检测并合并并发分支                        |
| Alembic        | `alembic_version` 表                        | revision 链           | 手写 `downgrade()`，少用 | autogenerate 必须人工审核；链本身就是数据 |
| Flyway         | `flyway_schema_history`                     | `V1__`、`V2__`        | `undo` 仅付费版          | 已应用脚本 checksum 不符则拒绝执行        |
| Liquibase      | `DATABASECHANGELOG`                         | changeset id + author | 支持                     | checksum 检测漂移                         |
| golang-migrate | `schema_migrations` + dirty 标记            | 时间戳                | 手写 `down`              | 失败会留下必须显式清理的 dirty 状态       |
| Home Assistant | config entry 的 `version` / `minor_version` | 主 + 次版本           | 无，靠恢复备份           | 迁移失败进入独立错误状态，不继续          |
| 自制 SQLite    | `PRAGMA user_version`                       | 递增整数              | 无                       | 用事务包裹每一步                          |

跨工具共识，也是本设计遵循的：

1. 已应用状态存在被管理的存储里，不放在"这个存储是怎么发出来的"这类元数据里。
2. 排序用单调的步骤标识，不用应用版本号。Flyway 的 `V1` 是迁移序号，不是 `4.28.1`。
3. 只向前。回滚 = 从备份恢复。
4. 每个已应用步骤记录 checksum，事后改脚本会被发现。
5. 每一步一个事务。
6. 失败可见并中止启动。
7. 迁移在应用对外服务之前运行，由单一持有者串行执行。
8. 破坏性变更拆成 expand 和 contract 两步。

同一批资料确认的反模式：带发布版本的脚本名、没有密钥分发方案的迁移脚本签名、靠哈希整个模块判断跑过什么、以及把 `down` 脚本当作回滚保障。

## 设计

### 每个物理存储一个迁移序列

每个持久化面在各自的时间线上变化，所以各自持有序列和 ledger。不设全局大版本——那正是旧的 `config_version` 和 `data_v4` 的问题。

| store id | 位置                        | 当前入口                                                  |
| -------- | --------------------------- | --------------------------------------------------------- |
| `main`   | `data/astrbot.db`           | `astrbot/core/db/schema.py` 的 `initialize_sqlite_schema` |
| `kb`     | `data/knowledge_base/kb.db` | `KBSQLiteDatabase.initialize`                             |
| `doc`    | `<kb>/doc.db`               | `DocumentStorage.initialize`                              |
| `config` | `data/cmd_config.json`      | `AstrBotConfig.__init__`                                  |

`data/astrbot.db` 是本 fork 的新主库名。旧的 `data/data_v4.db` 不再被直接打开，只在首次启动时被导入一次（见[旧库导入](#旧库导入)）。

### Revision 与 ledger

- 每个存储一个**单调整数 `revision`**，从 1 开始，只增。它不是应用版本号。
- SQLite 存储用一张 ledger 表，这样记录能带描述和 checksum，而单个 `user_version` 整数做不到：

```sql
CREATE TABLE IF NOT EXISTS _schema_migrations (
    store       TEXT    NOT NULL,
    revision    INTEGER NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    checksum    TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL,
    PRIMARY KEY (store, revision)
);
```

- `config` 是文件，所以它的 ledger 是 `cmd_config.json` 里的整数 `schema_revision`，语义相同。文件无法共用执行器的 SQLite 事务，因此一个步骤必须通过 `AstrBotConfig.save_config`（临时文件、`fsync`、`os.replace`）把迁移后的值和 `schema_revision` 一次性原子写入；分成两次写会在崩溃后让两者不一致。非法、布尔或负数的 revision 视为未设置并执行迁移；比代码更新的 revision 会拒绝启动。

### 步骤模块

```text
astrbot/core/db/migrations/
  __init__.py
  runner.py     # 通用执行器：run_migrations / Migration
  main.py       # 主库序列 MIGRATIONS
  kb.py         # 知识库元数据序列 MIGRATIONS
  doc.py        # 文档存储序列 MIGRATIONS
  bootstrap.py  # 旧 data_v4.db 的一次性导入
astrbot/core/config/migrations/
  __init__.py   # migrate_config_dict / CONFIG_SCHEMA_REVISION
```

每个 store 模块导出一个按 revision 排序的 `MIGRATIONS` 元组。一步携带身份和一个向前函数：

```python
async def _add_duration_ms(conn: AsyncConnection) -> None:
    await conn.exec_driver_sql(
        "ALTER TABLE provider_stats ADD COLUMN duration_ms INTEGER",
    )


MIGRATIONS = (
    Migration(1, "create current schema", _initial_schema),
    Migration(2, "add provider_stats.duration_ms", _add_duration_ms),
)
```

- 排序只认 `revision`；文件名和元组位置只是给人看的。
- 一个步骤只做一件事。破坏性变更拆成 expand 和 contract 两步。
- 不写 `downgrade`。
- `upgrade` 只接收一个打开的 `AsyncConnection`，在里面直接跑 SQL。

### 执行器行为

`run_migrations(engine, store, steps)` 的实际行为：

1. 校验序列（revision 唯一且 >= 1）。
2. 确保 `_schema_migrations` 存在。
3. 读取该 store 已应用的 revision；`current = max(applied)`，没有则为 0。
4. 若 `current` 高于代码里的最大 revision：立即失败，提示恢复备份或升级应用。
5. 逐个校验已应用步骤的 checksum 与代码一致；任一缺失或变化、或已应用 revision 出现空档，即失败。待执行步骤还必须从 `current + 1` 到 head 连续无空档，声明里出现空档会在执行任何步骤前被拒绝，而不是先跑后面的步骤、让下一次启动才发现 ledger 空档。
6. 对每个 `revision > current` 的步骤，升序执行：
   - 在驱动层显式 `BEGIN`；
   - `upgrade(conn)`，然后写 ledger 行；
   - 成功则 `COMMIT`，失败则 `ROLLBACK` 并抛出，启动中止。
7. 没有待执行步骤则 no-op。

实现细节：

- ledger 行与步骤在同一个事务里提交，崩溃不会留下"只做了一半却已记录"的步骤。
- SQLite 的 DDL 在 `engine.begin()` 下**不会回滚**（pysqlite 只在 DML 前开事务）。因此执行器用驱动级显式 `BEGIN` 把 DDL 与 ledger 行包进同一事务，而不是 `engine.begin()`。不要改回去。
- checksum 是 `upgrade` 源码的 `sha256`，检测已应用步骤被事后修改。**改动已应用的步骤会导致启动失败**，这是有意设计。
- 失败会拒绝启动，而不是在漂移状态下继续。这是 Home Assistant `MIGRATION_ERROR` 的思路，但因为我们没有运行中的 UI 可提示，所以更严格。
- 不做签名。没有密钥分发链时，给脚本签名只是仪式；checksum 才是诚实的工具。

### 并发与时机

- 迁移在任何读写之前串行、异步执行：各自 `initialize()` 内，config 则在 `AstrBotConfig` 首次读值前。
- 应用在启动期间持有 `runtime_instance_lock`，所以迁移只在单个进程上运行；每个 store 的 `initialize()` 用锁保证本进程内只跑一次。
- config 迁移要在日志配置之前，因为日志设置来自 config。

### 与 `create_all` 的关系

`create_all` 负责建缺失表，迁移只处理"旧存储到当前存储"的差额。另一种做法——去掉 `create_all`、让迁移 `0001` 负责建表——会让 35 张表的 schema 定义出现两份，真源分裂，因此否决。当前 `main/0001` 本身就是 `create_all` 的基线步骤。保留 `create_all` 的代价是"新建的库"和"迁移后的库"必须被证明等价，见[验证](#验证)。

### 旧库导入

旧主库 `data/data_v4.db` 是重塑前（没有代理 `id`、没有外键、时间戳列顺序不同）的形状。由于没有历史用户需要逐版本回放，重塑不写成多个 SQLite 步骤，而是一次性导入：

1. 目标 `data/astrbot.db` 为空且 `data/data_v4.db` 存在时触发。
2. `run_migrations` 先建出当前 schema 并记录 `main` 的 revision 1。
3. 用 `SQLModel.metadata.sorted_tables` 的依赖序逐表读取旧行。
4. 列名映射由 `LEGACY_COLUMN_RENAMES` 处理（五张表的 `inner_*` → `id`）。
5. 目标表里不存在的旧列被丢弃；旧库里缺的、带 Python 默认值的 NOT NULL 列（例如后加到 `session_project_relations` 的时间戳）在导入时补齐。
6. 整个拷贝在**一个事务**里完成，并临时 `PRAGMA foreign_keys=OFF`，因为旧数据可能引用已经不存在的父行。
7. 行通过驱动级参数插入，保持 SQLite 的磁盘表示：旧 `DATETIME` 列是 ISO 文本，旧 `JSON` 列是 JSON 文本，正好是当前列期望的格式；走 SQLAlchemy 绑定处理器反而会拒绝这些已序列化的文本。读取与插入都在同一事务里分批进行，大表不会整体驻留内存。
8. 拷贝的行与一条导入完成 ledger 行（`main_legacy_import`）在**同一个事务**里提交，崩溃不会留下"拷贝了一半却已记录完成"的导入。
9. `SQLiteDatabase.initialize()` 在完成标记缺失且没有任何用户行时重试导入，因此基线 schema 与拷贝之间崩溃不会留下静默为空的存储。
10. 旧文件保留在磁盘上作为备份，不删除。

`SQLiteDatabase` 只有在调用方显式传入 legacy 路径时才导入。运行时由 `runtime_services` 传入 `LEGACY_DB_PATH`；测试和二级存储传 `None`，因此永远不会读取仓库里的 `data/`。

### 首次上线：执行器出现前就存在的存储

第一个带执行器的版本不能对已有表、且有数据的存储直接重放 `0001_initial`。因此首次上线按已知形状认领每个旧存储，绝不把它的 revision 假定为 0：

- **空存储：** 基线步骤跑 `create_all`，然后把基线写进 ledger。
- **执行器出现前的有数据存储：** 识别已知的旧形状，要么记录基线，要么跑把它往前带的步骤：
  - `main`：唯一受支持的有数据旧文件是 `data/data_v4.db`。它的形状与当前不同（没有代理 `id`、没有外键），因此用一次性导入认领，而不是重放 `0001`；导入会自己记录 `main` 基线。
  - `kb`：旧 `kb.db` 的 `kb_media` 没有 `updated_at`；revision 2 会按需补列，所以有数据的存储可以安全地从 revision 1 开始跑链。
  - `doc` 和 `config`：基线是幂等的（`create_all` 与扁平转分组），已有存储原地认领。
- **未知形状：** 有数据但没有 `main` ledger 行的 `data/astrbot.db`，视为比代码更新，直接拒绝启动，而不是猜测。唯一受支持的旧主库文件是 `data_v4.db`。

每一种受支持的旧存储形状都有一份 fixture 断言不丢行迁到 head；有数据但没有 `main` ledger 的存储会拒绝启动。

## 贡献者规则

1. **改 schema 或改配置形状就是要加步骤的破坏性变更。** 在对应 store 的 `MIGRATIONS` 末尾追加一个新 revision 及其 `upgrade` 函数。不要修改已应用的步骤；checksum 会让启动失败。
2. **把当前 schema 声明在模型上。** 列、生成列、唯一约束和普通索引都写在 SQLModel 定义里，保证新建的存储正确。迁移步骤只把旧存储往前带。
3. **绝不吞掉迁移错误。** 失败必须中止启动，不能藏在裸 `try/except: pass` 里。
4. **一步一件事。** 破坏性变更拆成 expand 然后 contract。任何不可逆操作之前先取步骤快照。
5. **保持备份路径可用。** 表或列变化时，同一次改动里更新 `astrbot/core/backup/` 的导出/导入映射。
6. **删掉过时的转换代码。** 当步骤覆盖了所有可达的旧版本后，移除它取代的加载期 shim。
7. **补测试。** 新步骤要覆盖：空库一次跑到 head、重复运行 no-op、改已应用步骤会失败、回滚不写 ledger。schema 变化还要更新 schema 等价测试。

## 验证

迁移系统由以下测试锁定：

- `tests/unit/db/test_migrations_runner.py`：空库跑完、重复 no-op、checksum 漂移、store 超前、缺失步骤、ledger 空档、声明序列空档、失败回滚。
- `tests/unit/db/test_migrations_equivalence.py`：`create_all` 建的库与迁移到 head 的库，表、列、索引、唯一约束和外键一致。
- `tests/unit/db/test_migrations_bootstrap.py`：旧形状 `data_v4.db` 导入到 `astrbot.db`，含列改名、丢弃旧列、补齐新 NOT NULL 默认列、JSON/时间戳保持类型、分批拷贝；未显式传入旧路径时不导入；有数据但没有 `main` ledger 的 `astrbot.db` 拒绝启动。
- `tests/unit/db/test_foreign_keys.py`：`PRAGMA foreign_keys=ON` 生效，父行删除时级联清理子行。
- `tests/unit/test_config_migrations.py`：旧扁平配置迁到分组、保留用户值、幂等，并在加载时写回 `schema_revision`。

## 相关页面

- [项目架构](./architecture) —— 存储布局与启动顺序。
- [AstrBot 配置文件](./astrbot-config) —— 配置面。
- [备份与恢复](/deploy/astrbot/backup) —— 在安装之间携带数据的受支持方式。
