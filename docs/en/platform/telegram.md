# Connecting to Telegram

## Supported Message Types

| Message Type | Receive Support | Send Support | Notes |
| ------------ | --------------- | ------------ | ----- |
| Text         | Yes             | Yes          |       |
| Image        | Yes             | Yes          |       |
| Voice        | Yes             | Yes          |       |
| Video        | Yes             | Yes          |       |
| File         | Yes             | Yes          |       |

Proactive message push: Supported.

## 1. Create a Telegram Bot

First, open Telegram and search for `BotFather`. Click `Start`, then send `/newbot` and follow the prompts to enter your bot's name and username.

After successful creation, `BotFather` will provide you with a `token`. Please keep it secure.

If you need to use the bot in group chats, you must disable the bot's [Privacy mode](https://core.telegram.org/bots/features#privacy-mode). Send the `/setprivacy` command to `BotFather`, select your bot, and then choose `Disable`.

## 2. Configure AstrBot

1. Enter the AstrBot admin panel
2. Click `Bots` in the left sidebar
3. In the interface on the right, click `+ Create Bot`
4. Select `telegram`

Fill in the configuration fields that appear:

- ID: Enter any value to distinguish between different messaging platform instances.
- Enable: Check this option.
- Bot Token: Your Telegram bot's `token`.

Please ensure your network environment can access Telegram. You may need to configure a proxy using `Configuration -> Other Settings -> HTTP Proxy`.

## Native Command Menu

When Telegram command registration is enabled, AstrBot synchronizes every enabled built-in and extension-plugin root command, root group, and root alias to Telegram's native command menu; entries that violate Telegram's naming constraints are skipped. Telegram menus do not support subcommands or named parameters, so selecting a group such as `/persona`, `/provider`, or `/plugin` still leaves its subcommand and arguments to Orbit Command Syntax.

Plugin load, unload, reload, enable, and disable operations immediately request a menu refresh, as do command enablement, rename, and alias changes from Dashboard. The periodic refresh remains as recovery for network failures or external state changes. When no commands are eligible, AstrBot clears stale commands from the Telegram menu.

## Mentions

Text and media captions preserve emoji, whitespace, and other users' mentions. Mentions of this bot become mention components and are removed from the plain text, including repeated mentions. Invalid entity ranges are ignored without deleting text. Mentions alone do not enable group LLM replies; the configured group access, reply-to-bot, and continuation rules still apply.

## Streaming Output

The Telegram platform supports streaming output. Enable the "Streaming Output" switch in "AI Configuration" -> "Other Settings".

### Private Chat Streaming

In private chats, AstrBot uses the `sendMessageDraft` API (added in Telegram Bot API v9.3) for streaming output. This displays a "typing" draft preview animation in the chat interface, creating a more natural "typewriter" effect. It avoids issues with the traditional approach such as message flickering, push notification interference, and API edit frequency limits.

### Group Chat Streaming

In group chats, since the `sendMessageDraft` API only supports private chats, AstrBot automatically falls back to the traditional `send_message` + `edit_message_text` approach.

:::warning
`sendMessageDraft` requires `python-telegram-bot>=22.6`.
:::
