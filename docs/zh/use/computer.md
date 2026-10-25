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

新安装的 Windows、Linux 和 macOS 使用相同的嵌套默认权限。普通成员可访问工作区文件但不能执行代码，网络模式为 `off`，Unix 套接字模式为 `deny`。管理员可在整个环境执行代码，网络模式为 `unrestricted`，私有网络与环回标志均开启，没有文件系统拒绝规则，Unix 套接字模式为 `allow_all`。已有配置中保存的权限保持不变，包括用户明确关闭的普通成员文件访问。旧版 Windows 普通成员的默认值与手动关闭后的保存值完全相同，因此本 fork 不会在升级时自动改写；如需允许成员访问工作区文件，请在权限表中改为“工作区”。

原生执行恰好是管理员元组：文件范围 `host`、网络 `unrestricted`、两个地址标志均开启、没有拒绝规则、套接字 `allow_all`。它直接以 AstrBot 运行账户执行，不使用进程隔离，也不提供下文所述的任何沙箱保证。任何偏离，包括工作区范围、域名规则、关闭地址标志、文件系统拒绝规则或套接字拒绝模式，都需要真实的沙箱后端。后端不可用时，代码执行会被禁用，不会扩大文件访问范围，也不会改写已保存的策略。权限矩阵会将暂不可用的执行标记为“未生效”；悬浮或点按旁边的问号可查看原因。恢复隔离并重启 AstrBot 后，已保存的策略会重新生效。

### 嵌套沙箱策略

每个角色在 `provider_settings.computer_use_local_permissions.<role>` 下保存以下结构：

```json
{
  "allow_execution": true,
  "filesystem_scope": "workspace",
  "network": {
    "mode": "allowlist",
    "allowed_domains": ["example.com", "*.example.org:8443"],
    "denied_domains": ["blocked.example.com"],
    "allow_private_network": false,
    "allow_loopback": false
  },
  "filesystem": {
    "deny_read": ["~/.ssh", "/srv/private-secret.env"],
    "deny_write": ["/srv/shared"]
  },
  "unix_sockets": {
    "mode": "deny",
    "allowed_paths": []
  }
}
```

`filesystem_scope=none` 会强制关闭执行和网络。关闭执行会强制关闭网络。网络模式为 `off` 时会强制套接字为 `deny` 且不允许路径。旧的扁平 `allow_network` 键只做一次迁移，运行时不再读取。旧值 `allow_network=true` 会迁移为 `unrestricted` 并开启两个地址标志，以保留原有可达性；`false` 或缺失值迁移为 `off`。

### 网络策略

- `off`：沙箱工作负载不能访问直接 IP、宿主环回或 Unix 套接字出口；仅可使用沙箱内隔离的环回用于自身 IPC。
- `allowlist`：只有获批目标能通过带认证的 AstrBot 代理出站。`allowed_domains` 支持精确域名、`*.example.com` 子域规则、规范化 IP 字面量或 `*`，并可附加端口。拒绝规则始终优先。
- `unrestricted`：不设域名白名单，但流量仍必须经过代理；它不表示允许直接 IP 出站。元数据、链路本地、组播、未指定、保留、广播和宿主接口地址的内置防护仍然生效。

`allow_private_network` 和 `allow_loopback` 分别选择加入 RFC1918/ULA/CGNAT 和环回类别。元数据、链路本地、组播、未指定、保留、广播和宿主接口地址始终拒绝。允许列表中的规范化 IP 字面量会显式放行该 IP 及端口，即使其类别默认被阻止，但更具体的拒绝规则仍优先。IPv4-mapped、6to4、NAT64 及其他内嵌 IPv4 形式只会增加拒绝。

代理由宿主机执行一次 DNS 解析，并为连接固定数值地址，绝不要求沙箱解析域名。HTTPS 使用 `CONNECT`，因此使用宿主系统或 certifi CA 存储即可完成正常证书校验。支持明文 `http://` 绝对形式请求；拒绝 `https://` 绝对形式，因为 TLS 终止/MITM 不在范围内。`Proxy-Authorization` 只认证一次调用租约，并被消费而不是转发。直接 SSH、Git-over-SSH 以及绕过已配置 HTTP/SOCKS 代理的 SOCKS-only 工作负载不在覆盖范围内。

代理令牌按调用随机生成，仅通过继承的环境变量进入沙箱，不会出现在启动 argv 或内联 Python 源码中。以下环境变量会在调用方值之后按所有大小写形式覆盖：`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`；`NO_PROXY`/`no_proxy` 为空。受支持的 SOCKS 客户端使用 `socks5h`，由代理而非工作负载解析域名。

### 文件系统拒绝策略

`deny_read` 和 `deny_write` 接受绝对路径或以 `~` 开头的宿主路径。`~` 在配置/加载时按 AstrBot 操作系统账户展开，而不是沙箱 `HOME`。路径与通配使用 `pathlib.PurePath.full_match` 风格的 `*`、`?`、`[]`、`**` 语义并规范化分隔符，必须有字面量且存在的遍历锚点，并拒绝结尾分隔符、NUL、平台不适用的盘符或 UNC 形式。相对或无锚点的 `**/.env` 属于无效配置，不会静默扫描 `/`。

Linux 上，拒绝掩码会在所有工作区、宿主、Python 前缀和代理授权之后应用。拒绝写入会把目标绑定为只读；拒绝读取对文件使用空文件掩码，对目录使用可写 tmpfs，进程退出后其中内容消失。通配在启动时展开一次，最多 1,024 个掩码和 10,000 个遍历目录。字面目标缺失、遍历不可读或超限会使整个启动失败；规则绝不会创建目标。启动后新建的路径不会被通配覆盖。

macOS 上，同一套有界展开会生成字面 Seatbelt 拒绝规则，并排在所有授权之后。文件工具、文档读取、图片转换和 grep 在工作区及宿主范围都使用同一份解析后策略。读取/写入/编辑检查在打开文件或创建父目录之前执行。被拒绝的符号链接或解析目标会直接失败。这些掩码是启动时路径掩码，不是 inode 级机密隔离：预先存在的硬链接别名仍可能在拒绝路径之外引用同一 inode。文件工具仍拒绝多硬链接文件和符号链接，但进程级硬链接别名属于已记录的限制。

本地 grep 通过沙箱后端应用拒绝掩码。缺少所需 `rg` 或后端时会以通用错误失败关闭，绝不回退到直接宿主执行。

### Unix 套接字

- Linux `deny` 会在工作负载分支以 `EACCES` 阻止 `socket(AF_UNIX)`、`socket(AF_VSOCK)`、`socketpair(AF_UNIX)` 和 `io_uring_setup`。未过滤的 bridge 会先被 fork，并通过代理 Unix 套接字继续工作；工作负载不继承任何 Unix、ring 或 bridge 描述符。`allow_all` 不安装拒绝过滤器。
- macOS `deny` 阻止 Unix 套接字族创建及路径名/抽象连接。`allowed_paths` 仅适用于 macOS，接受规范化字面套接字路径而非通配。Linux 会拒绝非空 `allowed_paths`，而不是忽略。macOS 的 `allow_all` 整体重新开放出站 Unix 套接字，而不是按路径开放。
- 网络模式 `off` 始终使用套接字模式 `deny`。Windows 不支持进程隔离；其原生文件安全与本组设置相互独立。

任何沙箱组件失败、缺少必需后端或过滤器、或内核/架构不受支持时，执行会失败关闭，绝不回退到原生执行。活动隧道会关闭、租约被撤销，工具只收到有界通用错误。拒绝日志和结果只包含有界原因与脱敏目标元数据；令牌、凭据和宿主路径不会返回给模型。

Windows 通过原生文件句柄支持工作区范围内的文件读取、写入和编辑，并拒绝符号链接、目录联接和多重硬链接文件。Windows 原生环境仍不支持本地进程隔离；管理员可在整个环境执行代码并联网。

电脑能力走统一授权服务，不再使用“需要 AstrBot 管理员权限”开关。常见动作包括：

- `tool.computer_use`
- `tool.local_exec`
- `tool.python_exec`
- `tool.file_read`
- `tool.file_write`

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
