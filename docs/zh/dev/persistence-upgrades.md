# 持久化升级与迁移

本页是 AstrBot 跨版本处理持久化状态的约定。改动数据库模型、配置键或数据目录结构之前，请先读这一页。

> **状态：设计稿，尚未实现。** 这里描述的迁移执行器目前在代码库里还不存在。在它落地之前，实际行为是[迁移系统落地前的兜底策略](#迁移系统落地前的兜底策略)。

## 目标

AstrBot 正在转向**保数据的升级**：启动时按有序、有记录的迁移，把每个持久化存储带到当前 schema，不再需要手工删库。重点不是"每个版本发一个脚本"，而是一个确定性、可恢复的启动步骤，保证：

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
| `main`   | `data/data_v4.db`           | `astrbot/core/db/schema.py` 的 `initialize_sqlite_schema` |
| `kb`     | `data/knowledge_base/kb.db` | `KBSQLiteDatabase.initialize`                             |
| `doc`    | `<kb>/doc.db`               | `DocumentStorage.initialize`                              |
| `config` | `data/cmd_config.json`      | `AstrBotConfig.__init__`                                  |

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

- `config` 是文件，所以它的 ledger 是 `cmd_config.json` 里的整数 `schema_revision`，语义相同。文件无法共用执行器的 SQLite 事务，因此一个步骤必须通过 `AstrBotConfig.save_config`（临时文件、`fsync`、`os.replace`）把迁移后的值和 `schema_revision` 一次性原子写入；分成两次写会在崩溃后让两者不一致。

### 步骤模块

```text
astrbot/core/db/migrations/
  __init__.py
  runner.py          # 通用执行器
  main/0001_initial.py
  main/0002_....py
  kb/0001_initial.py
  doc/0001_initial.py
astrbot/core/config/migrations/
  0001_....py
```

一个步骤导出自己的身份和一个向前函数：

```python
revision = 2
description = "add provider_stats.duration_ms"


def upgrade(conn) -> None: ...
```

- 排序只认 `revision`。文件名里的 `NNNN` 前缀只是给人看的。
- 一个步骤只做一件事。破坏性变更拆成 expand 和 contract 两步。
- 不写 `downgrade`。

### 执行器行为

```text
run_migrations(engine, store, steps):
  1. 取进程锁
  2. 确保 ledger 表存在
  3. current = max(revision)，没有则为 0
  4. 校验每个已应用步骤的 checksum 与代码一致；不符则 fail fast
  5. 若 current > 代码里的最大 revision：fail fast，提示恢复备份
  6. 对每个 revision > current，升序：
       - 破坏性步骤前把该存储快照到 data/backups/
       - BEGIN -> upgrade(conn) -> 写 ledger 行 -> COMMIT
       - 出错 -> ROLLBACK，抛异常，不启动
  7. 没有待执行步骤则 no-op
```

- ledger 行与步骤在同一个事务里提交，崩溃不会留下"只做了一半却已记录"的步骤。
- checksum 是步骤源码的 sha256，检测已应用步骤被静默修改。
- 失败会拒绝启动，而不是在漂移状态下继续。这是 Home Assistant `MIGRATION_ERROR` 的思路，但因为我们没有运行中的 UI 可提示，所以更严格。
- 不做签名。没有密钥分发链时，给脚本签名只是仪式；checksum 才是诚实的工具。

### 并发与时机

- 复用现有的 `runtime_instance_lock`，保证只有一个进程执行迁移。
- 迁移在任何读写之前串行、异步执行：各自 `initialize()` 内，config 则在 `AstrBotConfig` 首次读值前。
- config 迁移要在日志配置之前，因为日志设置来自 config。

### 与 `create_all` 的关系

`create_all` 继续负责建缺失表，迁移只处理"旧存储到当前存储"的差额。另一种做法——去掉 `create_all`、让迁移 `0001` 负责建表——会让 35 张表的 schema 定义出现两份，真源分裂，因此否决。保留 `create_all` 的代价是"新建的库"和"迁移后的库"必须被证明等价，见[验证](#验证)。

### 首次上线：执行器出现前就存在的存储

第一个带执行器的版本不能对已有表、且有数据的存储直接重放 `0001_initial`。因此首次上线按 schema 认领每个旧存储，绝不把它的 revision 假定为 0：

- **空存储：** 通过 `0001_initial` 跑 `create_all`，然后把基线写进 ledger。
- **执行器出现前的有数据存储：** 识别已知的旧形状，要么记录基线，要么跑把它往前带的步骤：
  - `main`：唯一受支持的有数据旧文件是 `data/data_v4.db`。它的形状与当前不同（没有代理 `id`、没有外键），因此用一次性导入认领，而不是重放 `0001`；导入会自己记录 `main` 基线。
  - `kb`：旧 `kb.db` 的 `kb_media` 没有 `updated_at`；`0002` 会按需补列，所以有数据的存储可以安全地从 `0001` 开始跑链。
  - `doc` 和 `config`：基线是幂等的（`create_all` 与扁平转分组），已有存储原地认领。
- **未知形状：** 不匹配任何已知旧形状的有数据存储，视为比代码更新，直接拒绝启动，而不是猜测。

执行器发布前，要为每一种受支持的旧存储形状各加一份 fixture（在历史 revision fixture 之外），并断言它们都能在不丢行的情况下迁到 head。

## 贡献者规则

1. **改 schema 或改配置形状就是要加步骤的破坏性变更。** 新增一个 revision 及其 `upgrade` 函数。不要修改已应用的步骤；checksum 会让启动失败。
2. **把当前 schema 声明在模型上。** 列、生成列、唯一约束和普通索引都写在 SQLModel 定义里，保证新建的存储正确。迁移步骤只把旧存储往前带。
3. **绝不吞掉迁移错误。** 失败必须中止启动，不能藏在裸 `try/except: pass` 里。
4. **一步一件事。** 破坏性变更拆成 expand 然后 contract。任何不可逆操作之前先取步骤快照。
5. **保持备份路径可用。** 表或列变化时，同一次改动里更新 `astrbot/core/backup/` 的导出/导入映射。
6. **删掉过时的转换代码。** 当步骤覆盖了所有可达的旧版本后，移除它取代的加载期 shim。

## 迁移系统落地前的兜底策略

在执行器落地之前，适用当前策略：存储按当前定义创建，破坏性变更通过删除对应存储处理。这只因为没有用户才可接受。一旦用户数据需要保留，本节即失效，改用上面的设计。

## 验证

只有下列各项都被测试，迁移系统才算正确：

- 空存储跑完所有步骤一次，停在 head revision。
- 重复运行是 no-op。
- 改动已应用步骤会导致启动失败。
- 存储 revision 高于代码时启动失败，并给出恢复提示。
- 失败的步骤会回滚，且 ledger 不被改动。
- **Schema 等价：** `create_all` 建的库与从 `0001` 迁移到 head 的库，表、列、索引完全一致。
- **升级路径：** 每个历史 revision 各有一份 fixture 库，跑完整链到 head。
- **上线认领：** 每种受支持的旧存储形状各有一份有数据 fixture，都能不丢行迁到 head；未知形状拒绝启动。

## 相关页面

- [项目架构](./architecture) —— 存储布局与启动顺序。
- [AstrBot 配置文件](./astrbot-config) —— 配置面。
- [备份与恢复](/deploy/astrbot/backup) —— 在安装之间携带数据的受支持方式。
