# Split Architecture — Operations Reference

**Deployed:** Mar 26, 2026. All 11 tasks complete. Spot recovery tested.

**Design spec:** `docs/superpowers/specs/2026-03-26-split-architecture-design.md`
**Implementation plan:** `docs/superpowers/plans/2026-03-26-split-architecture-plan.md`
**Recovery playbook:** `/opt/site/ops/RECOVERY.md` on site box (also backed up to S3)

---

## Architecture

```
Internet -> EIP <SITE_EIP>
         -> Site Box (spot t3.micro, ASG-managed)
              nginx: HTTPS termination
              /     -> Next.js (port 3000)
              /ws   -> Data Box (<DATA_BOX_PRIVATE_IP>:8765)
              /deploy -> Webhook (port 9000)
              Cron: S3 sync every 60s, health check every 5m

Data Box (on-demand t4g.micro ARM, <DATA_BOX_PRIVATE_IP>)
  prismata-data.service: several spectator bots + WebSocket + data pipeline
  S3 exports every 60s: api.json, player_stats.json, unit_winrates.json
  SQLite DB: /opt/data/<ladder>/prismata_ladder.db
  Cron: DB backup to S3 daily at 04:00 UTC
```

**Key principle:** Site box is disposable (spot). Data box is persistent (on-demand). Bots and data survive site box replacement.

---

## Infrastructure Reference

| Resource | Value |
|---|---|
| **Data box** | `i-0d893acb3d1f1dd7f` (t4g.micro OD ARM, us-east-1c) |
| Data box private IP | `<DATA_BOX_PRIVATE_IP>` (via ENI `<DATA_BOX_ENI>`) |
| Data box SG | `sg-0a0afd512b4f06db9` (prismata-data-sg) |
| Data box service | `prismata-data.service` |
| Data box code | `/opt/data/<ladder>/` (venv at `.venv/`) |
| **Site box** | ASG-managed spot (instance ID changes on replacement) |
| Site box EIP | `<SITE_EIP>` (`<OLD_EIP_ALLOC>`) |
| Site box ASG | `prismata-live-asg` (min=max=1) |
| Launch template | `lt-0b099958c1d0bce6a` v6 |
| Site AMI | `ami-060e0f9db32af78bd` |
| Data AMI | `ami-0ba6ac27c94fa3535` |
| S3 bucket | `prismata-live-backups-<AWS_ACCOUNT>` |
| IAM role | `prismata-live-ec2` |
| Key pair | `<SSH_KEY>` (`~/.ssh/<SSH_KEY>.pem`) |
| DNS | `prismata.live` -> `<SITE_EIP>` (Porkbun) |
| Discord webhook | In `/opt/site/ops/.env` on site box |

---

## Daily Operations

### SSH access

```bash
# Site box (direct)
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<SITE_EIP>

# Data box (via site box jump)
ssh -i ~/.ssh/<SSH_KEY>.pem \
  -o "ProxyCommand=ssh -i ~/.ssh/<SSH_KEY>.pem -W %h:%p ubuntu@<SITE_EIP>" \
  ubuntu@<DATA_BOX_PRIVATE_IP>
```

### Deploy code changes to data box

Code changes to <ladder> are rare (~monthly). Manual deploy:

```bash
# SSH to data box, then:
cd /opt/data/<ladder>
git pull origin master
sudo systemctl restart prismata-data.service
journalctl -u prismata-data.service -f  # verify bots reconnect
```

Site box deploys automatically via GitHub webhook on push.

### Check if bots are working

```bash
# On data box:
journalctl -u prismata-data.service -n 20
# Look for: [STATUS] 6 clients active, X games being spectated
# Look for: [Client1] GAME OVER / Replay: XXXXX
```

### Manually trigger an export

```bash
# On data box:
cd /opt/data/<ladder>
S3_EXPORT_BUCKET=prismata-live-backups-<AWS_ACCOUNT> .venv/bin/python export_site_data.py
```

### Force S3 sync on site box

```bash
# On site box:
/opt/site/ops/s3_sync_data.sh
```

### Check health

```bash
# On site box:
/opt/site/ops/health_check.sh
# Checks: site services, data box WebSocket, S3 export freshness, disk, swap
```

---

## How to Verify Everything Works

1. **Bots collecting:** SSH to data box, check `journalctl -u prismata-data -f`. Should see heartbeats, game starts/ends, replay codes.

2. **S3 exports flowing:** `aws s3 ls s3://prismata-live-backups-<AWS_ACCOUNT>/exports/ --region us-east-1` — files should be <2 min old when games are active.

3. **Site showing fresh data:** Visit prismata.live, check Recent Games. Latest game should appear within ~2 min of finishing. Game count should increase after each completed game.

4. **WebSocket live spectating:** Open a game on prismata.live — the live viewer should connect and show real-time moves.

5. **Spot recovery:** Terminate site box from AWS console. ASG replaces it in ~2 min. Site comes back, bots never went down.

---

## Test Results (Mar 26, 2026)

### Spot Recovery Test

| Event | Time (UTC) | Elapsed |
|---|---|---|
| Site box terminated | 19:01:57 | 0s |
| New instance running | 19:02:46 | 49s |
| Elastic IP associated | 19:03:48 | 111s |
| All services active | ~19:04:00 | ~120s |
| **Data box impact** | **NONE** | Bots ran continuously |

During the test, the data box recorded a game (AlexanderJohan vs xYotsu, replay `fv@Ac-yE4Gq`) while the site box was down.

### Verified

- All 6 bots log in and spectate on data box
- S3 exports upload successfully (api.json, player_stats.json, unit_winrates.json)
- Site box S3 sync pulls fresh data every 60s
- nginx proxies WebSocket to data box
- Health check monitors data box connectivity + S3 freshness
- Discord alerts fire on state changes
- DB backup runs and uploads to S3
- ASG auto-replaces terminated site box with correct AMI and user-data

---

## Known Issues

- **SpectatorBot3 (Client7):** Login fails ("Invalid user name or password"). Removed from credentials. Running several spectator bots.
- **`headless_multi.py` has no `--quiet` flag:** Don't add unknown flags to systemd ExecStart.
- **WebSocket log misleading:** Prints `ws://127.0.0.1:8765` but actually binds to `0.0.0.0:8765` via `WS_HOST` env var.
- **ENI must be preserved:** `<DATA_BOX_ENI>` holds the static IP `<DATA_BOX_PRIVATE_IP>`. Never delete it. Site box nginx has this IP hardcoded.

---

## S3 Bucket Layout

```
s3://prismata-live-backups-<AWS_ACCOUNT>/
  daily/           -- DB backups (gzipped, 30 retained)
  exports/         -- JSON data files (synced to site box every 60s)
  config/          -- ops config backup
```

---

## Cost

| Component | Monthly |
|---|---|
| Data box (t4g.micro OD) | $6.04 |
| Site box (t3.micro spot) | $2.30 |
| S3 + data transfer | ~$0.01 |
| **Total** | **~$8.35** |
