#!/usr/bin/env bash
# Takes the README screenshots from a real n8n: one run fills the database,
# fake old prices make the run clicked in the editor post a price drop.
set -euo pipefail
compose="docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml -f ci/shots/docker-compose.shots.yml"

mkdir -p ci-out shots && chmod 777 ci-out
$compose up -d --build --wait
for _ in $(seq 60); do
  $compose logs n8n | grep -q "Editor is now accessible" && break
  sleep 2
done
$compose exec -T n8n n8n import:workflow --separate --input=/workflows/
$compose exec -T n8n n8n execute --id=pricewatch000001
$compose exec -T api python -m price_watch.demo 4

node ci/shots/shots.mjs shots
cat ci-out/messages.txt
