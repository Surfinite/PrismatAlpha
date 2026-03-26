# prismata.live — Operations Guide for Contributors

**Last updated:** 2026-03-26
**Site:** https://prismata.live
**Staging:** https://staging.prismata.live
**Repo:** <LADDER_REPO_OWNER>/<ladder>

---

## How Deploys Work Now

Pushing code to production is safe. The system has automatic rollback, so a bad build **cannot** take the site down. Here's how it works:

### Your workflow: staging → production

```
1. Push to staging branch     →  staging.prismata.live auto-updates (~60s)
2. Check staging looks good   →  visit https://staging.prismata.live
3. Merge staging → master     →  prismata.live auto-updates (~60s)
```

**That's it.** No SSH needed. No manual steps. Discord notifications tell you what happened.

### Step by step

#### 1. Push your changes to staging

```bash
# If you're on a feature branch:
git checkout staging
git merge my-feature-branch
git push origin staging

# Or if you're working directly on staging:
git checkout staging
# ... make changes ...
git add . && git commit -m "description of change"
git push origin staging
```

Within ~60 seconds, you'll see a Discord message in `#prismata-ops`:
> **Staging updated** — preview at https://staging.prismata.live (abc1234)

#### 2. Preview on staging

Visit https://staging.prismata.live and check your changes. This is a full copy of the site running on the same server. It reads from the same database, so you'll see real data.

**Take your time.** Staging can sit there as long as you want. There's no rush to merge.

#### 3. Deploy to production

When you're happy with staging, merge it into master:

**Option A — GitHub UI (easiest):**
1. Go to https://github.com/<LADDER_REPO_OWNER>/<ladder>
2. Click "Compare & pull request" or create a PR from `staging` → `master`
3. Merge the PR

**Option B — Command line:**
```bash
git checkout master
git merge staging
git push origin master
```

Within ~60 seconds, Discord will confirm:
> **prismata.live deployed** abc1234

#### What if the build fails?

The deploy script automatically rolls back. You'll see a Discord message:
> **prismata.live deploy FAILED** — rolled back to def5678

The site stays on the previous working version. Nobody sees any downtime. Fix the issue on staging and try again.

#### What if the site crashes after deploy?

The deploy script runs a smoke test (checks if the site responds on port 3000). If it fails, it automatically rolls back and you'll see the failure notification in Discord.

---

## What's New on the Server

These are changes Surfinite made on 2026-03-26. You don't need to do anything differently — these run automatically.

### Database Backups
- **Daily at 4 AM UTC** — SQLite database backed up to AWS S3
- Integrity check before upload (catches corruption)
- 30-day retention (90-day lifecycle on S3)
- Restore tested and verified

### Health Monitoring
- **Every 5 minutes** — checks all services, disk space, DB freshness, swap usage
- Alerts go to Discord `#prismata-ops` channel (Surfinite's server)
- Only alerts on state **changes** (not every 5 minutes)
- Sends "all clear" when issues resolve

### Safe Deploys (described above)
- Concurrent deploy protection (can't accidentally trigger two at once)
- Deterministic installs (`npm ci` instead of `npm install`)
- Automatic rollback on build failure or failed smoke test
- Discord notifications for success and failure

### Staging Environment
- `staging.prismata.live` — separate Next.js instance on port 3001
- Auto-deploys when `staging` branch is pushed
- Has its own SSL certificate
- Reads from the same production database (read-only)

### SSL Auto-Renewal
- Let's Encrypt certificate, auto-renews via certbot
- nginx automatically reloads after renewal
- Current cert valid until 2026-06-22

### Log Rotation
- Ops script logs rotate weekly, 4 archives kept
- Won't fill the disk

### Credential Security
- Webhook secret read from environment (not hardcoded)
- HMAC-SHA256 signature verification on all webhook requests
- Bot credentials file locked down (600 permissions)

---

## Discord Notifications

All notifications go to `#prismata-ops` in Surfinite's Discord server. Here's what you'll see:

| Message | Meaning |
|---------|---------|
| **prismata.live deployed** abc1234 | Production deploy succeeded |
| **prismata.live deploy FAILED** — rolled back to def5678 | Build failed, auto-rolled back, site still up |
| **Staging updated** — preview at staging.prismata.live (abc1234) | Staging deploy succeeded |
| **Staging build FAILED** | Staging build failed, check your code |
| **prismata.live alert:** Service X is DOWN | A service crashed (auto-restarts, but flagged) |
| **prismata.live alert:** Disk at 85% | Disk getting full |
| **prismata.live** all clear — issues resolved | Previously reported issue fixed itself |

---

## Emergency Procedures

### If the site is down and you have SSH access

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<OLD_VPS_IP>

# Check what's wrong
sudo systemctl status prismata-site <SSH_KEY> prismata-webhook nginx

# Restart a specific service
sudo systemctl restart prismata-site

# Check recent logs
sudo journalctl -u prismata-site --since '10 min ago'

# Full recovery playbook
cat /opt/site/ops/RECOVERY.md
```

### If you don't have SSH access

Contact Surfinite. The site auto-restarts crashed services, so most issues resolve within seconds.

---

## Important Paths on the Server

| Path | What it is |
|------|-----------|
| `/opt/site/` | Production site (git clone, master branch) |
| `/opt/staging/<ladder>/` | Staging site (git clone, staging branch) |
| `/opt/site/ops/` | Operations scripts (backup, health, deploy) |
| `/opt/site/ops/.env` | Config file (secrets, Discord webhook) |
| `/opt/site/ops/RECOVERY.md` | Disaster recovery playbook |
| `/opt/site/prismata_ladder.db` | SQLite database (1,777+ games) |

---

## Webhook Secret Rotation (One-Time Task)

The webhook secret should be rotated. When you're ready:

1. Go to GitHub → Settings → Webhooks → Edit the webhook
2. Enter a new secret (any random string — generate one with `python3 -c "import secrets; print(secrets.token_hex(32))"`)
3. SSH into the VPS and update the secret:
   ```bash
   sudo sed -i 's/^WEBHOOK_SECRET=.*/WEBHOOK_SECRET="YOUR_NEW_SECRET"/' /opt/site/ops/.env
   sudo systemctl restart prismata-webhook
   ```
4. Push a test commit to verify deploys still trigger

---

## FAQ

**Q: Can I push directly to master?**
A: Yes, and it will auto-deploy. But using staging first is safer — you can preview before it goes live.

**Q: What if I push to master and staging at the same time?**
A: Each deploy has a lock file. They'll run one at a time, never overlap.

**Q: Does staging use a separate database?**
A: No, it reads from the same production database. It's a frontend-only preview.

**Q: What if the VPS runs out of disk?**
A: EBS was expanded to 16GB (was 8GB). Health check alerts at 85%. If it fills up, clean with `sudo apt clean && npm cache clean --force`.

**Q: Where are the backups?**
A: S3 bucket `prismata-live-backups-<AWS_ACCOUNT>`, in the `daily/` prefix. 30-day retention.

**Q: How do I manually trigger a deploy?**
A: SSH in and run `/opt/site/ops/deploy.sh` (production) or `/opt/site/ops/deploy_staging.sh` (staging).
