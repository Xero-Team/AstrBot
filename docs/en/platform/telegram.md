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

When Telegram command registration is enabled, AstrBot synchronizes enabled built-in and extension-plugin root commands, root groups, and root aliases to Telegram's native command menu; entries that violate Telegram's naming constraints are skipped. Telegram accepts at most 100 menu entries, so AstrBot prioritizes primary commands before aliases and sorts each group by name, then logs how many local entries were omitted. Telegram menus do not support subcommands or named parameters, so selecting a group such as `/persona`, `/provider`, or `/plugin` still leaves its subcommand and arguments to Orbit Command Syntax.

Plugin load, unload, reload, enable, and disable operations immediately request a menu refresh, as do command enablement, rename, and alias changes from Dashboard. Non-empty replacements are written directly so a failed request does not clear the existing menu; an empty command set clears stale commands. The periodic refresh always reconciles the selected menu, including after network failures or external changes to the Telegram menu.

## Mentions

Text and media captions preserve emoji, whitespace, and other users' mentions. Mentions of this bot become mention components and are removed from the plain text, including repeated mentions. Invalid entity ranges are ignored without deleting text. Mentions alone do not enable group LLM replies; the configured group access, reply-to-bot, and continuation rules still apply.

## Media Albums

Telegram media albums are collected independently of the native command menu. Disabling command registration or periodic menu refresh does not disable album delivery. AstrBot waits briefly after each album item to collect the rest of the album, but always starts processing at the configured maximum collection deadline even if more items continue to arrive.

To keep the adapter responsive, an instance accepts at most 128 collecting or processing albums at once and at most 10 distinct items in each album. New albums or extra items over those limits are discarded. Processing is limited to 60 seconds; incomplete albums are also discarded when the Telegram adapter restarts or stops. These are internal safety limits, not Dashboard settings.

## Streaming Output

The Telegram platform supports streaming output. Enable the "Streaming Output" switch in "AI Configuration" -> "Other Settings".

### Private Chat Streaming

In private chats, AstrBot uses the `sendMessageDraft` API (added in Telegram Bot API v9.3) for streaming output. This displays a "typing" draft preview animation in the chat interface, creating a more natural "typewriter" effect. It avoids issues with the traditional approach such as message flickering, push notification interference, and API edit frequency limits.

### Group Chat Streaming

In group chats, since the `sendMessageDraft` API only supports private chats, AstrBot automatically falls back to the traditional `send_message` + `edit_message_text` approach. Responses longer than Telegram's 4096-character text limit are finalized and sent as ordered messages. If a segment submission fails, AstrBot stops sending and records the accepted prefix, failed fragment, and any remaining buffered text in the delivery receipt. Buffered text is not automatically retried. If the optional Markdown formatting step fails, the accepted plain-text segment remains available and streaming continues.

## Topic Sessions and Routing

When Telegram private-chat topics are enabled, each topic in the same private chat uses an independent AstrBot session. A regular private chat still uses its chat ID; a topic session uses `<chat_id>#<message_thread_id>` as its internal route identity, so replies, proactive messages, typing status, and streaming output return to the originating topic. Proactive sends also preserve the topic when given the complete stored target for that session.

Telegram group topics remain isolated by topic. A group's General topic keeps the parent-group route, and AstrBot does not pass General topic thread `1` explicitly to the Telegram API. A private General topic keeps a distinct logical session identity but likewise omits explicit thread `1` from API calls.

:::warning
`sendMessageDraft` requires `python-telegram-bot>=22.6`.
:::
