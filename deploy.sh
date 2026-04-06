#!/bin/bash
set -e
git pull origin main
docker compose -f docker-compose.prod.yml --env-file .env.prod build --no-cache
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
echo "server2 deploy complete"
