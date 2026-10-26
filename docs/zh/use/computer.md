# 使用电脑能力

电脑能力（Computer Use）决定 Agent 是否可以在 AstrBot 运行环境中执行代码、访问文件、调用 Shell。

## 模式选择

在 WebUI 中进入：

- `配置文件 -> 选择配置文件 -> AI 配置 -> 能力 -> 使用电脑能力`

核心配置项是 `Computer Use Runtime`：

- `none`：不启用电脑能力，不给 Agent 挂载 Shell、Python、文件系统等工具。读 Skill 手册仍走 `read_skill`，不需要电脑能力。
- `local`：在 AstrBot 所在机器上执行，适合需要访问本机文件、命令行工具或本地依赖的场景。

仅在确实需要直接访问本机时使用 `local`。旧配置中已移除的运行环境值会按 `none` 处理。

## Local 模式

`local` 模式会把电脑能力挂载到 AstrBot 所在的主机环境。Agent 可以调用本机 Shell、本机 Python，以及本机文件系统工具。

这意味着 Agent 的能力边界接近 AstrBot 进程本身：它能访问什么，取决于 AstrBot 进程的系统权限、运行用户、工作目录和操作系统限制。

### Workspace

在 `local` 模式下，AstrBot 会为每个会话准备一个 workspace：

```text
data/workspaces/{normalized_umo}
```

其中 `{normalized_umo}` 来自当前会话的 `unified_msg_origin`，并会将不适合文件名的字符替换为 `_`。

本地文件工具的相对路径会解析到这个 workspace 下。例如：

```text
notes/todo.txt
```

会被解析为：

```text
data/workspaces/{normalized_umo}/notes/todo.txt
```

本地 Shell 工具执行时，也会把当前工作目录设置为这个 workspace。

> [!NOTE]
> 本地 Python 工具会调用 AstrBot 当前 Python 环境执行代码。编写会读写文件的 Python 代码时，建议使用明确的绝对路径，或先通过文件工具在 workspace 中准备文件。

### 本地工具

`local` 模式主要提供以下工具：

- `Shell`：执行本机 shell 命令。Windows 下使用 `cmd.exe` 语义，Linux/macOS 下使用类 Unix shell 语义。
- `Python`：使用 AstrBot 当前 Python 环境执行 Python 代码。
- `文件读取`：读取 workspace 或允许路径中的文本、图片、表格等文件。
- `文件写入`：写入 UTF-8 文本文件；相对路径默认落在当前 workspace。
- `文件编辑`：按精确字符串替换文件内容。
- `Grep 搜索`：使用 ripgrep 能力搜索文件内容。

`local` 模式不会挂载远程上传/下载或浏览器自动化工具。

本地 Shell 内置了基础危险命令拦截，例如 `rm -rf`、`sudo`、`shutdown`、`reboot`、`kill -9` 等。但这不是完整安全沙箱，不能把它当作安全边界。

### 权限模型

在本地权限表中，展开“文件访问范围”下拉菜单即可查看各选项的说明。“工作区”允许受限访问会话工作区、临时目录和技能文件；“整个环境”（原“主机文件”）允许访问 AstrBot 运行账户有权限访问的文件。Docker 部署时，“整个环境”指容器内及挂载的文件，并非宿主机全部文件。“关闭”不允许通过本地电脑能力工具访问任何文件。范围说明已从表格下方移到下拉菜单的对应选项中；将鼠标悬停在“AstrBot 所在运行环境的所有文件。”后的问号上，或点按问号，可查看账户权限和 Docker 访问范围的详细说明。

新安装的 Windows、Linux 和 macOS 使用相同的默认权限：普通成员可访问工作区文件但不能执行代码；管理员可在整个环境执行代码并联网。已有配置中保存的权限保持不变，包括用户明确关闭的普通成员文件访问。旧版 Windows 普通成员的默认值与手动关闭后的保存值完全相同，因此本 fork 不会在升级时自动改写；如需允许成员访问工作区文件，请在权限表中改为“工作区”。该管理员默认值会直接以 AstrBot 运行账户执行本地代码，拥有整个环境的文件访问和联网能力；在 Linux 和 macOS 上不会使用进程隔离。若该访问范围不适合当前部署，请改用工作区范围。

若已保存的策略需要本地进程隔离，但当前隔离不可用，代码执行和执行环境联网会被禁用，同时不会扩大文件访问范围，也不会改写已保存的策略。工作区文件访问（不执行代码）和整个环境执行（允许联网）仍然可用。权限矩阵保留已勾选的执行项，并将暂不可用的执行标记为“未生效”；悬浮或点按旁边的问号可查看原因。恢复隔离并重启 AstrBot 后，已保存的策略会重新生效。

Windows 通过原生文件句柄支持工作区范围内的文件读取、写入和编辑，并拒绝符号链接、目录联接和多重硬链接文件。Windows 原生环境仍不支持本地进程隔离；管理员可在整个环境执行代码并联网。

电脑能力走统一授权服务，不再使用“需要 AstrBot 管理员权限”开关。常见动作包括：

- `tool.local_exec`
- `tool.python_exec`
- `tool.file_read`
- `tool.file_write`

`tool.computer_use` 保留给第三方 computer-use 工具，当前没有内置工具声明它。它仍留在高风险与 WebChat 硬裁集合中，避免这类工具绕过授权。

`tool.file_read` 对当前会话的 member 及以上开放，但仍受路径约束。`tool.local_exec`、`tool.python_exec`、`tool.file_write`、`tool.mcp_write` 和 `tool.computer_use` 是实例级高风险动作：已认证 Dashboard 驱动的 WebChat 仅可在当前 session/config 内，经 WebChat 一次性 step-up 后使用。IM 发送者若在该配置上绑了 `instance_operator`，可免 step-up 使用同一组动作。全局控制面仍 Dashboard-only；匿名 WebChat、插件、Agent、API Key 以及未绑定的 IM member 不会继承 Dashboard 角色。路径和 Prompt/工具声明限制仍然有效。

`local` 模式下，普通会话成员可以读取：

- `data/skills`
- `data/plugins/*/skills`（只读，用于插件内置 Skills）
- 当前会话的 `data/workspaces/{normalized_umo}`
- AstrBot 的临时目录
- 系统临时目录中的 `.astrbot`

写入和编辑仍限制在当前会话 workspace 和临时目录。请通过 Dashboard [权限页面](/use/authorization)把 IM 发送者绑成该配置的 `instance_operator`；`/admin grant` 只授予当前会话 `session_admin`，不能把 IM 用户变成全局 operator。开发模型见[项目架构](/dev/architecture#统一授权系统)。

## Skills

Skills 是给 Agent 使用的“任务说明书”，通常存放在 `data/skills` 下，每个 Skill 都包含一个 `SKILL.md`。

电脑能力和 Skills 的关系可以理解为：

- Skills 告诉 Agent 应该怎么做。
- 电脑能力决定 Agent 能不能执行这些步骤。

例如，一个 Skill 可能要求 Agent 读取文件、运行脚本、生成报告。如果 `Computer Use Runtime` 是 `none`，Agent 可以看到 Skill 的说明，但无法真正调用 Shell 或 Python 完成执行。

在 `local` 模式下，Agent 会读取本地 Skills。

更多内容请参考：[技能 Skills](/use/skills)。
