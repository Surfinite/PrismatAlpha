# Split Architecture Design — prismata.live

**Date:** 2026-03-26
**Status:** Approved, ready for implementation

## Problem

When the spot instance recovers from termination (~2 minutes), the spectator bots are down. Any Prismata games that **end** during that window permanently lose their replay codes — there is no API to backfill them. Replay code capture is Wonderboat's #1 priority for the infrastructure.

## Solution

Split prismata.live into two EC2 instances in the same VPC/subnet/AZ:

| Box | Type | Pricing | Cost/mo | Role |
|-----|------|---------|---------|------|
| **Data box** | t4g.micro (ARM/Graviton) | On-demand | ~$6.04 | Bots, DB, WebSocket, S3 exports |
| **Site box** | t3.micro (x86) | Spot via ASG | ~$2.30 | Next.js site, nginx, SSL, staging |
| | | **Total** | **~$8.34** | |

**Key property:** The data box is always-on (on-demand, no spot termination). If the site box dies and recovers, zero replay codes are lost — the data box keeps capturing throughout.

## Architecture

```
┌─────────────────────┐          ┌──────────────────────┐
│     DATA BOX        │          │      SITE BOX        │
│  t4g.micro OD       │          │   t3.micro Spot/ASG  │
│                     │          │                      │
│  headless_multi.py  │          │  Next.js (prod:3000) │
│    ├─ 6 bots        │  ws://   │  Next.js (stg:3001)  │
│    ├─ ws_broadcast ──┼──────────┼─ nginx proxy /ws     │
│    ├─ ladder_tracker │          │  nginx + SSL         │
│    └─ JSON exports ──┼── S3 ───┼─ ExecStartPre sync   │
│                     │          │  60s cron sync        │
│  SQLite DB          │          │  GitHub webhook       │
│  S3 backup cron     │          │                      │
│                     │          │  NO bots, NO DB       │
│  Private IP: static │          │  Elastic IP (public)  │
└─────────────────────┘          └──────────────────────┘
```

## Data Box

### Instance Configuration
- **Type:** t4g.micro (2 vCPU, 1GB RAM, ARM/Graviton)
- **Pricing:** On-demand (never goes down)
- **Storage:** 8GB gp3 (resizable online if needed)
- **Network:** Static private IP assigned at launch (`--private-ip-address` in `run-instances`)
- **IAM role:** `prismata-live-ec2` (S3 access)
- **No Elastic IP** — only reachable via VPC private IP

### Security Group
- Inbound: SSH (22) from admin IP, WebSocket (8765) from site box security group only
- Outbound: all (Prismata game servers, S3, package repos)
- **Not exposed to the internet** — WebSocket only reachable through the site box's nginx proxy

### Single Process
`headless_multi.py` is the sole entry point. It runs everything in-process:
- **several spectator bots** (HeadlessClient instances in threads)
- **BroadcastServer** (ws_broadcast, daemon thread, port 8765)
- **LadderTracker** (shared singleton, SQLite DB, triggers exports)
- **JSON exports** every 15 min when new data (export_site_data.py, export_player_stats.py, export_unit_winrates.py)
- **Player stats export** every 15 min
- **Weekly report** (Sunday ~23:45 UTC)

### Systemd Service
One service: `<SSH_KEY>.service`
- Runs `headless_multi.py`
- `Restart=always` with reasonable `RestartSec`
- Credentials via `~/.prismata_multi_credentials` (chmod 600)

### Code Changes Required

**1. WebSocket bind address**
`headless_multi.py` already passes `host=os.environ.get("WS_HOST", "0.0.0.0")` to `BroadcastServer` (line 1015), so this already binds to all interfaces by default. No code change needed.

**2. JSON export destination**
`ladder_tracker.py`'s deploy step currently writes JSON files to the local Next.js `public/data/` directory. Change to upload to S3:
```
s3://prismata-live-backups-<AWS_ACCOUNT>/exports/api.json
s3://prismata-live-backups-<AWS_ACCOUNT>/exports/player_stats.json
s3://prismata-live-backups-<AWS_ACCOUNT>/exports/unit_winrates.json
```
The IAM role already has S3 access. Use `boto3` (already available) or the AWS CLI.

### Backups
- Daily S3 backup cron moves to the data box (the DB lives here now)
- Same pattern as today: `backup_db.sh` at 4am UTC, uploads to `prismata-live-backups-<AWS_ACCOUNT>`

## Site Box

### What Changes
- **Spectator service removed** — `<SSH_KEY>.service` no longer runs here
- **Bot credentials removed** — `~/.prismata_multi_credentials` deleted from this box
- **Nginx** — `/ws` proxy target changes from `localhost:8765` to `<data-box-private-ip>:8765`
- **JSON data** — populated from S3 instead of locally generated

### JSON Data Sync
Two mechanisms ensure data is always available:

1. **On boot (ExecStartPre):** `prismata-site.service` gets an `ExecStartPre` that syncs from S3 before Next.js starts. This guarantees data files exist on first request after spot recovery — no 404 window.
   ```
   ExecStartPre=/usr/bin/aws s3 sync s3://prismata-live-backups-<AWS_ACCOUNT>/exports/ /opt/site/<ladder>-site/public/data/ --quiet
   ```

2. **Ongoing (cron):** Every 60 seconds, sync S3 exports to local disk. Next.js reads from local filesystem — zero application code changes.
   ```
   * * * * * /usr/bin/aws s3 sync s3://prismata-live-backups-<AWS_ACCOUNT>/exports/ /opt/site/<ladder>-site/public/data/ --quiet
   ```

### Deploy Model
- Auto-deploy via GitHub webhook — same as today, no changes
- Data box is NOT auto-deployed (bot code changes ~monthly, manual `git pull` + service restart)

### ASG / Launch Template Update
- User-data script updated: no spectator start, adds S3 sync cron, nginx config points to data box private IP
- New AMI snapshot after all changes verified

## Communication

| Channel | Mechanism | Frequency |
|---------|-----------|-----------|
| JSON exports | Data box → S3 (every 15 min on new data), site box syncs from S3 (every 60s + on boot) | Near-real-time on site |
| WebSocket | Site nginx → data box private IP:8765 | Real-time proxy |
| Backups | Data box → S3 | Daily 4am UTC |

No direct instance-to-instance dependency except the WebSocket proxy. If the data box is unreachable, the site still serves (stale) cached JSON files — it just can't proxy live WebSocket connections.

## Migration & Cutover

**Critical constraint:** Zero downtime on data capture. Bots must keep running on the old box until the new data box is verified.

### Cutover Sequence
1. Launch data box (t4g.micro OD, static private IP, same subnet, same security group with 8765 restricted)
2. Install Python deps (`pip install` — verify aarch64 wheels resolve for websockets, aiohttp, boto3, colorama etc. before proceeding), clone <ladder> repo, copy credentials + SQLite DB from current instance
3. Start `headless_multi.py` on data box
4. **Verify:** bots spectating games, WebSocket reachable from site box (`curl` or `websocat`), S3 exports appearing
5. **Stop** spectator service on site box
6. Update nginx: proxy `/ws` to data box private IP, reload
7. Add S3 sync cron + `ExecStartPre` on site box
8. **Verify:** site loads data from S3, live spectating works through proxy
9. Remove spectator service + bot credentials from site box
10. Update ASG launch template + take new AMIs of both boxes
11. **Test spot recovery:** terminate site box, verify it comes back with S3 data and WebSocket proxy working

### Rollback
- **Before step 5:** Stop the data box, nothing has changed on site box
- **After step 5:** Restart spectator on site box, revert nginx config

## Monitoring

### Health Checks
- Existing 5-min health check on site box extended to also check:
  - Data box private IP reachable (ping or TCP check on 8765)
  - S3 export freshness (files updated within last 30 min)
- Discord alerts to `#prismata-ops` — same channel, same dedup logic
- If data box unreachable: alert immediately (OD instance shouldn't go down)

### UptimeRobot
- Keep existing monitors (site + data pipeline)
- Data pipeline monitor checks `api.json` freshness, which validates the full chain: data box → S3 → site box

## Data Box Recovery

The data box is on-demand and should rarely need recovery. If it does:

### Procedure
1. **Do NOT terminate the instance** — stop it instead, or if already terminated, the ENI (Elastic Network Interface) must be preserved
2. If the ENI with the static private IP still exists: launch a new t4g.micro, attach the ENI
3. If starting from scratch: launch with `--private-ip-address <same IP>` in the same subnet
4. Restore SQLite DB from latest S3 backup
5. `git clone` <ladder> repo, copy credentials
6. Start `<SSH_KEY>.service`
7. Verify: bots connecting, WebSocket broadcasting, S3 exports flowing

### ENI Warning
The static private IP is tied to an ENI. If the instance is **terminated** (not just stopped), the default ENI is deleted and the IP is released. To protect against this:
- Either create a standalone ENI (persists independently of instance lifecycle) and attach it at launch
- Or document that recovery requires specifying `--private-ip-address` to claim the same IP in the subnet (works as long as no other instance grabbed it)

The standalone ENI approach is safer. Create it once, tag it `prismata-data-eni`, and always attach it when launching the data box.

### Recovery Playbook Update
Add data box recovery as a new section in `/opt/site/ops/RECOVERY.md` alongside the existing spot recovery procedure.

## Cost Summary

| Component | Before | After |
|-----------|--------|-------|
| Site (spot) | $2.30/mo | $2.30/mo |
| Data (OD) | — | $6.04/mo |
| Elastic IP | free (attached) | free (attached) |
| S3 | ~$0.01/mo | ~$0.02/mo |
| **Total** | **~$2.31/mo** | **~$8.36/mo** |

Cost increases by ~$6/mo. In return: replay codes are never lost during spot recovery, and the architecture cleanly separates concerns (data capture vs. web serving).
