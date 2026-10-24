#!/usr/bin/env bash
# Ephemeral DAST: k3d cluster + local registry, deploy charts/bugtracker with the
# given image, run an OWASP ZAP baseline (passive) scan, convert to SARIF.
# The same script runs in CI and locally.
#
#   IMAGE=bugtracker:ci TAG=<40-char sha> ZAP_IMAGE=zaproxy/zap-stable:...@sha256:... scripts/dast-zap.sh
#
# Output: $OUT/zap.json, $OUT/zap.html, $OUT/zap.sarif. The cluster is always deleted.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${IMAGE:?local image to test, e.g. bugtracker:ci}"
: "${TAG:?image tag (commit SHA)}"
: "${ZAP_IMAGE:?ZAP image pinned by digest}"
CLUSTER="${CLUSTER:-dast}"
REG_PORT="${REG_PORT:-5050}"
HOST_PORT="${HOST_PORT:-18080}"   # k3d load balancer only proxies ports mapped here
OUT="${OUT:-zap}"
CTX="k3d-${CLUSTER}"
REGISTRY="${CLUSTER}-registry"   # k3d does not prefix names given to --registry-create
TARGET_HOST="k3d-${CLUSTER}-serverlb"   # reachable by name on the k3d docker network
NETWORK="k3d-${CLUSTER}"

cleanup() {
  rc=$?
  if [ "$rc" -ne 0 ] && kubectl --context "$CTX" get ns bugtracker >/dev/null 2>&1; then
    echo "::group::diagnostics (exit $rc)"
    kubectl --context "$CTX" -n bugtracker get pods -o wide || true
    kubectl --context "$CTX" -n bugtracker get events --sort-by=.lastTimestamp | tail -n 30 || true
    kubectl --context "$CTX" -n bugtracker logs -l app.kubernetes.io/component=app --tail=40 --prefix || true
    echo "::endgroup::"
  fi
  k3d cluster delete "$CLUSTER" >/dev/null 2>&1 || true
  k3d registry delete "$REGISTRY" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "::group::k3d cluster"
k3d cluster create "$CLUSTER" \
  --port "${HOST_PORT}:80@loadbalancer" \
  --registry-create "${CLUSTER}-registry:0.0.0.0:${REG_PORT}" \
  --k3s-arg "--disable=metrics-server@server:0" \
  --wait --timeout 180s
echo "::endgroup::"

echo "::group::push image to the local registry"
docker tag "$IMAGE" "localhost:${REG_PORT}/bugtracker:${TAG}"
docker push -q "localhost:${REG_PORT}/bugtracker:${TAG}"
echo "::endgroup::"

echo "::group::deploy chart"
kubectl --context "$CTX" create namespace bugtracker
kubectl --context "$CTX" label namespace bugtracker pod-security.kubernetes.io/enforce=restricted
# One-off random secrets for this throwaway cluster; never stored anywhere.
kubectl --context "$CTX" -n bugtracker create secret generic bugtracker-secrets \
  --from-literal=db-password="$(openssl rand -hex 24)" \
  --from-literal=secret-key="$(openssl rand -hex 32)"
helm --kube-context "$CTX" install bugtracker charts/bugtracker -n bugtracker \
  --set image.repository="${REGISTRY}:${REG_PORT}/bugtracker" \
  --set image.tag="$TAG" \
  --set ingress.host="$TARGET_HOST" \
  --wait --timeout 5m
kubectl --context "$CTX" -n bugtracker get pods
echo "::endgroup::"

target="http://${TARGET_HOST}/"
echo "::group::wait for ${target}"
for _ in $(seq 1 60); do
  if docker run --rm --network "$NETWORK" --entrypoint curl "$ZAP_IMAGE" -fsS -o /dev/null "${target}health"; then
    break
  fi
  sleep 3
done
docker run --rm --network "$NETWORK" --entrypoint curl "$ZAP_IMAGE" -fsS "${target}health"
echo
echo "::endgroup::"

echo "::group::ZAP baseline scan"
mkdir -p "$OUT"
chmod 777 "$OUT"   # the ZAP container runs as its own user
set +e
# -I: warnings do not change the exit code; the SARIF gate decides.
docker run --rm --network "$NETWORK" -v "$PWD/$OUT:/zap/wrk:rw" "$ZAP_IMAGE" \
  zap-baseline.py -t "$target" -J zap.json -r zap.html -I
rc=$?
set -e
echo "::endgroup::"
# 0 = no alerts, 2 = warnings (with -I those exit 0); other codes are tool errors.
if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
  echo "::error::ZAP baseline failed (exit $rc)"; exit "$rc"
fi

python3 scripts/zap-to-sarif.py "$OUT/zap.json" "$OUT/zap.sarif"
