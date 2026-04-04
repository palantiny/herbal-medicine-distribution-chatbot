#!/bin/bash
set -e
git pull origin main
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d
echo "server2 deploy complete"
