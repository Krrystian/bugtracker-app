#!/usr/bin/env bash
# Prints the current public URL of the Cloudflare Quick Tunnel running in k3d.
# The URL changes every time the cloudflared pod restarts.
set -euo pipefail

CONTEXT="${KUBE_CONTEXT:-k3d-bugtracker}"

url=$(kubectl --context="$CONTEXT" -n cloudflared logs deploy/cloudflared 2>/dev/null \
  | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)

if [[ -z "$url" ]]; then
  echo "Tunnel URL not found. Is the cloudflared pod running?" >&2
  echo "  kubectl --context=$CONTEXT -n cloudflared get pods" >&2
  exit 1
fi

echo "$url"
