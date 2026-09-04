# Configuration profiles

A profile decides how a class of sessions runs the Agent, which models they use, when they wake, and which plugins are enabled. It is not process-level Settings, and it is not a per-session exception.

Open **Config**. The profile menu at the top switches, creates, and manages profiles. Process options (bind address, HTTPS, TOTP) live under **Settings** at the bottom of the sidebar.

## Default vs extra profiles

| Profile       | File                             | Role                            |
| ------------- | -------------------------------- | ------------------------------- |
| `default`     | `data/cmd_config.json`           | Fallback when no route matches  |
| Extra profile | `data/config/abconf_<uuid>.json` | Named profiles created in WebUI |

Bindings are owned by the configuration manager. Do not rename JSON files to move them. With `ASTRBOT_ROOT` set, paths sit under `$ASTRBOT_ROOT/data/`.

The file must be strict JSON: `true` / `false`, no comments, no trailing commas. Prefer WebUI saves. If you edit JSON by hand, restart and keep a copy. Structure is in the [configuration reference](/en/dev/astrbot-config).

## How a message picks a profile

Every message has a unified message origin (UMO): `platform-id:message-type:session-id`. `/session info` prints the current UMO.

A routing table maps UMO patterns to profile IDs. Unmatched messages use `default`.

Each of the three UMO segments may be a wildcard:

- `::` — every session
- `[platform_id]::` — every type and session on one platform
- `napcat:GroupMessage:123456` — one group

Priority, high to low: exact literal → partial glob (for example `group-*`) → `*` or empty. Ties keep insertion order.

Where to bind:

- Session routes while editing a platform instance on **Bots**
- ChatUI, for the current WebChat session
- The Config page menu only chooses **which profile you are editing**. It does not change routing by itself

Saving a profile reloads that profile's pipeline. Click **Save**. In code-edit mode, click **Apply this configuration** first.

## Priority versus neighbors

| Layer        | Dashboard            | Owns                                                          | Use when                                          |
| ------------ | -------------------- | ------------------------------------------------------------- | ------------------------------------------------- |
| Settings     | Sidebar **Settings** | Process network, security, appearance, maintenance            | The whole AstrBot process                         |
| Profile      | **Config**           | Agent, models, `llm_access`, plugin set, knowledge-base names | One behavior for a class of sessions              |
| Custom rules | **Custom rules**     | Per-UMO on/off, models, persona, knowledge bases              | A few exceptions. Do not split a profile for this |

Custom rules outrank the profile. If a rule disables LLM, turning it on in the profile does nothing. See [Custom rules](./custom-rules).

System settings do not follow profile switches. `dashboard.host`, TOTP, and reverse-proxy headers stay process-wide.

## Easy-to-lose fields

These live on the profile, not Settings:

- [When the bot replies in groups](./group-wake): `llm_access`, command prefixes, isolated sessions
- [Platform handling](./platform-settings): allowlist, rate limit, content safety, inbound coalesce
- [Speech STT / TTS](./speech)
- [Knowledge base](./knowledge-base) `kb_names`
- [Plugins](./plugin) `plugin_set`
- [Personas](./persona), [Agent runner](./agent-runner)

`plugin_set` defaults to `["*"]`: every plugin that is not disabled on the plugin page. A global disable on that page wins over the profile checklist.

## Common misconfigurations

1. Editing `default` while the group is bound to another profile.
2. Creating a whole profile for one group's persona or model. Use a custom rule.
3. Looking for wake, allowlist, or TTS under **Settings**.
4. Editing JSON without **Apply this configuration**, so the form still shows old values.
5. Copying profile files to another machine without the UMO routes.
