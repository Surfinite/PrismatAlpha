# prismata.live Ops & Resilience — Continuation Prompt

**Previous session:** Mar 26, 2026. Full ops infrastructure deployed + migrated to spot with auto-recovery.

**Memory files:** `project_ops_resilience.md`, `project_split_architecture_plan.md`, `feedback_wonderboat_replay_codes.md`

---

## What was completed

1. **S3 backups** — daily 4am UTC cron, `prismata-live-backups-<AWS_ACCOUNT>` bucket, integrity check, 30-day rotation + 90-day lifecycle, restore tested
2. **Health check** — 5-min cron, deduped Discord alerts to `#prismata-ops`, monitors services/disk/DB/swap
3. **Safe deploy** — flock locking, `npm ci`, `git fetch`+`reset --hard`, rollback on build/smoke fail, Discord notifications
4. **Staging** — `staging.prismata.live` with SSL, separate systemd service on port 3001, auto-deploy on `staging` branch push
5. **Credentials** — webhook secret in env file, EnvironmentFile for systemd, 600 permissions
6. **SSL** — auto-renewal verified, nginx reload hook, cert covers both domains
7. **Log rotation** — weekly rotation for ops logs
8. **Recovery playbook** — `/opt/site/ops/RECOVERY.md`
9. **Spot migration** — t3.micro spot ($2.30/mo) via ASG (min=max=1), Elastic IP `<SITE_EIP>`
10. **Recovery test** — `tools/test_recovery.sh` validates full boot-to-live (measured 118s)
11. **EBS** — expanded 8GB → 16GB (44% used)
12. **UptimeRobot** — 2 monitors (site + data pipeline)
13. **IAM role** — `prismata-live-ec2` with scoped S3 + EIP policies

## Current infrastructure

| Item | Value |
|---|---|
| Instance | `i-06c7ada0d850f351e` (spot, t3.micro) |
| Elastic IP | `<SITE_EIP>` (<OLD_EIP_ALLOC>) |
| ASG | `prismata-live-asg` (min=max=1 spot) |
| Launch template | `lt-0b099958c1d0bce6a` v4 (AMI `ami-040e226db64f62381`) |
| SSH | `ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<SITE_EIP>` |
| S3 bucket | `prismata-live-backups-<AWS_ACCOUNT>` |
| DNS | `prismata.live` + `staging.prismata.live` → `<SITE_EIP>` (Porkbun) |
| Cost | ~$2.30/mo spot (was $7.60/mo on-demand) |

## What still needs doing

### 1. Wonderboat instructions document + commit

Write `docs/prismata-live-ops-guide.md` (or similar) with clear instructions for Wonderboat covering:

- **Staging workflow**: push to `staging` branch → auto-builds → preview at `staging.prismata.live` → merge to `master` on GitHub to deploy to prod
- **How deploys work**: webhook triggers `/opt/site/ops/deploy.sh`, builds with rollback, Discord notifications on success/failure
- **What happens if the site goes down**: spot instance auto-recovers in ~2 min, Elastic IP stays the same, no DNS changes needed, Discord health alerts fire
- **What he should NOT do**: don't SSH and manually edit files, don't force-push to master without testing on staging first
- **Discord `#prismata-ops` channel**: what the alerts mean, when to worry vs ignore
- **How to check if things are working**: UptimeRobot dashboard, `prismata.live/data/api.json` freshness

Then commit the ops plan, recovery test script, and instructions to the PrismataAI repo.

### 2. Split architecture (nice-to-have, not urgent)

See `project_split_architecture_plan.md` for full details. Two-box setup:
- t4g.micro OD ($6/mo) for bots + data capture (never goes down)
- t3.micro spot ($2.30/mo) for website (auto-recovers)
- Total $8.34/mo, eliminates replay code loss during recovery

Wonderboat's take: "yeah the codes are the big thing" but also pragmatic — current setup is "way more codes" than his laptop was getting. Implement when convenient.

### 3. Update CLAUDE.md

Infrastructure section needs updating:
- New IP: `<SITE_EIP>` (was `<OLD_VPS_IP>`)
- New SSH command
- Spot + ASG details
- New instance ID
- Reference to ops scripts at `/opt/site/ops/`
- Reference to recovery test at `tools/test_recovery.sh`

### 4. Webhook secret rotation (requires Wonderboat)

The webhook secret was rotated and stored in `/opt/site/ops/.env`, but the GitHub webhook settings haven't been updated yet. Wonderboat (repo admin) needs to go to GitHub → Settings → Webhooks → update the secret. Coordinate with him when sending the instructions doc.

### 5. HMAC verification in webhook_listener.py

The webhook listener currently checks the secret but should use proper HMAC-SHA256 verification of the `X-Hub-Signature-256` header. Low priority but good security hygiene.
