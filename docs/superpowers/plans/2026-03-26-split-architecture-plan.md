# Split Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split prismata.live into two EC2 instances — an always-on data box (t4g.micro OD) for bots/DB/exports and a spot site box (t3.micro) for the website — eliminating replay code loss during spot recovery.

**Architecture:** Data box runs `headless_multi.py` (single process: 6 bots, WebSocket, ladder tracker, JSON exports to S3). Site box runs Next.js + nginx, reads JSON from S3, proxies `/ws` to data box's static private IP. Manual deploy on data box, auto-deploy on site box.

**Tech Stack:** AWS EC2 (t4g.micro ARM + t3.micro x86), S3, boto3, systemd, nginx, Python, Next.js

**Spec:** `docs/superpowers/specs/2026-03-26-split-architecture-design.md`

---

## File Map

### Files to Modify (<ladder> repo at `<LADDER_REPO_PATH>\`)

| File | Change |
|------|--------|
| `ladder_tracker.py:704-742` | Replace Vercel deploy with S3 upload in `_do_deploy()` |
| `headless_multi.py:135-163` | Replace Vercel deploy in `run_weekly_report_export()` with S3 upload |
| `export_site_data.py:19,591-597` | Add S3 upload after local write |
| `export_player_stats.py:25,452-456` | Add S3 upload after local write |
| `export_unit_winrates.py:14,241-245` | Add S3 upload after local write |
| `export_weekly_report.py:17,788-808` | Add S3 upload after local write |

### Files to Create (<ladder> repo)

| File | Purpose |
|------|---------|
| `s3_export.py` | Shared S3 upload helper (boto3, bucket config, upload function) |
| `requirements.txt` | Pin Python dependencies including boto3 |

### Files to Create/Modify on VPS (via SSH)

| File | Purpose |
|------|---------|
| `/etc/systemd/system/<SSH_KEY>.service` (data box) | systemd unit for headless_multi.py |
| `/etc/nginx/sites-available/prismata.live` (site box) | Update `/ws` proxy target |
| `/etc/systemd/system/prismata-site.service` (site box) | Add ExecStartPre S3 sync |
| crontab (site box) | Add 60s S3 sync cron |
| `/opt/site/ops/RECOVERY.md` (site box) | Add data box recovery section |

---

## Task 1: Create S3 Export Helper

**Files:**
- Create: `<LADDER_REPO_PATH>\s3_export.py`
- Create: `<LADDER_REPO_PATH>\tests\test_s3_export.py`

This helper centralizes S3 upload logic so all 4 export scripts use one function.

- [ ] **Step 1: Write the test**

Create `tests/test_s3_export.py`:

```python
"""Tests for S3 export helper."""
import json
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest


def test_upload_json_to_s3_calls_boto3_put_object():
    """Verify upload_json_to_s3 calls S3 put_object with correct params."""
    with patch("s3_export.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from s3_export import upload_json_to_s3

        local_path = Path(__file__).parent / "fixtures" / "test_api.json"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text('{"test": true}', encoding="utf-8")

        try:
            upload_json_to_s3(local_path, "api.json")

            mock_client.put_object.assert_called_once()
            call_kwargs = mock_client.put_object.call_args[1]
            assert call_kwargs["Key"] == "exports/api.json"
            assert call_kwargs["ContentType"] == "application/json"
            assert json.loads(call_kwargs["Body"]) == {"test": True}
        finally:
            local_path.unlink(missing_ok=True)


def test_upload_json_to_s3_uses_env_bucket():
    """Verify bucket name comes from S3_EXPORT_BUCKET env var."""
    with patch("s3_export.boto3") as mock_boto3, \
         patch.dict(os.environ, {"S3_EXPORT_BUCKET": "my-custom-bucket"}):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # Force reimport to pick up env var
        import importlib
        import s3_export
        importlib.reload(s3_export)

        local_path = Path(__file__).parent / "fixtures" / "test_api2.json"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text('{"test": true}', encoding="utf-8")

        try:
            s3_export.upload_json_to_s3(local_path, "api.json")
            call_kwargs = mock_client.put_object.call_args[1]
            assert call_kwargs["Bucket"] == "my-custom-bucket"
        finally:
            local_path.unlink(missing_ok=True)


def test_upload_json_to_s3_noop_when_no_bucket():
    """If S3_EXPORT_BUCKET is empty, upload is a silent no-op (local dev)."""
    with patch.dict(os.environ, {"S3_EXPORT_BUCKET": ""}, clear=False):
        import importlib
        import s3_export
        importlib.reload(s3_export)

        # Should not raise, should not call boto3
        with patch("s3_export.boto3") as mock_boto3:
            s3_export.upload_json_to_s3(Path("fake.json"), "fake.json")
            mock_boto3.client.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <LADDER_REPO_PATH> && python -m pytest tests/test_s3_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 's3_export'`

- [ ] **Step 3: Write the implementation**

Create `s3_export.py`:

```python
"""Shared S3 upload helper for JSON exports.

On the VPS data box, S3_EXPORT_BUCKET is set in the systemd EnvironmentFile.
On local dev machines, it's unset — uploads are silently skipped.
"""

import os
from pathlib import Path

import boto3

S3_EXPORT_BUCKET = os.environ.get("S3_EXPORT_BUCKET", "")
S3_EXPORT_PREFIX = "exports/"


def upload_json_to_s3(local_path: Path, s3_filename: str) -> bool:
    """Upload a JSON file to S3.

    Args:
        local_path: Path to the local JSON file.
        s3_filename: Filename in S3 (e.g. "api.json"). Stored under exports/ prefix.

    Returns:
        True if uploaded, False if skipped (no bucket configured).
    """
    if not S3_EXPORT_BUCKET:
        return False

    client = boto3.client("s3")
    body = local_path.read_text(encoding="utf-8")
    client.put_object(
        Bucket=S3_EXPORT_BUCKET,
        Key=f"{S3_EXPORT_PREFIX}{s3_filename}",
        Body=body,
        ContentType="application/json",
    )
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd <LADDER_REPO_PATH> && python -m pytest tests/test_s3_export.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd <LADDER_REPO_PATH>
git add s3_export.py tests/test_s3_export.py
git commit -m "feat: add S3 export helper for split architecture"
```

---

## Task 2: Add S3 Upload to Export Scripts

**Files:**
- Modify: `<LADDER_REPO_PATH>\export_site_data.py:591-597`
- Modify: `<LADDER_REPO_PATH>\export_player_stats.py:452-456`
- Modify: `<LADDER_REPO_PATH>\export_unit_winrates.py:241-245`
- Modify: `<LADDER_REPO_PATH>\export_weekly_report.py:788-808`

Each export script already writes JSON to local disk. Add an S3 upload call after each local write.

- [ ] **Step 1: Modify export_site_data.py**

After the existing local write at line 595, add:

```python
# After: json.dump(data, f, indent=2, default=str)
# After: print(f"[export] Exported to {OUTPUT_PATH}")

    # Upload to S3 (no-op on local dev)
    from s3_export import upload_json_to_s3
    if upload_json_to_s3(OUTPUT_PATH, "api.json"):
        print(f"[export] Uploaded api.json to S3")
```

Insert after line 597 (`print(f"[export] Exported to {OUTPUT_PATH}")`), before the stats print.

- [ ] **Step 2: Modify export_unit_winrates.py**

After the existing local write at line 243, add:

```python
# After: json.dump(data, f, indent=2)
# After: print(f"Exported to {OUTPUT_PATH}")

    from s3_export import upload_json_to_s3
    if upload_json_to_s3(OUTPUT_PATH, "unit_winrates.json"):
        print(f"Uploaded unit_winrates.json to S3")
```

Insert after line 245 (`print(f"Exported to {OUTPUT_PATH}")`).

- [ ] **Step 3: Modify export_player_stats.py**

After the existing local write at line 454, add:

```python
# After: json.dump(data, f, indent=2)
# After: print(f"Exported {len(all_stats)} players to {OUTPUT_PATH}")

        from s3_export import upload_json_to_s3
        if upload_json_to_s3(OUTPUT_PATH, "player_stats.json"):
            print(f"Uploaded player_stats.json to S3")
```

Insert after line 456 (`print(f"Exported {len(all_stats)} players to {OUTPUT_PATH}")`). Note the extra indent — this is inside a try block.

- [ ] **Step 4: Modify export_weekly_report.py**

After the existing local write at line 790, add:

```python
# After: json.dump(report, f, indent=2)
# After: print(f"Wrote report to {OUTPUT_PATH}")

        from s3_export import upload_json_to_s3
        if upload_json_to_s3(OUTPUT_PATH, "weekly_report.json"):
            print(f"Uploaded weekly_report.json to S3")
```

Insert after line 808 (`print(f"Wrote report to {OUTPUT_PATH}")`). Inside the try block.

- [ ] **Step 5: Test locally (dry run)**

Run: `cd <LADDER_REPO_PATH> && python -c "from s3_export import upload_json_to_s3; print('S3_EXPORT_BUCKET:', repr(__import__('os').environ.get('S3_EXPORT_BUCKET', ''))); print('No-op mode OK')"`
Expected: Shows empty bucket, confirms no-op mode works locally.

- [ ] **Step 6: Commit**

```bash
cd <LADDER_REPO_PATH>
git add export_site_data.py export_player_stats.py export_unit_winrates.py export_weekly_report.py
git commit -m "feat: add S3 upload to all JSON export scripts"
```

---

## Task 3: Replace Vercel Deploy with S3 Upload in ladder_tracker

**Files:**
- Modify: `<LADDER_REPO_PATH>\ladder_tracker.py:704-742`
- Modify: `<LADDER_REPO_PATH>\headless_multi.py:135-163`

The `_do_deploy()` method currently runs `export_site_data.py` (step 1) then deploys to Vercel (step 2). On the data box, Vercel deploy is irrelevant — the site box auto-deploys via webhook. Replace step 2 with a success log.

Similarly, `run_weekly_report_export()` in `headless_multi.py` deploys to Vercel after generating the report.

- [ ] **Step 1: Modify ladder_tracker.py _do_deploy()**

Replace lines 719-735 (the Vercel deploy block) with:

```python
            # Step 2: S3 upload handled by export scripts themselves.
            # No Vercel deploy needed — site box reads from S3.
            print(f"  {C_DEPLOY}[deploy]{C_RESET} {C_SUCCESS}SUCCESS{C_RESET} - Exports updated!", flush=True)
            with self._lock:
                self._deploy_fail_until = 0  # Clear any failure backoff
```

The old code:
```python
            # Step 2: Deploy to Vercel (using local vercel package via npm)
            print(f"  [deploy] Deploying to Vercel...", flush=True)
            returncode, stdout, stderr = self._run_with_timeout(
                ["npm", "run", "deploy"],
                cwd=str(SITE_PATH),
                timeout=120,
                use_shell=True  # npm is a .cmd file on Windows
            )
            if returncode == 0:
                print(f"  {C_DEPLOY}[deploy]{C_RESET} {C_SUCCESS}SUCCESS{C_RESET} - Site updated!", flush=True)
                with self._lock:
                    self._deploy_fail_until = 0  # Clear any failure backoff
            else:
                # Log both stdout and stderr for debugging
                output = (stdout + "\n" + stderr).strip()
                print(f"  {C_DEPLOY}[deploy]{C_RESET} {C_ERROR}Vercel failed{C_RESET} (code {returncode}): {output[-500:]}", flush=True)
                self._set_fail_backoff()
```

- [ ] **Step 2: Modify headless_multi.py run_weekly_report_export()**

Replace lines 143-156 (the Vercel deploy block) with:

```python
        # S3 upload handled by export_weekly_report.py itself.
        # No Vercel deploy needed — site box reads from S3.
        print(f"{C.TRACKER}[weekly]{C.RESET} Weekly report exported (S3 upload in export script)")
```

The old code:
```python
        # Auto-deploy to Vercel
        print(f"{C.TRACKER}[weekly]{C.RESET} Deploying to Vercel...")
        import subprocess
        result = subprocess.run(
            ['npm', 'run', 'deploy'],
            cwd=Path(__file__).parent / '<ladder>-site',
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            print(f"{C.TRACKER}[weekly]{C.RESET} Deploy successful!")
        else:
            print(f"{C.ERROR}[weekly]{C.RESET} Deploy failed: {result.stderr}")
```

- [ ] **Step 3: Commit**

```bash
cd <LADDER_REPO_PATH>
git add ladder_tracker.py headless_multi.py
git commit -m "feat: replace Vercel deploy with S3 export in deploy pipeline"
```

---

## Task 4: Create requirements.txt

**Files:**
- Create: `<LADDER_REPO_PATH>\requirements.txt`

- [ ] **Step 1: Identify current dependencies**

Run: `cd <LADDER_REPO_PATH> && python -c "import websockets, aiohttp, colorama, boto3; print('all found')" 2>&1 || echo "some missing"`

Check which are already installed. The data box needs all of these.

- [ ] **Step 2: Create requirements.txt**

```
websockets>=12.0
aiohttp>=3.9
colorama>=0.4
boto3>=1.34
requests>=2.31
```

- [ ] **Step 3: Verify install works**

Run: `cd <LADDER_REPO_PATH> && pip install -r requirements.txt --dry-run`
Expected: All satisfied or would install.

- [ ] **Step 4: Commit**

```bash
cd <LADDER_REPO_PATH>
git add requirements.txt
git commit -m "chore: add requirements.txt for data box setup"
```

---

## Task 5: Launch Data Box EC2 Instance

All remaining tasks are SSH/AWS operations. These cannot be TDD'd — they are infrastructure provisioning.

**Prerequisites:** AWS CLI configured locally, SSH key at `~/.ssh/<SSH_KEY>.pem`.

- [ ] **Step 1: Identify current subnet and security group**

```bash
aws ec2 describe-instances \
  --instance-ids i-06c7ada0d850f351e \
  --query "Reservations[0].Instances[0].[SubnetId, SecurityGroups[0].GroupId, Placement.AvailabilityZone]" \
  --output text
```

Note the subnet ID, security group ID, and AZ.

- [ ] **Step 2: Create a dedicated security group for the data box**

```bash
# Get the VPC ID from the subnet
aws ec2 describe-subnets --subnet-ids <SUBNET_ID> --query "Subnets[0].VpcId" --output text

aws ec2 create-security-group \
  --group-name prismata-data-sg \
  --description "Prismata data box - bots, DB, WebSocket" \
  --vpc-id <VPC_ID>
```

Note the new security group ID.

```bash
# SSH from admin IP only
aws ec2 authorize-security-group-ingress \
  --group-id <DATA_SG_ID> \
  --protocol tcp --port 22 \
  --cidr <YOUR_IP>/32

# WebSocket from site box security group only
aws ec2 authorize-security-group-ingress \
  --group-id <DATA_SG_ID> \
  --protocol tcp --port 8765 \
  --source-group <SITE_SG_ID>
```

- [ ] **Step 3: Create a standalone ENI with static private IP**

```bash
aws ec2 create-network-interface \
  --subnet-id <SUBNET_ID> \
  --description "prismata-data-eni - permanent private IP for data box" \
  --groups <DATA_SG_ID>
```

Note the ENI ID and the PrivateIpAddress assigned. Tag it:

```bash
aws ec2 create-tags --resources <ENI_ID> --tags Key=Name,Value=prismata-data-eni
```

- [ ] **Step 4: Find the latest Ubuntu 24.04 ARM AMI**

```bash
aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*" \
  --query "sort_by(Images, &CreationDate)[-1].[ImageId,Name]" \
  --output text
```

- [ ] **Step 5: Launch the data box instance**

```bash
aws ec2 run-instances \
  --image-id <AMI_ID> \
  --instance-type t4g.micro \
  --network-interfaces "[{\"NetworkInterfaceId\": \"<ENI_ID>\", \"DeviceIndex\": 0}]" \
  --iam-instance-profile Name=prismata-live-ec2 \
  --key-name <SSH_KEY> \
  --block-device-mappings "[{\"DeviceName\": \"/dev/sda1\", \"Ebs\": {\"VolumeSize\": 8, \"VolumeType\": \"gp3\"}}]" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=prismata-data}]"
```

Note the instance ID.

- [ ] **Step 6: Verify instance is running**

```bash
aws ec2 describe-instances --instance-ids <DATA_INSTANCE_ID> \
  --query "Reservations[0].Instances[0].[State.Name, PrivateIpAddress]" \
  --output text
```

Expected: `running <PRIVATE_IP>` (should match the ENI's IP).

---

## Task 6: Provision Data Box

- [ ] **Step 1: SSH into data box**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<DATA_PRIVATE_IP> \
  -o ProxyJump=ubuntu@<SITE_EIP>
```

Note: The data box has no public IP. SSH via the site box as a jump host. Alternatively, temporarily assign a public IP or use SSM.

If ProxyJump doesn't work (site box needs to have the key), use two hops:
```bash
# From local: SSH to site box
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<SITE_EIP>

# From site box: SSH to data box (key needs to be on site box or use agent forwarding)
ssh -A -i ~/.ssh/<SSH_KEY>.pem ubuntu@<SITE_EIP>
# Then: ssh ubuntu@<DATA_PRIVATE_IP>
```

- [ ] **Step 2: Install Python, dependencies, and tools**

```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git sqlite3
```

- [ ] **Step 3: Clone <ladder> repo**

```bash
# Copy deploy key from site box, or create a new read-only deploy key
sudo mkdir -p /opt/data
sudo chown ubuntu:ubuntu /opt/data
cd /opt/data
git clone git@github.com:<REPO_OWNER>/<ladder>.git
cd <ladder>
```

- [ ] **Step 4: Create venv and install Python dependencies (verify ARM wheels)**

Ubuntu 24.04 enforces PEP 668 — system pip is locked. Use a venv:

```bash
cd /opt/data/<ladder>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "import websockets, aiohttp, colorama, boto3; print('All deps OK')"
```

If any fail to install (missing aarch64 wheel), investigate and resolve before proceeding.

- [ ] **Step 5: Copy credentials from site box**

```bash
# From site box, copy credentials to data box:
scp /home/ubuntu/.prismata_multi_credentials ubuntu@<DATA_PRIVATE_IP>:~/.prismata_multi_credentials

# On data box:
chmod 600 ~/.prismata_multi_credentials
```

- [ ] **Step 6: Copy SQLite database from site box**

```bash
# From site box:
scp /opt/site/<ladder>/prismata_ladder.db ubuntu@<DATA_PRIVATE_IP>:/opt/data/<ladder>/prismata_ladder.db
```

- [ ] **Step 7: Create systemd EnvironmentFile**

On the data box:
```bash
sudo mkdir -p /opt/data/ops
sudo tee /opt/data/ops/.env > /dev/null << 'EOF'
S3_EXPORT_BUCKET=prismata-live-backups-<AWS_ACCOUNT>
PYTHONUNBUFFERED=1
PYTHONIOENCODING=utf-8
EOF
sudo chmod 600 /opt/data/ops/.env
```

- [ ] **Step 8: Create systemd service**

```bash
sudo tee /etc/systemd/system/<SSH_KEY>.service > /dev/null << 'EOF'
[Unit]
Description=Prismata Spectator Bots + Ladder Tracker + WebSocket
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/data/<ladder>
EnvironmentFile=/opt/data/ops/.env
ExecStart=/opt/data/<ladder>/.venv/bin/python headless_multi.py --quiet
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable <SSH_KEY>
sudo systemctl start <SSH_KEY>
```

- [ ] **Step 9: Verify service is running**

```bash
sudo systemctl status <SSH_KEY>
journalctl -u <SSH_KEY> -n 50 --no-pager
```

Expected: Service active, bots connecting to Prismata servers, no import errors.

- [ ] **Step 10: Verify S3 exports**

Wait for the first export cycle (~15 min after new data), or trigger manually:

```bash
cd /opt/data/<ladder>
S3_EXPORT_BUCKET=prismata-live-backups-<AWS_ACCOUNT> python3 export_site_data.py
```

Then check S3:
```bash
aws s3 ls s3://prismata-live-backups-<AWS_ACCOUNT>/exports/
```

Expected: `api.json`, `unit_winrates.json` present with recent timestamps.

- [ ] **Step 11: Verify WebSocket is reachable from site box**

From the site box:
```bash
# Install websocat or use curl
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  http://<DATA_PRIVATE_IP>:8765/
```

Expected: HTTP 101 Switching Protocols (WebSocket upgrade).

---

## Task 7: Update Site Box — Nginx, S3 Sync, Service Changes

- [ ] **Step 1: Stop spectator on site box**

```bash
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<SITE_EIP>
sudo systemctl stop <SSH_KEY>
sudo systemctl disable <SSH_KEY>
```

- [ ] **Step 2: Update nginx WebSocket proxy**

Edit `/etc/nginx/sites-available/prismata.live`:

Find the `/ws` location block and change `proxy_pass` from `http://127.0.0.1:8765` to `http://<DATA_PRIVATE_IP>:8765`:

```nginx
    location /ws {
        proxy_pass http://<DATA_PRIVATE_IP>:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
```

Test and reload:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

- [ ] **Step 3: Add ExecStartPre to prismata-site.service**

```bash
sudo systemctl edit prismata-site
```

Add override:
```ini
[Service]
ExecStartPre=/usr/bin/aws s3 sync s3://prismata-live-backups-<AWS_ACCOUNT>/exports/ /opt/site/<ladder>-site/public/data/ --quiet
```

Then reload:
```bash
sudo systemctl daemon-reload
```

- [ ] **Step 4: Add 60s S3 sync cron**

```bash
crontab -e
```

Add:
```
* * * * * /usr/bin/aws s3 sync s3://prismata-live-backups-<AWS_ACCOUNT>/exports/ /opt/site/<ladder>-site/public/data/ --quiet 2>/dev/null
```

- [ ] **Step 5: Verify site loads data from S3**

```bash
# Force a sync
aws s3 sync s3://prismata-live-backups-<AWS_ACCOUNT>/exports/ /opt/site/<ladder>-site/public/data/ --quiet

# Check files exist
ls -la /opt/site/<ladder>-site/public/data/

# Check site serves data
curl -s https://prismata.live/data/api.json | head -c 200
```

- [ ] **Step 6: Verify live spectating through proxy**

Open `https://prismata.live` in browser, check that live spectating WebSocket connects (check browser devtools Network tab for `/ws` connection).

- [ ] **Step 7: Remove bot credentials from site box**

```bash
rm /home/ubuntu/.prismata_multi_credentials
```

- [ ] **Step 8: Move backup cron to data box**

On the site box, remove the backup cron entry for `backup_db.sh`.

On the data box, set up the backup cron:
```bash
# Copy backup_db.sh to data box (or create a simplified version)
sudo tee /opt/data/ops/backup_db.sh > /dev/null << 'SCRIPT'
#!/bin/bash
set -euo pipefail
BUCKET="prismata-live-backups-<AWS_ACCOUNT>"
DB_PATH="/opt/data/<ladder>/prismata_ladder.db"
BACKUP_NAME="prismata_ladder_$(date +%Y%m%d_%H%M%S).db"

# Copy DB (SQLite safe copy)
sqlite3 "$DB_PATH" ".backup '/tmp/$BACKUP_NAME'"

# Upload to S3
aws s3 cp "/tmp/$BACKUP_NAME" "s3://$BUCKET/backups/$BACKUP_NAME"

# Cleanup
rm "/tmp/$BACKUP_NAME"
echo "[backup] Uploaded $BACKUP_NAME to S3"
SCRIPT
chmod +x /opt/data/ops/backup_db.sh

# Add cron
(crontab -l 2>/dev/null; echo "0 4 * * * /opt/data/ops/backup_db.sh >> /var/log/prismata-backup.log 2>&1") | crontab -
```

---

## Task 8: Update ASG Launch Template and Take AMIs

- [ ] **Step 1: Take AMI of data box**

```bash
aws ec2 create-image \
  --instance-id <DATA_INSTANCE_ID> \
  --name "prismata-data-$(date +%Y%m%d)" \
  --description "Prismata data box - bots, DB, WebSocket, S3 exports" \
  --no-reboot
```

Note the AMI ID.

- [ ] **Step 2: Take AMI of site box**

```bash
aws ec2 create-image \
  --instance-id i-06c7ada0d850f351e \
  --name "prismata-site-$(date +%Y%m%d)" \
  --description "Prismata site box - Next.js, nginx, S3 sync, no bots" \
  --no-reboot
```

Note the AMI ID.

- [ ] **Step 3: Update ASG launch template**

Update the launch template with the new site AMI. The user-data script should NOT start the spectator service and should include the S3 sync cron setup:

```bash
# Create user-data script
cat > /tmp/userdata.sh << 'EOF'
#!/bin/bash
set -euo pipefail

# Associate Elastic IP
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
aws ec2 associate-address --instance-id $INSTANCE_ID --allocation-id <OLD_EIP_ALLOC> --allow-reassociation --region us-east-1

# Restore latest DB backup (for site's local cache, not authoritative)
LATEST=$(aws s3 ls s3://prismata-live-backups-<AWS_ACCOUNT>/backups/ --region us-east-1 | sort | tail -1 | awk '{print $4}')
if [ -n "$LATEST" ]; then
    aws s3 cp "s3://prismata-live-backups-<AWS_ACCOUNT>/backups/$LATEST" /opt/site/<ladder>/prismata_ladder.db --region us-east-1
fi

# Initial S3 data sync (before Next.js starts)
aws s3 sync s3://prismata-live-backups-<AWS_ACCOUNT>/exports/ /opt/site/<ladder>-site/public/data/ --quiet --region us-east-1

# Ensure S3 sync cron exists
(crontab -l -u ubuntu 2>/dev/null | grep -v "s3 sync.*exports" ; echo "* * * * * /usr/bin/aws s3 sync s3://prismata-live-backups-<AWS_ACCOUNT>/exports/ /opt/site/<ladder>-site/public/data/ --quiet 2>/dev/null") | crontab -u ubuntu -

# Start services (spectator is NOT on this box)
systemctl start prismata-site prismata-webhook
EOF

# Base64 encode and create new launch template version
USERDATA_B64=$(base64 -w 0 /tmp/userdata.sh)
aws ec2 create-launch-template-version \
  --launch-template-id lt-0b099958c1d0bce6a \
  --source-version 4 \
  --launch-template-data "{\"ImageId\": \"<SITE_AMI_ID>\", \"UserData\": \"$USERDATA_B64\"}"

# Set as default
aws ec2 modify-launch-template \
  --launch-template-id lt-0b099958c1d0bce6a \
  --default-version <NEW_VERSION>
```

---

## Task 9: Test Spot Recovery

- [ ] **Step 1: Terminate the site box to trigger ASG replacement**

```bash
aws ec2 terminate-instances --instance-ids i-06c7ada0d850f351e
```

- [ ] **Step 2: Monitor recovery**

```bash
# Watch ASG activity
aws autoscaling describe-scaling-activities \
  --auto-scaling-group-name prismata-live-asg \
  --query "Activities[0].[StatusCode,Description]" \
  --output text

# Watch for new instance
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=prismata-live" "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].[InstanceId,State.Name,PublicIpAddress]" \
  --output text
```

- [ ] **Step 3: Verify site is back**

```bash
# Check site responds
curl -s -o /dev/null -w "%{http_code}" https://prismata.live

# Check data files are populated (from S3 sync)
curl -s https://prismata.live/data/api.json | head -c 100

# Check WebSocket proxy works (connects to data box)
# Open browser to https://prismata.live and verify live spectating
```

- [ ] **Step 4: Verify data box was unaffected**

```bash
# SSH to data box via new site instance
ssh -i ~/.ssh/<SSH_KEY>.pem ubuntu@<SITE_EIP>
ssh ubuntu@<DATA_PRIVATE_IP>

# Check bots were running the whole time
journalctl -u <SSH_KEY> --since "10 minutes ago" --no-pager | tail -20
```

Expected: No restarts, continuous bot activity throughout site recovery.

---

## Task 10: Update Recovery Playbook

- [ ] **Step 1: Add data box recovery section to RECOVERY.md**

SSH to site box and edit `/opt/site/ops/RECOVERY.md`. Add a new section:

```markdown
## Scenario 5: Data Box Recovery

The data box (t4g.micro on-demand) runs all spectator bots, the ladder tracker,
WebSocket broadcast, and JSON exports. It should rarely need recovery.

### Symptoms
- Discord health alerts: "WebSocket unreachable" or "S3 exports stale"
- Live spectating broken on prismata.live
- No new games appearing in the ladder

### Recovery Steps

1. **Check if instance is running:**
   ```bash
   aws ec2 describe-instances --instance-ids <DATA_INSTANCE_ID> \
     --query "Reservations[0].Instances[0].State.Name" --output text
   ```

2. **If stopped:** Start it.
   ```bash
   aws ec2 start-instances --instance-ids <DATA_INSTANCE_ID>
   ```
   The private IP is preserved on stop/start (attached via standalone ENI).

3. **If terminated:** The ENI `prismata-data-eni` (<ENI_ID>) must still exist.
   ```bash
   # Check ENI exists
   aws ec2 describe-network-interfaces --network-interface-ids <ENI_ID>

   # Launch new instance with the ENI attached
   aws ec2 run-instances \
     --image-id <DATA_AMI_ID> \
     --instance-type t4g.micro \
     --network-interfaces "[{\"NetworkInterfaceId\": \"<ENI_ID>\", \"DeviceIndex\": 0}]" \
     --iam-instance-profile Name=prismata-live-ec2 \
     --key-name <SSH_KEY> \
     --block-device-mappings "[{\"DeviceName\": \"/dev/sda1\", \"Ebs\": {\"VolumeSize\": 8, \"VolumeType\": \"gp3\"}}]" \
     --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=prismata-data}]"
   ```

4. **Restore database from S3:**
   ```bash
   LATEST=$(aws s3 ls s3://prismata-live-backups-<AWS_ACCOUNT>/backups/ | sort | tail -1 | awk '{print $4}')
   aws s3 cp "s3://prismata-live-backups-<AWS_ACCOUNT>/backups/$LATEST" /opt/data/<ladder>/prismata_ladder.db
   ```

5. **Start service:**
   ```bash
   sudo systemctl start <SSH_KEY>
   ```

6. **Verify:** Bots connecting, WebSocket reachable, S3 exports flowing.

### WARNING: Do Not Delete the ENI
The standalone ENI (`prismata-data-eni`) holds the static private IP that the
site box's nginx config points to. If this ENI is deleted, you must:
1. Create a new ENI (may get a different IP)
2. Update nginx on the site box to point to the new IP
3. Update the ASG launch template user-data with the new IP
4. Take a new site box AMI
```

- [ ] **Step 2: Commit recovery playbook update**

This is on the VPS — commit will happen as part of the next deploy cycle, or manually if RECOVERY.md is tracked in git.

---

## Task 11: Update Health Check for Data Box Monitoring

- [ ] **Step 1: Extend health_check.sh on site box**

SSH to site box, edit `/opt/site/ops/health_check.sh`. Add checks for the data box:

```bash
# === Data Box Health ===
DATA_BOX_IP="<DATA_PRIVATE_IP>"

# Check WebSocket port reachable
if ! nc -z -w 3 "$DATA_BOX_IP" 8765 2>/dev/null; then
    alert "Data box WebSocket unreachable at $DATA_BOX_IP:8765"
fi

# Check S3 export freshness (api.json should be < 30 min old)
EXPORT_AGE=$(aws s3api head-object \
    --bucket prismata-live-backups-<AWS_ACCOUNT> \
    --key exports/api.json \
    --query "LastModified" --output text 2>/dev/null || echo "MISSING")

if [ "$EXPORT_AGE" = "MISSING" ]; then
    alert "S3 export api.json missing!"
else
    EXPORT_EPOCH=$(date -d "$EXPORT_AGE" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    AGE_MIN=$(( (NOW_EPOCH - EXPORT_EPOCH) / 60 ))
    if [ "$AGE_MIN" -gt 30 ]; then
        alert "S3 export api.json is ${AGE_MIN}m old (stale)"
    fi
fi
```

- [ ] **Step 2: Verify health check runs**

```bash
sudo bash /opt/site/ops/health_check.sh
```

Expected: No alerts (everything healthy).

---

## Summary

| Task | What | Where |
|------|------|-------|
| 1 | S3 export helper | <ladder> repo (local) |
| 2 | Add S3 upload to export scripts | <ladder> repo (local) |
| 3 | Replace Vercel deploy with S3 | <ladder> repo (local) |
| 4 | requirements.txt | <ladder> repo (local) |
| 5 | Launch data box EC2 | AWS CLI (local) |
| 6 | Provision data box | SSH to data box |
| 7 | Update site box | SSH to site box |
| 8 | Update ASG + AMIs | AWS CLI (local) |
| 9 | Test spot recovery | AWS CLI + browser |
| 10 | Update recovery playbook | SSH to site box |
| 11 | Health check for data box | SSH to site box |

Tasks 1-4 are code changes (can be done locally, committed, pushed). Tasks 5-11 are infrastructure (done via AWS CLI and SSH). The cutover happens at Task 7 Step 1 — that's when bots stop on the site box and the data box takes over.
