# Authorization

AstrBot splits Dashboard login, IM session management, and high-risk actions. Making a group member an "admin" does not let them sign in to WebUI and does not make them a global operator.

Open **More → Authorization** under the sidebar's **More** group (`/authorization`). The developer model is in [Architecture](/en/dev/architecture#unified-authorization). TOTP and login stay in [WebUI](./webui#two-factor-authentication).

## Three identities

| Identity               | Source                                                                                              | What it can do                                                                           |
| ---------------------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Dashboard account      | Bootstrap `root` on first start (username is usually `astrbot`), plus accounts created on this page | Sign in to WebUI. `root` / `operator` bind only to real Dashboard accounts               |
| IM direct-message peer | Runtime fact `private_session`, not a Dashboard binding                                             | `session_owner` of **that DM only**, so `/conversation reset` works without extra grants |
| `/admin grant`         | A binding on the current session                                                                    | Current-session `session_admin` only. Never a global operator                            |

A username never implies `root`. Control-plane identity comes from the account table and role bindings.

## Fixed roles

| Role                | Scope                     | Typical use                                 |
| ------------------- | ------------------------- | ------------------------------------------- |
| `root`              | Global control plane      | Accounts, restart, pip install              |
| `operator`          | Global control plane      | Config, providers, plugins, data ops        |
| `instance_operator` | One configuration profile | Management actions for that profile         |
| `session_owner`     | Current group or DM       | Session management, in-session model choice |
| `session_admin`     | Current session           | Limited management such as stopping a task  |
| `member`            | Current session           | Ordinary chat                               |
| `guest`             | Unauthenticated           | Anonymous WebChat                           |

A current-session owner may grant or revoke only that session's `session_admin` / `member`. They cannot delegate owner. Platform owner/admin facts have a TTL, decay after expiry, and are never written as global bindings.

## What the page does

Three tabs:

1. **Bindings**: list, grant, and revoke role bindings. Filter by subject, role, and scope.
2. **Accounts**: create, edit, and disable Dashboard accounts.
3. **Audit**: redacted authorization decisions.

Account CRUD, granting `root` / `operator`, and disabling accounts require a current `root` binding plus a one-time password or TOTP step-up. The last `root` cannot be removed.

## Granting access in a group

1. Send `/session info` in the target group and copy the user ID (and group ID if needed).
2. The current session owner runs `/admin grant <user-id>`, or grants `session_admin` on this page.
3. `/admin list` shows bindings visible in this session; `/admin revoke <user-id>` removes one.

All three subcommands need `identity.manage`. See [Built-in commands](./command#session-administrators).

Group `/conversation reset` and similar management commands need `session_admin` or higher. A DM peer is already `session_owner` and does not need a pre-bound `session_admin`.

Profiles can bind separately to platforms, groups, or DMs. Editing `default` may not change the current session. See [Configuration profiles](./config-profiles).

## Step-up

These actions prompt for the current password or TOTP. The proof is single-use for that operation, never placed in a URL, and never reused:

- Install a plugin
- Write credentials
- Export all conversations
- pip install
- Restart

Conversation export requires the exact `conversation:export` resource and `data.export_all`. A generic `data` API key is denied. Backup downloads use an authenticated blob request and never put a Dashboard JWT in the query string.

High-risk tools in ChatUI (local shell, file write, browser, and similar) use a separate step-up that covers only the current WebChat session. See [WebUI](./webui#high-risk-tools-in-chatui). It does not turn an IM user into a global operator and does not authorize account changes, plugin installs, or restarts.

## Common misconfigurations

1. After `/admin grant`, expecting the peer to log into WebUI.
2. Treating Dashboard `operator` as a group-admin switch.
3. Granting in group A and expecting the same binding in group B or another profile.
4. Treating anonymous WebChat or an API key as Dashboard `root`.
