#!/usr/bin/env bash
# Lance le tir k6 dans le cluster (namespace loadtest, hors de perf-lab
# pour que Beyla n'instrumente pas le générateur de charge).
# Usage : scripts/run-k6.sh <nom> [PROFILE] [RATE] [DURATION]
set -euo pipefail
NAME=${1:?nom du tir}
PROFILE=${2:-constant}
RATE=${3:-50}
DURATION=${4:-3m}
cd "$(dirname "$0")/.."

kubectl create namespace loadtest --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n loadtest create configmap k6-script --from-file=k6/order-load.js \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n loadtest delete job "k6-$NAME" --ignore-not-found >/dev/null

sed -e "s/__NAME__/$NAME/" -e "s/__PROFILE__/$PROFILE/" \
    -e "s/__RATE__/$RATE/" -e "s/__DURATION__/$DURATION/" k6/job.yaml | kubectl apply -f -
kubectl -n loadtest wait --for=condition=ready pod -l job-name="k6-$NAME" --timeout=120s >/dev/null
kubectl -n loadtest logs -f job/"k6-$NAME"
