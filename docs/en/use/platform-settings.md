# Platform handling

**Config → Platform** and **Ext.** hold send/receive behavior shared by every messaging platform. These run **after** the [wake check](./group-wake). A policy-admitted message can still be dropped by an allowlist, rate limit, or content-safety check.

Open **Config → Platform**. Segmented replies live under **Ext.** Fields belong to the current profile. See [Configuration profiles](./config-profiles).

## Allowlist

| Field                                                    | Default | Notes                                                    |
| -------------------------------------------------------- | ------- | -------------------------------------------------------- |
| `enable_id_white_list`                                   | On      | Master switch                                            |
| `id_whitelist`                                           | Empty   | An empty list means **no restriction** (every ID passes) |
| `id_whitelist_log`                                       | On      | INFO log on reject                                       |
| `wl_ignore_admin_on_group` / `wl_ignore_admin_on_friend` | On      | Whether admin messages bypass the list                   |

The allowlist only blocks when the switch is on **and** the list is non-empty. Use `/session info` for IDs. With [isolated sessions](./group-wake#isolated-sessions) on, that command also prints the group ID.

Admin bypass follows session authorization, not Dashboard `root`. See [Authorization](./authorization) before widening bypasses.

## Rate limit

Default: 30 messages per 60 seconds. Over the cap:

- `stall` (default): wait
- `discard`: drop

Counts are per session. Isolated sessions give each member their own counter.

## Content safety

Built-in keyword checks are on by default. You can add extra regex keywords. Optional Baidu moderation requires installing `baidu-aip` yourself. `also_use_in_response` also scans model output.

Blocked messages never reach the LLM. Content safety is not a wake switch.

## Inbound turn coalescing

`inbound_coalesce.enable` is off by default. When on, consecutive private LLM messages merge into one turn inside a bounded window. The current implementation **does not merge group chat**.

| Field               | Role                                                    |
| ------------------- | ------------------------------------------------------- |
| `wait_seconds`      | Quiet time that ends a turn                             |
| `max_total_seconds` | Window lifetime; new fragments do not extend it forever |
| `max_typing_wait`   | Guard timeout if typing signals are lost                |

Later fragments do not need to repeat the LLM prefix. A command discards the buffered turn. NapCat `input_status` only pauses or resumes the window and does not enter the message pipeline.

## Segmented replies

Off by default. Splits non-streaming results. Can be limited to LLM results. Interval is random or a log of character count. On platforms that support forwards, `forward_threshold` (default 1500 characters) sends long replies as forwards.

Streaming replies, and groups with sender concurrency, do not use this splitter.

## Text to image

`t2i` is off by default. Past `t2i_word_threshold` (default 150 characters), long text can be rendered as an image. Templates and CJK fonts live under **Settings**; the font must actually be installed in the container. See [FAQ](/en/faq#cjk-text-is-garbled-in-t2i-output).

## Other common fields

- **Reply prefix / mention sender / quote original**: adapter-dependent.
- **Ignore the bot's own messages**: some platforms re-deliver the bot's messages from other clients.
- **Ignore @ everyone**: when on, @ everyone is no longer an LLM wake reason.
- **Reply on missing permission**: whether to tell the user a command was denied.
- **Wait after a mention-only message**: see [When the bot replies in groups](./group-wake#mention-only-messages).

Pre-ack emoji for Lark / Telegram / Discord sit under Other, per platform.
