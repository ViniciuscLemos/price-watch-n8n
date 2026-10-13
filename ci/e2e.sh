#!/usr/bin/env bash
# Runs the real workflow inside n8n twice: the first run only fills the
# database, then fake old prices make the second run post to the catcher.
set -euo pipefail
compose="docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml"

mkdir -p ci-out && chmod 777 ci-out
$compose up -d --build --wait
# n8n answers before its database migrations are done, and the import below
# runs the same migrations: wait for the editor line so they don't collide
for _ in $(seq 60); do
  $compose logs n8n | grep -q "Editor is now accessible" && break
  sleep 2
done
# --separate takes each file as one workflow (a plain --input wants an array)
$compose exec -T n8n n8n import:workflow --separate --input=/workflows/

$compose exec -T n8n n8n execute --id=pricewatch000001
test ! -s ci-out/messages.txt || { echo "first run should not notify"; exit 1; }

$compose exec -T api python -m price_watch.demo 4
$compose exec -T n8n n8n execute --id=pricewatch000001

cat ci-out/messages.txt
grep -qE "Price drop|Back in stock" ci-out/messages.txt
