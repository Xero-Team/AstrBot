# Computer Use

Computer Use controls whether an Agent can execute code, access files, run Shell commands.

## Mode Selection

In WebUI, open:

- `Config -> select a profile -> AI -> Capabilities -> Agent Computer Use`

The key option is `Computer Use Runtime`:

- `none`: disables Computer Use; Shell, Python, filesystem, and related tools are not mounted. Skill manuals still load through `read_skill` and do not require Computer Use.
- `local`: executes on the host machine where AstrBot is running. Use this when the Agent needs local files, command-line tools, or local dependencies.

Use `local` only when direct host access is required. Legacy configurations with a removed runtime value are treated as `none`.

## Local Mode

`local` mode mounts Computer Use tools into the host environment where AstrBot runs. The Agent can call the host Shell, host Python, and host filesystem tools.

This means the Agent's boundary is close to the AstrBot process itself. What it can access depends on the system permissions, runtime user, working directory, and operating-system restrictions of the AstrBot process.

### Workspace

In `local` mode, AstrBot prepares a workspace for each session:

```text
data/workspaces/{normalized_umo}
```

`{normalized_umo}` is derived from the current session's `unified_msg_origin`; characters unsuitable for filenames are replaced with `_`.

Relative paths passed to local filesystem tools are resolved under this workspace. For example:

```text
notes/todo.txt
```

is resolved as:

```text
data/workspaces/{normalized_umo}/notes/todo.txt
```

The local Shell tool also runs with this workspace as its current working directory.

> [!NOTE]
> The local Python tool executes code through AstrBot's current Python environment. When Python code reads or writes files, use explicit absolute paths or prepare files through filesystem tools in the workspace first.

### Local Tools

`local` mode mainly provides:

- `Shell`: executes host shell commands. Windows follows `cmd.exe` semantics; Linux/macOS follow Unix-like shell semantics.
- `Python`: executes Python code in AstrBot's current Python environment.
- `File read`: reads text, image, spreadsheet, and other supported files.
- `File write`: writes UTF-8 text files; relative paths default to the current workspace.
- `File edit`: replaces exact text in files.
- `Grep search`: searches file contents through ripgrep.

`local` mode does not mount remote upload/download or browser automation tools.

The local Shell tool includes basic blocking for dangerous commands such as `rm -rf`, `sudo`, `shutdown`, `reboot`, and `kill -9`. This is not a complete security sandbox and should not be treated as one.

### Permission Model

In the local permission table, open the **File access scope** menu to read each option's description. **Workspace** restricts access to the session workspace, temporary directories, and skill files. **Entire environment** (formerly **Host files**) allows access to files permitted by the account running AstrBot. In Docker, this means files inside the container and mounted files, not all files on the Docker host. **Disabled** prevents file access through local Computer Use tools. These descriptions now appear under the corresponding menu options instead of below the table. Hover over or tap the question mark after “All files in the environment where AstrBot runs.” for details about account permissions and Docker file access.

New installations use the same nested defaults on Windows, Linux, and macOS. Members get workspace files without execution, network mode `off`, and Unix socket mode `deny`. Administrators get entire-environment execution, network mode `unrestricted`, both private-network and loopback flags enabled, no filesystem deny rules, and Unix socket mode `allow_all`. Existing saved permissions are preserved, including a member file access scope that was explicitly set to **Disabled**. The legacy Windows member default has the same saved value as a deliberate opt-out, so the fork does not rewrite it during upgrade; choose **Workspace** in the permission table when member file access is wanted.

Native execution is exactly the administrator tuple `host` / `unrestricted` / both address flags enabled / no deny rules / socket `allow_all`. It runs directly under the AstrBot account without process isolation and provides none of the sandbox guarantees described below. Any deviation, including a workspace scope, a domain rule, a disabled address flag, a filesystem deny rule, or a socket deny mode, requires a real sandbox backend. If that backend is unavailable, code execution is disabled without widening file access or rewriting the saved policy. The permission matrix marks unavailable execution as **Inactive**; hover over or select the adjacent help icon to see the cause. Restoring isolation and restarting AstrBot makes the saved policy effective again.

### Nested sandbox policy

Each role stores this shape under `provider_settings.computer_use_local_permissions.<role>`:

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

`filesystem_scope=none` forces execution off and network off. Execution off forces network off. Network mode `off` forces socket mode `deny` with no allowed paths. The old flat `allow_network` key is migrated once, then never read at runtime. A legacy `allow_network=true` becomes `unrestricted` with both address flags enabled so its previous reachability is preserved; `false` or a missing value becomes `off`.

### Network policy

- `off`: sandboxed workloads cannot use direct IP, host loopback, or Unix-socket egress. Only the isolated loopback inside the sandbox is available for its own IPC.
- `allowlist`: only approved destinations can leave through the authenticated AstrBot proxy. `allowed_domains` entries are exact names, `*.example.com` subdomain rules, canonical IP literals, or `*`, with an optional port. Deny rules always win.
- `unrestricted`: no domain allowlist, but traffic still goes through the proxy. It does not mean direct IP egress. Built-in metadata, link-local, multicast, unspecified, reserved, broadcast, and host-interface guards still apply.

`allow_private_network` and `allow_loopback` opt into RFC1918/ULA/CGNAT and loopback classes. Metadata, link-local, multicast, unspecified, reserved, broadcast, and host-interface addresses stay denied. A canonical IP literal in the allowlist explicitly permits that IP and port even when its class is otherwise blocked, unless a more specific deny rule wins. IPv4-mapped, 6to4, NAT64, and other embedded IPv4 forms only add denials.

The proxy performs host-side DNS once, pins the numeric address for the connection, and never asks the sandbox to resolve names. HTTPS uses `CONNECT`, so normal certificate verification succeeds with the host's system or certifi CA store. Plain `http://` absolute-form requests are supported; absolute-form `https://` is rejected because TLS termination/MITM is out of scope. `Proxy-Authorization` authenticates exactly one invocation lease and is consumed, never forwarded. Direct SSH, Git-over-SSH, and SOCKS-only workloads that bypass the configured HTTP/SOCKS proxy are not covered.

Proxy tokens are random per invocation and reach the sandbox only through inherited environment variables, never launcher argv or inline Python source. The following environment names are overridden after any caller values, in every case variant: `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY`; `NO_PROXY`/`no_proxy` are empty. Supported SOCKS clients use `socks5h` so the proxy, not the workload, resolves the hostname.

### Filesystem deny policy

`deny_read` and `deny_write` accept absolute or `~`-based host paths. `~` expands against the AstrBot OS account at configuration/load time, not the sandbox `HOME`. Paths and globs use `pathlib.PurePath.full_match` style `*`, `?`, `[]`, and `**` semantics with normalized separators, must have a literal existing traversal anchor, and reject trailing separators, NUL bytes, and platform-inappropriate drive or UNC forms. A relative or anchorless pattern such as `**/.env` is invalid instead of silently scanning `/`.

On Linux, deny masks are applied after every workspace, host, Python-prefix, and proxy grant. A write denial binds the target read-only; a read denial masks files with an empty file and directories with a writable tmpfs whose contents disappear when the process exits. Globs expand once at launch with at most 1,024 masks and 10,000 visited directories. A missing literal target, an unreadable traversal, or an overflow fails the whole launch; rules never create their targets. A glob cannot cover paths created after launch.

On macOS, the same bounded expansion produces literal Seatbelt deny rules ordered after every grant. File tools, document reads, image conversions, and grep use the same resolved policy in workspace and host scope. Read/write/edit checks run before opening a file or creating parents. A denied symlink or resolved target fails. These masks are launch-time path masks, not inode-level secret isolation: a preexisting hard-link alias can still reference the same inode outside a denied path. File tools continue to reject multiply linked files and symlinks, but process-level hard-link aliases are a documented limitation.

Local grep applies deny masks through the sandbox backend. If the required `rg` executable or backend is unavailable, the tool fails closed with a generic error; it never falls back to direct host execution.

### Unix sockets

- Linux `deny` blocks `socket(AF_UNIX)`, `socket(AF_VSOCK)`, `socketpair(AF_UNIX)`, and `io_uring_setup` with `EACCES` in the workload branch. The unfiltered bridge is forked first and keeps working through the proxy Unix sockets; the workload inherits no Unix, ring, or bridge descriptor. `allow_all` installs no deny filter.
- macOS `deny` blocks Unix socket family creation and pathname/abstract connections. `allowed_paths` is macOS-only and accepts normalized literal socket paths, not globs. Linux rejects nonempty `allowed_paths` instead of ignoring them. `allow_all` on macOS reopens outbound Unix sockets as a whole rather than per path.
- Network mode `off` always uses socket mode `deny`. Windows does not support process isolation; its native file security remains separate from these settings.

When any sandbox component fails, a required backend or filter is missing, or the kernel/architecture is unsupported, execution fails closed. There is no native fallback. Active tunnels close, leases are revoked, and tools receive a bounded generic error. Denial logs and results contain only bounded reason and redacted target metadata; tokens, credentials, and host paths are not returned to the model.

Windows supports workspace-scoped file reading, writing, and editing through native file handles. File operations reject symbolic links, directory junctions, and multiply linked files. Local process isolation is still unsupported on native Windows; administrators can execute code with entire-environment access and networking.

Computer Use uses the unified authorization service. There is no “Require AstrBot admin permission” switch. Typical actions include:

- `tool.computer_use`
- `tool.local_exec`
- `tool.python_exec`
- `tool.file_read`
- `tool.file_write`

`tool.file_read` is available to current-session members and above, still subject to path limits. `tool.local_exec`, `tool.python_exec`, `tool.file_write`, `tool.mcp_write`, and `tool.computer_use` are instance-scoped high-risk actions: an authenticated Dashboard-driven WebChat may use them only in its current session/config after the WebChat one-time step-up. An IM sender bound as `instance_operator` on that config may use the same set without step-up. Global control-plane actions remain Dashboard-only; anonymous WebChat, plugins, agents, API keys, and unbound IM members do not inherit Dashboard roles. Path, Prompt, and declared-tool restrictions still apply.

In `local` mode, ordinary session members may read:

- `data/skills`
- `data/plugins/*/skills` (read-only, for plugin-provided Skills)
- the current session's `data/workspaces/{normalized_umo}`
- AstrBot temporary directories
- `.astrbot` under the system temporary directory

Writes and edits remain limited to the current session workspace and temporary directories. Bind the IM sender as `instance_operator` on that config from the Dashboard [authorization page](/en/use/authorization). `/admin grant` only creates current-session `session_admin`; it does not turn an IM user into a global operator. See [Architecture](/en/dev/architecture#unified-authorization) for the developer model.

## Skills

Skills are reusable instruction bundles for Agents. They are usually stored under `data/skills`, and each Skill contains a `SKILL.md`.

The relationship between Skills and Computer Use is:

- Skills tell the Agent what to do.
- Computer Use decides whether the Agent can execute those steps.

For example, a Skill may ask the Agent to read files, run scripts, and generate a report. If `Computer Use Runtime` is `none`, the Agent may see the Skill instructions, but it cannot call Shell or Python to execute them.

In `local` mode, the Agent reads local Skills.

For more details, see [Anthropic Skills](/en/use/skills).
