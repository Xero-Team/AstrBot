# Diagnostics

This page provides a general checklist for diagnosing AstrBot issues. When something goes wrong, first identify which stage is affected, then collect the relevant logs.

## Common Issue Types

- Startup failures: the process exits after startup, WebUI is unavailable, or database/config loading fails.
- Platform connection issues: QQ, OneBot, Telegram, WeCom, or other platforms cannot connect, receive messages, or send messages.
- Model request issues: replies take too long, requests time out, 429/5xx errors appear, or the proxy/API base is unavailable.
- Plugin or MCP issues: enabling fails, tool calls fail, dependencies fail to install, or an MCP service does not respond.
- Slow tasks or abnormal CPU usage: messages, proactive tasks, or scheduled tasks start but continue much later; or the process keeps unusually high CPU usage.

## Logs to Check First

Start with the main AstrBot log:

```text
data/logs/astrbot.log
```

For Docker deployments, also check container logs:

```bash
docker logs <container-name>
```

If the issue involves slow tasks, abnormal CPU usage, or multiple sessions becoming slow at the same time, also check the event loop diagnostic logs:

```text
data/logs/event_loop_watchdog.log
data/logs/event_loop_watchdog.log.1
```

`event_loop_watchdog.log` rotates to `.1` after it exceeds 1 MB.

## General Checklist

1. Identify the time of the incident, then collect logs from 1 to 3 minutes before and after it.
2. Check the scope: all platforms, one platform, one group, one user, or one plugin.
3. For slow or missing model replies, check the model provider status, API key, API base, proxy, network, request timeout, and retry logs.
4. For plugin or MCP issues, disable recently installed or updated plugins first, then check plugin dependencies and MCP service logs.
5. For platform messaging issues, check whether the adapter is connected, platform-side settings are correct, and callback/WebSocket URLs are reachable.
6. For slow tasks or abnormal CPU usage, see "Event Loop Lag Diagnostics" below.

## Event Loop Lag Diagnostics

The event loop schedules messages, plugins, scheduled jobs, model requests, and tool calls. If it is blocked by synchronous code, many features can look delayed at once.

Common symptoms:

- Logs stop after `ready to request llm provider`, `acquired session lock for llm request`, or a tool result, then continue much later.
- A proactive or scheduled task starts, but one step in the middle takes a long time to continue.
- Multiple platforms or sessions become slow at the same time.
- CPU usage stays at 100%, or CPU usage is low but requests keep waiting for an external service.

If the main log contains the following entry, the event loop experienced visible scheduling delay:

```text
Event loop lag detected: 18.432s (threshold 15.000s).
```

If the event loop does not resume for a long time, AstrBot writes Python thread stacks to:

```text
data/logs/event_loop_watchdog.log
```

When reading this file, focus on the top frames. Useful clues often include plugin functions, platform adapters, MCP tools, synchronous network requests, `time.sleep()`, `subprocess.run()`, or CPU-heavy loops.

Watchdog dumps redact recognized tokens, secret fields, and URLs, but keep file paths so the stall location stays readable. They do not dump local variable values. Cookies, private chat content, and custom secrets in source lines are not guaranteed to be stripped. Review the file before sharing.

## What to Collect

When diagnosing a problem, collect as much of the following as possible:

- Approximate time of the incident and timezone.
- AstrBot version, deployment method (Docker, manual deployment, desktop client, etc.), and operating system.
- Trigger path: startup, normal chat, group chat, platform callback, scheduled task, MCP tool, plugin feature, etc.
- Scope: all sessions, one platform, one group, one user, or one plugin.
- Logs from `data/logs/astrbot.log` for 1 to 3 minutes around the incident.
- If the issue involves lag or abnormal CPU usage, include `data/logs/event_loop_watchdog.log` and `data/logs/event_loop_watchdog.log.1`.
- For Docker deployments, include the matching `docker logs` output.
- Installed plugin list, and whether the issue still happens after disabling third-party plugins.

Stack traces in `astrbot.log` no longer include loguru local-variable dumps, and absolute paths in frames are replaced with `[REDACTED_PATH]`. The sink only redacts recognized patterns (secret fields, Bearer tokens, URLs, and absolute paths). Cookies, private chat content, and custom secrets are not guaranteed to be stripped.

Before sharing logs, still review and redact API keys, tokens, cookies, private chat content, and other sensitive information.

## Export a diagnostics bundle

When you need to submit logs, prefer `Export diagnostics` in the Dashboard over collecting files by hand. The entry points are **More Features → Data and Logs → Logs** and **Settings → Maintenance → Diagnostics**. Both use the same export. Only authenticated dashboard administrators can download a bundle; developer API keys are not accepted.

The archive contains disk and rotated logs, configured custom logs, cached logs, available trace history, configuration and routes, plugin status, environment details, and a manifest. `Redact credentials (recommended)` is enabled by default, masking recognized credentials and replacing public IP addresses with consistent aliases. Unchecking it keeps original sensitive values and adds `raw` to the filename; share that only privately with someone you trust. Export a preset range of the last hour, 12 hours, day, or 3 days, or choose custom start and end times.

See [Logs](/en/use/webui#logs) for the full contents and limits. Review chat content, cookies, and custom secrets before sharing.

## Operational Metrics and Tracing

AstrBot can expose operational metrics and OpenTelemetry traces. Both are off by
default so the standard install is unchanged. Configure them in
`data/cmd_config.json`:

```json
"observability": {
  "enable": false,
  "metrics_enable": false,
  "tracing_enable": false,
  "service_name": "astrbot"
}
```

- `enable` is the master switch. The other options only take effect when it is
  true.
- `metrics_enable` serves Prometheus text metrics at `GET /metrics` on the
  WebUI port. The endpoint is unauthenticated and returns `404` when disabled,
  so only expose it on a trusted network or behind a reverse proxy.
- `tracing_enable` emits spans through the OpenTelemetry API for the message
  pipeline and each agent run. AstrBot does not bundle an exporter; install and
  configure an OpenTelemetry SDK, or start the process with
  `opentelemetry-instrument`, to export the spans. `service_name` sets the
  reported service name.

The metrics endpoint reports:

- `astrbot_events_received_total{platform}` and `astrbot_events_processed_total`.
- `astrbot_event_bus_backlog` and `astrbot_webchat_queue_depth` gauges.
- `astrbot_agent_steps_total` and `astrbot_llm_calls_total{provider}`.
- `astrbot_llm_tokens_total{provider,type}`.
- `astrbot_llm_time_to_first_token_seconds` and
  `astrbot_llm_call_duration_seconds` histograms.
