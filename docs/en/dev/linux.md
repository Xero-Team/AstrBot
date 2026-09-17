# Linux Development

This is the supported source-development workflow for Linux. It uses Python
3.14.6, `uv`, Node.js 26, and pnpm. The commands below do
not require PowerShell.

## Prerequisites

Install the base tools with your distribution package manager, then install
Python 3.14.6, `uv`, and Node.js 26 using the method your distribution
recommends. CI uses Node.js 26.5.0; `make doctor` accepts compatible Node 26
releases.

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install git make curl shellcheck shfmt hadolint
```

Fedora:

```bash
sudo dnf install git make curl ShellCheck shfmt hadolint
```

Arch Linux:

```bash
sudo pacman -S git make curl shellcheck shfmt hadolint
```

If a distribution does not package `hadolint`, use its official release binary.
Docker itself is optional unless you are working on container deployment.

## First setup

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

`make bootstrap` creates the locked Python environment, installs the root
formatting toolchain, and installs dashboard dependencies. It never installs
system packages; resolve missing tools reported by `make doctor` first.

`make format` runs the same preflight before changing files. If it reports that
Node.js is missing, install or activate Node 26 in the current shell, verify
`node --version`, then rerun the command. Local `node_modules/.bin` tools need
the `node` executable on `PATH` because their launchers use `/usr/bin/env node`.

## Daily workflow

```bash
make dev             # backend on 6185 and Vite dashboard on 3000
make status           # health check both processes
make stop             # stop both process groups
make perf             # sample a running backend (Linux only)
make stop-perf        # stop DURATION=0 sampling and write the flame graph
make check            # strict Linux/macOS source checks
make test             # full pytest suite
make test-blocking    # blocking pytest profile
make pr-test-full     # lint, tests, smoke test, and dashboard build
```

Backend output is written to `backend_run.log` and `backend_run.err.log`.
Dashboard output is written to `frontend_run.log` and
`frontend_run.err.log`. PID files live in `.make/`. `make clean` stops the
development servers and removes generated local state; it does not remove
`data/config` or `data/plugins`.

## Performance sampling {#performance-sampling}

`make perf` is Linux-only. It attaches to an already-running backend and does
not start or wrap `make dev` / `make run`. The default capture is a 30-second
CPU flame graph under `.tmp/perf/`.

```bash
make run                   # or make dev
make perf                  # 30s CPU flame graph
make perf MODE=idle        # include await / I/O waits
make perf DURATION=0       # background sidecar at 10Hz until make stop-perf / make stop
make perf DURATION=0 RATE=5
make perf MODE=mem DURATION=60
```

`DURATION=0` returns to the shell like `make run`: CPU/idle keep a background
`py-spy` sampler, and `MODE=mem` leaves the tracker in the backend process.
The wide stacks in the SVG are the hot call paths; this is sampling, not a
per-call counter. Default `MODE=cpu` records on-CPU Python stacks only;
`MODE=idle` also counts await / I/O waits. Use CPU sampling in production.
Unlimited `MODE=mem` is much heavier and omits `--native`. Stop the sampler
with `make stop-perf` before stopping the backend so the flame graph is
written. `make stop` stops the sidecar first.

`py-spy` defaults to 100Hz. Background captures (`DURATION=0`) use 10Hz and
`--nonblocking` so ptrace does not leave the backend in tracing stop (WebUI /
API would time out). If it still falls `behind in sampling`, lower `RATE` to 5
or 1. Do not use `MODE=idle DURATION=0` as a production sidecar: idle walks
sleeping threads and stays heavier even with non-blocking samples.

`MODE=cpu` and `MODE=idle` call `py-spy` through `uvx` and do not add it to the
project lockfile. `MODE=mem` requires `import memray` to succeed in the backend
virtualenv, because attach injects that import into the target process. Install
it once with `uv sync --group perf --locked`. The `perf` group is not part of
`make bootstrap`.

Attaching to a running process usually needs ptrace. If permission is denied,
the script prints how to relax `/proc/sys/kernel/yama/ptrace_scope`. Containers
may also need `cap_add: SYS_PTRACE`. Do not rerun `make perf` with `sudo`. The

target fails immediately on Windows and macOS.

`make check-all-platforms` additionally validates the PowerShell scripts. It
is only needed when changing those scripts and requires `pwsh` plus
PSScriptAnalyzer; CI always validates that surface separately.

## NapCat event model generation

The NapCat generator is native Python on Linux and Windows. It needs `git`,
`pnpm`, `uv`, and network access to clone the NapCat repository and download
the schema generator.

```bash
make napcat-codegen
make napcat-test
```

Generated intermediate files are kept under `.tmp/napcat-schema`; the checked
in model is `astrbot/core/platform/sources/napcat/generated/ob11_events.py`.
