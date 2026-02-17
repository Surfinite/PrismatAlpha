# Cloud Operations Reference

> Operational details for the multi-cloud self-play fleet. Referenced from `CLAUDE.md` — read this file when working on cloud launch scripts, TheWatcher, or debugging remote workers.

## General / Multi-Cloud

- **Debugging cloud worker crashes**: Download `log_worker_*.txt` and `selfplay_boot.log` from S3 results dir. Working instances show `[Progress] X / N rounds` lines; crashing instances cut off at `[SelfPlay] Exporting...`. Compare patched configs between providers — differing `rounds` values are a common misconfiguration.
- **Cloud provider comparison (Feb 16)**: Oracle Cloud not competitive (Windows licensing $0.092/OCPU/hr, "Out of Capacity" common, no spot). Azure better third option (spot at ~$0.07/hr for D8s_v5, $200 free credits, default quota ~10 vCPUs).
- **Writing shell variables to files**: Use `printf '%s' "$VAR" > file` not `echo "$VAR" > file`. `echo` may interpret backslash sequences, corrupting PowerShell scripts.

## AWS EC2

- **EC2 config patching**: `launch_selfplay.sh` patches config line-by-line (not regex across properties) because JSON property ordering varies. Don't switch to cross-property regexes.
- **AWS CLI in Git Bash**: Native Windows exe. Temp file paths must be Windows-accessible (not `/tmp/`). Use `file://` prefix for user-data. PATH: `export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"`.
- **EC2 spot has separate vCPU quota**: `USE_SPOT=true bash aws/launch_selfplay.sh ...` uses separate quota. Run on-demand + spot simultaneously for double capacity. Quota codes: `L-34B43A08` (spot), `L-1216C47A` (on-demand).
- **EC2 file-lock sync**: `Write-S3Object` cannot read locked files. The periodic sync copies to temp dir first via `Copy-Item`, then uploads from temp.
- **AWS quota management**: Check: `aws service-quotas get-service-quota --service-code ec2 --quota-code <CODE> --region eu-north-1`. Increase: `aws service-quotas request-service-quota-increase --service-code ec2 --quota-code <CODE> --desired-value <N> --region eu-north-1`. Modest asks (64-128) more likely auto-approved.

## GCP Compute Engine

- **GCP hybrid cloud**: Instances install AWS CLI, upload to S3 bucket `prismata-selfplay-data`. No GCS. Credentials from `gcp/.aws_credentials`. Project: `prismata-selfplay`, zone: `us-central1-a`.
- **GCP quotas**: N2_CPUS=200 (25 n2-standard-8), INSTANCES=24, PREEMPTIBLE_CPUS=0. SSD_TOTAL_GB=250 may limit concurrent instances. Check: `gcloud compute regions describe us-central1 --project=prismata-selfplay --format="json(quotas)"`.
- **GCP instance self-deletion**: Uses `gcloud compute instances delete` (not Stop-Computer). Requires `compute-rw` scope. Falls back to Stop-Computer if delete fails.
- **GCP gcloud.cmd vs gcloud**: Use `gcloud.cmd` in PowerShell, `gcloud` in bash. Git Bash can't execute `.cmd` directly. SDK: `C:\google-cloud-sdk\bin`.
- **gcloud.cmd stderr noise**: Harmless stderr about temp files even on success. TheWatcher logs as warnings, reports call as successful.
- **GCP quota increase on new projects**: Google denies if project <48 hours old or lacks billing history. Wait 48h and resubmit. **CPUS_ALL_REGIONS=12 is the actual bottleneck** — not N2_CPUS (200).

## Azure

- **Azure `--custom-data` encoding**: No Unicode chars > U+00FF in startup scripts. Azure CLI encodes to latin-1. Use `PYTHONUTF8=1` before `az` commands.
- **Azure VM name limit**: Windows VMs max 15 chars. Script uses `prsm-HHMMSS-N` (13 chars).
- **Azure VM billing + quota**: `Stop-Computer` only stops OS (still bills, consumes quota). Must `az vm deallocate` then `az vm delete`. TheWatcher handles automatically.
- **Azure batch loop for OOM**: Launch script runs 250 rounds per batch in restart loop. Without this, processes crash at ~80 games. Config patched to `"rounds":250`, loop runs `ceil(gamesPerProcess / 250)` batches.
- **Azure FSv2 unavailable**: Returns empty from `az vm list-skus` across European regions despite showing in `list-sizes`. Always use `list-skus` (actual availability). D-series v7 works.
- **Azure `az.cmd` JMESPath broken**: `cmd.exe` mangles special characters (`]`, `.`, `{`, `:`). Fix: skip `--query`, fetch full JSON with `--output json`, filter in PowerShell.
- **Azure quota increases auto-reject**: On new/free-credit accounts, both "My Quotas" and `az quota` CLI get auto-rejected. Submit support requests (Severity C, 24-48hr). Per-family increase auto-increases regional quota.
- **Azure CLI path**: Bash: `AZ="/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az"`. PowerShell: `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd`.
- **Azure VM think-time multipliers**: vs local Ryzen 5700X3D. F2s_v2 (2 vCPUs, 4 threads): **3x**. F8s_v2/D8als_v7 (8 vCPUs, 4 threads): **2x**. Formula: base cloud penalty (2x) x oversubscription factor.
- **Azure hybrid cloud**: Same S3 pattern as GCP. AWS credentials from `azure/.aws_credentials`.
- **Azure quota management**: Two-tier: Total Regional vCPUs (ceiling, 64) + per-family limits (default 10 each). Both must allow a VM. "VM stopped" still consumes quota — must deallocate. Check: `az vm list-usage --location northeurope --output json`. **Quotas are per-region.**
- **Azure orphaned resources after VM deletion**: `az vm delete` does NOT cascade — NICs, public IPs, OS disks, NSGs, and VNets persist and bill. After deleting VMs, clean up in order: NICs → public IPs → disks → NSGs → VNets. All `az` commands must use `MSYS_NO_PATHCONV=1` in Git Bash (Azure resource IDs start with `/subscriptions/` which Git Bash mangles to Windows paths). Verify cleanup: `az resource list --resource-group prismata-selfplay --query "length(@)"` → should be 0.
- **Azure orphan cleanup commands** (Git Bash):
  ```bash
  AZ="/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az"
  MSYS_NO_PATHCONV=1 "$AZ" network nic list --resource-group RG --query "[].id" -o tsv | while read id; do MSYS_NO_PATHCONV=1 "$AZ" network nic delete --ids "$id" --no-wait; done
  MSYS_NO_PATHCONV=1 "$AZ" network public-ip list --resource-group RG --query "[].id" -o tsv | while read id; do MSYS_NO_PATHCONV=1 "$AZ" network public-ip delete --ids "$id" --no-wait; done
  MSYS_NO_PATHCONV=1 "$AZ" disk list --resource-group RG --query "[].id" -o tsv | while read id; do MSYS_NO_PATHCONV=1 "$AZ" disk delete --ids "$id" --yes --no-wait; done
  MSYS_NO_PATHCONV=1 "$AZ" network nsg list --resource-group RG --query "[].id" -o tsv | while read id; do MSYS_NO_PATHCONV=1 "$AZ" network nsg delete --ids "$id" --no-wait; done
  ```

## Fleet Health Checks

When checking cloud compute status, verify ALL of these — not just running VMs:

### Azure
1. **Running VMs**: `az vm list --resource-group prismata-selfplay --output table`
2. **Orphaned resources**: `az resource list --resource-group prismata-selfplay --query "length(@)"` — should equal VM count or 0
3. **Idle VM detection**: Check `watcher_status.json` → `shard_activity.last_new_shard`. If stale (>1hr), VMs may be idle/crashed. Cross-check S3 boot logs: directories with `selfplay_boot.log` = completed VMs; without = potentially still running or crashed.

### AWS EC2
1. **Running instances**: `aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" "Name=tag:purpose,Values=selfplay" --query "Reservations[].Instances[].InstanceId" --region eu-north-1`
2. **Orphaned EBS volumes**: `aws ec2 describe-volumes --filters "Name=status,Values=available" --region eu-north-1 --query "Volumes[].{Id:VolumeId,Size:Size}"` — "available" = unattached, still billing
3. **Orphaned Elastic IPs**: `aws ec2 describe-addresses --region eu-north-1 --query "Addresses[?AssociationId==null]"` — unattached EIPs bill ~$3.65/month each

### GCP
1. **Running instances**: `gcloud compute instances list --project=prismata-selfplay`
2. **Orphaned disks**: `gcloud compute disks list --project=prismata-selfplay --filter="NOT users:*"` — unattached disks still bill
3. **Static IPs**: `gcloud compute addresses list --project=prismata-selfplay` — unused static IPs bill ~$2.88/month
