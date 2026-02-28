# Azure Compute for PrismataAI Self-Play — Implementation Plan

## Overview

Add Azure as a third cloud provider for self-play generation. Replicates the existing AWS EC2 / GCP Compute Engine pattern: launch Windows Server VMs, download exe+config from S3, run self-play, upload shards to S3, auto-terminate.

**Status:** COMPLETE — Azure pipeline operational (Feb 16-17). 28 VMs running across 12 D/F-series families in North Europe. TheWatcher monitors and auto-relaunches. See CLAUDE.md for current fleet status.

**Estimated total work**: ~3-4 hours of implementation (phases 2-4), spread across waiting for quota approval.

---

## What You Can Do RIGHT NOW (Before Any Code)

These steps don't require me and can run in parallel with everything else:

### 1. Create Azure Account (~10 min)
- Go to https://azure.microsoft.com/en-us/free/
- Sign up with your Microsoft account (or create one)
- You get **$200 free credits for 30 days** + 12 months of free services
- Use a **Pay-As-You-Go** subscription (not Free Trial) for compute quota flexibility
- Note your **Subscription ID** — you'll need it later

### 2. Install Azure CLI (~5 min)
- Download from https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows
- Or via winget: `winget install -e --id Microsoft.AzureCLI`
- After install, restart your terminal and run: `az login`
- Verify: `az account show` (should show your subscription)

### 3. Request Quota Increase IMMEDIATELY (~10 min)
This is the bottleneck. New accounts get ~10 vCPUs per VM family. Do this the moment you have an account:

```bash
# Check current quotas
az vm list-usage --location eastus --output table

# Look for "Standard Dv5 Family vCPUs" and "Total Regional vCPUs"
```

Then go to **Azure Portal > Subscriptions > [your sub] > Usage + quotas**:
- Request increase for **Standard DSv5 Family vCPUs** → 64 (for 8 × D8s_v5 instances)
- Request increase for **Total Regional vCPUs** → 64
- Request increase for **Spot vCPU quota** → 128
- Region: pick **East US** or **North Europe** (good availability)
- Justification: "Batch compute for AI research — CPU-intensive game simulation. Ephemeral Windows VMs that run for 2-4 hours and self-terminate. Need 8-16 concurrent instances."

**Typical approval: 1-10 business days.** Sometimes instant for modest asks (10-20 vCPUs).

### 4. Create Resource Group & Setup (~5 min)
```bash
az group create --name prismata-selfplay --location eastus
```

This is where all VMs will live. One resource group keeps cleanup easy.

---

## Phase 1: Azure Infrastructure Setup (Me + You, ~30 min)

**Prereqs**: Azure account exists, CLI installed, logged in.

### Tasks:
1. **Create resource group** (if not done above)
2. **Create a test VM manually** to verify everything works:
   ```bash
   az vm create \
     --resource-group prismata-selfplay \
     --name test-vm \
     --image Win2022AzureEditionCore \
     --size Standard_D2s_v5 \
     --admin-username prismata \
     --admin-password '<strong-password>' \
     --location eastus \
     --public-ip-sku Standard
   ```
3. **Verify Windows boots** and we can RDP in (optional but useful for debugging)
4. **Delete test VM**: `az vm delete --resource-group prismata-selfplay --name test-vm --yes`
5. **Verify quota**: `az vm list-usage --location eastus --output table`
6. **Pick region** based on available quota and spot pricing

### Verification:
- [ ] `az group show --name prismata-selfplay` returns the resource group
- [ ] `az vm list-usage --location eastus` shows quotas
- [ ] Test VM created and deleted successfully

---

## Phase 2: Create `azure/launch_selfplay.sh` (~1.5 hours)

**Pattern**: Copy from `gcp/launch_selfplay.sh` (closer match than AWS because Azure also needs AWS CLI installed on-instance for S3 uploads).

### Key Differences from GCP:

| Aspect | GCP | Azure |
|--------|-----|-------|
| CLI | `gcloud compute instances create` | `az vm create` |
| Startup script | `--metadata-from-file windows-startup-script-ps1=file` | Custom Script Extension (post-create) |
| Credentials to instance | GCP metadata attributes | Azure VM tags or custom-data file |
| Image | `windows-2022-core` from `windows-cloud` | `Win2022AzureEditionCore` |
| Self-delete | `gcloud compute instances delete` | REST API call or `az vm delete` via managed identity |
| Spot | `--provisioning-model=SPOT` | `--priority Spot --eviction-policy Delete` |

### File: `azure/launch_selfplay.sh`

**Structure** (following existing pattern):
```
Lines 1-50:    Argument parsing, instance type → process count mapping
Lines 51-60:   Azure config (resource group, location, image, VM size)
Lines 61-200:  Build PowerShell startup script (same as GCP but with Azure-specific bits)
Lines 200-260: Write script to temp file, launch VM(s), apply Custom Script Extension
Lines 260-280: Cleanup, print summary
```

**Startup script differences from GCP**:
1. **No metadata fetch** — get instance name from `$env:COMPUTERNAME` or Azure Instance Metadata Service (`http://169.254.169.254/metadata/instance?api-version=2021-02-01`)
2. **AWS CLI install** — same as GCP (download AWSCLIV2.msi, install, add to PATH)
3. **AWS credentials** — inject via custom-data (base64-decoded file at `C:\AzureData\CustomData.bin`) or embed in startup script
4. **Self-termination** — two options:
   - **Option A (simpler)**: `Stop-Computer -Force` + external cleanup. Azure charges stop when VM is deallocated.
   - **Option B (cleaner)**: Use managed identity + REST API to self-delete. Requires assigning a managed identity with `Contributor` role on the resource group.
   - **Recommendation**: Start with Option A (Stop-Computer). Add a cleanup step in TheWatcher to `az vm delete` deallocated VMs.

**Launch mechanism** (2-step because Azure doesn't support inline startup scripts):
```bash
# Step 1: Create VM with custom-data (carries AWS credentials + config)
az vm create \
  --resource-group prismata-selfplay \
  --name "prismata-selfplay-$(date +%H%M%S)-$i" \
  --image Win2022AzureEditionCore \
  --size Standard_D8s_v5 \
  --location eastus \
  --admin-username prismata \
  --admin-password "$AZURE_VM_PASSWORD" \
  --custom-data @azure/.startup_payload.b64 \
  --priority Spot \
  --eviction-policy Delete \
  --max-price -1 \
  --no-wait \
  --tags purpose=selfplay games=$NUM_GAMES

# Step 2: Apply Custom Script Extension to execute startup script
az vm extension set \
  --resource-group prismata-selfplay \
  --vm-name "prismata-selfplay-$(date +%H%M%S)-$i" \
  --name CustomScriptExtension \
  --publisher Microsoft.Compute \
  --version 1.10 \
  --settings "{\"commandToExecute\":\"powershell -ExecutionPolicy Unrestricted -File C:\\\\path\\\\to\\\\startup.ps1\"}"
```

**Alternative (simpler) approach**: Encode the entire PowerShell startup script into the `commandToExecute` field of the Custom Script Extension settings, or host the script on S3/blob and reference it via `fileUris`. The S3 approach is cleanest since we already have the bucket:
```bash
# Upload startup script to S3 once
aws s3 cp azure/.startup_tmp.ps1 s3://$CLOUD_BUCKET/deploy/azure_startup.ps1

# Then in az vm extension set:
--settings '{"fileUris":["https://$CLOUD_BUCKET.s3.eu-north-1.amazonaws.com/deploy/azure_startup.ps1"],"commandToExecute":"powershell -ExecutionPolicy Unrestricted -File azure_startup.ps1"}'
```

### New files to create:
- `azure/launch_selfplay.sh` — main launch script
- `azure/.aws_credentials` — AWS credentials for S3 access (gitignored, same as `gcp/.aws_credentials`)

### Verification:
- [ ] Script creates a VM that boots Windows Server
- [ ] Custom Script Extension executes the startup PowerShell
- [ ] AWS CLI installs and can access S3
- [ ] Exe downloads and runs self-play
- [ ] Shards appear in S3 under `results/`
- [ ] VM stops/deallocates after completion

---

## Phase 3: Integrate with TheWatcher (`aws/watcher.ps1`) (~1 hour)

**Pattern**: Copy the GCP sections and adapt for Azure CLI commands.

### Config additions (`aws/watcher_config.json`):
```json
{
  "azure": {
    "enabled": false,
    "resource_group": "prismata-selfplay",
    "location": "eastus",
    "instance_type": "Standard_D8s_v5",
    "games_per_instance": 5000,
    "think_time": 1,
    "vm_multiplier": 2,
    "auto_relaunch": true
  }
}
```

### Status additions (`aws/watcher_status.json`):
```json
{
  "azure": {
    "alive": 0,
    "running": 0,
    "standard": 0,
    "spot": 0,
    "tracked_instances": 0,
    "batches_launched": 0,
    "auto_relaunch": true
  },
  "quotas": {
    "azure_total_vcpus": 10,
    "azure_spot_vcpus": 0,
    "azure_dv5_vcpus": 10
  }
}
```

### Watcher sections to add (following GCP pattern):

1. **Azure Instance Counting** (after GCP counting, ~line 93):
   ```powershell
   # Count Azure VMs by name pattern
   $azureVMs = az vm list --resource-group $azureResourceGroup --query "[?starts_with(name,'prismata-selfplay-')]" | ConvertFrom-Json
   $azureAlive = ($azureVMs | Where-Object { $_.powerState -in @('VM running','VM starting') }).Count
   $azureRunning = ($azureVMs | Where-Object { $_.powerState -eq 'VM running' }).Count
   ```

2. **Azure Quota Checking**:
   ```powershell
   $azureUsage = az vm list-usage --location $azureLocation --query "[?name.value=='totalRegionalvCPUs']" | ConvertFrom-Json
   $azureTotalQuota = $azureUsage[0].limit
   $azureTotalUsed = $azureUsage[0].currentValue
   ```

3. **Azure Auto-Relaunch** (after GCP auto-relaunch, ~line 300):
   - Same logic: if `prevAzureTrackedInstances > 0 AND azureAlive == 0`, relaunch
   - Pre-relaunch S3 sync
   - Calculate instance count from quota
   - Launch via `bash azure/launch_selfplay.sh`

4. **Azure Scale-Up** (after GCP scale-up, ~line 420):
   - Same logic: if running instances exist but quota has room, launch more

5. **Azure Cleanup** (new section):
   - Find deallocated VMs: `az vm list --resource-group ... --query "[?powerState=='VM deallocated']"`
   - Delete them: `az vm delete --ids ... --yes --no-wait`
   - This handles the Stop-Computer → deallocate → delete lifecycle

6. **Status file output** — add azure section and quota values

### Verification:
- [ ] `watcher_config.json` has `azure` section
- [ ] `watcher_status.json` shows Azure instance counts and quotas
- [ ] `watcher_log.txt` shows Azure monitoring lines
- [ ] Auto-relaunch triggers when Azure instances finish
- [ ] Scale-up works when quota > current instances
- [ ] Deallocated VMs get cleaned up

---

## Phase 4: Update `/status` Command & CLAUDE.md (~20 min)

### Tasks:
1. Update `.claude/commands/status.md` to include Azure fleet status
2. Update `CLAUDE.md` with Azure documentation:
   - Add to "Current Status" section
   - Add Azure gotchas (Custom Script Extension, 2-step launch, deallocate cleanup)
   - Add `azure/` files to Key Files table
   - Add Azure quota info to TheWatcher section
3. Update `.gitignore` to exclude `azure/.aws_credentials`

### Verification:
- [ ] `/status` shows Azure instances, quotas, and game counts
- [ ] CLAUDE.md documents the Azure pipeline
- [ ] `azure/.aws_credentials` is gitignored

---

## Phase 5: End-to-End Test & Go-Live (~30 min)

### Tasks:
1. Run `bash azure/launch_selfplay.sh Standard_D2s_v5 100 1 2 1` (small test: 1 instance, 100 games)
2. Monitor: `az vm list --resource-group prismata-selfplay --output table`
3. Check S3 for shards: `aws s3 ls s3://$CLOUD_BUCKET/results/ --recursive | tail -5`
4. Verify VM deallocates after completion
5. Verify TheWatcher detects the instance and cleans it up
6. If working: enable in watcher config (`azure.enabled: true`)
7. Launch full fleet: `bash azure/launch_selfplay.sh Standard_D8s_v5 5000 1 2 N` (where N = quota / 8)

### Verification:
- [ ] Shards appear in S3 with correct format
- [ ] `load_selfplay.py` can read Azure-generated shards
- [ ] VM self-terminates (deallocates) after work completes
- [ ] TheWatcher auto-relaunches Azure batch when it finishes
- [ ] TheWatcher cleans up deallocated VMs

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Quota stuck at 10 vCPUs for days | Only 1 instance (8 vCPU) | Request increase immediately; start with 1 instance while waiting |
| Custom Script Extension fails silently | VM boots but does nothing | Add logging to S3; test with small VM first |
| Azure spot eviction mid-run | Lost in-flight games (not shards) | Crash-safe design already handles this (shards saved per-run) |
| Azure CLI not in Git Bash PATH | Watcher can't query Azure | Add `az.cmd` to PATH; use `az.cmd` not `az` in PowerShell (like `gcloud.cmd`) |
| Stop-Computer doesn't deallocate (keeps billing) | Unexpected costs | Watcher cleanup deletes deallocated VMs; monitor billing |
| 2-step launch (create + extension) is slow | ~3-5 min per VM vs ~1 min on EC2 | Use `--no-wait` on create, apply extensions in parallel |

---

## Cost Estimate

| Config | $/hr per instance | Fleet of 8 | Monthly (24/7) |
|--------|-------------------|------------|----------------|
| D8s_v5 on-demand (8 vCPU) | ~$0.38 | $3.07/hr | ~$2,210 |
| D8s_v5 spot (8 vCPU) | ~$0.07 | $0.59/hr | ~$425 |

With $200 free credits: **~530 spot-hours** or **~65 on-demand-hours** before paying.

---

## Timeline

| Day | What Happens |
|-----|-------------|
| **Today (Day 0)** | Create Azure account, install CLI, request quotas, create resource group |
| **Day 0-1** | I implement phases 2-4 (launch script, watcher, docs) — can do this while waiting for quotas |
| **Day 1-3** | Quota approval (hopefully). Test with whatever quota you have (even 10 vCPUs = 1 instance) |
| **Day 3-7** | Full fleet running if quota approved. Scale up as quotas increase |

**Key insight**: The implementation work (phases 2-4) doesn't depend on quota approval. I can build everything now, and you flip the switch when quotas come through.
