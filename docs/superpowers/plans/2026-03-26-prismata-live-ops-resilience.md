# prismata.live Operations & Resilience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Secure prismata.live with database backups, disk monitoring, credential hygiene, deploy safety, staging workflow for Wonderboat, and health alerting — all implementable via SSH to the production VPS.

**Architecture:** Fresh shell scripts deployed to `/opt/site/ops/` on the VPS. Cron-driven (no daemons). Discord webhook for alerts. S3 for backups. Subdomain-based staging at `staging.prismata.live` (Wonderboat pushes to `staging` branch, previews on separate subdomain, merges staging→master on GitHub to promote to prod). VPS is pull-only — no git push from server. All scripts are standalone — no dependencies on existing watcher or ladder_tracker code.

**Tech Stack:** Bash scripts, cron, AWS CLI (S3), SQLite3, Discord webhooks, certbot, systemd, nginx

**VPS Access:** `ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP>`

**VPS State (verified 2026-03-26):**
- Disk: 91% used (739MB free) — **cleanup is urgent**
- AWS CLI: **not installed** — must install before S3 tasks
- Deploy key: **read-only** — VPS cannot push to GitHub
- SQLite: default journal mode (not WAL) — `.db` mtime is reliable for freshness
- Branch: `master` (confirmed on both local and VPS)
- Services confirmed: `prismata-site`, `<SSH_KEY>`, `prismata-webhook` (all active)

---

## File Structure

All new ops scripts live in `/opt/site/ops/` on the VPS (fresh directory).

| File (on VPS) | Responsibility |
|---|---|
| `/opt/site/ops/backup_db.sh` | Daily SQLite backup to S3 with rotation |
| `/opt/site/ops/health_check.sh` | 5-min cron: service health + disk + DB freshness → Discord |
| `/opt/site/ops/deploy.sh` | Safe deploy with build verification + rollback |
| `/opt/site/ops/RECOVERY.md` | Disaster recovery playbook |
| `/opt/site/ops/.env` | Discord webhook URL, S3 bucket name (sourced by scripts) |
| `/opt/site/ops/deploy_staging.sh` | Auto-deploy staging branch to port 3001 |
| `/opt/staging/` | Staging site clone (separate directory, port 3001) |

Also modified on VPS:
| File | Change |
|---|---|
| `/opt/site/webhook_listener.py` | Point deploy command at new `/opt/site/ops/deploy.sh`; add staging branch handler; add HMAC verification |
| `/home/ubuntu/.prismata_multi_credentials` | Verify permissions (chmod 600) |
| `/etc/nginx/sites-available/prismata.live` | Add `/staging/` location block proxying to port 3001 |
| `/etc/systemd/system/prismata-staging.service` | Staging Next.js service on port 3001 |
| crontab | Add backup + health check entries |

---

## Task 1: Create ops directory and environment config

**Files:**
- Create: `/opt/site/ops/.env`
- Create: `/opt/site/ops/` directory

- [ ] **Step 1: SSH in and create the ops directory**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "mkdir -p /opt/site/ops && ls -la /opt/site/ops"
```

Expected: Empty directory listing.

- [ ] **Step 2: Check disk space baseline**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "df -h / && echo '---' && du -sh /opt/site/node_modules /opt/site/.next /var/log /tmp 2>/dev/null | sort -rh"
```

Record the output — this is our baseline.

- [ ] **Step 3: Install AWS CLI (confirmed missing)**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo apt update && sudo apt install -y awscli sqlite3 && aws --version"
```

Expected: `aws-cli/1.x.x` or `aws-cli/2.x.x`. Also installs `sqlite3` (needed for backup integrity checks).

- [ ] **Step 3b: Configure AWS credentials**

If no instance role is attached (likely), configure static credentials:
```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "aws configure"
```

Enter: AWS Access Key ID, Secret, region=us-east-1, output=json.

Verify: `aws sts get-caller-identity`

**Preferred alternative:** Attach an IAM instance role with S3-only permissions to avoid storing static credentials. This requires AWS Console → IAM → Create Role → EC2 → attach `AmazonS3FullAccess` (or a scoped policy) → EC2 → Actions → Security → Modify IAM Role.

- [ ] **Step 4: Create the .env config file**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat > /opt/site/ops/.env << 'EOF'
# prismata.live ops config
S3_BUCKET=prismata-live-backups
DB_PATH=/opt/site/prismata_ladder.db
SITE_DIR=/opt/site
DISCORD_WEBHOOK=""
EOF
chmod 600 /opt/site/ops/.env"
```

Note: `DISCORD_WEBHOOK` is empty until the user creates one in Discord settings. We'll prompt for it in Task 4.

- [ ] **Step 5: Verify**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat /opt/site/ops/.env"
```

---

## Task 2: Database backup to S3

**Files:**
- Create: `/opt/site/ops/backup_db.sh`
- Modify: crontab

- [ ] **Step 1: Create the S3 bucket with hardening**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> << 'REMOTE'
# Use a unique bucket name (globally unique requirement)
BUCKET="prismata-live-backups-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo surfinite)"

aws s3 mb "s3://${BUCKET}" --region us-east-1 2>&1 || echo 'Bucket may already exist'

# Block all public access
aws s3api put-public-access-block --bucket "${BUCKET}" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Enable server-side encryption
aws s3api put-bucket-encryption --bucket "${BUCKET}" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# Lifecycle: auto-delete after 90 days (belt and suspenders with script rotation)
aws s3api put-bucket-lifecycle-configuration --bucket "${BUCKET}" --lifecycle-configuration \
  '{"Rules":[{"ID":"expire-old-backups","Status":"Enabled","Filter":{"Prefix":"daily/"},"Expiration":{"Days":90}}]}'

echo "Bucket ${BUCKET} created and hardened"
REMOTE
```

Update the `S3_BUCKET` value in `/opt/site/ops/.env` with the actual bucket name used.

- [ ] **Step 2: Test that S3 access works**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "source /opt/site/ops/.env && aws s3 ls s3://\${S3_BUCKET}/ 2>&1"
```

Expected: Empty listing or existing files. If "Access Denied", check AWS credentials (Task 1 Step 3b).

- [ ] **Step 3: Write backup_db.sh**

Key improvements over v1: explicit PATH for cron, flock to prevent concurrent runs, integrity check before upload.

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat > /opt/site/ops/backup_db.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# Explicit PATH for cron environment
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Prevent concurrent runs
exec 200>/tmp/prismata_backup.lock
if ! flock -n 200; then
    echo \"[\$(date)] Backup already running, skipping\"
    exit 0
fi

source /opt/site/ops/.env

TIMESTAMP=\$(date +%Y%m%d_%H%M%S)
BACKUP_TMP=\"/tmp/prismata_ladder_backup.db\"
BACKUP_FILE=\"/tmp/prismata_ladder_\${TIMESTAMP}.db.gz\"

# Safe SQLite backup (consistent snapshot)
sqlite3 \"\$DB_PATH\" \".backup \$BACKUP_TMP\"

# Integrity check before uploading
INTEGRITY=\$(sqlite3 \"\$BACKUP_TMP\" \"PRAGMA integrity_check;\" 2>&1)
if [ \"\$INTEGRITY\" != \"ok\" ]; then
    echo \"[\$(date)] INTEGRITY CHECK FAILED: \$INTEGRITY\"
    rm -f \"\$BACKUP_TMP\"
    exit 1
fi

gzip -c \"\$BACKUP_TMP\" > \"\$BACKUP_FILE\"
rm \"\$BACKUP_TMP\"

# Upload to S3
aws s3 cp \"\$BACKUP_FILE\" \"s3://\${S3_BUCKET}/daily/\" --quiet
rm \"\$BACKUP_FILE\"

# Rotate: keep last 30 daily backups (lifecycle rule is belt-and-suspenders)
BACKUP_COUNT=\$(aws s3 ls \"s3://\${S3_BUCKET}/daily/\" | wc -l)
if [ \"\$BACKUP_COUNT\" -gt 30 ]; then
    DELETE_COUNT=\$((BACKUP_COUNT - 30))
    aws s3 ls \"s3://\${S3_BUCKET}/daily/\" | sort | head -n \"\$DELETE_COUNT\" | \\
        awk '{print \$4}' | while read -r f; do
            aws s3 rm \"s3://\${S3_BUCKET}/daily/\$f\" --quiet
        done
fi

echo \"[\$(date)] Backup OK: prismata_ladder_\${TIMESTAMP}.db.gz (\$(aws s3 ls s3://\${S3_BUCKET}/daily/ | wc -l) kept)\"
SCRIPT
chmod +x /opt/site/ops/backup_db.sh"
```

- [ ] **Step 4: Test the backup script manually**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "/opt/site/ops/backup_db.sh"
```

Expected: `[<date>] Backup complete: prismata_ladder_<timestamp>.db.gz (kept 1 backups)`

- [ ] **Step 5: Verify backup landed in S3**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "aws s3 ls s3://prismata-live-backups/daily/"
```

Expected: One `.db.gz` file, ~2-5MB.

- [ ] **Step 6: One-time restore test**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "source /opt/site/ops/.env && \
   LATEST=\$(aws s3 ls s3://\${S3_BUCKET}/daily/ | sort | tail -1 | awk '{print \$4}') && \
   aws s3 cp s3://\${S3_BUCKET}/daily/\${LATEST} /tmp/restore_test.db.gz && \
   gunzip -c /tmp/restore_test.db.gz > /tmp/restore_test.db && \
   sqlite3 /tmp/restore_test.db 'PRAGMA integrity_check; SELECT count(*) FROM games;' && \
   rm /tmp/restore_test.db /tmp/restore_test.db.gz && \
   echo 'Restore test PASSED'"
```

Expected: `ok` + game count + "Restore test PASSED".

- [ ] **Step 7: Add to cron — daily at 4 AM UTC**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  '(crontab -l 2>/dev/null | grep -v backup_db; echo "0 4 * * * /opt/site/ops/backup_db.sh >> /var/log/prismata_backup.log 2>&1") | crontab -'
```

- [ ] **Step 7: Verify cron entry**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "crontab -l"
```

Expected: Line with `0 4 * * * /opt/site/ops/backup_db.sh`.

---

## Task 3: Disk cleanup

**Files:** None (one-time commands)

- [ ] **Step 1: Clean npm cache**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "npm cache clean --force 2>&1; echo '---'; df -h /"
```

Record space reclaimed.

- [ ] **Step 2: Clean apt cache**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo apt clean; echo '---'; df -h /"
```

- [ ] **Step 3: Vacuum systemd journal to 7 days**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo journalctl --vacuum-time=7d 2>&1; echo '---'; df -h /"
```

- [ ] **Step 4: Check for large unexpected files**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo du -sh /opt/site/* /var/log/* /tmp/* 2>/dev/null | sort -rh | head -20"
```

Review output — flag anything unexpected before deleting.

- [ ] **Step 5: Record final disk state**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "df -h /"
```

Compare with Task 1 Step 2 baseline.

---

## Task 4: Health check script with Discord alerts

**Files:**
- Create: `/opt/site/ops/health_check.sh`
- Modify: `/opt/site/ops/.env` (add Discord webhook URL)
- Modify: crontab

**Prerequisite:** User must create a Discord webhook in their server's settings and provide the URL. We'll store it in `.env`.

- [ ] **Step 1: Ask user for Discord webhook URL**

The user needs to go to Discord → Server Settings → Integrations → Webhooks → New Webhook. Copy the URL.

Then update `.env`:
```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sed -i 's|^DISCORD_WEBHOOK=.*|DISCORD_WEBHOOK=\"https://discord.com/api/webhooks/THEIR_URL_HERE\"|' /opt/site/ops/.env"
```

- [ ] **Step 2: Write health_check.sh**

Key improvements: explicit PATH for cron, alert deduplication (only alerts on state change, sends recovery message when cleared), no Discord spam.

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat > /opt/site/ops/health_check.sh << 'SCRIPT'
#!/bin/bash
set -uo pipefail

# Explicit PATH for cron environment
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

source /opt/site/ops/.env

STATE_FILE=\"/tmp/prismata_health_state\"
ALERTS=\"\"

# Check systemd services
for svc in prismata-site <SSH_KEY> prismata-webhook nginx; do
    if ! systemctl is-active --quiet \"\$svc\" 2>/dev/null; then
        ALERTS+=\"svc_\${svc}_down \"
    fi
done

# Check disk usage (warn at 85%, critical at 92%)
USAGE=\$(df / | tail -1 | awk '{print \$5}' | tr -d '%')
if [ \"\$USAGE\" -gt 92 ]; then
    ALERTS+=\"disk_critical_\${USAGE} \"
elif [ \"\$USAGE\" -gt 85 ]; then
    ALERTS+=\"disk_warn_\${USAGE} \"
fi

# Check DB freshness (mtime-based — valid since DB is in default journal mode, not WAL)
if [ -f \"\$DB_PATH\" ]; then
    DB_AGE=\$(( \$(date +%s) - \$(stat -c %Y \"\$DB_PATH\") ))
    if [ \"\$DB_AGE\" -gt 600 ]; then
        ALERTS+=\"db_stale_\$((DB_AGE / 60))min \"
    fi
fi

# Check RAM (warn if swap usage > 500MB)
SWAP_USED=\$(free -m | awk '/Swap:/ {print \$3}')
if [ \"\$SWAP_USED\" -gt 500 ]; then
    ALERTS+=\"swap_high_\${SWAP_USED}MB \"
fi

# Alert deduplication: only notify on state CHANGE
PREV_STATE=\"\"
[ -f \"\$STATE_FILE\" ] && PREV_STATE=\$(cat \"\$STATE_FILE\")
echo \"\$ALERTS\" > \"\$STATE_FILE\"

send_discord() {
    local msg=\"\$1\"
    if [ -n \"\${DISCORD_WEBHOOK:-}\" ]; then
        curl -s -H \"Content-Type: application/json\" \\
            -d \"{\\\"content\\\":\\\"\$msg\\\"}\" \\
            \"\$DISCORD_WEBHOOK\" > /dev/null
    fi
}

if [ -n \"\$ALERTS\" ] && [ \"\$ALERTS\" != \"\$PREV_STATE\" ]; then
    # New or changed alert — notify Discord
    HUMAN_MSG=\"\"
    for alert in \$ALERTS; do
        case \"\$alert\" in
            svc_*_down) svc=\$(echo \"\$alert\" | sed 's/svc_//;s/_down//'); HUMAN_MSG+=\"Service **\$svc** is DOWN. \" ;;
            disk_critical_*) pct=\$(echo \"\$alert\" | sed 's/disk_critical_//'); HUMAN_MSG+=\"CRITICAL: Disk at **\${pct}%**. \" ;;
            disk_warn_*) pct=\$(echo \"\$alert\" | sed 's/disk_warn_//'); HUMAN_MSG+=\"Disk at **\${pct}%**. \" ;;
            db_stale_*) age=\$(echo \"\$alert\" | sed 's/db_stale_//'); HUMAN_MSG+=\"DB stale: **\$age**. \" ;;
            swap_high_*) mb=\$(echo \"\$alert\" | sed 's/swap_high_//'); HUMAN_MSG+=\"Swap high: **\$mb**. \" ;;
        esac
    done
    send_discord \"⚠️ **prismata.live** \$HUMAN_MSG\"
    echo \"[\$(date)] ALERT (new): \$ALERTS\"
elif [ -z \"\$ALERTS\" ] && [ -n \"\$PREV_STATE\" ]; then
    # Was alerting, now clear — send recovery
    send_discord \"✅ **prismata.live** all clear — issues resolved\"
    echo \"[\$(date)] RECOVERED (was: \$PREV_STATE)\"
else
    echo \"[\$(date)] OK: disk=\${USAGE}% swap=\${SWAP_USED}MB\"
fi
SCRIPT
chmod +x /opt/site/ops/health_check.sh"
```

- [ ] **Step 3: Test health check (should report OK)**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "/opt/site/ops/health_check.sh"
```

Expected: `[<date>] OK: disk=XX% swap=XXmb`

- [ ] **Step 4: Test Discord alert delivery (force a fake alert)**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  'source /opt/site/ops/.env; curl -s -H "Content-Type: application/json" -d "{\"content\":\"✅ prismata.live health check test — if you see this, alerts work!\"}" "$DISCORD_WEBHOOK"'
```

Expected: Message appears in the Discord channel.

- [ ] **Step 5: Add to cron — every 5 minutes**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  '(crontab -l 2>/dev/null | grep -v health_check; echo "*/5 * * * * /opt/site/ops/health_check.sh >> /var/log/prismata_health.log 2>&1") | crontab -'
```

- [ ] **Step 6: Verify cron**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "crontab -l"
```

Expected: Both backup_db and health_check entries present.

---

## Task 5: Safe deploy script with rollback

**Files:**
- Create: `/opt/site/ops/deploy.sh`
- Modify: `/opt/site/webhook_listener.py` (point to new deploy script)

- [ ] **Step 1: Read current deploy.sh to understand what it does**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat /opt/site/deploy.sh 2>/dev/null || echo 'No existing deploy.sh'"
```

- [ ] **Step 2: Read webhook_listener.py to find the deploy command reference**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat /opt/site/webhook_listener.py 2>/dev/null || echo 'File not found'"
```

- [ ] **Step 3: Write the new safe deploy script**

Key improvements: explicit PATH, flock for concurrency, `npm ci` instead of `npm install --production`, `git fetch`+`reset --hard` instead of `git pull`, clean rollback without detached HEAD.

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat > /opt/site/ops/deploy.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# Explicit PATH for cron/webhook environment
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Prevent concurrent deploys
exec 200>/tmp/prismata_deploy.lock
if ! flock -n 200; then
    echo \"[\$(date)] Deploy already running, skipping\"
    exit 0
fi

source /opt/site/ops/.env

cd \"\$SITE_DIR\"
PREV_COMMIT=\$(git rev-parse HEAD)
echo \"[\$(date)] Deploy starting (current: \$(git rev-parse --short HEAD))\"

# Fetch and fast-forward (no merge commits, no detached HEAD)
git fetch origin master
NEW_COMMIT=\$(git rev-parse origin/master)

if [ \"\$PREV_COMMIT\" = \"\$NEW_COMMIT\" ]; then
    echo \"[\$(date)] No changes to deploy\"
    exit 0
fi

git checkout master
git reset --hard origin/master

# Install deps (npm ci for deterministic, includes devDeps needed for build)
cd <ladder>-site
npm ci 2>&1 | tail -5

# Build — if this fails, rollback
if ! npm run build 2>&1 | tail -20; then
    echo \"[\$(date)] BUILD FAILED — rolling back to \$(git rev-parse --short \$PREV_COMMIT)\"
    git checkout master
    git reset --hard \"\$PREV_COMMIT\"
    npm ci 2>&1 | tail -5
    npm run build 2>&1 | tail -5

    if [ -n \"\${DISCORD_WEBHOOK:-}\" ]; then
        curl -s -H \"Content-Type: application/json\" \\
            -d \"{\\\"content\\\":\\\"🔴 **prismata.live deploy FAILED** — rolled back to \$(git rev-parse --short \$PREV_COMMIT)\\\"}\" \\
            \"\$DISCORD_WEBHOOK\" > /dev/null
    fi
    exit 1
fi

# Restart site
sudo systemctl restart prismata-site

# Smoke test — wait 5s for startup, then check
sleep 5
if curl -sf http://localhost:3000 > /dev/null 2>&1; then
    echo \"[\$(date)] Deploy SUCCESS: \$(git rev-parse --short HEAD)\"
    if [ -n \"\${DISCORD_WEBHOOK:-}\" ]; then
        curl -s -H \"Content-Type: application/json\" \\
            -d \"{\\\"content\\\":\\\"✅ **prismata.live deployed** \$(git rev-parse --short HEAD)\\\"}\" \\
            \"\$DISCORD_WEBHOOK\" > /dev/null
    fi
else
    echo \"[\$(date)] SMOKE TEST FAILED — rolling back\"
    git checkout master
    git reset --hard \"\$PREV_COMMIT\"
    npm ci 2>&1 | tail -5
    npm run build 2>&1 | tail -5
    sudo systemctl restart prismata-site

    if [ -n \"\${DISCORD_WEBHOOK:-}\" ]; then
        curl -s -H \"Content-Type: application/json\" \\
            -d \"{\\\"content\\\":\\\"🔴 **prismata.live deploy FAILED smoke test** — rolled back to \$(git rev-parse --short \$PREV_COMMIT)\\\"}\" \\
            \"\$DISCORD_WEBHOOK\" > /dev/null
    fi
    exit 1
fi
SCRIPT
chmod +x /opt/site/ops/deploy.sh"
```

- [ ] **Step 4: Update webhook_listener.py to use new deploy script**

Read the file, find the deploy command reference, update it to call `/opt/site/ops/deploy.sh`. The exact edit depends on what we find in Step 2.

- [ ] **Step 5: Test the deploy script manually**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "/opt/site/ops/deploy.sh 2>&1"
```

Expected: Either "No changes to deploy" or a successful build + restart.

---

## Task 6: Staging environment for Wonderboat

**Goal:** Wonderboat pushes to a `staging` branch → auto-builds on VPS at port 3001 → previews at `https://staging.prismata.live` → when happy, merges staging→master on GitHub (auto-deploys to prod).

**Key design decisions (from review feedback):**
- **Subdomain** (`staging.prismata.live`) not subpath (`/staging/`): Next.js has 30+ hardcoded absolute paths and no `basePath` config. Subpath deployment would break routing silently.
- **VPS stays read-only**: Deploy key is confirmed read-only. No `promote_to_prod.sh` — promotion happens by merging on GitHub.
- **Staging is read-only frontend**: Shares prod DB for data display but cannot write to it. No separate DB needed.

**Files:**
- Create: `/opt/staging/` (staging site directory)
- Create: `/etc/systemd/system/prismata-staging.service`
- Create: `/opt/site/ops/deploy_staging.sh`
- Modify: `/etc/nginx/sites-available/prismata.live` (add staging server block)
- Modify: `/opt/site/webhook_listener.py` (handle staging branch pushes)
- Modify: DNS (add `staging.prismata.live` A record on Porkbun)

- [ ] **Step 1: Add DNS record for staging.prismata.live**

Manual step: Go to Porkbun → DNS → Add A record:
- Host: `staging`
- Answer: `<OLD_VPS_IP>`
- TTL: 600

Wait for propagation (~5 min): `dig staging.prismata.live`

- [ ] **Step 2: Create staging directory with separate clone**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo mkdir -p /opt/staging && sudo chown ubuntu:ubuntu /opt/staging && \
   git clone git@github.com:<LADDER_REPO_OWNER>/<ladder>.git /opt/staging/<ladder>"
```

- [ ] **Step 3: Create the staging branch on GitHub**

Do this from your local machine (not VPS — deploy key is read-only):
```bash
cd <LADDER_REPO_PATH>
git checkout master && git pull
git checkout -b staging
git push -u origin staging
```

Then on VPS, fetch it:
```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cd /opt/staging/<ladder> && git fetch origin && git checkout staging"
```

- [ ] **Step 4: Build staging site**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cd /opt/staging/<ladder>/<ladder>-site && \
   npm ci && npm run build"
```

- [ ] **Step 5: Create staging systemd service**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo tee /etc/systemd/system/prismata-staging.service > /dev/null << 'EOF'
[Unit]
Description=Prismata Ladder Staging Site
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/staging/<ladder>/<ladder>-site
Environment=PORT=3001
Environment=NODE_ENV=production
ExecStart=/usr/bin/npm start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable prismata-staging && sudo systemctl start prismata-staging"
```

- [ ] **Step 6: Verify staging is running on port 3001**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "curl -sf http://localhost:3001 > /dev/null && echo 'Staging OK on port 3001' || echo 'FAILED'"
```

- [ ] **Step 7: Add nginx server block for staging.prismata.live**

Read current nginx config:
```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat /etc/nginx/sites-available/prismata.live"
```

Add a new `server` block (separate from the prod block) for the staging subdomain:
```nginx
server {
    server_name staging.prismata.live;

    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    listen 80;
}
```

Then get SSL for the subdomain:
```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo nginx -t && sudo systemctl reload nginx && \
   sudo certbot --nginx -d staging.prismata.live --non-interactive --agree-tos"
```

- [ ] **Step 8: Verify staging accessible at https://staging.prismata.live**

```bash
curl -sf https://staging.prismata.live > /dev/null && echo "Staging OK" || echo "FAILED"
```

- [ ] **Step 9: Write deploy_staging.sh**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat > /opt/site/ops/deploy_staging.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Prevent concurrent staging deploys
exec 200>/tmp/prismata_staging_deploy.lock
if ! flock -n 200; then
    echo \"[\$(date)] Staging deploy already running, skipping\"
    exit 0
fi

source /opt/site/ops/.env

cd /opt/staging/<ladder>
echo \"[\$(date)] Staging deploy starting\"

git fetch origin staging
git checkout staging
git reset --hard origin/staging

cd <ladder>-site
npm ci 2>&1 | tail -5

if ! npm run build 2>&1 | tail -20; then
    echo \"[\$(date)] Staging BUILD FAILED\"
    if [ -n \"\${DISCORD_WEBHOOK:-}\" ]; then
        curl -s -H \"Content-Type: application/json\" \\
            -d \"{\\\"content\\\":\\\"🟡 **Staging build FAILED** — check logs\\\"}\" \\
            \"\$DISCORD_WEBHOOK\" > /dev/null
    fi
    exit 1
fi

sudo systemctl restart prismata-staging

sleep 3
if curl -sf http://localhost:3001 > /dev/null 2>&1; then
    echo \"[\$(date)] Staging deployed: \$(git rev-parse --short HEAD)\"
    if [ -n \"\${DISCORD_WEBHOOK:-}\" ]; then
        curl -s -H \"Content-Type: application/json\" \\
            -d \"{\\\"content\\\":\\\"🟡 **Staging updated** — preview at https://staging.prismata.live (\$(git rev-parse --short HEAD))\\\"}\" \\
            \"\$DISCORD_WEBHOOK\" > /dev/null
    fi
else
    echo \"[\$(date)] Staging smoke test FAILED\"
    exit 1
fi
SCRIPT
chmod +x /opt/site/ops/deploy_staging.sh"
```

- [ ] **Step 10: Update webhook_listener.py to handle staging branch**

Read the webhook listener to understand its structure, then add a handler that runs `deploy_staging.sh` when it receives a push to the `staging` branch (vs `deploy.sh` for `master`). The webhook payload includes `ref: "refs/heads/staging"`.

General approach — add branch detection:
```python
branch = payload.get('ref', '').split('/')[-1]
if branch == 'staging':
    subprocess.Popen(['/opt/site/ops/deploy_staging.sh'], ...)
elif branch == 'master':
    subprocess.Popen(['/opt/site/ops/deploy.sh'], ...)
```

Also ensure the GitHub webhook is configured to send push events for ALL branches (not just master). Check in GitHub → Settings → Webhooks → Edit → "Which events" → "Just the push event" with no branch filter.

- [ ] **Step 11: Test the full workflow**

1. Push a trivial change to `staging` branch from your local machine
2. Verify staging auto-deploys and Discord notification appears
3. Preview at `https://staging.prismata.live`
4. If happy: merge staging→master on GitHub (creates PR or direct merge)
5. Verify prod auto-deploys from master push

**Wonderboat's workflow after setup:**
1. `git push origin staging` (or merge PR into staging)
2. Wait for Discord "Staging updated" notification (~60s)
3. Preview at `https://staging.prismata.live`
4. If happy: merge staging→master on GitHub (auto-deploys to prod)
5. No SSH needed — entire flow is GitHub-driven

---

## Task 7: Credential hygiene (renumbered from Task 6)

**Files:**
- Modify: `/home/ubuntu/.prismata_multi_credentials` (permissions)
- Modify: `/opt/site/webhook_listener.py` (move secret to env var)
- Modify: systemd service (add env var)

- [ ] **Step 1: Lock down credential file permissions**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "chmod 600 /home/ubuntu/.prismata_multi_credentials && ls -la /home/ubuntu/.prismata_multi_credentials"
```

Expected: `-rw-------` permissions.

- [ ] **Step 2: Check current webhook secret handling**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "grep -n 'secret\|SECRET\|webhook' /opt/site/webhook_listener.py 2>/dev/null | head -10"
```

- [ ] **Step 3: Generate new webhook secret**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "python3 -c 'import secrets; print(secrets.token_hex(32))'"
```

Save this output — it goes into both `/opt/site/ops/.env` and GitHub webhook settings.

- [ ] **Step 4: Add webhook secret to .env**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "echo 'WEBHOOK_SECRET=\"<NEW_SECRET_HERE>\"' >> /opt/site/ops/.env"
```

- [ ] **Step 5: Add EnvironmentFile to webhook systemd service**

Cleaner than manual parsing — systemd injects env vars automatically:
```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo sed -i '/\[Service\]/a EnvironmentFile=/opt/site/ops/.env' /etc/systemd/system/prismata-webhook.service && \
   sudo systemctl daemon-reload && sudo systemctl restart prismata-webhook"
```

- [ ] **Step 6: Update webhook_listener.py to use HMAC verification**

The exact edit depends on what we find in Step 2. Replace hardcoded secret with proper GitHub webhook HMAC:
```python
import os, hmac, hashlib

WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '')

def verify_signature(payload_body, signature_header):
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not WEBHOOK_SECRET or not signature_header:
        return False
    expected = 'sha256=' + hmac.new(
        WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)

# In the request handler:
# sig = headers.get('X-Hub-Signature-256', '')
# if not verify_signature(raw_body, sig):
#     return 403, 'Invalid signature'
# Only accept push events:
# if headers.get('X-GitHub-Event') != 'push':
#     return 200, 'Ignored'
```

- [ ] **Step 7: Update GitHub webhook with new secret**

Manual step: Go to GitHub repo → Settings → Webhooks → Edit → Update secret. This must be done by the repo owner (Wonderboat) or someone with admin access.

**Important:** Don't rotate the secret until the new code is deployed and tested. Sequence: deploy new code with HMAC → update GitHub secret → test.

- [ ] **Step 8: Test webhook still works**

Push a trivial commit (whitespace change) and verify the deploy triggers.

- [ ] **Step 9: Verify secrets aren't exposed in logs**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat /opt/site/ops/.env | sed 's/=.*/=<REDACTED>/' && echo '--- permissions ---' && ls -la /opt/site/ops/.env"
```

Expected: Values redacted, permissions `-rw-------`.

---

## Task 8: SSL verification

**Files:** None (verification only, possible one-line config fix)

- [ ] **Step 1: Check certbot timer is active**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo systemctl status certbot.timer 2>&1 | head -5"
```

Expected: `Active: active (waiting)`

- [ ] **Step 2: Check certificate expiry date**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo certbot certificates 2>&1"
```

Expected: Certificate for `prismata.live`, expiry date ~90 days from last renewal.

- [ ] **Step 3: Dry-run renewal**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo certbot renew --dry-run 2>&1 | tail -10"
```

Expected: "Congratulations, all simulated renewals succeeded"

- [ ] **Step 4: Verify nginx reload hook exists**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat /etc/letsencrypt/renewal/prismata.live.conf 2>/dev/null | grep -i deploy"
```

If no deploy hook found, add one:
```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo sh -c 'echo \"deploy-hook = systemctl reload nginx\" >> /etc/letsencrypt/renewal/prismata.live.conf'"
```

---

## Task 9: Log rotation

**Files:**
- Create: `/etc/logrotate.d/prismata-live`

- [ ] **Step 1: Create logrotate config**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo tee /etc/logrotate.d/prismata-live > /dev/null << 'EOF'
/var/log/prismata_backup.log
/var/log/prismata_health.log
{
    weekly
    rotate 4
    compress
    missingok
    notifempty
    create 644 ubuntu ubuntu
}
EOF"
```

- [ ] **Step 2: Verify logrotate config is valid**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "sudo logrotate --debug /etc/logrotate.d/prismata-live 2>&1 | tail -10"
```

Expected: No errors.

---

## Task 10: Recovery playbook (renumbered)

**Files:**
- Create: `/opt/site/ops/RECOVERY.md`

- [ ] **Step 1: Gather instance metadata for the playbook**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "echo 'Instance ID:' && curl -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null && echo && \
   echo 'Volume ID:' && lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT && echo && \
   echo 'Security Group:' && curl -s http://169.254.169.254/latest/meta-data/security-groups 2>/dev/null && echo && \
   echo 'AMI:' && curl -s http://169.254.169.254/latest/meta-data/ami-id 2>/dev/null && echo"
```

- [ ] **Step 2: Write RECOVERY.md**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "cat > /opt/site/ops/RECOVERY.md << 'DOC'
# prismata.live Disaster Recovery Playbook

## Quick Reference
- **Instance**: i-0553afd9fd5fff4c3 (t3.micro, us-east-1)
- **IP**: <OLD_VPS_IP>
- **SSH**: ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP>
- **Domain**: prismata.live (Porkbun, expires 2027-03-24)
- **Repo**: <LADDER_REPO_OWNER>/<ladder> (deploy key: read-only)
- **Backups**: s3://prismata-live-backups/daily/

## Scenario 1: Service crashed (site down, SSH works)

Check which service is down:
    sudo systemctl status prismata-site <SSH_KEY> prismata-webhook nginx

Restart it:
    sudo systemctl restart <service-name>

Check logs:
    sudo journalctl -u <service-name> --since '10 min ago'

## Scenario 2: Instance unreachable but not terminated

1. AWS Console → EC2 → check instance state
2. Try reboot: aws ec2 reboot-instances --instance-ids i-0553afd9fd5fff4c3
3. Wait 2 min, retry SSH
4. If stuck in 'stopping': force stop, then start

## Scenario 3: Instance terminated / EBS lost

1. Launch new t3.micro:
   - Ubuntu 24.04, us-east-1a
   - Same security group (ports 22, 80, 443, 8765)
   - 16GB gp3 EBS

2. SSH in and set up:
   sudo apt update && sudo apt install -y python3-pip nginx certbot python3-certbot-nginx awscli sqlite3 nodejs npm
   sudo ln -sf /usr/bin/python3 /usr/bin/python
   sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile

3. Clone repo:
   sudo mkdir -p /opt/site && sudo chown ubuntu:ubuntu /opt/site
   git clone git@github.com:<LADDER_REPO_OWNER>/<ladder>.git /opt/site

4. Restore DB from S3:
   aws s3 ls s3://prismata-live-backups/daily/ | sort | tail -1
   aws s3 cp s3://prismata-live-backups/daily/<LATEST>.db.gz /tmp/
   gunzip /tmp/<LATEST>.db.gz
   mv /tmp/<LATEST>.db /opt/site/prismata_ladder.db

5. Restore credentials:
   scp ~/.prismata_multi_credentials to /home/ubuntu/

6. Build site:
   cd /opt/site/<ladder>-site && npm install && npm run build

7. Set up SSL:
   sudo certbot --nginx -d prismata.live

8. Update Porkbun DNS A record to new IP

9. Restore systemd services (create .service files)

10. Restore ops scripts:
    mkdir -p /opt/site/ops
    # Re-run the ops setup or restore from repo

## Scenario 4: DB corrupted

1. Stop services: sudo systemctl stop prismata-site <SSH_KEY>
2. Backup corrupted file: mv /opt/site/prismata_ladder.db /opt/site/prismata_ladder.db.corrupted
3. Restore from S3 (see Scenario 3, step 4)
4. Restart services: sudo systemctl start prismata-site <SSH_KEY>
5. Data loss = time since last backup (max 24h)

## Service management cheatsheet

    sudo systemctl start|stop|restart|status prismata-site
    sudo systemctl start|stop|restart|status <SSH_KEY>
    sudo systemctl start|stop|restart|status prismata-webhook
    sudo systemctl start|stop|restart|status nginx

## Log locations

    /var/log/prismata_backup.log    — backup script output
    /var/log/prismata_health.log    — health check output
    sudo journalctl -u <service>    — systemd service logs
DOC"
```

- [ ] **Step 3: Verify the playbook is readable**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "head -30 /opt/site/ops/RECOVERY.md"
```

---

## Task 11: Create AMI snapshot

**Files:** None (AWS CLI command from local machine)

- [ ] **Step 1: Run a DB backup first (AMI is crash-consistent, not app-consistent)**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP> \
  "/opt/site/ops/backup_db.sh"
```

- [ ] **Step 2: Create AMI with tags (no-reboot to avoid downtime)**

```bash
aws ec2 create-image \
  --instance-id i-0553afd9fd5fff4c3 \
  --name "prismata-live-$(date +%Y%m%d)" \
  --description "prismata.live with ops scripts, backups configured" \
  --tag-specifications "ResourceType=image,Tags=[{Key=Purpose,Value=prismata-live-baseline},{Key=Date,Value=$(date +%Y-%m-%d)}]" \
  --no-reboot \
  --region us-east-1
```

Expected: Returns an AMI ID (`ami-xxxx`). Record it.

Note: AMI is for fast machine rebuild. The authoritative DB recovery source is S3 backups, not the AMI.

- [ ] **Step 3: Verify AMI creation started**

```bash
aws ec2 describe-images --owners self --region us-east-1 \
  --query 'Images[*].[ImageId,Name,State]' --output table
```

Expected: AMI in `pending` or `available` state.

- [ ] **Step 4: Add AMI ID to RECOVERY.md**

Update the playbook on the VPS with the AMI ID for quick restore reference.

**Retention:** Review and deregister old AMIs quarterly. Each AMI snapshot costs ~$0.50/month.

---

## Task 12: Set up UptimeRobot external monitoring

**Files:** None (web-based setup)

This is a manual step — the user signs up at uptimerobot.com (free tier).

- [ ] **Step 1: Create UptimeRobot account**

Go to https://uptimerobot.com, sign up free.

- [ ] **Step 2: Add monitors**

Create 2 HTTP(s) monitors (5-min check interval):
1. `https://prismata.live` — keyword "Prismata" in response
2. `https://prismata.live/data/api.json` — HTTP 200 check (confirms data pipeline)

- [ ] **Step 3: Configure alerts**

Add alert contact: email and/or Discord webhook integration.

- [ ] **Step 4: Verify monitoring works**

Check UptimeRobot dashboard shows both monitors as UP.

---

## Execution Order

### Prod safety principle

Most tasks do NOT touch production services. Only these steps cause prod downtime:
- Task 5 Step 5 (test deploy — may restart `prismata-site`, ~5s)
- Task 7 Steps 5-8 (webhook update — brief webhook unavailability during restart)

All other tasks create new files, add cron jobs, or set up staging — zero prod impact. **Alert the user before any prod-touching step.**

### Dependencies

- Task 1 must complete before Tasks 2, 4, 5, 6, 10 (they depend on `/opt/site/ops/` and `.env`)
- Task 3 (disk cleanup) should run early — disk at 91%, need room for staging `npm ci`
- Task 5 (deploy safety) should complete before Task 6 (staging uses same patterns)
- Task 7 Step 7 (GitHub webhook update) requires Wonderboat or admin access
- Task 6 Step 1 (DNS) needs Porkbun access and propagation time (~5 min)
- Task 6 Step 3 (staging branch) must be done from local machine, not VPS

### Recommended batch order

1. **Batch 1** (foundation + urgent cleanup): Task 1 (ops dir + AWS CLI), Task 3 (disk cleanup), Task 8 (SSL verify)
2. **Batch 2** (core safety): Task 2 (S3 backups), Task 4 (health alerts), Task 9 (log rotation)
3. **Batch 3** (deploy safety): Task 5 (safe deploy script) — **user confirmation before prod test**
4. **Batch 4** (staging): Task 6 (staging.prismata.live) — no prod impact, separate directory
5. **Batch 5** (hardening): Task 7 (credentials + HMAC) — **user confirmation before webhook changes**
6. **Batch 6** (documentation): Task 10 (recovery playbook), Task 11 (AMI snapshot)
7. **Batch 7** (external): Task 12 (UptimeRobot) — user does manually
