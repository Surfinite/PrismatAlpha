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

Prismata connects to its game server via a hostname. This tool temporarily redirects that hostname to your own computer (via the Windows hosts file), running a local proxy that forwards all traffic to the real server untouched. While forwarding, it asks the server for your replay codes using the same protocol messages the game client uses internally.

The extraction uses two methods:
1. The `/getreplays` chat command — instant, but the server caps it at 5,000 codes
2. The `RequestReplays` protocol message (the same one the in-game replay browser uses) to fetch the rest in batches of 100

When it's done, it restores your hosts file so Prismata connects directly again.

## What It Does NOT Do

- Does not modify your Prismata installation or SWF files
- Does not send your credentials anywhere — they go straight to the real server
- Does not store or log any game traffic — only the replay codes
- Does not run in the background after completion
- Zero third-party dependencies — only Python standard library

## Why It Needs Administrator

Solely to edit `C:\Windows\System32\drivers\etc\hosts` (the network redirect). You can verify this yourself — search for `HOSTS_PATH` in the Python script. The entire tool is ~1,000 lines of readable Python, no compiled binaries.

## Requirements

- **Windows**
- **Prismata** installed via Steam

That's it — Python is included in the `python/` folder.

## Troubleshooting

**Prismata won't connect** — The tool restores the hosts file automatically, but if it crashed, you can fix it manually: open `C:\Windows\System32\drivers\etc\hosts` as Administrator and change the line containing `ec2-54-83-83-240` to:
```
3.229.49.48 ec2-54-83-83-240.compute-1.amazonaws.com
```

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
