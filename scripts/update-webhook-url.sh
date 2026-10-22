#!/usr/bin/env bash
# Points the GitHub webhook of the GitOps repo at the current Cloudflare Quick
# Tunnel URL. Run it after every restart of the cloudflared pod (the quick
# tunnel URL changes each time).
#
# The webhook secret is read from the cluster (argocd-secret) and re-sent so
# GitHub and Argo CD always share the same value. It is never printed.
set -euo pipefail

CONTEXT="${KUBE_CONTEXT:-k3d-bugtracker}"
REPO="${GITOPS_REPO:-Krrystian/bugtracker-gitops}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

url="$("$SCRIPT_DIR/tunnel-url.sh")/api/webhook"

hook_id=$(gh api "repos/$REPO/hooks" \
  --jq '[.[] | select(.config.url | endswith("/api/webhook"))][0].id // empty')
if [[ -z "$hook_id" ]]; then
  echo "No webhook ending with /api/webhook found in $REPO" >&2
  exit 1
fi

current=$(gh api "repos/$REPO/hooks/$hook_id/config" --jq .url)
if [[ "$current" == "$url" ]]; then
  echo "Webhook already points at $url"
  exit 0
fi

secret=$(kubectl --context="$CONTEXT" -n argocd get secret argocd-secret \
  -o jsonpath='{.data.webhook\.github\.secret}' | base64 -d)
if [[ -z "$secret" ]]; then
  echo "webhook.github.secret is not set in argocd-secret" >&2
  exit 1
fi

# Pass the secret via stdin, not as a command-line argument.
python3 -c 'import json,sys; print(json.dumps({"url": sys.argv[1], "content_type": "json", "insecure_ssl": "0", "secret": sys.stdin.read().rstrip("\n")}))' "$url" <<<"$secret" \
  | gh api -X PATCH "repos/$REPO/hooks/$hook_id/config" --input - --jq '"Webhook \(.url) updated"' \
  | sed "s|^|[$REPO #$hook_id] |"
unset secret

gh api -X POST "repos/$REPO/hooks/$hook_id/pings" >/dev/null
echo "Ping sent. Check: gh api repos/$REPO/hooks/$hook_id/deliveries --jq '.[0] | \"\\(.event) \\(.status_code)\"'"
