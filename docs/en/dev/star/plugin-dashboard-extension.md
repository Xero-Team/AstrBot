---
outline: deep
---

# Plugin Dashboard Extension Development Guide

Dashboard Extension Protocol v1 lets a plugin provide isolated pages inside the
AstrBot Dashboard and call its Python code through host-managed Actions. Each
page runs in a sandboxed iframe with only `allow-scripts`. It cannot read the
Dashboard DOM, cookies, local storage, or authentication data, and it cannot
call Dashboard APIs or external networks directly.

A page can only use `window.AstrBotPluginPage` to invoke Actions explicitly
allowed by its manifest. A plugin page cannot submit a target URL, HTTP method,
request header, or absolute server path.

## Minimal Directory Layout

The executable minimal example in this repository is under
`tests/fixtures/plugins/dashboard_extension_example/`:

```text
dashboard_extension_example/
  main.py
  metadata.yaml
  pages/
    settings/
      app.js
      assets.v1.json
```

A Page does not provide its own HTML. AstrBot generates a fixed secure Shell
and loads the module and styles declared by the manifest.

## Declare the Metadata Capability

A Dashboard Extension must declare both `requires.dashboard_extension: 1` and
`dashboard` in `metadata.yaml`. These fields must appear together. An unknown
protocol version, the old top-level `pages` field, or any unknown field makes
plugin loading fail.

```yaml
name: dashboard_extension_example
display_name: Dashboard Extension Example
author: Xero-Team
version: 1.0.0
desc: Minimal Dashboard Extension Protocol v1 example plugin
astrbot_version: '>=4.26.6'
requires:
  dashboard_extension: 1
dashboard:
  extension_id: team.xero.astrbot-dashboard-extension-example
  pages:
    - id: settings
      title: Settings
      module: pages/settings/app.js
      assets_manifest: pages/settings/assets.v1.json
      icon: mdi-view-dashboard-outline
      actions:
        - settings.read
```

### Field Constraints

- `dashboard.extension_id` is the stable extension identity across installs,
  renames, and upgrades. It must contain 3–128 lowercase ASCII characters and
  at least two dot-separated labels. Each label must match
  <code>^[a-z0-9]&lpar;?:[a-z0-9-]{0,61}[a-z0-9])?$</code>. Do not derive it
  from a mutable plugin directory name.
- `page.id` must match `^[a-z][a-z0-9-]{0,47}$` and be unique within the
  extension.
- `page.title` must contain 1–80 characters.
- `page.module` must be a `.js` or `.mjs` file.
- `page.styles` is optional and accepts at most eight unique `.css` files.
- `page.icon` is optional and uses an MDI icon name supported by the Dashboard.
- `page.actions` accepts at most 64 unique IDs. An Action ID is at most 64
  characters and must match `^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$`.
- An extension declares at least one Page. Every Action referenced by a Page
  must be registered successfully during plugin `initialize()`.

## Create the Assets Manifest

Every Page must provide its own `assets.v1.json`. It is the complete allowlist
of static files available to that Page, not a hint about build output. List the
module, styles, dynamic imports, images, fonts, and every other runtime asset.

```json
{
  "version": 1,
  "files": [
    {
      "path": "pages/settings/app.js",
      "sha256": "34151ab52abbc2cfdde2b611e63e9f22190e27d656301c60af398a10fbadf079",
      "size": 676
    }
  ]
}
```

`sha256` must be the 64-character lowercase hexadecimal SHA-256 digest of the
raw file bytes. `size` must be the exact byte length of the same file. Plugin
loading and every bundle read recheck path containment, type, size, and digest;
any mismatch fails closed.

Asset paths must be ordinary paths relative to the plugin root. AstrBot rejects
absolute paths, `..`, backslashes, encoded paths, NUL, hidden segments, trailing
dots or spaces, Windows drive/UNC/ADS paths, symlink escapes, and case or
Unicode-normalization collisions.

The limits are 16 MiB per file, 32 MiB total per Page, and 256 files. Allowed
suffixes are:

```text
.js .mjs .css .json .png .jpg .jpeg .gif .webp .ico
.woff .woff2 .ttf
```

SVG, WASM, and source maps are not served. The frontend build must emit a
deterministic file list and regenerate size/digest values after every build. Do
not retain stale digests manually.

## Register Python Actions

Import Dashboard types only from the public `astrbot.api.dashboard` SDK. Action
registration is valid only during `initialize()`; registration from the
constructor fails. AstrBot wraps initialization in a staging transaction, so a
manifest, Action, or handler validation failure cannot expose a partially
registered extension.

```python
from pydantic import BaseModel, ConfigDict

from astrbot.api.dashboard import (
    DashboardActionContext,
    DashboardJsonAction,
)
from astrbot.api.star import Star


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsResult(BaseModel):
    message: str


class DashboardExtensionExample(Star):
    async def initialize(self) -> None:
        registrar = self.context.dashboard_extensions.for_plugin(self)
        registrar.register_json(
            DashboardJsonAction(
                name="settings.read",
                input_model=SettingsRequest,
                output_model=SettingsResult,
                description="Read the example Dashboard settings",
            ),
            self.read_settings,
        )

    async def read_settings(
        self,
        _payload: SettingsRequest,
        _context: DashboardActionContext,
    ) -> SettingsResult:
        return SettingsResult(message="Dashboard Extension Protocol v1 is ready")
```

An input or upload fields model must be a Pydantic v2 `BaseModel` with
`ConfigDict(extra="forbid")`. An output must also be a `BaseModel`; AstrBot
validates the returned value against the declared output model. Do not return a
`Response`, redirect, response headers, or arbitrary status code.

### Action Kinds

| Kind               | Registration      | Handler signature                      | Page SDK                    |
| ------------------ | ----------------- | -------------------------------------- | --------------------------- |
| JSON               | `register_json`   | `(payload, context) -> BaseModel`      | `invoke()`                  |
| Single-file upload | `register_upload` | `(file, fields, context) -> BaseModel` | `upload()`                  |
| File read          | `register_file`   | `(payload, context) -> DashboardFile`  | `readFile()` / `download()` |

`DashboardJsonAction` declares `input_model` and `output_model`.
`DashboardUploadAction` declares `fields_model`, `output_model`,
`max_file_bytes`, `allowed_content_types`, and `allowed_extensions`. The upload
limit must be between 1 byte and 64 MiB. MIME values must be exact lowercase
values without wildcards or parameters. Extensions must be lowercase `.ext`
values.

`DashboardFileAction` declares `input_model`, `disposition`, `max_file_bytes`,
and `allowed_content_types`. Use `disposition="inline"` with `readFile()` and a
maximum of 32 MiB. Use `disposition="attachment"` with `download()` and a
maximum of 128 MiB. The handler returns:

```python
from pathlib import Path

from astrbot.api.dashboard import DashboardFile

return DashboardFile(
    relative_path=Path("exports/result.json"),
    filename="result.json",
    content_type="application/json",
)
```

`relative_path` must identify an existing regular file under the plugin root.
It cannot be absolute or contain traversal. The host rechecks containment, file
size, and MIME, then streams the file through a short-lived owner-bound ticket.

Every Action can declare:

- `required_scope`: defaults to `plugin`; allowed values are `bot`, `provider`,
  `prompt`, `im`, `config`, `chat`, `kb`, `memory`, `data`, `file`, `plugin`,
  `mcp`, and `skill`.
- `timeout_seconds`: 5–120 seconds, default 30.
- `description`: at most 200 characters.

`DashboardActionContext` exposes `request_id`, `username`, `scopes`,
`extension_id`, `plugin_name`, and `cancellation`. Long-running work should
check `cancellation.cancelled` or await `cancellation.wait()` regularly and
stop promptly after cancellation. For an expected business error whose message
is safe to show, use:

```python
from astrbot.api.dashboard import DashboardActionError

raise DashboardActionError("invalid_palette", "The selected palette is invalid")
```

Other exceptions produce only a generic error for the Page. Never place tokens,
paths, URLs, upload content, or sensitive configuration in exception messages.

A `DashboardUploadedFile` is valid only for the handler call. It exposes
`filename`, `content_type`, `size`, and asynchronous `iter_chunks()`. If the
content must survive the call, copy it in chunks to plugin-owned storage before
the handler returns.

## Write the Page Module

The fixed Shell installs `window.AstrBotPluginPage` before running the module.
Await `ready()` before building UI or invoking an Action:

```js
const api = window.AstrBotPluginPage;
const context = await api.ready();

const button = document.createElement('button');
button.textContent = `Read settings for ${context.plugin_name}`;
button.addEventListener('click', async () => {
  try {
    const result = await api.invoke('settings.read', {});
    console.log(result.message);
  } catch (error) {
    console.error(error.code, error.message, error.request_id);
  }
});
document.body.append(button);
```

The browser SDK provides:

- `ready()`: returns the initial context.
- `invoke(actionId, payload)`: invokes a JSON Action.
- `upload(actionId, file, fields)`: invokes a single-file upload Action.
- `readFile(actionId, payload)`: reads an `inline` file and returns an object
  containing `bytes`, `filename`, `contentType`, `size`, and `disposition`.
- `download(actionId, payload)`: starts a streamed `attachment` download.
- `createObjectURL(file)` / `revokeObjectURL(url)`: creates and revokes an
  SDK-tracked object URL for a `readFile()` result.
- `onContext(listener)`: subscribes to context changes such as theme and locale
  and returns an unsubscribe function.
- `dispose()`: closes the current Page instance and rejects pending requests.

The context contains `protocol_version`, `extension_id`, `plugin_name`,
`page_id`, `instance_id`, `plugin_generation`, `expires_at`, `locale`, `theme`,
and `capabilities`. Treat only the IDs in `capabilities.actions` as available to
the current Page.

A Page may hold at most 64 pending requests, and a Bridge JSON message is at
most 256 KiB. The Host manages timeout, cancellation, generation changes,
logout, reload, disable, uninstall, and route departure. A rejected Promise
receives an `Error` with `code`, `retryable`, and an optional `request_id`.

An object URL created with `createObjectURL()` is revoked explicitly or when the
Page is disposed. URLs created directly with the browser
`URL.createObjectURL()` API are not tracked by the SDK and remain the plugin's
responsibility.

## Security and Lifecycle Boundaries

- The iframe is fixed to `sandbox="allow-scripts"`. Do not request
  `allow-same-origin`, `allow-forms`, `allow-popups`, or `allow-downloads`.
- CSP permits only the current content-addressed bundle and fixed SDK. It blocks
  external scripts, fetch/beacon/WebSocket calls, frames, objects, and form
  submissions.
- Do not use `fetch()` to call Dashboard APIs. Model every privileged operation
  as a structured Action.
- Never put user data, tokens, session/ticket handles, or absolute file paths in
  static bundles, URLs, DOM logs, or Action errors.
- Plugin reload, disable, uninstall, and AstrBot shutdown invalidate Actions,
  Page sessions, and file tickets from the old generation. A Page must allow the
  Host to dispose it at any time and must not rely on cross-generation state.
- Python plugin code still runs in the AstrBot process. The iframe is a browser
  isolation boundary, not a Python sandbox.

## Local Verification

After changing Page assets, regenerate `assets.v1.json` and reload the plugin
from the Dashboard. During development, verify at least:

1. The metadata capability, extension ID, Page/Action IDs, and asset digests
   pass plugin loading.
2. The Page can invoke only allowlisted Actions.
3. JSON input and output pass their Pydantic schemas.
4. Upload MIME, extension, and actual content match the declaration.
5. Inline object URLs are revoked and attachments stream successfully.
6. The old Page cannot keep invoking after reload, disable, uninstall, or
   logout.

This protocol is a breaking contract. It provides no compatibility layer for
legacy Page metadata, arbitrary HTTP proxies, or the legacy plugin runtime API. Existing
plugins must migrate directly to the v1 manifest, Actions, and Page SDK
described in this guide.
