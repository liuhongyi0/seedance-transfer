#!/bin/bash
# Seedance Studio — Let's Encrypt SSL certificate initial setup
# Run once before first production docker compose up.
# Requires: domain DNS pointing to this server, port 80 open, docker compose.
#
# Usage:
#   chmod +x deploy/certbot-init.sh
#   ./deploy/certbot-init.sh                           # production
#   ./deploy/certbot-init.sh see4dance.com admin@see4dance.com 1  # staging test

set -euo pipefail

DOMAIN="${1:-see4dance.com}"
EMAIL="${2:-admin@see4dance.com}"
STAGING="${3:-0}"

STAGING_FLAG=""
if [ "$STAGING" = "1" ]; then
    STAGING_FLAG="--staging"
    echo "⚠️  Staging mode — test cert only (no rate limits)"
fi

echo "🔐 Requesting Let's Encrypt certificate for: $DOMAIN"
echo "   Email: $EMAIL"

# Step 1: Start nginx with init config (HTTP only, no SSL)
echo "→ Starting nginx with HTTP-only config for ACME challenge..."
docker compose -f docker-compose.yml -f docker-compose.init-ssl.yml up -d nginx
sleep 3

# Step 2: Run certbot with webroot authenticator
echo "→ Running certbot..."
docker run --rm \
    -v seedance-transfer_certbot_www:/var/www/certbot \
    -v seedance-transfer_certbot_conf:/etc/letsencrypt \
    certbot/certbot:latest \
    certonly --webroot \
    --webroot-path=/var/www/certbot \
    $STAGING_FLAG \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

# Step 3: Restart nginx with full SSL config
echo ""
echo "✅ Certificate obtained. Restarting nginx with SSL config..."
docker compose -f docker-compose.yml up -d nginx

echo ""
echo "🔒 HTTPS setup complete!"
echo "   Certificate live at: /etc/letsencrypt/live/$DOMAIN/"
echo "   Auto-renewal: certbot service (checks every 12h)"
echo "   Verify: curl -I https://$DOMAIN"
