#!/bin/sh
set -eu

# Create a first-run settings file with a random secret_key and the JSON API
# enabled. Once the file exists it is treated as operator-owned configuration
# and never rewritten.
settings="/etc/searxng/settings.yml"
if [ ! -f "$settings" ]; then
  umask 077
  secret="$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)"
  tmp="$(mktemp "${settings}.XXXXXX")"
  trap 'rm -f "$tmp"' EXIT HUP INT TERM
  cat >"$tmp" <<EOF
# Generated on first start by scripts/searxng/entrypoint.sh.
# Keep this file out of version control: it contains the instance secret.
use_default_settings: true

search:
  formats:
    - html
    - json

server:
  secret_key: "$secret"
  image_proxy: true
EOF
  chmod 0640 "$tmp"
  if ! ln "$tmp" "$settings"; then
    rm -f "$tmp"
    trap - EXIT HUP INT TERM
    exit 1
  fi
  rm -f "$tmp"
  trap - EXIT HUP INT TERM
  if id searxng >/dev/null 2>&1; then
    chown searxng:searxng "$settings"
  fi
fi

exec /usr/local/searxng/entrypoint.sh "$@"
