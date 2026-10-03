#!/usr/bin/env bash
# Drive traffic at the application so that dashboards and traces are not empty.
#
#   ./scripts/traffic.sh                 # 2 requests per second until stopped
#   RATE=10 DURATION=60 ./scripts/traffic.sh
#   BASE_URL=http://localhost:8000 ./scripts/traffic.sh
#
# Handlers are picked by weight: mostly post reads, some reports, CPU work and new posts, now and
# then a missing post (404) and a deliberate failure (500).
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
RATE="${RATE:-2}"
DURATION="${DURATION:-0}"

pause=$(awk -v rate="$RATE" 'BEGIN { printf "%.3f", 1 / rate }')
started=$SECONDS

pick_request() {
  local post_id=$((RANDOM % 100 + 1))
  # Every twentieth post is a missing one.
  if ((RANDOM % 20 == 0)); then
    post_id=1000
  fi

  local roll=$((RANDOM % 100))
  if ((roll < 40)); then
    echo "GET /api/posts/${post_id}"
  elif ((roll < 58)); then
    echo "GET /api/report/${post_id}"
  elif ((roll < 68)); then
    echo "GET /api/posts"
  elif ((roll < 78)); then
    echo "POST /api/posts"
  elif ((roll < 95)); then
    echo "GET /api/cpu?below=$(((RANDOM % 35 + 5) * 10000))"
  else
    echo "GET /api/fail"
  fi
}

# A new post with a body of 100 to 5000 characters: request sizes get a spread to show.
draft() {
  local text
  text=$(head -c $((RANDOM % 4900 + 100)) /dev/zero | tr '\0' 'x')
  printf '{"user_id": %d, "title": "post from traffic.sh", "body": "%s"}' $((RANDOM % 10 + 1)) "$text"
}

visit() {
  local method=$1 path=$2
  local body=()
  if [[ $method == POST ]]; then
    body=(--header "content-type: application/json" --data "$(draft)")
  fi
  local answer
  answer=$(curl --silent --output /dev/null --max-time 15 --request "$method" "${body[@]}" \
    --write-out "%{http_code} %{time_total}s" "${BASE_URL}${path}" || echo "000 failed")
  printf '%s  %-4s %-28s %s\n' "$(date +%T)" "$method" "$path" "$answer"
}

echo "traffic → ${BASE_URL}, ${RATE} rps$([[ $DURATION -gt 0 ]] && echo ", ${DURATION}s"); Ctrl+C to stop"
trap 'wait; exit 0' INT TERM

while ((DURATION == 0 || SECONDS - started < DURATION)); do
  # shellcheck disable=SC2046  # the method and the path are two words on purpose
  visit $(pick_request) &
  sleep "$pause"
done
wait
