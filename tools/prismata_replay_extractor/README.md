# Prismata Replay Code Extractor

Extracts **all** of your replay codes from the Prismata server — even the ones older than what `/getreplays` gives you (which caps at 5,000).

## Quick Start

1. Extract this zip somewhere
2. Double-click **`run_replay_dump.bat`**
3. Approve the Administrator prompt
4. Launch Prismata and log in normally
5. Tab back to the cmd window to see progress — your codes are saved to `my_replay_codes_YourName.txt`

No install needed — Python is bundled in the zip.

## How It Works

1. **Temporarily patches** `Prismata.swf` so the game client connects via hostname (the unpatched client uses a hardcoded IP that can't be redirected)
2. **Redirects** that hostname to your own computer (via the Windows hosts file)
3. **Runs a local proxy** that forwards all traffic to the real server untouched
4. **Asks the server** for your replay codes using the same protocol the game uses internally
5. **Restores everything** — unpatches the SWF and restores the hosts file

The extraction uses two methods:
1. The `/getreplays` chat command — instant, but the server caps it at 5,000 codes
2. The `RequestReplays` protocol message (the same one the in-game replay browser uses) to fetch the rest in batches of 100

## What It Does NOT Do

- Does not permanently modify your Prismata installation — the SWF patch is reversed on exit
- Does not send your credentials anywhere — they go straight to the real server
- Does not store or log any game traffic — only the replay codes
- Does not run in the background after completion
- Zero third-party dependencies — only Python standard library

## Why It Needs Administrator

To edit `C:\Windows\System32\drivers\etc\hosts` (the network redirect) and to patch/unpatch the SWF file in Steam's folder. You can verify this yourself — search for `HOSTS_PATH` and `patch_swf` in the Python script. The entire tool is readable Python, no compiled binaries.

## Requirements

- **Windows**
- **Prismata** installed via Steam

That's it — Python is included in the `python/` folder.

## Troubleshooting

**Prismata won't connect** — The tool restores everything automatically, but if it crashed:
1. Open `C:\Windows\System32\drivers\etc\hosts` as Administrator and change the line containing `ec2-54-83-83-240` to:
   ```
   3.229.49.48 ec2-54-83-83-240.compute-1.amazonaws.com
   ```
2. In Steam, right-click Prismata → Properties → Installed Files → "Verify integrity of game files" to restore the SWF

**"Timed out waiting for login"** — Make sure you launch Prismata *after* the tool says "Proxy ready". If Prismata was already open, close and relaunch it.

## Output Format

One replay code per line, newest first:
```
F59kH-qqEZ2
rJzFP-yFDJm
mKcli-2Tsag
...
```

View any replay at: `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/CODE.json.gz`

Or paste codes into [prismata-stats](https://prismata-stats.web.app/) for game analytics.

## Credits

Built by Surfinite for the Prismata community.
