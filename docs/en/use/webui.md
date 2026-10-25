# WebUI

The AstrBot admin panel features plugin management, log viewing, visual configuration, statistics viewing, and more.

![image](https://files.astrbot.app/docs/source/images/webui/image-4.png)

## Navigation and previous entry points

These entries match the default WebUI sidebar. If you customized the sidebar, check or restore the default layout under `Settings → Appearance` in the lower-left corner.

| Previous entry point                            | Current entry point                                                                 |
| ----------------------------------------------- | ----------------------------------------------------------------------------------- |
| Providers → Add Provider → Agent Runner         | Config → Select a profile → AI → `…` next to the AI heading → Change execution mode |
| Data / Dashboard                                | More Features → Data and Logs → Statistics                                          |
| Conversation Management / Conversations         | More Features → Data and Logs → Conversations                                       |
| Logs / Console                                  | More Features → Data and Logs → Logs                                                |
| Trace                                           | More Features → Data and Logs → Trace                                               |
| Config → Normal Config                          | Config → Select a profile                                                           |
| Config → System Config                          | Settings → General, Appearance, Network, or Security                                |
| Settings → General → Cache → Export diagnostics | Settings → Maintenance → Diagnostics → Export diagnostics                           |
| Command Management                              | Extensions → Manage Handlers → Commands                                             |
| Standalone MCP / Skills entries                 | Extensions → MCP Servers / Skills                                                   |
| Config → AI → Capabilities → BTW dual loops     | More Features → BTW Dual Loop (`/btw`)                                              |
| Work-task status and coding-agent output        | More Features → BTW Delegated Runs (`/btw/runs`)                                    |
| Persona / Persona Settings                      | Prompts / Prompt Settings                                                           |

Legacy log, trace, conversation, and statistics URLs still redirect to the matching tabs. Agent runners are now saved with each profile instead of being created as a provider; see [Agent Runner](./agent-runner.md).

The BTW dual-loop settings moved out of the AI panel on the configuration page to **More Features → BTW Dual Loop** (`/btw`). The page loads and saves whichever profile it is pointed at, and holds what it held before: both loops and their models, the work loop's read-only boundary, the Computer Use runtime, the task folder root and result reporting, and the coding-agent list. The separate delegated-runs page shows current and retained work sessions, coding agents, latest actions, normalized event timelines, usage, and artifacts; active tasks refresh automatically.

**More Features → CLI Global Config** (`/cli-config`) is a new entry: it keeps the provider list for Claude Code and Codex and switches one of them to be that CLI's own default on this host. A switch rewrites the CLI's own configuration file (backed up once, and "take back" restores it), so it asks for a step-up; a delegated task loads a layer of its own and is not affected.

If enabling a provider, restoring the configuration, or reading its status opens a reauthentication dialog, verify your current Dashboard account as prompted. After verification, the page automatically retries that operation. The credential is bound to this operation on the running default profile and can be used only once.

## Accessing the Admin Panel

After starting AstrBot, the local machine can open the admin panel at `http://localhost:6185`.

> [!IMPORTANT]
> WebUI binds only to `127.0.0.1` by default. Replacing `localhost` with a server IP in the browser does not expose it remotely.

For remote access, explicitly set `dashboard.host` in `data/cmd_config.json` to `0.0.0.0` or a selected interface address, then restart AstrBot. `0.0.0.0` increases the exposed surface; configure a firewall and preferably use an HTTPS reverse proxy. See the [source-deployment remote-access section](/en/deploy/astrbot/cli#remote-access) for a complete example.

## Login

For first-time login, AstrBot generates a random initial password only when `ASTRBOT_DASHBOARD_INITIAL_PASSWORD` is unset. Generated passwords appear only on an attached operator terminal and are not written to startup logs; supplied passwords are not displayed. The username is usually `astrbot`. For a non-interactive service or container startup, set the variable to a strong temporary value before the first run, then change it immediately after login.

The login page now also shows public version information before authentication:

- WebUI version
- AstrBot runtime version
- AstrBot code version when it differs from the runtime package version

If the login page detects a WebUI/runtime mismatch or runtime/code mismatch, it shows a warning dialog so you can fix stale static assets before signing in.

## Single sign-on (OIDC)

AstrBot can authenticate Dashboard users through an external OpenID Connect
provider. It is off by default and local password plus TOTP login keep working
unchanged. Configure it in `data/cmd_config.json` under `dashboard.oidc` (or the
Dashboard config editor):

| Key             | Role                                                                       |
| --------------- | -------------------------------------------------------------------------- |
| `enable`        | Show the SSO button on the login page.                                     |
| `issuer`        | Provider issuer URL; AstrBot reads `/.well-known/openid-configuration`.    |
| `client_id`     | Client registered with the provider.                                       |
| `client_secret` | Server-side secret used for the token exchange; never sent to the browser. |
| `redirect_uri`  | Fixed callback URL, for example `https://host/api/v1/auth/oidc/callback`.  |
| `scopes`        | Requested scopes; default `openid profile email`.                          |
| `auto_create`   | Create a Dashboard account on first verified login (no role is granted).   |
| `button_label`  | Text shown on the SSO button.                                              |

The flow uses the authorization-code grant with PKCE, a single-use `state` and
`nonce`, and a fixed redirect URI. AstrBot verifies the ID token signature
against the provider JWKS and binds the external identity to the stable
`account_id` by `(issuer, subject)`. Email is stored for display only and never
grants privilege. Auto-created accounts receive no role binding, so an operator
must grant access through the existing authorization rules. When `auto_create`
is off, only pre-linked identities can sign in. A failed or replayed callback
shows a generic error on the login page.

## Layout and appearance

Dashboard uses a responsive sidebar and main content area. On desktop, you can collapse and resize the sidebar; on narrow screens it becomes an overlay navigation panel. The appearance menu on login, setup, and signed-in pages selects light, dark, or system appearance. This preference is stored only in the current browser and does not change the AstrBot configuration.

### Wallpaper and surfaces

**Settings → Appearance** includes a separate landscape and portrait wallpaper library. Wallpaper files and appearance settings are stored on the server, and open Dashboard tabs stay in sync. Theme mode remains browser-local.

- JPEG, PNG, WebP, and GIF are supported up to `32 MiB` per file. The server validates the real format and pixel count, then uses a thumbnail for gallery previews and theme colours.
- Landscape wallpapers are preferred on desktop and landscape viewports; portrait wallpapers are preferred on phones and portrait viewports. The other orientation is used as a fallback.
- You can adjust fit, position, background blur, brightness, saturation, grayscale, dimming, and surface opacity. Surface opacity applies to the page, cards, header, and sidebar; floating menus keep a minimum readable background.
- Surface glass blur controls the backdrop blur on cards and page surfaces. Narrow-screen sidebars have a separate blur setting.
- Text readability enhancement offers a soft shadow and a strong stroke for low-opacity surfaces.
- Follow wallpaper theme colours replaces the theme primary/secondary colours with colours extracted from the active wallpaper. Disabling it restores the previous theme colours.
- Random wallpaper on open and scheduled rotation choose from the current orientation without immediately repeating the active wallpaper. Rotation runs only while the page is visible and is coordinated by one tab.
- The browser caches authenticated wallpaper downloads. Deleting a wallpaper removes its cache entry. Clearing site data or using a private window downloads it again.
- Deleting a wallpaper removes the server file and library reference; other tabs fall back automatically. Wallpaper assets are included in WebUI data backups, and the server-side selection survives a restore.

GIF and animated WebP use the static thumbnail when reduced motion is enabled.

## Two-Factor Authentication

AstrBot WebUI supports TOTP (Time-based One-Time Password) based two-factor authentication. The second factor and trusted devices belong to the current Dashboard account. Each account must configure its own factor; it is not inherited from a username or global configuration.

### Enabling Two-Factor Authentication

1. Open **Settings** at the bottom of the WebUI sidebar and select the **Security** section.
2. Toggle on "Enable WebUI TOTP"; a setup dialog with a QR code will appear.
3. Scan the QR code using any TOTP-compatible authenticator app (e.g., Google Authenticator, etc.).
4. Enter the 6-digit verification code generated by the authenticator app to complete the verification.
5. The system will generate recovery codes for logging in if the authenticator device is lost. Be sure to save them securely.

To replace the TOTP secret, you can do so in the TOTP management window, where you will need to verify the current TOTP code first.

### Recovery Codes

- Each recovery code can be used only once. After logging in with a recovery code, two-factor authentication will be automatically disabled, and you will need to set it up again.
- Recovery codes can be regenerated in the TOTP management window.
- If you lose the recovery codes, `data/cmd_config.json` is not an account-factor recovery mechanism. Ask the deployment administrator to perform account-level recovery; do not bypass verification by editing `dashboard.totp`, copying a TOTP secret, or modifying the database.

### Security Related

- Once two-factor authentication is enabled, replacing the secret requires verification of the current TOTP code to prevent unauthorized changes.
- Changing the admin-panel password revokes all trusted devices for the current account.
- High-risk operations, including plugin installation, credential writes, data exports, and restarts, ask you to re-enter the current password or TOTP. The resulting proof is single-use and applies only to that operation; cancelling or failing verification performs no change.

## Settings

System-wide settings have moved from the old Config → System Config route to **Settings** at the bottom of the sidebar. The page groups General, Appearance, Network, Security, Maintenance, and OpenAPI settings. The `Network` group holds the HTTP proxy, Python package sources, and GitHub mirror; for the address to use when AstrBot runs in Docker, see [Deploy with Docker](/en/deploy/astrbot/docker#configure-an-http-proxy-in-docker). System changes are saved automatically and a restart notice appears when required.

Backups under `Maintenance` include session aliases, scheduled tasks, model usage statistics, OpenAPI access keys, and MCP server configuration. Workspace files require a separate backup. TOTP trusted devices are excluded; replacing data from a backup clears existing device trust and requires device verification again. Older backups cannot recover data they did not include: export a new backup from the original instance before migrating. If a backup has no MCP configuration, the target instance's MCP configuration is kept.

Config profiles still control routed Agent, model, message-processing, and plugin behavior. Do not confuse profile settings with the system-level network and security controls under Settings.

## Data workspace

**More Features → Data and Logs** opens `/dashboard` with tabs for Statistics, Conversations, Logs, and Trace. The first visit opens Statistics; later visits reopen the last tab you used. The runtime `data/` file manager remains at `/data`; see [Data files](#data-files).

### Statistics

The Statistics tab summarizes platform instances, messages, model calls, tokens, and uptime. It also shows message trends, platform rankings, model-call trends, model usage rankings, and session token rankings. You can switch the window between 1 day, 3 days, and 1 week. Session rankings show UMO aliases, can copy the raw UMO, and can open that UMO in the Conversations tab.

The same page includes a local text-to-image section. It shows the in-process Chromium connection, render successes and failures, active pages, timing, reusable browser contexts, and aggregate output size. These values reset when AstrBot restarts and never include templates, rendered content, file paths, or user data.

### Conversations

The Conversations tab searches and manages saved conversation history:

- Filter by keyword, bot ID, private/group type, and UMO, and sort by created or updated time.
- The list paginates 30 rows at a time. Group-by-session paginates by UMO and expands to every conversation in that session. Full messages load only after you select a conversation.
- You can edit titles and bulk-export or bulk-delete. Export requires step-up reauthentication.
- The `{}` control in the preview opens a read-only Monaco editor for the wrapped raw `history` JSON.

### Logs

The Logs tab shows live AstrBot logs. You can filter by level and install a missing Pip package from the page. Pip install requires step-up. Enable DEBUG logs in Settings before looking for DEBUG output.

Click `Export diagnostics` and confirm the content and privacy notice to download a ZIP. It includes available disk and rotated logs, configured custom logs, up to 500 cached events, available trace history, configuration profiles and routes, plugin versions and status, environment details and a manifest. Existing data remains exportable when file logging or tracing is disabled; missing trace history is recorded without enabling tracing. Trace history is limited to the latest 50 traces and 16 MiB in total. Disk logs are limited to 256 MiB of source data, skipping individual files larger than 64 MiB and, in redacted mode, oversized lines. Truncation and missing items are recorded. Raw databases and plugin source code are excluded. The dialog enables `Redact credentials (recommended)` by default. Recognized credentials are masked, and public IPv4/IPv6 addresses use consistent aliases such as `[PUBLIC_IP_1]` across the bundle. Alternate spellings of the same address share an alias; protocols, ports, paths, local and other non-public addresses remain. No original-address mapping is included. Conversations and personal data may remain; review before sharing. Uncheck this option when diagnosis requires original values. This retains passwords, keys, tokens, public IPs and other sensitive data, and adds `raw` to the filename; share only privately with someone you trust. Reopening the dialog resets the option to enabled. Only authenticated dashboard administrators can download bundles; developer API keys are not accepted. The `Diagnostics` entry under `Settings` → `Maintenance` uses the same export.

The export dialog offers `Last hour`, `Last 12 hours`, `Last day`, `Last 3 days` and `Custom`, with `Last day` selected by default. Preset ranges are calculated when you click download. Select `Custom` to enter start and end times using your browser’s local time. Only disk logs, cached logs and traces within that range are exported. Timestamp-free continuation lines follow the preceding disk-log record; standalone content without a recognized timestamp is excluded. Disk timestamps without an explicit offset use the server’s local time. Traces are selected by start time and retain their complete details, with the existing limit of the latest 50 matching traces and 16 MiB. Configuration, plugin status and environment details remain current snapshots. The selected range is recorded in `manifest.json`.

In the diagnostic bundle, cached logs are stored in `logs/astrbot.in-memory.log`, cached traces in `traces/history.in-memory.jsonl`, and persisted trace history in `traces/history.jsonl`. The `webui_version` field in `environment.json` records the version declared by the WebUI assets being served, or `null` when unavailable.

Open `Filters` next to the search box to filter by level, source (System/Plugin), individual plugin, and bot platform. Combine these conditions with `Search logs`. Plugin menus prefer display names and show plugin IDs as subtitles; `System` replaces the former Core source label.

The toolbar also has font-size controls from 8–16px (12px by default, in 2px steps), plus the `Hide user chat` and `Auto-scroll` switches. Turn off `Auto-scroll` to read older entries without being pulled to the newest log. Logs stay in memory without new file-reading or database persistence.

### Trace

The Agent execution heading shows chips for recorded model and persona IDs, plus the number of actual tool calls when nonzero. Hover over a model chip to see its provider ID. These remain visible when the execution chain is collapsed; nested and parallel Agents are counted separately, and unavailable metadata is omitted.

Below the detail title, UMO and sender appear on separate icon-and-value rows. UMO aliases retain their hover tooltip showing the full identifier.

Trace text and tooltips use the system UI font rather than Outfit. Running status is blue; completed and error statuses remain green and red.

List and detail timestamps include month and day using `MM-DD HH:mm:ss.SSS` in the browser's local time zone; timeline timestamp tooltips use the same format.

Traces containing Agent calls add a borderless Tokens statistics card. Its total sums this execution's input (including cached input) and output, displayed with two-decimal k/M notation while the tooltip retains exact counts; hover or focus to inspect input, output, and cached-input counts. Only the latest cumulative snapshot per Agent is used, and separate Agents are summed. Unavailable usage shows an em dash rather than a reported zero.

The Type column precedes UMO. Blue Agent indicates an Agent call; green Command indicates a command-handler call. Neutral Group chat / Private chat chips appear independently alongside them. Ordinary listeners and event hooks do not count as commands. Message type comes from the summary, falling back to UMO for older records; unknown types have no chat chip. Legacy command flags are derived for the current page without opening each trace's details.

New spans identify calls with `astrbot.kind` and describe execution through timestamps and status. They no longer store `astrbot.action`, `astrbot.end_action`, or `astrbot.duration_ms`; duration is calculated from nanosecond timestamps and `astrbot.handler_type` remains. Existing trace history stays readable without rewriting stored records.

Long titles show two lines and received/sent message previews show four lines by default. Overflowing text offers Show full text / Collapse. This only folds the display; recorded content is not truncated.

Complete means the entire event has finished processing, not just its model request or response delivery. Ordinary messages and Cron tasks share the event execution lifecycle. Cron does not run through the message Pipeline; its trace ends after Agent execution and history saving, and failures or cancellations also close the trace with an error.

The detail timeline uses a compact grouped layout: "Plugin handler triggered (Type)" becomes "Call plugin" with a category chip, and "Start Agent" becomes "Agent execution". A consistent right-hand chevron replaces repeated standalone View details links; click a regular node's heading to inspect its raw data, or a plugin call group to expand its calls. Platform IDs move to secondary chips, metadata chips use neutral colors, and times show offsets from trace start with precise timestamps on hover.

Agents fold their execution chain by default. Click Agent execution to expand request preparation, tools, and plugin hooks; Raw data exposes the Agent's own fields. Folding follows actual span parent relationships, without capturing unrelated interleaved branches. Expansion preserves record order and final responses stay on the main line. Collapsed headers retain internal error indicators, and folding does not change call, response, or span counts.

![Compact grouped timeline with a collapsed Agent (preview data)](images/trace-timeline-en.jpg)

Under Settings → General, Log & Cache Cleanup is now Log, Cache & Trace Cleanup. Total usage includes the trace database and its sidecar files. The menu adds Clear Trace Data, and Clean All includes historical traces. Confirmation warns that completed/interrupted traces are permanently removed while running traces are retained; the database file is not deleted directly. Clean Logs and Clean Cache do not clear traces.

Toggle Enable Trace Recording under Settings → General → Logs. It shares the same global setting as the trace toolbar’s start/pause button; disabling recording stops collecting new traces without deleting history. Below it, configure the database path, capacity budget (MB), and retention days. Defaults are `logs/traces.db`, 80 MB, and 7 days; restart the backend after changing the path. Top-level text fields such as system prompts have no separate 4 KB truncation limit; whole-trace content and node budgets still apply.

The trace tab has no outer gray card; its toolbar and list sit directly on the page with only the necessary separators. The former hint and switch are replaced by a toolbar button showing Pause (enabled and connected), Connecting (enabled but disconnected), or Start (disabled). Filters, recording, and refresh use matching light-gray icon-and-text buttons sharing the input's background color, all 36px high. Search fills the remaining width, pushing actions to the right. Its placeholder includes the message count instead of a separate counter. Click to pause or resume. Updates show loading and prevent repeated clicks; failures preserve the previous state and display an error. Pausing retains the list and open details in both themes.

The `Trace` tab shows message execution chains: receipt, plugin handlers, Agent requests, responses, and completion. It opens as a full-width Vuetify datatable with columns ordered as status chip, platform logo, timestamp, duration, message, type, UMO, sender, and Spans. Header and cell text uses 13px with a 40px header height, while body row height and spacing use Vuetify defaults; only cell content such as status, platform icons, and messages is customized. Status chips use the flat variant; the platform column is 80px wide with a non-wrapping header. Duration updates while execution is active. Click a row to open its timeline details on the right; use the close button or Escape to return to the list. History loading, incoming records, and filtering never automatically open another trace. Scroll horizontally on narrow screens. Spans counts actual spans including the message root, excluding span events; collapsing does not change the count. The search placeholder shows the total message traces matching the current filters. History is searched, filtered, and paginated server-side. Vuetify's datatable pager replaces Load more, with 50 rows by default, options of 25/50/100, and previous/next and first/last page controls. The browser retains only the current page's summaries and loads full detail only for the selected trace, releasing it on close. Search/filter changes return to page one. New records refresh the first page without inserting into historical pages. Open `Filters` next to search to select `Has errors`, `Has model calls`, and `Has plugin calls`. Multiple selections require all conditions and can be combined with search. No selection shows all traces; `Reset` clears selections, and closing the sidebar preserves them. This sidebar replaces the former `All / Errors / Agent / Plugins` single-select tabs. Use the toolbar recording button to enable or disable trace recording.

Session aliases replace raw UMOs when available; hover over the dotted underline to see the full UMO. Plugins use their display name when available; hover to see the plugin ID. Handler names and duration are also shown. Listener nodes omit the redundant `AdapterMessageEvent` type; other hook event types remain visible. Plugin handler nodes use the plugin logo when available and the plugin card's default blue star icon if it is missing or fails to load. Neutral chips next to the title show the category, matching the plugin detail page: command/command group, event listener, event hook, or LLM tool.

> [!NOTE]
> Traces are persisted in dedicated SQLite at `data/logs/traces.db` by default, with 7-day retention and an 80 MB capacity target. Old traces are evicted as complete units. WAL and checkpoints may temporarily add disk usage; the target is not an instantaneous hard limit. Pausing leaves history readable and allows existing traces to finish. Traces unfinished at restart are marked errored/interrupted. Queue pressure or storage failures show a warning without blocking message processing. Legacy JSONL files are neither appended nor imported; ordinary logs keep their existing file settings.

Handler names also have a dotted underline. Hover to lazily fetch plugin details and show that handler's description, including nested commands, using the same description as the plugin detail page. Details are cached for the current page; hover again to retry a failed request.

Streaming responses show one final aggregated response after delivery finishes, without intermediate chunks or protocol closing frames. Messages sent independently by tools or plugins during generation remain separate responses.

Timeline chips show the runner name without an execution-mode prefix, using the profile page's labels (`local` uses the AstrBot built-in AI title), and plugin names (comma-separated in collapsed groups). Response ownership chips are removed: successful public sends through `event.send()` and `Context.send_message()` record message outlines without a source field. Context sends attach to the current event execution, without creating a new trace when none is active. Nested forwarding is recorded once; streaming keeps only its final aggregate and separate tool messages.

Consecutive nodes of the same type are collapsed by default, such as "Call plugin" with an "Event listener" chip, with a record count and stacked icons. Click to expand or collapse the individual records. Different handler categories and records separated by another node type remain separate, preserving execution order. Collapsed groups still show error counts, and summary cards continue to count actual calls.

The message list and message-received node show the platform logo. The message-received node shows `platform_id` in a secondary chip. A generic icon is used when no logo matches or the image fails to load; text still indicates processing status. The former standalone Select persona node is removed; the resolved `persona_id` appears in the Agent request prepared details. The search placeholder is "Search messages, sessions, or plugins in X records". Summary cards show duration, plugin handler calls, and responses, without counting steps.

## ChatUI

AstrBot includes a built-in ChatUI for talking to configured models directly in your browser.

ChatUI supports these common workflows:

- The sidebar initially loads the 30 most recent conversations. Scroll near the bottom to automatically load older conversations, with a progress bar while loading. Automatic requests pause after a failure; select **Retry** to continue. If the list does not fill the sidebar, more pages load automatically. Opening an older conversation by URL keeps its title and selected sidebar entry visible before its page loads.
- Create, rename, and delete conversations, and switch previous conversations from the sidebar.
- Select the config profile, model provider, and model on the chat page; if Provider session separation is enabled, you can also choose a model for the current session only.
- Send text, images, files, and voice input; uploaded attachments show previews and use file signature checks to help identify file types.
- View model thinking, tool-call status, knowledge-base or web-search references, and per-message token and latency statistics.
- Reasoning is shown by default. Use the composer menu to override reasoning display for the current request, a regeneration, or a thread.
- Copy or regenerate existing replies, including regenerating with another model.
- Edit a user message and continue generation from that point, or start a thread from a specific excerpt.
- Switch between streaming/normal response modes and SSE/WebSocket transport modes. On touch or other coarse-pointer devices, the nested Transport and Language menus open on click instead of hover.

To return to the model configured in the selected profile, open the model selector and choose **Default model** (**Follow the selected profile's default model**). This clears the override for the current conversation; other conversations retain their saved model choices. Logging out clears all saved ChatUI model choices in this browser.

- Browse the current project workspace from ChatUI. Text previews use Shiki syntax highlighting and follow the active light or dark theme; binary files show metadata only.

### Sharing a conversation

In the conversation list, hover a conversation and select the share button to create a read-only link for it. The link opens without signing in, and anyone who has it can read the transcript, so share it carefully.

- Expiry choices are 1, 7, 30, or 90 days, or never.
- The raw link is shown once when created and cannot be recovered; copy it immediately.
- The public page shows only that conversation's text transcript (no attachments), is read-only, and cannot reach your other data.
- The same dialog lists existing links for the conversation and lets you revoke any of them; revoked or expired links show as unavailable.
- Very long conversations show only the most recent messages, with a notice at the top of the page.

> [!WARNING]
> The share link is itself a credential. Anyone holding it can read the conversation, so do not share conversations that contain sensitive information.

### Parallel models

Multi-model turns are off by default. Enable `dashboard.chatui_multi_model.enable` and set `dashboard.chatui_multi_model.max_models` (2–8, default 3) in `data/cmd_config.json`. In ChatUI, use **Compare models** beside the model selector to choose several models for the next prompt. Each answer becomes a branch saved with the assistant message, and the reply header switches between the branches. The first selected model is stored as the session's model.

### High-risk tools in ChatUI

The shield-key button beside the message box enables high-risk tools for one
ChatUI run. It is available only when the signed-in Dashboard account has an
`instance_operator` (or stronger) binding for the selected configuration
profile. The confirmation dialog asks for the current password or TOTP code.

The confirmation grants only the following instance-scoped tool actions:

- local shell and Python execution;
- local file writes;
- browser and Computer Use control;
- write-capable MCP tools.

The proof is held only in browser memory and is bound to the active WebChat
conversation and configuration profile. It is used once when the next run
starts, then discarded; change the conversation or profile, wait for it to
expire, or click the button again to disable it. Enable it again before another
high-risk run.

This does not grant access to global Dashboard operations such as changing
accounts, providers, plugins, system settings, exports, or restarts. The
account's Prompt, tool, local-isolation, and path restrictions still apply. Anonymous
WebChat, API keys, IM messages, plugins, and background continuations cannot
reuse this authorization. IM senders use a different path: bind the Subject ID
from `/session info` as `instance_operator` on that config. See
[Authorization](./authorization).

> [!NOTE]
> To keep message delivery ordered, keep only one ChatUI page open for the same browser session. If you open chat in multiple tabs, the system may ask you to reconnect.

## Accounts and authorization

WebUI supports multiple Dashboard accounts. First startup creates a bootstrap `root` account (username is usually `astrbot`). Control-plane identity comes from the account table and role bindings; a username never implies `root`.

**More Features → Authorization** opens `/authorization`. Dashboard accounts, IM session owners, and `/admin grant` are not the same identity. Group grants, step-up, and the role table are in [Authorization](./authorization).

Cross-session watches, connects, and `/send` have no Dashboard management surface in this stage. After binding `instance_operator`, create, list, and stop watches or links only with the [built-in IM commands](./command#cross-session-watches-and-sending). The command-management page can enable or disable those commands, but it does not list active watches or links.

The developer model is in [Architecture](/en/dev/architecture#unified-authorization).

## Visual Configuration

In the admin panel, you can configure AstrBot's plugins through visual configuration. Click `Config` in the left sidebar to enter the configuration page. Profiles, session binding, and priority versus custom rules are in [Configuration profiles](./config-profiles).

![image](https://files.astrbot.app/docs/source/images/webui/image-3.png)

After modifying the configuration, you need to click the `Save` button in the bottom right corner to successfully save the configuration.

Use the first circular button in the bottom right corner to switch to `Code Edit Configuration`. In `Code Edit Configuration`, you can directly edit the configuration file.

After editing, first click `Apply This Configuration`, which will apply the configuration to the visual configuration, then click the `Save` button in the bottom right corner to save the configuration. If you don't click `Apply This Configuration`, your modifications won't take effect.

![alt text](https://files.astrbot.app/docs/source/images/webui/image-5.png)

## Extensions (plugins)

In the admin panel, you can view installed plugins and install new plugins through the `Extensions` section in the left sidebar. Marketplace source, `astrbot_version`, and Dashboard extensions are in [Plugins](./plugin).

Click the **AstrBot Plugin Market** tab to browse plugins from the default marketplace source. That source first requests the upstream `cloud.astrbot.app` market JSON, then falls back to `AstrBotDevs/AstrBot_Plugins_Collection` and its CDN; Xero-Team does not operate or review it. This fork requires Python 3.15+ and does not keep legacy plugin APIs, so entries in that list may fail to install or load.

![image](https://files.astrbot.app/docs/source/images/webui/image-1.png)

You can also click the + button in the bottom right corner to manually install plugins via URL or file upload.

> Neither this fork nor the upstream AstrBot Team guarantees the security or compatibility of these plugins. Maintainers are not responsible for losses caused by plugins.

### Handling Plugin Load Failures

If a plugin fails to load, the admin panel will display the error message and provide a **"Try one-click reload fix"** button. This allows you to quickly reload the plugin after fixing the environment (e.g., installing missing dependencies) or modifying the code, without having to restart the entire application.

## Prompts

The Prompts page can create folders, move or reorder prompts, and import or export one prompt at a time. Exported JSON contains the prompt ID, system prompt, and preset dialogs only; it intentionally excludes tools and Skills. Recheck and configure tools, Skills, and provider choices after importing.

If an imported prompt ID already exists, WebUI creates a new ID with an `_imported` suffix instead of overwriting the existing prompt. Review JSON from untrusted sources before attaching it to an Agent with privileged tools.

## Command Management

Use the `Command Management` menu on the left to centrally manage all registered commands; system plugins are hidden by default.

Filter by plugin, type (command / command group / subcommand), permission, and status, and combine with the search box for quick lookup. Command group rows can expand to show subcommands, badges display the subcommand count, and subcommand rows are indented to indicate hierarchy.

You can enable/disable, rename, and edit aliases for each command. Commands from a deactivated plugin appear as Plugin off: enable/disable and rename stay blocked until the plugin is enabled, but details remain available, and those commands are excluded from conflict detection. Saving immediately rebuilds the immutable command catalog owned by the plugin lifecycle. Telegram and Discord adapters with native command registration enabled also refresh their menus or slash commands immediately instead of waiting for the next message.

Commands are identified by a stable `command_id` of the form `plugin-name:original-command-path` with spaces replaced by dots, for example `builtin_commands:plugin.list`. Permission overrides are read and written only under that key; Python method names and historical short-name keys are ignored. Built-in commands without an explicit Dashboard rename keep their current declared names. Unmatched `command_configs` rows that cannot be claimed by `handler_full_name` or `command_id` are deleted during sync.

## Data files

**More Features → Data Files** opens `/data` to browse and edit the active runtime `data/` directory. It is not a remote IDE: there is no terminal, code execution, Git, or arbitrary host-path access.

On desktop the left pane is a directory tree and the center holds file tabs plus a Monaco editor. The URL stores only a relative path such as `/data?path=skills/demo/SKILL.md`, never file contents or credentials. An invalid path falls back to the `data/` root. Hidden files are shown. Leaving a dirty tab prompts for confirmation.

`operator` and `root` can browse ordinary text and save it. Editable text is capped at 1 MiB; larger files become read-only downloads. You can create, rename, move, and delete files and directories, upload a file up to 32 MiB, and search by filename (not contents). Images and audio can be previewed; databases, archives, and unknown binaries expose metadata and download only.

Protected paths have a separate policy:

- `plugins/` is read-only until a root `filesystem.manage` step-up.
- `dist/`, `site-packages/`, `astrbot.lock`, and live databases plus WAL/SHM are never writable.
- Raw reads of `cmd_config.json` and `config/` require root; ordinary configuration still belongs on the structured config pages.
- Demo mode is read-only.
- API keys cannot open this page.

Concurrent saves use an etag; a changed file on disk returns a conflict with **Keep local** or **Reload**. The developer model is in [Architecture](/en/dev/architecture#data-file-manager).

## Updating the Admin Panel

This fork does not provide a Dashboard one-click Core updater. Source deployments should rebuild `dashboard/dist` after updating the checkout and run `uv run python scripts/sync_dashboard_dist.py`; see [Update the Checkout](/en/deploy/astrbot/cli#update-the-checkout).

Message commands and the `astrbot` CLI never download, install, or update Dashboard assets. Upstream Dashboard static files are incompatible with this fork's backend API and frontend behavior and must not be copied into `data/dist`. Startup uses only an explicit `--webui-dir`, a build from the current source tree, bundled assets, or a version-matched `data/dist`. Without a compatible build, the backend continues to run but the WebUI is unavailable.

## Customizing WebUI Port

Modify the `port` in the `dashboard` configuration in the data/cmd_config.json file.

## Forgot Password

Stop AstrBot, then use one of the CLI reset flows:

```bash
uv run astrbot password
# or
uv run astrbot run --reset-password
```

> [!TIP]
> For more details, see [FAQ - I forgot the WebUI password](/en/faq#i-forgot-the-webui-password). Do not manually delete password hashes or the JWT secret.
