# Split Architecture — Infrastructure Continuation Prompt

**Previous session:** Mar 26, 2026. Code changes (Tasks 1-4) complete and committed. Ready for infrastructure provisioning.

**Spec:** `docs/superpowers/specs/2026-03-26-split-architecture-design.md`
**Full plan:** `docs/superpowers/plans/2026-03-26-split-architecture-plan.md` (Tasks 5-11)
**Memory files:** `project_split_architecture_plan.md`, `project_prismata_live_infrastructure.md`

---

## What's done

**Code changes in <ladder> repo** (4 commits on master, not yet pushed):
```
27a9fc7 chore: add requirements.txt for data box setup
9cbdac3 feat: replace Vercel deploy with S3 export in deploy pipeline
e392963 feat: add S3 upload to all JSON export scripts
a4a8541 feat: add S3 export helper for split architecture
```

- `s3_export.py` — shared helper, reads `S3_EXPORT_BUCKET` from env, no-op when unset
- 4 export scripts now upload to S3 after local write (api.json, player_stats.json, unit_winrates.json, weekly_report.json)
- Vercel deploy removed from `ladder_tracker.py` and `headless_multi.py`
- `requirements.txt` created (websockets, colorama, boto3, requests)
- Tests: 3/3 passing for s3_export

## What's left (Tasks 5-11)

### Task 5: Launch Data Box EC2
- t4g.micro OD (ARM/Graviton), same VPC/subnet/AZ as current spot instance
- Create dedicated security group (SSH + port 8765 from site SG only)
- Create standalone ENI with static private IP (survives instance replacement)
- Tag ENI as `prismata-data-eni`

### Task 6: Provision Data Box
- SSH via jump host: `ssh -A ubuntu@<SITE_EIP>` then `ssh ubuntu@<DATA_PRIVATE_IP>`
- Install: `python3 python3-pip python3-venv git sqlite3`
- Create venv: `python3 -m venv .venv` (Ubuntu 24.04 PEP 668)
- Clone <ladder> repo, `pip install -r requirements.txt`
- Copy credentials + SQLite DB from site box
- Create systemd EnvironmentFile with `S3_EXPORT_BUCKET=prismata-live-backups-<AWS_ACCOUNT>`
- Create systemd service using venv python: `/opt/data/<ladder>/.venv/bin/python headless_multi.py --quiet`

### Task 7: Update Site Box
- Stop + disable spectator service on site box
- Update nginx: proxy `/ws` to data box private IP instead of localhost
- Add `ExecStartPre` S3 sync to prismata-site.service (populate data before Next.js starts)
- Add 60s S3 sync cron
- Remove bot credentials from site box
- Move backup cron to data box

### Task 8: Update ASG Launch Template + AMIs
- Take AMIs of both boxes
- Update launch template user-data (no spectator, adds S3 sync cron + ExecStartPre)

### Task 9: Test Spot Recovery
- Terminate site box, verify ASG replaces it
- Verify data files populated from S3 on boot
- Verify WebSocket proxy works through to data box
- Verify data box was unaffected (bots running the whole time)

### Task 10: Update Recovery Playbook
- Add data box recovery section to `/opt/site/ops/RECOVERY.md`
- Document ENI preservation warning

### Task 11: Update Health Check
- Extend health_check.sh to monitor data box (WebSocket port, S3 export freshness)

## Important notes for the next session

1. **Push <ladder> first**: The 4 code commits need to be pushed before deploying to the data box. `cd <LADDER_REPO_PATH> && git push origin master`

2. **Staged cutover**: Start data box with 1 bot account first, verify it works, then move remaining 5 accounts over, then stop spectator on site box. Never have zero bots running.

3. **Current Elastic IP**: `<SITE_EIP>` (CLAUDE.md still says old IP `<OLD_VPS_IP>` — needs updating)

4. **SSH key**: `~/.ssh/<SSH_KEY>.pem`

5. **PEP 668**: Ubuntu 24.04 ARM requires venv, not system pip. Systemd ExecStart must use `.venv/bin/python`.

6. **sqlite3 CLI**: Must be installed for backup script's `.backup` command.

7. **WebSocket bind**: Already `0.0.0.0` by default (`headless_multi.py:1015` reads `WS_HOST` env, defaults to `0.0.0.0`). No code change needed.

8. **Vercel removal is one-way**: Once the code changes are deployed, the old Vercel deploy path is gone. Ensure S3 exports are verified working on the data box before pushing Task 3 changes to any box that was using Vercel.

## Current infrastructure reference

| Item | Value |
|---|---|
| Site instance | `i-06c7ada0d850f351e` (spot, t3.micro) |
| Elastic IP | `<SITE_EIP>` (<OLD_EIP_ALLOC>) |
| ASG | `prismata-live-asg` (min=max=1 spot) |
| Launch template | `lt-0b099958c1d0bce6a` v4 (AMI `ami-040e226db64f62381`) |
| SSH | `ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<SITE_EIP>` |
| S3 bucket | `prismata-live-backups-<AWS_ACCOUNT>` |
| IAM role | `prismata-live-ec2` (S3 + EIP associate) |
| DNS | `prismata.live` + `staging.prismata.live` → `<SITE_EIP>` (Porkbun) |
