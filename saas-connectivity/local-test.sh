#!/usr/bin/env bash
# Sends each std:* command to the local dev server (npm run dev) using the demo key from ./.env (DEMO_API, DEMO_API_KEY).
# Usage: ./local-test.sh [outdir]   (prints a summary; raw responses go to evidence/, never the key)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
set -a; . "$HERE/.env"; set +a
OUT="${1:-$HERE/evidence}"; mkdir -p "$OUT"
call() { # name type input-json
  curl -sS -X POST localhost:3000 -H "Content-Type: application/json" \
    -d "{\"type\":\"$2\",\"input\":$3,\"config\":{\"baseUrl\":\"$DEMO_API\",\"apiKey\":\"$DEMO_API_KEY\"}}" > "$OUT/$1.ndjson"
  printf '%-22s %s lines  %s\n' "$1" "$(wc -l < "$OUT/$1.ndjson" | tr -d ' ')" "$(head -c 160 "$OUT/$1.ndjson")"
}
call test-connection    std:test-connection  '{}'
call account-list       std:account:list     '{}'
FIRST=$(python3 -c "import json,sys;print(json.loads(open('$OUT/account-list.ndjson').readline())['data']['identity'])")
call account-read       std:account:read     "{\"identity\":\"$FIRST\"}"
call account-read-404   std:account:read     '{"identity":"usr_doesnotexist"}'
call entitlement-list   std:entitlement:list '{"type":"group"}'
GRP=$(python3 -c "import json,sys;print(json.loads(open('$OUT/entitlement-list.ndjson').readline())['data']['identity'])")
call entitlement-read   std:entitlement:read "{\"type\":\"group\",\"identity\":\"$GRP\"}"
# bad key -> friendly error
curl -sS -X POST localhost:3000 -H "Content-Type: application/json" \
  -d "{\"type\":\"std:test-connection\",\"input\":{},\"config\":{\"baseUrl\":\"$DEMO_API\",\"apiKey\":\"sck_bad\"}}" > "$OUT/test-connection-badkey.ndjson"
printf '%-22s %s\n' test-connection-badkey "$(head -c 200 "$OUT/test-connection-badkey.ndjson")"
