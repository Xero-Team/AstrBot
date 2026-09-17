# Linux 开发环境

这是 Linux 下受支持的源码开发流程。项目使用 Python 3.14.6、`uv`、Node.js
26 和 pnpm；以下命令不依赖 PowerShell。

## 前置工具

先使用发行版包管理器安装基础工具，再用发行版推荐的方式安装 Python 3.14.6、`uv`
与 Node.js 26。CI 使用 Node.js 26.5.0；`make doctor` 接受兼容的 Node 26
版本。

Ubuntu/Debian：

```bash
sudo apt update
sudo apt install git make curl shellcheck shfmt hadolint
```

Fedora：

```bash
sudo dnf install git make curl ShellCheck shfmt hadolint
```

Arch Linux：

```bash
sudo pacman -S git make curl shellcheck shfmt hadolint
```

若发行版没有打包 `hadolint`，请使用其官方发布的二进制文件。除非需要调试容器部署，
Docker 本身不是开发前置条件。

## 首次安装

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

`make bootstrap` 会按照锁文件创建 Python 环境、安装根目录格式化工具和 Dashboard
依赖；它不会安装系统软件包，应先解决 `make doctor` 报出的缺失工具。

`make format` 在修改文件前也会执行同样的预检。若提示找不到 Node.js，请在当前
shell 中安装或启用 Node 26，确认 `node --version` 可用后再执行。根目录
`node_modules/.bin` 中的本地工具使用 `/usr/bin/env node` 启动，因此 `node`
必须在 `PATH` 中。

## 日常开发

```bash
make dev             # 后端 6185，Vite Dashboard 3000
make status          # 检查两个进程
make stop            # 停止两个进程组
make perf            # 对已运行的后端采样（仅 Linux）
make stop-perf       # 停止 DURATION=0 后台采样并写火焰图
make check           # 严格执行 Linux/macOS 源码检查
make test            # 执行全量 pytest
make test-blocking   # 执行 blocking pytest
make pr-test-full    # lint、测试、启动 smoke test 与 Dashboard 构建
```

后端日志为 `backend_run.log`、`backend_run.err.log`；Dashboard 日志为
`frontend_run.log`、`frontend_run.err.log`。PID 文件放在 `.make/`。
`make clean` 会停止开发进程并清理生成的本地状态，但不会删除 `data/config` 与
`data/plugins`。

## 性能采样 {#performance-sampling}

`make perf` 只在 Linux 上附加到已经在跑的后端，不会启动或包装 `make dev` /
`make run`。默认采 30 秒 CPU 火焰图，产物写在 `.tmp/perf/`。

```bash
make run                   # 或 make dev
make perf                  # 30 秒 CPU 火焰图
make perf MODE=idle        # 把 await / I/O 等待也算进去
make perf DURATION=0       # 后台常驻，默认 10Hz，直到 make stop-perf / make stop
make perf DURATION=0 RATE=5
make perf MODE=mem DURATION=60
```

`DURATION=0` 和 `make run` 一样启动后回到 shell：CPU/idle 用后台 `py-spy` 采样，
`MODE=mem` 把 tracker 留在后端进程里。火焰图里的宽栈就是热点调用；这是采样，不是
每次调用计数。默认 `MODE=cpu` 只采正在跑的 Python 栈；`MODE=idle` 才把 await /
I/O 等待算进去。生产环境用 CPU 采样；无限时长的 `MODE=mem` 开销明显更大，且不会加
`--native`。先 `make stop-perf` 再停后端，火焰图才会写完。`make stop` 会先停采样侧车。

`py-spy` 默认 100Hz。常驻采样（`DURATION=0`）改成 10Hz，并加上 `--nonblocking`，避免
ptrace 把后端停在 tracing stop（WebUI / API 会超时）。若仍出现并加上 `--nonblocking`，避免
ptrace 把后端停在 tracing stop（WebUI / API 会超时）。若仍出现
`behind in sampling`，再把 `RATE` 降到 5 或 1。不要用 `MODE=idle DURATION=0`
当生产常驻：idle 会扫睡眠线程，即使用非阻塞采样也更重。

`MODE=cpu` 和 `MODE=idle` 通过 `uvx` 调用 `py-spy`，不写进项目锁文件。`MODE=mem`
需要后端虚拟环境里能 `import memray`（附加时会在目标进程里 import），先执行一次
`uv sync --group perf --locked`。`perf` 组不进入 `make bootstrap`。

附加已有进程通常需要 ptrace。权限被拒绝时，脚本会提示如何放宽
`/proc/sys/kernel/yama/ptrace_scope`。容器里还可能需要 `cap_add: SYS_PTRACE`。
不要用 `sudo` 跑 `make perf`。Windows 与 macOS 上该目标会直接失败。

`make check-all-platforms` 会额外检查 PowerShell 脚本。只有修改 PS 脚本时才需要；
该目标要求安装 `pwsh` 和 PSScriptAnalyzer，CI 会单独验证它们。

## NapCat 事件模型生成

NapCat 生成流程在 Linux 与 Windows 都使用 Python 原生入口。它需要 `git`、`pnpm`、
`uv`，并需要联网克隆 NapCat 仓库和下载 schema 生成器。

```bash
make napcat-codegen
make napcat-test
```

中间文件位于 `.tmp/napcat-schema`；受版本控制的生成结果为
`astrbot/core/platform/sources/napcat/generated/ob11_events.py`。
