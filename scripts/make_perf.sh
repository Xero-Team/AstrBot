#!/usr/bin/env bash

set -euo pipefail

MODE="${MODE:-cpu}"
DURATION="${DURATION:-30}"
RATE="${RATE:-}"
PYSPY_FROM="${ASTRBOT_PERF_PYSPY_FROM:-py-spy>=0.4.2}"

action="start"
if (($# == 1)) && [[ "$1" == "stop" ]]; then
  action="stop"
elif (($# != 0)); then
  echo "Usage: MODE=cpu|idle|mem DURATION=<seconds|0> RATE=<hz> scripts/make_perf.sh [stop]" >&2
  echo "Do not pass other positional arguments; use make perf MODE=... DURATION=... RATE=..." >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pid_file="${ASTRBOT_PERF_PID_FILE:-$repo_root/.make/backend.pid}"
sidecar_pid_file="${ASTRBOT_PERF_SIDECAR_PID_FILE:-$repo_root/.make/perf.pid}"
meta_file="${ASTRBOT_PERF_META_FILE:-$repo_root/.make/perf.meta}"
output_dir="${ASTRBOT_PERF_OUTPUT_DIR:-$repo_root/.tmp/perf}"
sidecar_log="${ASTRBOT_PERF_LOG_FILE:-$output_dir/perf_run.log}"
port="${ASTRBOT_DASHBOARD_PORT:-6185}"

usage_error() {
  echo "Usage: MODE=cpu|idle|mem DURATION=<seconds or 0> RATE=<hz> make perf" >&2
  echo "DURATION=0 starts a background sidecar until make stop-perf or make stop." >&2
  echo "RATE is samples per second for cpu/idle. DURATION=0 defaults to 10; otherwise py-spy default 100." >&2
  echo "Linux-only: attaches to a running backend started by make dev or make run." >&2
  exit 2
}

print_ptrace_hint() {
  echo "Permission to inspect the backend process was denied." >&2
  echo "On Linux, attaching usually needs ptrace. Grant it for your user, for example:" >&2
  echo "  echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope" >&2
  echo "Docker/production may also need cap_add: SYS_PTRACE." >&2
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

pid_is_alive() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

stop_perf_pid() {
  local pid="$1"
  local pgid
  pid_is_alive "$pid" || return 0

  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ "$pgid" == "$pid" ]]; then
    kill -INT -- "-$pid" 2>/dev/null || true
  else
    kill -INT "$pid" 2>/dev/null || true
  fi

  local _
  for _ in {1..50}; do
    pid_is_alive "$pid" || return 0
    sleep 0.2
  done

  if [[ "$pgid" == "$pid" ]]; then
    kill -TERM -- "-$pid" 2>/dev/null || true
  else
    kill -TERM "$pid" 2>/dev/null || true
  fi
  for _ in {1..10}; do
    pid_is_alive "$pid" || return 0
    sleep 0.2
  done
  if [[ "$pgid" == "$pid" ]]; then
    kill -KILL -- "-$pid" 2>/dev/null || true
  else
    kill -KILL "$pid" 2>/dev/null || true
  fi
}

write_meta() {
  mkdir -p "$(dirname "$meta_file")"
  cat >"$meta_file" <<EOF
mode=$1
outfile=${2:-}
capture=${3:-}
report=${4:-}
backend_pid=${5:-}
EOF
}

sidecar_is_running() {
  local pid
  [[ -f "$sidecar_pid_file" ]] || return 1
  pid="$(<"$sidecar_pid_file")"
  pid_is_alive "$pid"
}

start_sidecar() {
  mkdir -p "$(dirname "$sidecar_pid_file")" "$output_dir"
  : >"$sidecar_log"
  (
    if command -v setsid >/dev/null 2>&1; then
      exec setsid "$@"
    fi
    exec "$@"
  ) >>"$sidecar_log" 2>>"$sidecar_log" &
  local pid=$!
  printf '%s\n' "$pid" >"$sidecar_pid_file"
  sleep 0.4
  if pid_is_alive "$pid"; then
    return 0
  fi
  if [[ -s "$sidecar_log" ]]; then
    cat "$sidecar_log" >&2
    if is_permission_error "$(<"$sidecar_log")"; then
      print_ptrace_hint
    fi
  fi
  rm -f -- "$sidecar_pid_file"
  return 1
}

stop_session() {
  local mode="" outfile="" capture="" report="" backend_pid="" sidecar_pid=""
  if [[ -f "$meta_file" ]]; then
    # shellcheck disable=SC1090
    source "$meta_file"
  fi
  if [[ -f "$sidecar_pid_file" ]]; then
    sidecar_pid="$(<"$sidecar_pid_file")"
    stop_perf_pid "$sidecar_pid"
    rm -f -- "$sidecar_pid_file"
  fi
  if [[ "$mode" == "mem" ]]; then
    if [[ -n "$backend_pid" ]] && pid_is_alive "$backend_pid"; then
      run_checked uv run --no-sync memray detach --method sys.remote_exec "$backend_pid" || true
    fi
    if [[ -n "$capture" && -f "$capture" && -n "$report" ]]; then
      run_checked uv run --no-sync memray flamegraph -o "$report" "$capture"
      echo "Wrote $capture"
      echo "Wrote $report"
    fi
  elif [[ -n "$outfile" ]]; then
    echo "Wrote $outfile"
  fi
  rm -f -- "$meta_file"
}

if [[ "$(uname -s)" != "Linux" ]]; then
  if [[ "$action" == "stop" ]]; then
    exit 0
  fi
  echo "make perf is Linux-only." >&2
  exit 2
fi

if [[ "$action" == "stop" ]]; then
  stop_session
  exit 0
fi

case "$MODE" in
  cpu | idle | mem) ;;
  *)
    echo "Unsupported MODE: $MODE" >&2
    usage_error
    ;;
esac

if [[ "$DURATION" != "0" && ! "$DURATION" =~ ^[1-9][0-9]*$ ]]; then
  echo "DURATION must be 0 (until stop) or a positive integer of seconds, got: $DURATION" >&2
  usage_error
fi

if [[ -z "$RATE" && "$DURATION" == "0" && "$MODE" != "mem" ]]; then
  RATE=10
fi
if [[ -n "$RATE" && ! "$RATE" =~ ^[1-9][0-9]*$ ]]; then
  echo "RATE must be a positive integer of samples per second, got: $RATE" >&2
  usage_error
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required." >&2
  exit 2
fi

if sidecar_is_running || [[ -f "$meta_file" ]]; then
  echo "A perf sidecar is already running. Stop it with make stop-perf first." >&2
  exit 2
fi

backend_pid="$(resolve_backend_python_pid)" || {
  echo "Backend is not running. Start it with make dev or make run, then retry." >&2
  echo "Looked for a Python process listening on port $port and PID file $pid_file." >&2
  exit 2
}

mkdir -p "$output_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ "$DURATION" == "0" ]]; then
  echo "Profiling backend PID $backend_pid (MODE=$MODE RATE=${RATE:-default} until make stop-perf / make stop)"
else
  echo "Profiling backend PID $backend_pid (MODE=$MODE DURATION=${DURATION}s RATE=${RATE:-default})"
fi

case "$MODE" in
  cpu | idle)
    if ! command -v uvx >/dev/null 2>&1; then
      echo "uvx is required for MODE=$MODE." >&2
      exit 2
    fi
    outfile="$output_dir/${MODE}-${stamp}.svg"
    record_args=(record --format flamegraph -o "$outfile" --pid "$backend_pid")
    if [[ -n "$RATE" ]]; then
      record_args+=(--rate "$RATE")
    fi
    if [[ "$MODE" == "idle" ]]; then
      record_args+=(--idle)
    fi
    if [[ "$DURATION" == "0" ]]; then
      start_sidecar uvx --from "$PYSPY_FROM" py-spy "${record_args[@]}"
      write_meta "$MODE" "$outfile" "" "" "$backend_pid"
      echo "Sampler PID $(<"$sidecar_pid_file")"
      echo "Writing $outfile on make stop-perf / make stop"
    else
      record_args+=(--duration "$DURATION")
      run_checked uvx --from "$PYSPY_FROM" py-spy "${record_args[@]}"
      echo "Wrote $outfile"
    fi
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
    attach_args=(attach --method sys.remote_exec -o "$capture")
    if [[ "$DURATION" == "0" ]]; then
      run_checked uv run --no-sync memray "${attach_args[@]}" "$backend_pid"
      write_meta mem "" "$capture" "$report" "$backend_pid"
      echo "Memory capture $capture until make stop-perf / make stop"
    else
      attach_args+=(--native --duration "$DURATION")
      run_checked uv run --no-sync memray "${attach_args[@]}" "$backend_pid"
      sleep "$DURATION"
      run_checked uv run --no-sync memray flamegraph -o "$report" "$capture"
      echo "Wrote $capture"
      echo "Wrote $report"
    fi
    ;;
esac
