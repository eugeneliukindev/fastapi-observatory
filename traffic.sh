#!/usr/bin/env bash
# Drive traffic at the application so that dashboards and traces are not empty.
#
#   ./traffic.sh                         # 2 requests per second until stopped
#   RATE=10 DURATION=60 ./traffic.sh
#   BASE_URL=http://localhost:8000 ./traffic.sh
#   RATE=200 CPU_PERCENT=3 REPORT_PERCENT=3 CPU_BELOW_MAX=100000 ./traffic.sh
#   FAIL_PERCENT=30 INVALID_PERCENT=20 ./traffic.sh   # an incident
#
# Handlers are picked by weight: mostly post reads, some reports, CPU work and new posts, now and
# then a missing post (404), a request the API refuses (422, 405) and a deliberate failure (500)
# with one of five exception types. Reports and CPU work cost CPU time — about 0.3 s a report, up
# to a second /api/cpu — so a high rate needs a lighter mix or more workers.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
RATE="${RATE:-2}"
DURATION="${DURATION:-0}"
CPU_PERCENT="${CPU_PERCENT:-17}"
REPORT_PERCENT="${REPORT_PERCENT:-18}"
CPU_BELOW_MAX="${CPU_BELOW_MAX:-390000}"
FAIL_PERCENT="${FAIL_PERCENT:-5}"
INVALID_PERCENT="${INVALID_PERCENT:-4}"

# A runtime error most often, the rest of the kinds /api/fail knows now and then.
FAILURES=(runtime runtime runtime invalid invalid lookup timeout permission)

pause=$(awk -v rate="$RATE" 'BEGIN { printf "%.3f", 1 / rate }')
started=$SECONDS

pick_request() {
  local post_id=$((RANDOM % 100 + 1))
  # Every twentieth post is a missing one.
  if ((RANDOM % 20 == 0)); then
    post_id=1000
  fi

  # Post reads take whatever share the others leave.
  local roll=$((RANDOM % 100)) refused=$((FAIL_PERCENT + INVALID_PERCENT)) list=10 create=10
  if ((roll < FAIL_PERCENT)); then
    echo "GET /api/fail?kind=${FAILURES[RANDOM % ${#FAILURES[@]}]}"
  elif ((roll < refused)); then
    pick_invalid "$post_id"
  elif ((roll < refused + list)); then
    echo "GET /api/posts"
  elif ((roll < refused + list + create)); then
    echo "POST /api/posts"
  elif ((roll < refused + list + create + REPORT_PERCENT)); then
    echo "GET /api/report/${post_id}"
  elif ((roll < refused + list + create + REPORT_PERCENT + CPU_PERCENT)); then
    echo "GET /api/cpu?below=$(((RANDOM % (CPU_BELOW_MAX / 10000 - 4) + 5) * 10000))"
  else
    echo "GET /api/posts/${post_id}"
  fi
}

# A request the API refuses before any handler runs: a bad parameter (422), a wrong method (405).
pick_invalid() {
  case $((RANDOM % 3)) in
    0) echo "GET /api/posts/latest" ;;
    1) echo "GET /api/cpu?below=$((CPU_BELOW_MAX * 100))" ;;
    *) echo "DELETE /api/posts/$1" ;;
  esac
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
