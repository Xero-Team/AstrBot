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

## Update Ingestion

Whenever polling starts or its client is rebuilt, AstrBot explicitly subscribes to `message`, `channel_post`, and `business_message`. It does not inherit a subscription left on Telegram's servers.

| Telegram Update field                                              | Handling                                                                                                                                                                                                          |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `message`                                                          | Ingest private, group, and topic messages using the content types above and the existing album handling.                                                                                                          |
| `channel_post`                                                     | Ingest as a group message, preserving the channel and topic route. Use `sender_chat` as the sender instead of an anonymous sender's compatibility user. Group access rules still decide whether to run the LLM.   |
| `business_message`                                                 | Ingest incoming customer messages in private chats with a `business_connection_id`. Ignore account-owner sends, outgoing bot messages marked with `sender_business_bot`, and incomplete routes.                   |
| `edited_message`, `edited_channel_post`, `edited_business_message` | Do not subscribe, create a new message event, or change stored context. Send a new message to run a command or agent again.                                                                                       |
| `guest_message`                                                    | Not ingested. Guest Bot messages require the dedicated `answerGuestQuery` / `InlineQueryResult` reply protocol and cannot be answered through ordinary chat sends.                                                |
| Other updates                                                      | Not subscribed to or converted into chat messages. This includes button callbacks, member changes, reactions, polls, payments, Business connection changes and deletion notices, boosts, and managed bot updates. |

The handler accepts only the three supported message variants even if unacknowledged updates from an older subscription still arrive. Each adapter retains the latest 4096 admitted Update IDs, so repeated delivery does not execute a command or agent again while its ID remains cached. The cache survives polling-client rebuilds but is not persisted across process restarts. Edited updates are always ignored.

### Business Sessions and Replies

A Business chat is independent of an ordinary Bot chat with the same chat ID. AstrBot uses `business:<percent-encoded connection ID>:<chat_id>` as its Business route, appending `#<message_thread_id>` for topics. Save the complete session target for proactive sends: the connection, chat, and topic are restored, and albums are isolated by that route too.

Text, media, typing status, and streaming edits carry the original `business_connection_id`. Business private chats stream by sending and editing messages because `sendMessageDraft` cannot address a Business connection. Message reactions are likewise skipped because their API cannot carry that identity. Replies and proactive sends remain subject to Telegram's connection permissions and requirement for an incoming message within the last 24 hours.

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

## Media Albums

Telegram media albums are collected independently of the native command menu. Disabling command registration or periodic menu refresh does not disable album delivery. AstrBot waits briefly after each album item to collect the rest of the album, but always starts processing at the configured maximum collection deadline even if more items continue to arrive.

To keep the adapter responsive, an instance accepts at most 128 collecting or processing albums at once and at most 10 distinct items in each album. New albums or extra items over those limits are discarded. Processing is limited to 60 seconds; incomplete albums are also discarded when the Telegram adapter restarts or stops. These are internal safety limits, not Dashboard settings.

## Streaming Output

The Telegram platform supports streaming output. Enable the "Streaming Output" switch in "AI Configuration" -> "Other Settings".

### Private Chat Streaming

In ordinary Bot private chats, AstrBot uses the `sendMessageDraft` API (added in Telegram Bot API v9.3) for streaming output. This displays a "typing" draft preview animation in the chat interface, creating a more natural "typewriter" effect. It avoids issues with the traditional approach such as message flickering, push notification interference, and API edit frequency limits.

### Group Chat Streaming

In group chats, since the `sendMessageDraft` API only supports private chats, AstrBot automatically falls back to the traditional `send_message` + `edit_message_text` approach. Responses longer than Telegram's 4096-character text limit are finalized and sent as ordered messages. If a segment submission fails, AstrBot stops sending and records the accepted prefix, failed fragment, and any remaining buffered text in the delivery receipt. Buffered text is not automatically retried. If the optional Markdown formatting step fails, the accepted plain-text segment remains available and streaming continues.

## Topic Sessions and Routing

When Telegram private-chat topics are enabled, each topic in the same private chat uses an independent AstrBot session. A regular private chat still uses its chat ID; a topic session uses `<chat_id>#<message_thread_id>` as its internal route identity, so replies, proactive messages, typing status, and streaming output return to the originating topic. Proactive sends also preserve the topic when given the complete stored target for that session.

Telegram group topics remain isolated by topic. A group's General topic keeps the parent-group route, and AstrBot does not pass General topic thread `1` explicitly to the Telegram API. A private General topic keeps a distinct logical session identity but likewise omits explicit thread `1` from API calls.

:::warning
`sendMessageDraft` requires `python-telegram-bot>=22.6`.
:::
