#!/usr/bin/env bash
# Regenerates the fully pinned lock files from the direct dependency lists:
#   requirements.in      -> requirements.txt      (runtime, installed in the image)
#   requirements-dev.in  -> requirements-dev.txt  (runtime + tests, used in CI)
# Resolution runs in the same Python base image as the Dockerfile, so the
# pinned versions are exactly what ships in the container.
set -euo pipefail
cd "$(dirname "$0")/.."

image=$(grep -oE 'python:[^ ]+@sha256:[0-9a-f]+' Dockerfile | head -n 1)

docker run --rm -v "$PWD:/w" -w /w "$image" sh -ec '
  freeze() { pip freeze --all --exclude pip --exclude setuptools --exclude wheel; }
  python -m venv /tmp/rt && . /tmp/rt/bin/activate
  pip install -q --disable-pip-version-check -r requirements.in
  { echo "# GENERATED lock file — do not edit by hand."
    echo "# Direct dependencies live in requirements.in; regenerate with scripts/lock-deps.sh."
    freeze; } > requirements.txt
  pip install -q --disable-pip-version-check -r requirements-dev.in
  { echo "# GENERATED lock file — do not edit by hand (runtime + test dependencies)."
    echo "# Direct dependencies live in requirements-dev.in; regenerate with scripts/lock-deps.sh."
    freeze; } > requirements-dev.txt
'
echo "requirements.txt: $(grep -vc '^#' requirements.txt) packages, requirements-dev.txt: $(grep -vc '^#' requirements-dev.txt) packages"
