# Acceptance-test lab

Use this target for live Dashboard checks when relevant to the audit scope
and the user has not selected another host, origin, or account. **Acceptance-test only. Never production.**

| Field    | Value                                                                         |
| -------- | ----------------------------------------------------------------------------- |
| Target   | Current-branch process in this worktree, not `soulter/astrbot` or another SHA |
| Origin   | `http://127.0.0.1:6185`                                                       |
| Username | `astrbot`                                                                     |
| Password | `Astrbot123`                                                                  |
| Use      | Live Dashboard login, operator-path evidence, optional CWV/axe                |

If `127.0.0.1:6185` is already bound, confirm it is this worktree
(`make status`, startup log, or process cwd) before logging in. If it
is down, start this checkout (`make dev` unless the user asked for
`make run`) and record the command plus HEAD SHA in `manifest.json`.
A SHA/bind mismatch is an inventory assumption, not a silent login.

Do not write the lab password into `REPORT.md`, `CHAPTER.md`, Issues, or
changelogs. Cite "acceptance-test lab in `references/lab.md`". Do not copy
this password into product `default.py`, docs, Compose, or images.
Shipped first-start remains: username `astrbot`, random password in the
startup log (`AGENTS.md`). Finding `Astrbot123` hardcoded as a product
default is a separate insecure-default finding, not this lab convention.
