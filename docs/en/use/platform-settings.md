# Platform handling

**Config → Platform** and **Ext.** hold send/receive behavior shared by every messaging platform. These run **after** the [wake check](./group-wake). A policy-admitted message can still be dropped by the unlisted-session or unlisted-sender policy, the unwritten session/LLM default, a rate limit, or a content-safety check.

Open **Config → Platform**. Segmented replies live under **Ext.** Fields belong to the current profile. See [Configuration profiles](./config-profiles).

## Unlisted sessions and senders

| Field                         | Default | Notes                                                                                       |
| ----------------------------- | ------- | ------------------------------------------------------------------------------------------- |
| `admission.unlisted_sessions` | `allow` | `allow` admits sessions with no overlay; `deny` admits only listed groups or DMs            |
| `admission.unlisted_senders`  | `allow` | `allow` admits senders with no overlay; `deny` admits only IM subjects that have an overlay |

The default is `allow`: new groups and DMs pass this stage. They still stay silent until `/bot enable` then `/llm enable`, because unwritten session, LLM, and TTS overlays default off. After you switch to `deny`, only sessions that already have an overlay on the canonical session key pass this stage. Overlays come from IM `/bot`, `/llm`, and Dashboard [custom rules](./custom-rules) writing `llm_enabled` / `session_enabled` / `session_blocked`.

Group admission uses the canonical session key (`session:{platform instance}:group:{group id}`), not a unique-session rewritten UMO. Direct messages use `session:{platform instance}:private:{peer id}`. Sender overlays live on `im:{platform instance}:{bot account}:{sender id}` and apply instance-wide. WebChat, OneBot `notice` / `request`, and senders with `provider.manage` on the current instance skip this stage. The default is `unlisted_senders=allow`: senders with no overlay still pass. After you switch to `deny`, only senders with a written `blocked` or `llm_enabled` overlay are listed. The Sender target on Dashboard [custom rules](./custom-rules) and `/user block`, `/user unblock`, and `/user llm on|off` write the same sender overlay. Any written `blocked` or `llm_enabled` value lists that sender.

`id_whitelist`, `enable_id_white_list`, and `wl_ignore_admin_*` are gone. Dashboard writes that include them fail. This fork does not convert them on load: delete `data/cmd_config.json` (and any `data/config/abconf_*.json`), start from the current defaults, and configure `admission.unlisted_sessions` directly.

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

Off by default. Splits non-streaming results. Can be limited to LLM results. Interval is random or a log of character count. `forward_threshold` (default 1500 characters) currently applies only to the OneBot `aiocqhttp` adapter and turns long replies into forward nodes; support on other platforms depends on the adapter.

Streaming replies, and groups with sender concurrency, do not use this splitter.

## Text to image

`t2i.enable` is off by default. Past `t2i.word_threshold` (default 150 characters), long text can be rendered as an image. Templates and CJK fonts live under **Settings**; the font must actually be installed in the container. See [FAQ](/en/faq#cjk-text-is-garbled-in-t2i-output).

## Other common fields

- **Reply prefix / mention sender / quote original**: adapter-dependent.
- **Ignore the bot's own messages**: some platforms re-deliver the bot's messages from other clients.
- **Reply on missing permission**: whether to tell the user a command was denied.
- **Wait after a prefix-only message**: gated by `empty_mention_waiting`. See [When the bot replies in groups](./group-wake#prefix-only-messages).

Pre-ack emoji for Lark / Telegram / Discord sit under Other, per platform.
