#!/usr/bin/env bash

set -euo pipefail

MODE="${MODE:-cpu}"
DURATION="${DURATION:-30}"
PYSPY_FROM="${ASTRBOT_PERF_PYSPY_FROM:-py-spy>=0.4.2}"

if (($# != 0)); then
  echo "Usage: MODE=cpu|idle|mem DURATION=<seconds> scripts/make_perf.sh" >&2
  echo "Do not pass positional arguments; use make perf MODE=... DURATION=..." >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pid_file="${ASTRBOT_PERF_PID_FILE:-$repo_root/.make/backend.pid}"
output_dir="${ASTRBOT_PERF_OUTPUT_DIR:-$repo_root/.tmp/perf}"
port="${ASTRBOT_DASHBOARD_PORT:-6185}"

usage_error() {
  echo "Usage: MODE=cpu|idle|mem DURATION=<positive seconds> make perf" >&2
  echo "Linux-only sidecar: attaches to a running backend started by make dev or make run." >&2
  exit 2
}

print_ptrace_hint() {
  echo "Permission to inspect the backend process was denied." >&2
  echo "On Linux, attaching usually needs ptrace. Grant it for your user, for example:" >&2
  echo "  echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope" >&2
  echo "Do not rerun this script with sudo." >&2
}

is_permission_error() {
  local text="$1"
  grep -Eiq 'permission denied|ptrace|operation not permitted|sys_ptrace' <<<"$text"
}

pids_listening_on_port() {
  local listen_port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$listen_port" -sTCP:LISTEN 2>/dev/null || true
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | sed -nE "s/.*[:.]${listen_port}[[:space:]].*pid=([0-9]+).*/\\1/p" || true
  elif command -v netstat >/dev/null 2>&1; then
    netstat -ltnp 2>/dev/null | sed -nE "s/.*[:.]${listen_port}[[:space:]].*[[:space:]]([0-9]+)\\/.*/\\1/p" || true
  else
    echo "Unable to inspect port $listen_port: install lsof, iproute2, or net-tools." >&2
    return 1
  fi
}

is_python_pid() {
  local pid="$1"
  local comm exe
  comm="$(tr -d '\0\n' <"/proc/$pid/comm" 2>/dev/null || true)"
  if [[ "$comm" == python* ]]; then
    return 0
  fi
  exe="$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)"
  [[ "$(basename -- "$exe")" == python* ]]
}

python_pid_from() {
  local -a queue=("$1")
  local -A seen=()
  local pid children_file child
  local -a children=()

  while ((${#queue[@]} > 0)); do
    pid="${queue[0]}"
    queue=("${queue[@]:1}")
    [[ -n "${seen[$pid]:-}" ]] && continue
    seen[$pid]=1
    [[ -d "/proc/$pid" ]] || continue
    if is_python_pid "$pid"; then
      printf '%s\n' "$pid"
      return 0
    fi
    children=()
    children_file="/proc/$pid/task/$pid/children"
    if [[ -f "$children_file" ]]; then
      read -r -a children <"$children_file" || true
      for child in "${children[@]}"; do
        [[ "$child" =~ ^[0-9]+$ ]] && queue+=("$child")
      done
    fi
  done
  return 1
}

read_pid_file() {
  local pid
  [[ -f "$pid_file" ]] || return 1
  pid="$(<"$pid_file")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  [[ -d "/proc/$pid" ]] || return 1
  printf '%s\n' "$pid"
}

resolve_backend_python_pid() {
  local pid python_pid
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    if python_pid="$(python_pid_from "$pid")"; then
      printf '%s\n' "$python_pid"
      return 0
    fi
  done < <(pids_listening_on_port "$port")

  if pid="$(read_pid_file)" && python_pid="$(python_pid_from "$pid")"; then
    printf '%s\n' "$python_pid"
    return 0
  fi
  return 1
}

run_checked() {
  local output
  local status
  set +e
  output="$("$@" 2>&1)"
  status=$?
  set -e
  if ((status == 0)); then
    [[ -n "$output" ]] && printf '%s\n' "$output"
    return 0
  fi
  printf '%s\n' "$output" >&2
  if is_permission_error "$output"; then
    print_ptrace_hint
  fi
  return "$status"
}

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "make perf is Linux-only." >&2
  exit 2
fi

case "$MODE" in
  cpu | idle | mem) ;;
  *)
    echo "Unsupported MODE: $MODE" >&2
    usage_error
    ;;
esac

if [[ ! "$DURATION" =~ ^[1-9][0-9]*$ ]]; then
  echo "DURATION must be a positive integer of seconds, got: $DURATION" >&2
  usage_error
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required." >&2
  exit 2
fi

backend_pid="$(resolve_backend_python_pid)" || {
  echo "Backend is not running. Start it with make dev or make run, then retry." >&2
  echo "Looked for a Python process listening on port $port and PID file $pid_file." >&2
  exit 2
}

mkdir -p "$output_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"

echo "Profiling backend PID $backend_pid (MODE=$MODE DURATION=${DURATION}s)"

case "$MODE" in
  cpu | idle)
    if ! command -v uvx >/dev/null 2>&1; then
      echo "uvx is required for MODE=$MODE." >&2
      exit 2
    fi
    outfile="$output_dir/${MODE}-${stamp}.svg"
    record_args=(record --duration "$DURATION" --format flamegraph -o "$outfile" --pid "$backend_pid")
    if [[ "$MODE" == "idle" ]]; then
      record_args+=(--idle)
    fi
    run_checked uvx --from "$PYSPY_FROM" py-spy "${record_args[@]}"
    echo "Wrote $outfile"
    ;;
  mem)
    if ! uv run --no-sync python -c "import memray" >/dev/null 2>&1; then
      echo "MODE=mem needs memray in the backend virtualenv so the running process can import it." >&2
      echo "Install once with: uv sync --group perf --locked" >&2
      echo "Then rerun make perf MODE=mem. A restart is not required after the install." >&2
      exit 2
    fi
    capture="$output_dir/mem-${stamp}.bin"
    report="$output_dir/mem-${stamp}.html"
    run_checked uv run --no-sync memray attach \
      --native \
      --method sys.remote_exec \
      --duration "$DURATION" \
      -o "$capture" \
      "$backend_pid"
    sleep "$DURATION"
    run_checked uv run --no-sync memray flamegraph -o "$report" "$capture"
    echo "Wrote $capture"
    echo "Wrote $report"
    ;;
esac
