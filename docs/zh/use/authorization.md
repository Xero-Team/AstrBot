# 授权管理

AstrBot 把 Dashboard 登录、IM 会话管理和高风险操作拆开。把群友加成「管理员」不会让对方登录 WebUI，也不会变成全局 operator。

入口：侧栏 **更多 → 权限**，打开 `/authorization`。开发模型见 [项目架构](/dev/architecture#统一授权系统)。TOTP 和登录仍在 [WebUI](./webui#双因素认证)。

## 三套身份不要混

| 身份           | 从哪来                                                                        | 能做什么                                                                   |
| -------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Dashboard 账户 | 首次启动的 bootstrap `root`（用户名通常是 `astrbot`），以及权限页里创建的账户 | 登录 WebUI。`root` / `operator` 只绑定有效 Dashboard 账户                  |
| IM 私聊对端    | 运行时事实 `private_session`，不是 Dashboard 绑定                             | 只当**这一对一会话**的 `session_owner`，例如可以直接 `/conversation reset` |
| `/admin grant` | 当前会话的角色绑定                                                            | 只给本会话 `session_admin`，不能把 IM 用户变成全局 operator                |

不能凭用户名推断 `root`。控制面身份来自账户表和角色绑定。

## 固定角色

| 角色                | 范围            | 典型用途                       |
| ------------------- | --------------- | ------------------------------ |
| `root`              | 全局控制面      | 账户管理、重启、pip 安装       |
| `operator`          | 全局控制面      | 配置、Provider、插件、数据运维 |
| `instance_operator` | 单个配置档      | 该配置档的管理动作             |
| `session_owner`     | 当前群/私聊会话 | 会话管理、会话内模型选择       |
| `session_admin`     | 当前会话        | 有限管理，例如停任务、改会话名 |
| `member`            | 当前会话        | 普通对话                       |
| `guest`             | 未认证          | 匿名 WebChat                   |

当前会话的 owner 只能授予或撤销本会话的 `session_admin` / `member`，不能委派 owner。平台群主/管理员事实带 TTL，过期后降级，并且不会写成全局绑定。

## 权限页能做什么

页面有三个标签：

1. **绑定**：查看、授予、撤销角色绑定。可以按主体、角色、作用域筛选。
2. **账户**：创建、编辑、停用 Dashboard 账户。
3. **审计**：查看脱敏后的授权决策。

账户 CRUD、授予 `root` / `operator`、停用账户，都要求当前 `root` 绑定，再加上一次性密码或 TOTP 二次验证（step-up）。最后一个 `root` 不能删掉。

## 群聊里怎么授权

1. 在目标群发送 `/session info`，记下用户 ID（以及需要时的群 ID）。
2. 由当前会话 owner 执行 `/admin grant <用户 ID>`，或在权限页为该会话授予 `session_admin`。
3. `/admin list` 查看本会话可见绑定；`/admin revoke <用户 ID>` 撤销。

这三个子指令需要 `identity.manage`。完整指令见 [内置指令](./command#会话管理员)。

群聊的 `/conversation reset` 等管理指令需要 `session_admin` 及以上。私聊对端已经是 `session_owner`，不必预先绑定 `session_admin`。

配置档可以按平台、群或私聊分别绑定。改 `default` 不一定改变当前会话的授权范围，见 [配置文件](./config-profiles)。

## 二次验证（step-up）

以下操作会弹出密码或 TOTP 确认。凭证只用于当前这一次，不会放进 URL，也不能留给下一次：

- 安装插件
- 写入凭据
- 导出全部对话
- pip 安装
- 重启

对话导出要求精确的 `conversation:export` 资源和 `data.export_all`；普通 `data` scope 的 API Key 会被拒绝。备份下载走已认证 Blob 请求，不会把 Dashboard JWT 放进查询参数。

ChatUI 里的高风险工具（本机 Shell、文件写入、浏览器等）是另一次、只覆盖当前 WebChat 会话的 step-up，说明见 [WebUI](./webui#chatui-中的高风险工具)。它不会把 IM 用户变成全局 operator，也不会授权改账户、装插件或重启。

## 常见误配

1. 用 `/admin grant` 之后，以为对方可以登录 WebUI。
2. 把 Dashboard 的 `operator` 当成群管理开关。
3. 在 A 群授权，却在 B 群或另一份配置档上期望同样生效。
4. 把匿名 WebChat 或 API Key 当成 Dashboard `root`。
