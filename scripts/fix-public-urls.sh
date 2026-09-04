#!/usr/bin/env bash
# Fix /health, /docs, /api/v1/ on www.gnkalgo.com — run on Oracle VM as ubuntu.
set -euo pipefail
cd /opt/gnkalgo

echo "==> Pull latest code"
git fetch origin
git checkout main
git pull origin main

echo "==> Update Nginx (proxy /api, /health, /docs to backend)"
sudo cp deploy/nginx/www.gnkalgo.com.conf /etc/nginx/sites-available/www.gnkalgo.com.conf
sudo ln -sf /etc/nginx/sites-available/www.gnkalgo.com.conf /etc/nginx/sites-enabled/www.gnkalgo.com.conf 2>/dev/null || true
sudo nginx -t
sudo systemctl reload nginx

echo "==> Rebuild backend + frontend (API root + proxy routes)"
docker compose -f docker-compose.prod.yml build --no-cache backend frontend
docker compose -f docker-compose.prod.yml up -d

echo "==> Smoke tests"
sleep 5
curl -sf http://127.0.0.1:8000/health | head -c 200 && echo ""
curl -sf http://127.0.0.1:8000/api/v1/ | head -c 200 && echo ""
curl -sf http://127.0.0.1:3000/health | head -c 200 && echo ""

echo "==> Done. Test in browser:"
echo "  https://www.gnkalgo.com/health"
echo "  https://www.gnkalgo.com/docs"
echo "  https://www.gnkalgo.com/api/v1/"
