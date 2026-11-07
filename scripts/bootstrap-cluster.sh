#!/usr/bin/env bash
# Builds a complete local k3d cluster for the project in one go:
# k3d + Sealed Secrets + Argo CD (+ optional Kyverno) + the production
# Argo CD Application from the GitOps repo. Meant for team members who want
# the same setup as the reference cluster.
#
#   scripts/bootstrap-cluster.sh                         # without Kyverno
#   WITH_KYVERNO=1 scripts/bootstrap-cluster.sh          # + image signature checks
#   SEALED_KEY=~/sealed-secrets-key.backup.yaml scripts/bootstrap-cluster.sh
#
# Secrets: the SealedSecrets in the GitOps repo can only be decrypted with the
# controller key of the reference cluster. Without SEALED_KEY the script creates
# bugtracker-secrets with random values instead (never written to disk); the
# SealedSecret then reports "not managed" and the app still runs.
#
# Webhook/tunnel are not set up: Argo CD polls the GitOps repo every ~3 min.
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER="${CLUSTER:-bugtracker}"
HTTP_PORT="${HTTP_PORT:-80}"
WITH_KYVERNO="${WITH_KYVERNO:-0}"
SEALED_KEY="${SEALED_KEY:-}"
GITOPS_APP_URL="${GITOPS_APP_URL:-https://raw.githubusercontent.com/Krrystian/bugtracker-gitops/main/argocd/application.yaml}"
CTX="k3d-${CLUSTER}"

SEALED_VERSION=v0.40.0
SEALED_SHA=ac8aabccdd9110430d117501705818115b2ab0993700a9c118d4d42cf4015a17
ARGOCD_CHART_VERSION=10.10.1
KYVERNO_VERSION=v1.19.1
KYVERNO_SHA=d3322cb346d3d42dd0f41e230b0d1d7bc5619960e1c36fdac4d9151d724b88e6

step() { echo; echo "==> $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }
k() { kubectl --context "$CTX" "$@"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fetch_verified() {  # fetch_verified <url> <sha256> <dest>
  curl -fsSLo "$3" "$1"
  echo "$2  $3" | shasum -a 256 -c - >/dev/null || fail "checksum mismatch: $1"
}

step "checking tools"
for tool in docker k3d kubectl helm curl openssl shasum; do
  command -v "$tool" >/dev/null || fail "missing tool: $tool (macOS: brew install $tool)"
done
docker info >/dev/null 2>&1 || fail "Docker is not running (start Docker Desktop)"
[[ -z "$SEALED_KEY" || -f "$SEALED_KEY" ]] || fail "SEALED_KEY file not found: $SEALED_KEY"

step "k3d cluster ${CLUSTER} (http://localhost:${HTTP_PORT})"
if k3d cluster list "$CLUSTER" >/dev/null 2>&1; then
  echo "cluster already exists, reusing it"
else
  k3d cluster create "$CLUSTER" --port "${HTTP_PORT}:80@loadbalancer" --wait --timeout 180s
fi

step "Sealed Secrets ${SEALED_VERSION}"
if [[ -n "$SEALED_KEY" ]]; then
  # The key must exist before the controller starts, otherwise it generates a new one.
  k apply -f "$SEALED_KEY"
fi
fetch_verified "https://github.com/bitnami-labs/sealed-secrets/releases/download/${SEALED_VERSION}/controller.yaml" \
  "$SEALED_SHA" "$TMP/sealed-secrets.yaml"
k apply -f "$TMP/sealed-secrets.yaml"
k -n kube-system rollout status deploy/sealed-secrets-controller --timeout=180s

if [[ "$WITH_KYVERNO" == 1 ]]; then
  step "Kyverno ${KYVERNO_VERSION}"
  fetch_verified "https://github.com/kyverno/kyverno/releases/download/${KYVERNO_VERSION}/install.yaml" \
    "$KYVERNO_SHA" "$TMP/kyverno.yaml"
  k apply --server-side -f "$TMP/kyverno.yaml" >/dev/null
  k -n kyverno rollout status deploy/kyverno-admission-controller --timeout=300s
  if ! k -n kyverno get secret dockerhub-readonly >/dev/null 2>&1; then
    # Kyverno reads signatures from Docker Hub; anonymous access hits the rate limit.
    echo "Docker Hub account with a READ-ONLY access token (hub.docker.com -> Account settings -> Personal access tokens)"
    [[ -n "${DOCKERHUB_USERNAME:-}" ]] || read -rp "Docker Hub username: " DOCKERHUB_USERNAME
    [[ -n "${DOCKERHUB_TOKEN:-}" ]] || { read -rsp "Read-only token (hidden): " DOCKERHUB_TOKEN; echo; }
    k -n kyverno create secret docker-registry dockerhub-readonly \
      --docker-server=https://index.docker.io/v1/ \
      --docker-username="$DOCKERHUB_USERNAME" --docker-password="$DOCKERHUB_TOKEN" >/dev/null
    unset DOCKERHUB_TOKEN
  fi
  k apply -f infra/kyverno/verify-images.yaml
fi

step "Argo CD (chart ${ARGOCD_CHART_VERSION})"
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null 2>&1 || true
helm repo update argo >/dev/null
helm --kube-context "$CTX" upgrade --install argocd argo/argo-cd --version "$ARGOCD_CHART_VERSION" \
  -n argocd --create-namespace -f infra/argocd/values.yaml --wait --timeout 10m

step "application secrets"
k create namespace bugtracker --dry-run=client -o yaml | k apply -f -
k label namespace bugtracker pod-security.kubernetes.io/enforce=restricted --overwrite
if [[ -n "$SEALED_KEY" ]]; then
  echo "using the SealedSecrets from the GitOps repo (decrypted with SEALED_KEY)"
elif k -n bugtracker get secret bugtracker-secrets >/dev/null 2>&1; then
  echo "bugtracker-secrets already exists, keeping it"
else
  k -n bugtracker create secret generic bugtracker-secrets \
    --from-literal=db-password="$(openssl rand -hex 24)" \
    --from-literal=secret-key="$(openssl rand -hex 32)" >/dev/null
  echo "created bugtracker-secrets with random values (local only)"
fi

step "Argo CD Application"
k apply -f "$GITOPS_APP_URL"
echo "waiting for the app (first image pull can take a few minutes)..."
for _ in $(seq 1 100); do
  if curl -fsS -o /dev/null "http://localhost:${HTTP_PORT}/health" 2>/dev/null; then break; fi
  sleep 6
done
k -n argocd get applications
k -n bugtracker get pods
curl -fsS "http://localhost:${HTTP_PORT}/health" \
  || fail "app not reachable yet: check 'kubectl -n bugtracker get pods' and the Argo CD UI"
echo

cat <<EOF

Done.
  App:        http://localhost:${HTTP_PORT}
  Argo CD UI: kubectl --context ${CTX} -n argocd port-forward svc/argocd-server 8080:80
              -> http://localhost:8080, user admin, password:
              kubectl --context ${CTX} -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
  Remove:     k3d cluster delete ${CLUSTER}
EOF
