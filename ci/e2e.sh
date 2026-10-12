#!/usr/bin/env bash
# Runs the real workflow inside n8n twice: the first run only fills the
# database, then fake old prices make the second run post to the catcher.
set -euo pipefail
compose="docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml"

mkdir -p ci-out && chmod 777 ci-out
$compose up -d --build --wait
$compose exec -T n8n n8n import:workflow --input=/workflows/price-watch.json

$compose exec -T n8n n8n execute --id=pricewatch000001
test ! -s ci-out/messages.txt || { echo "first run should not notify"; exit 1; }

$compose exec -T api python -m price_watch.demo 4
$compose exec -T n8n n8n execute --id=pricewatch000001

cat ci-out/messages.txt
grep -qE "Price drop|Back in stock" ci-out/messages.txt
