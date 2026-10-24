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

New installations use the same defaults on Windows, Linux, and macOS: members get workspace files without execution, while administrators get entire-environment execution with networking. Existing saved permissions are preserved, including a member file access scope that was explicitly set to **Disabled**. The legacy Windows member default has the same saved value as a deliberate opt-out, so the fork does not rewrite it during upgrade; choose **Workspace** in the permission table when member file access is wanted. This administrator default runs Local code directly under the AstrBot account with entire-environment file access and networking; on Linux and macOS it does not use process isolation. Choose workspace scope when that access is not appropriate.

If a saved policy requires Local process isolation but isolation is unavailable, code execution and execution network access are disabled without widening file access or rewriting the saved policy. Workspace files without execution and entire-environment execution with networking remain available. The permission matrix keeps saved checks and marks unavailable execution as **Inactive**; hover over or select the adjacent help icon to see the cause. Restoring isolation and restarting AstrBot makes the saved policy effective again.

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
