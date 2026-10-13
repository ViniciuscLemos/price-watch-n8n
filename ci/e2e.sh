#!/usr/bin/env bash
# Runs the real workflow inside n8n against a fake Steam and fake senders:
#   1. first run: the games already on sale go out on all three channels
#   2. same prices again: nothing, a sale that goes on isn't news
#   3. fake higher prices from "yesterday": the drops go out
set -euo pipefail
compose="docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml"
out=ci-out/messages.txt

mkdir -p ci-out && chmod 777 ci-out && rm -f $out
$compose up -d --build --wait
# n8n answers before its database migrations are done, and the import below
# runs the same migrations: wait for the editor line so they don't collide
for _ in $(seq 60); do
  $compose logs n8n | grep -q "Editor is now accessible" && break
  sleep 2
done
# --separate takes each file as one workflow (a plain --input wants an array)
$compose exec -T n8n n8n import:workflow --separate --input=/workflows/
# quiet when it works, the whole execution (with the failing node) when it doesn't
run() { local log; log=$($compose exec -T n8n n8n execute --id=pricewatch000001 2>&1) || { echo "$log" | tail -80; return 1; }; }

run
cat $out
for channel in discord ntfy whatsapp; do
  grep "^$channel .*Red Dead Redemption 2" $out > /dev/null || { echo "no sale on $channel"; exit 1; }
done

rm -f $out
run
test ! -s $out || { echo "the same sale was sent twice"; cat $out; exit 1; }

$compose exec -T api python -m price_watch.demo 4
run
cat $out
grep "Lowest since I started watching" $out > /dev/null
test "$(grep -c '' $out)" -eq 3
