#!/usr/bin/env bash
set -euo pipefail

if uv sync "$@"; then
  exit 0
fi

echo "[ci] primary Python package index failed; retrying with official PyPI" >&2
lock_file="uv.lock"
backup_file="$(mktemp)"
cp "$lock_file" "$backup_file"

restore_lockfile() {
  cp "$backup_file" "$lock_file"
  rm -f "$backup_file"
}
trap restore_lockfile EXIT

# uv.lock stores both the resolved index and exact artifact URLs. The package
# paths and hashes are identical on PyPI, so this keeps the lock resolution
# intact while making the retry independent of the failed mirror.
sed \
  -e 's|https://mirrors.aliyun.com/pypi/simple|https://pypi.org/simple|g' \
  -e 's|https://mirrors.aliyun.com/pypi/packages/|https://files.pythonhosted.org/packages/|g' \
  "$backup_file" >"$lock_file"

UV_DEFAULT_INDEX="https://pypi.org/simple" uv sync "$@"
