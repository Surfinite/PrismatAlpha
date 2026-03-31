#!/usr/bin/env bash
# deadgame/deploy.sh — Deploy DeadGameBot trigger site to site box
set -euo pipefail

KEY=~/.ssh/<SSH_KEY>.pem
HOST=ubuntu@<SITE_EIP>
SSH="ssh -i $KEY $HOST"
SCP="scp -i $KEY"

echo "=== Deploying DeadGameBot trigger site ==="

# Create directories
$SSH "sudo mkdir -p /opt/deadgame/public /opt/deadgame/lib /opt/deadgame/routes"

# Upload server files
$SCP deadgame/server.js $HOST:/tmp/deadgame-server.js
$SCP deadgame/package.json $HOST:/tmp/deadgame-package.json
$SCP deadgame/lib/db.js $HOST:/tmp/deadgame-db.js
$SCP deadgame/lib/auth.js $HOST:/tmp/deadgame-auth.js
$SCP deadgame/routes/bot.js $HOST:/tmp/deadgame-bot.js
$SCP deadgame/public/index.html $HOST:/tmp/deadgame-index.html

# Upload infrastructure
$SCP deadgame/deadgame.service $HOST:/tmp/deadgame.service
$SCP deadgame/deadgame.nginx.conf $HOST:/tmp/deadgame.nginx.conf

# Fetch secrets from SSM
BOT_API_KEY=$(aws ssm get-parameter --name /deadgame/bot-api-key --region us-east-1 --with-decryption --query "Parameter.Value" --output text 2>/dev/null || echo "")
SESSION_SECRET=$(aws ssm get-parameter --name /<service>/session-secret --region us-east-1 --with-decryption --query "Parameter.Value" --output text 2>/dev/null || echo "dev-secret-change-in-production")

# Install files
$SSH "
  sudo cp /tmp/deadgame-server.js /opt/deadgame/server.js
  sudo cp /tmp/deadgame-package.json /opt/deadgame/package.json
  sudo cp /tmp/deadgame-db.js /opt/deadgame/lib/db.js
  sudo cp /tmp/deadgame-auth.js /opt/deadgame/lib/auth.js
  sudo cp /tmp/deadgame-bot.js /opt/deadgame/routes/bot.js
  sudo cp /tmp/deadgame-index.html /opt/deadgame/public/index.html
  sudo chown -R ubuntu:ubuntu /opt/deadgame
"

# Write .env
$SSH "echo 'BOT_API_KEY=$BOT_API_KEY
SESSION_SECRET=$SESSION_SECRET' | sudo tee /opt/deadgame/.env > /dev/null && sudo chmod 600 /opt/deadgame/.env"

# Install dependencies
$SSH "cd /opt/deadgame && npm install --omit=dev"

# Install systemd service
$SSH "sudo cp /tmp/deadgame.service /etc/systemd/system/deadgame.service && sudo systemctl daemon-reload && sudo systemctl enable deadgame && sudo systemctl restart deadgame"

# Install nginx vhost
$SSH "sudo cp /tmp/deadgame.nginx.conf /etc/nginx/sites-available/deadgame.prismata.live && sudo ln -sf /etc/nginx/sites-available/deadgame.prismata.live /etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx"

# SSL certificate
$SSH "sudo certbot --nginx -d deadgame.prismata.live --non-interactive --agree-tos"

# Verify
sleep 2
$SSH "sudo systemctl status deadgame --no-pager" || true
echo ""
echo "=== Checking health ==="
$SSH "curl -s http://localhost:3101/healthz" || echo "Health check failed"

echo ""
echo "=== Deploy complete ==="
echo "Site: https://deadgame.prismata.live"
