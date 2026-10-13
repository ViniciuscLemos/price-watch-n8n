#!/usr/bin/env bash
# Takes the README screenshots from a real n8n, with the fake Steam and senders
# from CI: the run clicked in the editor finds the drops the demo script fakes.
set -euo pipefail
compose="docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml -f ci/shots/docker-compose.shots.yml"

mkdir -p ci-out shots && chmod 777 ci-out && rm -f ci-out/messages.txt
$compose up -d --build --wait
for _ in $(seq 60); do
  $compose logs n8n | grep -q "Editor is now accessible" && break
  sleep 2
done
$compose exec -T n8n n8n import:workflow --separate --input=/workflows/
# a first run plus a few pricier "yesterdays", so the page has some history to draw
$compose exec -T n8n n8n execute --id=pricewatch000001 > /dev/null
$compose exec -T api python -m price_watch.demo 5

node ci/shots/shots.mjs shots
cat ci-out/messages.txt
