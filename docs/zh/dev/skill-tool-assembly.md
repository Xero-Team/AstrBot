---
outline: deep
---

# Skills 读取与工具目录装配

本文记录当前运行时行为。实现条款已迁入 [项目架构](/dev/architecture) 和 [技能 Skills](/use/skills)；本页保留装配公式、基线表和验收边界。

相关用户文档：[技能 Skills](/use/skills)、[使用电脑能力](/use/computer)、[授权](/use/authorization)。配置字段见 [AstrBot 配置文件](/dev/astrbot-config)。

## 问题

Skills 应是按需加载的任务手册，不应把读手册绑到本机 Shell，也不应靠手册声明扩权。

当前实现有三条真实缺陷：

1. **工具目录不按已启用 Skill 计算。** `SKILL.md` 前言只解析 `description`（Neo 同步再写 `name`），没有工具名声明。主 Agent 装配是人格白名单并上后来硬加的电脑、检索、记忆工具。`agent_runner.config.misc.tool_schema_mode=skills_like` 只做两阶段轻 schema，不按 Skill 收目录。
2. **读 Skill 绑死 `tool.local_exec`。** `build_skills_prompt()` 强制用 `cat` / `type` 读绝对路径。`computer_use_runtime=none` 仍注入 Skill 清单，同时写「不能用 Shell」。没有运行时拥有的读取动作。记忆、检索类 Skill 在未开电脑能力时读不了手册。
3. **社交表面不从目录硬裁高权限工具。** Skill 现在声明不了 `execute_shell`，所以还不能靠手册扩权。但 `_apply_local_env_tools` / `_apply_sandbox_tools` 在人格合并之后无条件把 Shell、Python、写文件挂进目录。IM 等社交表面只在执行时授权拒绝，模型仍能看见并尝试调用。

## 目标

1. 多根扫描不变，系统提示只放 Skill **名称和短描述**。
2. 读手册走运行时工具 `read_skill`，路径锁在已登记 Skill 目录内。不要求电脑能力。
3. Skill 可用前言 `tools:` 声明需要的**已有**工具名。多个 Skill 声明同一工具只挂一次。
4. 主 Agent 工具目录按交集计算，而不是先铺全库再靠 `skills_like` 藏参数。人格 `tools is None`（使用全部）不得把会话已启用的插件、MCP 工具从目录里拿掉。
5. 绑定表语义是过滤，不是授权。社交表面按 `WEBCHAT_INSTANCE_TOOL_ACTIONS` 硬裁实例级高权限工具，即使某张 Skill 写了 `astrbot_execute_shell`。不要用整份 `HIGH_RISK_ACTIONS` 当工具目录黑名单：后者还含控制面动作。

## 非目标

不要做这些：

- Claude Code 式 `allowed-tools` 预批准（写入 `alwaysAllowRules`）。社交 IM 上这等于 Skill 偷偷发 Shell。
- Codex 的 `$mention` 输入协议、`skill://` URI、`openai.yaml` / `SKILL.json`、MCP 依赖自动安装。
- OpenCode 的「目录永远是全工具池」。它面向本机开发者；AstrBot 面向 QQ、Telegram 等社交表面。
- 把 `skills_like` 两阶段 schema 当成 Skill 绑定。它只藏参数，不收目录。
- 正文内嵌 Shell、fork 子 Agent、按文件 glob 自动激活 Skill。
- 恢复 `platform_settings.group_wake_policy` 或其他已删除表面。
- 为读手册重新引入 `CERT_NONE`、任意文件系统读取或 Dashboard HTTP 代理。

用户点名 Skill 时，主机可以顺手把 `SKILL.md` 注入当前请求，作为可选优化，不作为对外协议。

## 对照

| 项         | 当前 AstrBot                  | 不要照搬的 Codex 形态                           | 本需求                                                                                 |
| ---------- | ----------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------- |
| 发现       | 多根扫描，清单进系统提示      | 同左                                            | 保持                                                                                   |
| 读正文     | 提示词要求 `cat` / `type`     | `$mention` 主机注入或 `skills.read`             | 只要 `read_skill`；点名注入是可选优化                                                  |
| 路径       | 绝对路径交给 Shell            | `package` + `skill://`，沙箱感知                | `name` + 相对路径，锁已登记目录                                                        |
| 工具声明   | 无                            | `openai.yaml` 的 `dependencies.tools`（偏 MCP） | `SKILL.md` 前言 `tools:`，值为已有工具名                                               |
| 声明语义   | —                             | 缺 MCP 时弹安装                                 | 过滤不是授权                                                                           |
| 目录怎么算 | 人格白名单 ∪ 事后全挂电脑工具 | 未按 Skill 收内置工具                           | 平台基线 ∪ 会话插件/MCP ∪ Skill 声明 ∪ 按需电脑工具，再 ∩ 人格 ∩ 可见性过滤 ∩ 表面硬裁 |
| 社交表面   | 目录里有高权限，执行时拒绝    | 本机 CLI 权限模型                               | IM / 匿名 WebChat / API Key 按 `WEBCHAT_INSTANCE_TOOL_ACTIONS` 从目录硬裁              |
| 读手册授权 | `tool.local_exec`             | 独立 `skills.read`                              | `skill.read` 或等价低风险动作；`computer_use_runtime=none` 也能读                      |

## 现状锚点

实现时以这些符号为准，不要发明平行装配路径：

| 职责           | 位置                                                                                                  |
| -------------- | ----------------------------------------------------------------------------------------------------- |
| Skill 清单提示 | `astrbot/core/skills/_skill_inventory.py` 的 `build_skills_prompt()`                                  |
| 前言解析       | `_parse_frontmatter_description()`；Neo 同步另认 `name`                                               |
| 请求级过滤     | `astrbot/core/astr_main_agent.py` 的 `_append_skills_prompt()`、`_filter_skills_for_current_config()` |
| 人格工具合并   | `_merge_persona_tools()`                                                                              |
| 电脑工具硬挂   | `_apply_local_env_tools()`、`_apply_sandbox_tools()`                                                  |
| 插件/MCP 过滤  | `_plugin_tool_fix()`                                                                                  |
| 执行期授权     | `astrbot/core/astr_agent_tool_exec.py` 的 `FunctionToolExecutor._authorize_execution()`               |
| 高风险动作     | `HIGH_RISK_ACTIONS`（控制面 + 工具）、`WEBCHAT_INSTANCE_TOOL_ACTIONS`（工具目录硬裁）                 |
| 两阶段 schema  | `tool_loop_agent_runner.py` 的 `tool_schema_mode=skills_like`                                         |

## 目标装配

对每一次主 Agent 请求，以 8 步为准。下面的公式是摘要，漏项以步骤和基线表为准。

1. 按现有来源和优先级解析**已启用 Skill 集合**：人格空列表禁用全部（含工作区）；指定列表筛选本地、插件、sandbox；工作区 Skill 在 `computer_use_runtime=local` 且人格未禁用 Skills 时仍注入。来源优先级见 [技能 Skills](/use/skills)。
2. 取出**候选工具并集**（见基线表）：平台基线 ∪ 会话已启用的插件/MCP（非高风险） ∪ 已启用 Skill 的 `tools:` ∪ 本请求运行时按需电脑工具。Skill 声明只往并集里加已注册工具名，不能安装 MCP、不能放开私网、不能把未启用的插件工具拉进来。
3. 去重。多个 Skill 声明同一工具只保留一次。未知工具名忽略并记日志。
4. 与人格工具白名单求交。人格 `tools is None` 表示不额外收缩这一层，因此步骤 2 的并集（含插件/MCP）都还在；空列表表示不要普通工具（仍保留 `read_skill`，见三态表）。
5. 与会话插件过滤求交（现有 `_plugin_tool_fix()` 语义：MCP 和无插件归属的工具保留），再按每个工具的 `required_actions` 风险标签和入口表面做可见性过滤。装配阶段不调用完整 `authorize()`。
6. **社交表面硬裁**：从目录移除任何 `required_actions` 与 `WEBCHAT_INSTANCE_TOOL_ACTIONS` 有交集的工具。当前集合是 `tool.local_exec`、`tool.python_exec`、`tool.file_write`、`tool.browser_control`、`tool.mcp_write`、`tool.computer_use`。按动作交集裁，不维护工具名黑名单。IM、匿名 WebChat、插件、Agent、API Key 从目录移除，不只在执行时拒绝。已认证 Dashboard 驱动的 WebChat 仍走现有一次性 step-up，不靠 Skill 绕过。`HIGH_RISK_ACTIONS` 里的控制面动作（如 `identity.operator.write`、`system.pip_install`）本来就不该出现在主 Agent 工具目录。
7. `computer_use_runtime=none` 时，即使 Skill 声明了 Shell、Python、写文件，这些工具也不进目录。`tool.file_read` 不在硬裁集合里；社交表面是否允许读工作区文件必须单独规定并测试，默认：仅 local/sandbox 且已通过人格与可见性过滤时才进目录，IM 上不要仅因 Skill 声明就挂出工作区读文件。
8. `_apply_local_env_tools` / `_apply_sandbox_tools` 只提供运行时能力清单，由装配函数按交集补电脑工具，禁止无条件全挂。

公式（摘要）：

```text
候选 = 平台基线 ∪ 会话插件/MCP ∪ Skill.tools ∪ 按需电脑工具
目录 = 表面硬裁(
  可见性过滤(
    人格白名单 ∩ 候选
  )
)
```

`read_skill` 按人格三态始终保留（空 Skill 快照时可不挂）。`skills_like` 可继续作为 token 优化，与目录计算正交。

目录计算必须是单一纯函数，建议 `assemble_tool_catalog(...)`，放在 `astrbot/core/` 下独立模块，不要继续堆进 `astr_main_agent.py`。输入是冻结的 Skill 快照、人格三态、入口表面、`computer_use_runtime`、会话插件过滤和已注册工具表；输出是工具名集合，再一次性物化 `ToolSet`。

### 基线与候选层

人格 `tools is None` 的「使用全部」是「不收缩下面四层」，不是「Skill 没声明就不给插件工具」。未写入 `tools:` 的 Skill 只提供手册，不额外加工具，也不删除其他层。

| 层             | 何时进入候选                                                     | 例子                                                                                                                            | 是否靠 Skill `tools:`                         |
| -------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 平台基线       | 对应能力已开                                                     | 记忆检索（`search_memory` 等）、主动消息、已开启的网页搜索、群历史（配置打开时）、`read_skill`（有已启用 Skill 或按三态保留时） | 否                                            |
| 会话插件 / MCP | 插件已激活且通过 `_plugin_tool_fix()`；MCP 无插件归属则保留      | 用户插件工具、MCP 读工具                                                                                                        | 否。Skill 不能安装或放开私网 MCP              |
| Skill 声明     | 本请求已启用 Skill 前言 `tools:`                                 | 某张检索 Skill 声明 `search_memory`                                                                                             | 是。只过滤已有工具名                          |
| 按需电脑工具   | `computer_use_runtime` 为 `local` 或 `sandbox`，且通过人格与硬裁 | Shell、Python、写文件、Neo 生命周期工具、浏览器（sandbox 能力允许时）                                                           | 可声明，但不能扩权。`runtime=none` 时本层为空 |

Neo 生命周期工具（`astrbot_create_skill_payload` 等）属于 sandbox + `shipyard_neo` 的按需电脑层，不是平台基线，也不要无条件全挂。

### 实现约束：可见性与授权分层

上式中的「可见性过滤」不是在装配阶段调用完整的异步 `authorize()`。装配阶段只允许使用静态、可预测的可见性信息：

1. 先收集四层候选、Persona 三态和入口表面。
2. 按运行时能力、插件过滤、工具的 `required_actions` 风险标签和入口表面做可见性过滤。
3. 最后一次性生成 `ToolSet`；实际调用仍必须经过 `FunctionToolExecutor._authorize_execution()`。

这样可以保留 WebChat step-up 等请求级授权，同时避免因为装配时机不同导致目录与执行结果不一致。社交表面按 `WEBCHAT_INSTANCE_TOOL_ACTIONS` 交集硬裁，而不是按工具名黑名单，也不是整份 `HIGH_RISK_ACTIONS`。

### Persona 工具三态

实现必须固定以下语义，不能把 `None`、空列表和非空列表混为一谈：

| Persona `tools`    | 普通工具                                                           | `read_skill`                       |
| ------------------ | ------------------------------------------------------------------ | ---------------------------------- |
| `None`（使用全部） | 不收缩四层候选（平台基线、会话插件/MCP、Skill 声明、按需电脑工具） | 保留                               |
| `[]`（不使用工具） | 全部移除                                                           | 保留，但只能读取本请求已启用 Skill |
| 非空列表           | 与列表求交                                                         | 保留，即使列表未写出该工具名       |

`read_skill` 是系统保留的低风险读取能力，不等于给 Persona 或 Skill 授予其他工具权限。

### 请求级 Skill 快照

`read_skill` 必须使用请求创建时冻结的 Skill 快照，而不能按名称重新扫描全局目录。快照至少包含 Skill 名称、来源、已解析的 Skill 根目录、运行时副本位置和身份信息（例如内容摘要）。在一次工具循环内，即使 Skill 被禁用、替换、同步或符号链接改向，提示词中的 Skill 与实际读取对象也必须保持一致。

同名 Skill 覆盖完成后只能保留最终选中的来源；不能让 `read_skill(name=...)` 在多个来源之间重新猜测。Sandbox 缓存路径也必须经过当前会话沙盒根校验，不能把缓存中的字符串路径直接当作可信路径。

## `read_skill`

新增内置工具，建议注册名 `astrbot_read_skill`，模型侧可暴露为 `read_skill`。不要复用 `astrbot_file_read_tool` 或 Shell。

### 输入

| 字段   | 约束                                                        |
| ------ | ----------------------------------------------------------- |
| `name` | 必填。必须是本次请求已启用 Skill 集合中的名字。             |
| `path` | 可选，默认 `SKILL.md`。相对该 Skill 目录的 POSIX 相对路径。 |

### 解析与拒绝

相对 `skill_dir` 解析。拒绝：

- `..`、绝对路径、盘符、UNC、多余前导 `/`
- 解析后逃出该 Skill 目录
- 目录、符号链接逃逸、非普通文件
- 不在已启用集合中的 `name`
- 空文件名、控制字符

只打开已登记 Skill 的 `SKILL.md` 及其目录内引用文件。不进用户工作区其它路径，也不进 `data/` 根目录。

sandbox 运行时读 sandbox 内可解析副本；local 读本地或工作区副本。路径对模型只回相对 Skill 目录的路径，或固定占位，不把宿主机绝对路径写进工具结果。

路径校验不能停留在“先 `resolve()` 再 `read_text()`”的非原子检查；实现应避免符号链接替换造成 TOCTOU。若平台允许，使用目录句柄、`O_NOFOLLOW` 或等价的“不跟随链接”打开方式；否则至少在打开后再次确认真实路径仍位于快照根目录内。

### 输出与限额

返回 UTF-8 文本。单文件上限 64 KiB，超限截断并说明，提示用相对 `path` 再读引用文件。引用文件同样锁目录；不要一次枚举整个 Skill 树。系统提示可注明「相对路径相对于该 Skill 目录」。空 Skill 快照时目录里不要挂 `read_skill`。

### 授权

`required_actions` 应使用单独的低风险动作 `skill.read`，并同步加入 `ACTIONS`、角色授予、资源类型映射、授权文档和测试。不要为了少注册一个动作而复用 `session.read`：当前工具执行边界使用 `Resource(type="tool", ...)`，两者的资源语义并不相同。禁止标成 `tool.local_exec` 或 `tool.file_read`。

`computer_use_runtime=none` 时目录里仍有 `read_skill`。没有电脑能力也能用记忆、检索类 Skill。

脚本、Shell、写文件仍走原高风险工具，授权不变。

### 系统提示

删除「先跑与当前 runtime shell 兼容的 `cat` / `type`」规则。改为：匹配到 Skill 时调用 `read_skill`；需要引用文件时带相对 `path`。`runtime=none` 时保留「不能执行 Shell / Python」说明，但不再因此禁止读手册。

## 前言 `tools:`

在现有 YAML 前言中增加可选字段 `tools`。

```markdown
---
name: search-notes
description: 按用户笔记检索并引用原文。
tools:
  - search_memory
---
```

规则：

- 值是 AstrBot 已注册工具名的字符串列表，例如 `astrbot_execute_shell`、`search_memory`。解析用注册名，不认模型侧别名。
- 不要把 `astrbot_read_skill` / `read_skill` 写进 `tools:`。它按人格三态保留，不靠声明。
- 只认 `tools:`。不读 `allowed-tools` 或其他 Claude / Codex 别名，也不引入 `Bash(gh:*)` 模式语言。语义是**过滤不是预批准**。Agent Skills 规范里的 `allowed-tools` 是实验性预批准字段；本仓库不实现、不兼容映射。用户文档必须写明：社区手册里的 `allowed-tools` 会被忽略，也不会升权。
- 未知工具名忽略并记日志，不失败整个 Skill。
- 缺省 `tools:` 表示该 Skill **不额外往目录里加工具**，只提供手册。基线工具仍在。不要把缺省解释成「全工具池」。
- 不新增 `SKILL.json` / `openai.yaml`。MCP 仍走现有 MCP 服务器配置，Skill 不能安装或放开私网 MCP。

前言应一次解析为结构化元数据（名称、描述、声明工具和解析警告），不要为每个字段分别读取 YAML。`tools` 必须是字符串列表，去重并限制单项长度和总数量；未知工具只记录日志并忽略。插件、Workspace、Sandbox 缓存 Skill 都必须使用同一解析结果，不能只让本地 Skill 支持 `tools:`。

Skill 正文和描述属于可不完全信任的数据。`read_skill` 返回时应带 Skill 名称和相对路径等结构化边界，并明确正文不会提高权限；不要把正文中的指令当作授权策略。

## 授权与表面

执行仍走 `FunctionToolExecutor._authorize_execution`。Skill 只影响**目录可见性**。

硬约束：

- Dashboard 默认绑 `127.0.0.1`；非回环是部署选择。
- IM、匿名 WebChat、插件、Agent、API Key 不继承 Dashboard 角色。
- WebChat 六个实例级高风险动作仍需 `/authorization/webchat-step-up`，且仅当前 session/config。
- 社交表面即使 Skill 写了 `astrbot_execute_shell`，目录里也不出现对应工具。
- 已认证 WebChat 在 step-up 成功后，目录可以出现 `WEBCHAT_INSTANCE_TOOL_ACTIONS` 对应工具；IM / API Key 始终没有。
- 用户面向失败信息保持泛化，不回显宿主机路径或授权细节。

## 落地切面

按这个顺序拆，避免一次同时改提示词、目录和授权。

### 第一刀：读手册与 Shell 解绑

- 实现 `astrbot_read_skill`，路径锁死，低风险授权。
- 同时建立请求级 Skill 快照，供提示词和 `read_skill` 共用。
- 改 `build_skills_prompt()`，删除 `cat` / `type`。
- `runtime=none` 也把 `read_skill` 放进目录。
- 回归：未开电脑能力时，记忆类 Skill 能读 `SKILL.md`；`../` 和绝对路径被拒。

### 第二刀：声明过滤与硬裁

- 前言解析 `tools:`。
- 先生成纯函数式的候选工具集合，再一次性物化 `ToolSet`；`_apply_local_env_tools` / `_apply_sandbox_tools` 只提供运行时能力，不直接无条件修改请求目录。
- 抽出 `assemble_tool_catalog`；按 8 步和基线表计算目录，不以摘要公式替代。电脑工具改为按需补，不再全挂。
- 社交表面按 `WEBCHAT_INSTANCE_TOOL_ACTIONS` 硬裁，包括 MCP 写工具。
- 回归：两个 Skill 声明同一工具只出现一次；IM 上看不见 Shell；WebChat step-up 不被 Skill 绕过；人格空 Skills 列表仍禁用工作区 Skill；人格 `tools is None` 时未声明的插件工具仍在。

### 明确不做的第三刀

主机在用户明文点名时自动注入 `SKILL.md`、分页 `skills.list`、MCP 依赖安装，均不在本需求范围。

## 验收

实现 PR 必须覆盖这些行为，测试放在最近的现有目录（通常是 `tests/unit/`）：

1. 系统提示列出已启用 Skill 的名称和描述，且不含 `cat` / `type` 必读规则。
2. `read_skill` 只打开已启用 Skill 目录内文件；`../etc/passwd`、绝对路径、其它 Skill 目录均失败。
3. `computer_use_runtime=none` 时 `read_skill` 可用，Shell / Python / 写文件不在目录中。
4. 已启用 Skill 的 `tools:` 进入候选并与人格白名单求交后出现在目录中。未声明的平台基线、会话插件/MCP 在人格 `tools is None` 时仍在；人格空列表时它们被移除，只留 `read_skill`。
5. 两个 Skill 声明同一工具只挂一次。
6. 社交表面（非 WebChat step-up 主体）目录不含 `required_actions` 与 `WEBCHAT_INSTANCE_TOOL_ACTIONS` 有交集的工具。
7. Skill 前言写了 `astrbot_execute_shell` 也不使 IM 主体通过 `tool.local_exec`。
8. `skills_like` 仍只影响 schema 形状，不改变上述目录集合。
9. 请求创建后替换或禁用 Skill，不改变该请求快照中的 `read_skill` 结果。
10. `persona.tools` 的 `None`、`[]`、非空列表分别覆盖；空列表保留 `read_skill`，其他工具按规则移除。
11. 同名 Skill 覆盖、Sandbox 缓存路径和符号链接变更不会导致跨来源读取或目录逃逸。
12. 人格 `tools is None` 时，未写入任何 Skill `tools:` 的已启用插件工具仍在目录中。
13. 已认证 WebChat step-up 成功后目录可以出现高风险电脑工具；IM / API Key 始终没有。
14. `read_skill` 打开后再次确认真实路径仍在快照根内（`O_NOFOLLOW` 或等价）。
15. sandbox + `shipyard_neo` 的生命周期工具走按需电脑层，`runtime=none` 时不出现。
16. 前言只写 `allowed-tools`、未写 `tools:` 的 Skill 不额外加工具、不升权。

## 文档与配置同步

落地同一变更必须：

- 更新 [技能 Skills](/use/skills) 的加载步骤、Local 执行环境说明，以及「只认 `tools:`、忽略 `allowed-tools`、声明不升权」。
- 更新本页状态：已实现条款改为「当前行为」，或迁入 [项目架构](/dev/architecture)。
- 若新增 `skill.read` 动作，同步授权文档与 `astrbot/core/auth/registry.py`。
- 英文页 [Skill reading and tool-catalog assembly](/en/dev/skill-tool-assembly) 必须保持结构对齐。
- 不要指向 `docs.astrbot.app`。
