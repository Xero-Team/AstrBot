# Anthropic Skills

Anthropic 推出的 Agent Skills（智能体技能）是一套模块化的功能扩展标准，旨在将 Claude 从一个“通用聊天机器人”转变为具备特定领域专业知识的“任务执行者”。Skills 是包含指令、脚本、元数据和参考资源的结构化文件夹。它不仅仅是提示词（Prompt），更像是一本专门的“操作手册”，在 Agent 需要执行特定任务时才会动态加载。Tool 是模型用来与外部世界交互的“具体工具/函数接口”，而 Skill 是将指令、模板和工具组合在一起的“标准化任务执行手册”。传统 Tool 需要在对话开始时一次性将所有 API 定义填入 Prompt。如果工具超过 50 个，可能还没开始说话就消耗了数万个 Token，导致响应变慢且昂贵。

AstrBot 支持 Anthropic Skills，使得用户可以轻松集成和使用各种预定义的技能模块，提升 Agent 在特定任务上的表现。

## 关键特性

- 按需加载 (Progressive Disclosure)：模型初始只加载技能名称和简短描述。只有当任务匹配时，才会加载详细的 SKILL.md 指令，从而节省上下文窗口并降低成本。
- 高度可复用：技能可以在不同的 Claude API 项目、Claude Code 或 Claude.ai 中通用。
- 执行能力：技能可以包含可执行代码脚本，配合 Anthropic 代码执行环境（Code Execution）直接生成或处理文件。

## 上传 Skills 到 AstrBot

进入 AstrBot 管理面板，导航到 `插件` 页面，找到 `Skills`。

![Skills](https://files.astrbot.app/docs/source/images/skills/image.png)

你可以上传 Skills，上传格式要求如下：

1. 是一个 .zip 压缩包
2. 解压后可以是一个或多个 Skill 文件夹，Skill 文件夹的名字即为这个 Skill 在 AstrBot 中的标识，请用英文、数字、点、下划线或短横线命名。
3. Skill 文件夹内必须包含一个名为 `SKILL.md` 的文件，且文件名大小写需要完全一致。该文件内容最好符合 Anthropic Skills 规范。你可以参考 [Anthropic 技能](https://code.claude.com/docs/zh-CN/skills)

## Skill 来源与优先级

AstrBot 会从多个位置发现 Skills：

- **本地 Skills**：通过 WebUI 上传或放置在 `data/skills/<skill_name>/SKILL.md`，会显示在 WebUI 的 Skills 管理页面中。
- **插件内置 Skills**：插件可以在自己的 `skills/` 目录中提供 Skills。它们会显示在 WebUI 中，但由插件管理，因此不能在本地 Skills 页面删除或编辑。
- **Sandbox 预置 Skills**：使用 sandbox 运行环境时，AstrBot 会读取沙盒中已发现的 Skills，并在请求时提供给 Agent。
- **工作区 Skills**：当前会话 workspace 下的 `skills/<skill_name>/SKILL.md`。目前仅在 local 运行环境下注入，路径通常是 `data/workspaces/{normalized_umo}/skills/<skill_name>/SKILL.md`。

工作区 Skills 是**请求级**能力：local 运行环境下，AstrBot 会在每次构建请求时检测当前会话 workspace 下的 `skills/` 目录，并把合法的 Skills 拼进本次请求的 Skills 清单。它们暂时不会显示在 WebUI 的 Skills 管理页面，也不会写入全局 Skills 配置。

如果人格配置为“选择指定 Skills”，该列表只用于筛选本地、插件内置和 sandbox Skills；工作区 Skills 仍会作为当前请求的一部分被检测并注入。只有人格明确配置为“不使用任何 Skills”时，才会同时禁用工作区 Skills。

当不同来源出现同名 Skill 时，请求中的优先级如下：

1. 如果当前人格明确配置为“不使用任何 Skills”，则不会注入任何 Skills，包括工作区 Skills。
2. 如果当前人格配置了指定 Skills 列表，该列表不会过滤工作区 Skills。
3. 当前会话的工作区 Skill 优先级最高。同名时，它会覆盖本地、插件或 sandbox 中的同名 Skill，仅对当前请求生效。
4. 本地 Skills 优先于插件内置 Skills 和 sandbox-only Skills。
5. 插件内置 Skills 优先于 sandbox-only Skills。
6. sandbox-only Skills 只会在没有同名本地、插件或工作区 Skill 时作为可用 Skill 注入。

如果本地 Skill 已同步到 sandbox，AstrBot 会把它视为同一个 Skill；在 sandbox 运行环境下，请求中会优先使用 sandbox 内可读取的路径。工作区 Skills 暂不会自动同步到 sandbox。

## 加载步骤

系统提示只列出已启用 Skill 的名称和短描述。匹配到任务后，模型应调用 `read_skill` 读取该 Skill 的 `SKILL.md`；引用文件再传相对 `path`。读取手册不需要电脑能力，`computer_use_runtime=none` 时仍可调用 `read_skill`。授权动作为低风险 `skill.read`，不是 `tool.local_exec` 或 `tool.file_read`。

前言只认 `tools:`。值为已注册工具名列表，例如 `tools: [search_memory]`。语义是过滤不是授权。社区手册里的 `allowed-tools` 会被忽略，也不会升权。缺省 `tools:` 只提供手册，不额外加工具。不要把 `read_skill` 写进 `tools:`。未知工具名会被忽略。社交 IM、匿名 WebChat 和 API Key 即使 Skill 声明了 `astrbot_execute_shell`，目录里也不会出现 Shell。开发侧装配公式见 [项目架构](/dev/architecture)。

## 在 AstrBot 使用 Skills

Skills 是按需加载的任务手册。手册里的脚本仍需要执行环境，但读手册本身不再依赖 Shell。

目前，AstrBot 提供两种执行环境：

- Local（Agent 将在你的 AstrBot 运行环境中运行。**请谨慎使用，因为这会允许 Agent 在你的环境执行任意代码，可能带来安全风险**）
- Sandbox（Agent 在隔离化的沙盒环境中运行。**需要先启动 AstrBot 沙盒模式**，请参考：[沙盒模式](/use/astrbot-agent-sandbox)）

你可以在 `配置` 页面 - 使用电脑能力 中选择默认的执行环境。未开启电脑能力时，仍可通过 `read_skill` 读取记忆、检索类 Skill 手册。

> [!NOTE]
> 如果您使用 Local 作为执行环境，Shell、Python 和本机文件写入分别按 `tool.local_exec`、`tool.python_exec` 和 `tool.file_write` 授权。已认证 Dashboard 驱动的 WebChat 可在当前 session/config 内通过 WebChat step-up 使用这些高风险动作。IM 发送者若绑成该配置的 `instance_operator`，可免 step-up 使用同一组动作。全局控制面仍仅限 Dashboard；匿名 WebChat、插件、Agent、API Key 和未绑定的 IM member 不会继承 Dashboard 角色。Skill 前言声明工具不会绕过这些限制。
