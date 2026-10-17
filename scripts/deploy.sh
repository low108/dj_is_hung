#!/usr/bin/env bash
# Deploys the public demo: the API to Cloud Run, the web app to Firebase Hosting.
#   PROJECT=my-project scripts/deploy.sh          # both
#   PROJECT=my-project scripts/deploy.sh api|web  # one
# Needs: gcloud (logged in, billing on), the ILMU key in Secret Manager as "ilmu-api-key", and
# `npx firebase-tools login`. Live runs are limited: scripted twins, plus one ILMU run at a time.
set -euo pipefail
: "${PROJECT:?set PROJECT to the Google Cloud project id}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-garden-api}"
DEMO_REPLAY="${DEMO_REPLAY:-ddd60e575909/r00}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
what="${1:-all}"

deploy_api() {
  local ctx; ctx="$(mktemp -d)"
  trap 'rm -rf "$ctx"' RETURN
  cp "$ROOT/deploy/Dockerfile" "$ROOT/pyproject.toml" "$ROOT/uv.lock" "$ROOT/README.md" "$ctx/"
  cp -R "$ROOT/garden" "$ROOT/api" "$ctx/"
  find "$ctx" -name __pycache__ -prune -exec rm -rf {} +
  mkdir -p "$ctx/data/raw" "$ctx/data/replays/${DEMO_REPLAY%/*}"
  cp "$ROOT/data/raw/speed_dating.csv" "$ctx/data/raw/"
  cp "$ROOT/data/replays/$DEMO_REPLAY.json" "$ROOT/data/replays/$DEMO_REPLAY.summary.json" \
     "$ctx/data/replays/${DEMO_REPLAY%/*}/"
  # One instance that is always on and keeps its CPU, so a live run's background thread isn't paused or
  # lost between requests (simulations are kept in memory).
  gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source "$ctx" \
    --allow-unauthenticated --min-instances 1 --max-instances 1 --no-cpu-throttling \
    --cpu 2 --memory 4Gi --timeout 300 \
    --set-secrets "ILMU_API_KEY=ilmu-api-key:latest" \
    --set-env-vars "^@^ALLOWED_MODELS=ilmu:ilmu-mini-v3.3@MAX_REAL_SIMS=1@MAX_REAL_RUNS=1@CORS_ORIGINS=https://$PROJECT.web.app,https://$PROJECT.firebaseapp.com"
}

deploy_web() {
  local api; api="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')"
  (cd "$ROOT/web" && NEXT_PUBLIC_API_URL="$api" NEXT_PUBLIC_SIGN_IN=off \
     NEXT_PUBLIC_LIVE_MODELS="fake,ilmu:ilmu-mini-v3.3" NEXT_PUBLIC_DEMO_REPLAYS="$DEMO_REPLAY" npm run export)
  (cd "$ROOT" && npx -y firebase-tools@14 deploy --only hosting --project "$PROJECT")
}

case "$what" in
  api) deploy_api ;;
  web) deploy_web ;;
  all) deploy_api; deploy_web ;;
  *) echo "usage: scripts/deploy.sh [api|web|all]" >&2; exit 2 ;;
esac
