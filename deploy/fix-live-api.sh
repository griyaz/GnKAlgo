#!/usr/bin/env bash
# Run on the Oracle VM after git clone. Ensures the site calls /api on the same host (www.gnkalgo.com).
set -euo pipefail
cd /opt/gnkalgo

git fetch origin
git checkout main
git pull origin main

if [ -f .env ]; then
  sed -i 's|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=|' .env
  grep -q '^NEXT_PUBLIC_API_URL=' .env || echo 'NEXT_PUBLIC_API_URL=' >> .env
else
  echo "Missing /opt/gnkalgo/.env" >&2
  exit 1
fi

sudo cp deploy/nginx/www.gnkalgo.com.conf /etc/nginx/sites-available/
sudo cp deploy/nginx/api.gnkalgo.com.conf /etc/nginx/sites-available/
sudo nginx -t
sudo systemctl reload nginx

docker compose -f docker-compose.prod.yml build --no-cache frontend backend
docker compose -f docker-compose.prod.yml up -d

echo "If /health or /docs still 404, run: ./scripts/fix-public-urls.sh"
echo "Test: curl -s https://www.gnkalgo.com/health && curl -s https://www.gnkalgo.com/api/v1/"
