#!/usr/bin/env python3
"""Prismata Replay Capture Tool

One-script setup: patches SWF for proxy compatibility, redirects traffic
through a local proxy, and captures replay codes from completed games.
Restores everything on exit.

Usage:
    python replay_capture.py              # auto-detect SWF location
    python replay_capture.py --swf-dir "C:\path\to\Prismata"

Requires admin privileges (for hosts file modification).
"""

import argparse
import atexit
import ctypes
import os
import shutil
import signal
import subprocess
import sys
import zlib

# ─── Constants ───────────────────────────────────────────────────────────────

PRISMATA_HOSTNAME = "ec2-54-83-83-240.compute-1.amazonaws.com"
REAL_SERVER_IP = "3.229.49.48"
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
HOSTS_MARKER = "# Prismata Replay Capture"

SWF_FILENAME = "Prismata.swf"
SWF_BACKUP_SUFFIX = ".replay_capture_backup"
SWF_PATCH_OFFSET = 0x1580196   # Offset in decompressed (FWS) file
SWF_PATCH_FROM = 0x27           # AVM2 pushfalse
SWF_PATCH_TO = 0x26             # AVM2 pushtrue

STEAM_SEARCH_PATHS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Prismata",
    r"C:\Program Files\Steam\steamapps\common\Prismata",
    r"D:\Steam\steamapps\common\Prismata",
    r"D:\SteamLibrary\steamapps\common\Prismata",
    r"E:\Steam\steamapps\common\Prismata",
    r"E:\SteamLibrary\steamapps\common\Prismata",
]

# ─── Admin elevation ─────────────────────────────────────────────────────────

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_and_relaunch():
    """Re-launch this script with admin privileges via UAC prompt."""
    print("[!] Admin privileges required for hosts file modification.")
    print("[!] Requesting elevation...")
    params = " ".join(f'"{a}"' for a in sys.argv)
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )
    if ret <= 32:
        print("[!] Elevation failed or was denied. Exiting.")
        sys.exit(1)
    sys.exit(0)


# ─── SWF patching ────────────────────────────────────────────────────────────

def find_swf(swf_dir=None):
    """Find Prismata.swf, searching common Steam paths if not specified."""
    if swf_dir:
        path = os.path.join(swf_dir, SWF_FILENAME)
        if os.path.isfile(path):
            return path
        print(f"[!] SWF not found at: {path}")
        sys.exit(1)

    for search_dir in STEAM_SEARCH_PATHS:
        path = os.path.join(search_dir, SWF_FILENAME)
        if os.path.isfile(path):
            print(f"[+] Found SWF: {path}")
            return path

    print("[!] Could not find Prismata.swf in common Steam locations.")
    print("[!] Use --swf-dir to specify the Prismata installation directory.")
    sys.exit(1)


def patch_swf(swf_path):
    """Patch Prismata.swf to disable load balancing (enables proxy interception).

    The patch changes FlashBuildOptions.developerVersion from false to true,
    which forces the client to connect via hostname instead of hardcoded IP.
    """
    backup_path = swf_path + SWF_BACKUP_SUFFIX

    # Check if already patched
    if os.path.exists(backup_path):
        print("[*] SWF backup already exists — checking if patch is needed...")
        # Read current SWF to verify patch state
        with open(swf_path, "rb") as f:
            data = f.read()
        patched_byte = _read_patch_byte(data)
        if patched_byte == SWF_PATCH_TO:
            print("[*] SWF already patched — skipping.")
            return backup_path
        # Backup exists but SWF isn't patched (maybe Steam verified files)
        print("[*] SWF was reverted — re-patching...")

    # Read SWF
    with open(swf_path, "rb") as f:
        data = f.read()

    # Verify it's a valid SWF
    sig = data[:3]
    if sig not in (b"CWS", b"FWS"):
        print(f"[!] Not a valid SWF file (signature: {sig})")
        sys.exit(1)

    # Check current state
    current_byte = _read_patch_byte(data)
    if current_byte == SWF_PATCH_TO:
        print("[*] SWF already patched.")
        if not os.path.exists(backup_path):
            print("[!] WARNING: No backup found for already-patched SWF.")
        return backup_path

    if current_byte != SWF_PATCH_FROM:
        print(f"[!] Unexpected byte at patch offset: {current_byte:#x}")
        print(f"[!] Expected {SWF_PATCH_FROM:#x} (pushfalse). SWF may be a different version.")
        sys.exit(1)

    # Create backup
    if not os.path.exists(backup_path):
        shutil.copy2(swf_path, backup_path)
        print(f"[+] Backup created: {backup_path}")

    # Patch
    new_data = _apply_patch(data, SWF_PATCH_TO)

    with open(swf_path, "wb") as f:
        f.write(new_data)

    print("[+] SWF patched successfully (load balancing disabled).")
    return backup_path


def restore_swf(swf_path):
    """Restore SWF from backup."""
    backup_path = swf_path + SWF_BACKUP_SUFFIX
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, swf_path)
        os.remove(backup_path)
        print("[+] SWF restored from backup.")
    else:
        # Try to unpatch directly
        with open(swf_path, "rb") as f:
            data = f.read()
        if _read_patch_byte(data) == SWF_PATCH_TO:
            new_data = _apply_patch(data, SWF_PATCH_FROM)
            with open(swf_path, "wb") as f:
                f.write(new_data)
            print("[+] SWF unpatched (no backup found, reversed in-place).")
        else:
            print("[*] SWF already in original state.")


def _read_patch_byte(swf_data):
    """Read the byte at the patch offset, handling CWS compression."""
    if swf_data[:3] == b"CWS":
        body = zlib.decompress(swf_data[8:])
        offset = SWF_PATCH_OFFSET - 8
        return body[offset]
    elif swf_data[:3] == b"FWS":
        return swf_data[SWF_PATCH_OFFSET]
    else:
        return None


def _apply_patch(swf_data, new_byte):
    """Apply the patch byte, handling CWS compression."""
    if swf_data[:3] == b"CWS":
        header = swf_data[:8]
        body = zlib.decompress(swf_data[8:])
        offset = SWF_PATCH_OFFSET - 8
        body = body[:offset] + bytes([new_byte]) + body[offset + 1:]
        return header + zlib.compress(body)
    elif swf_data[:3] == b"FWS":
        offset = SWF_PATCH_OFFSET
        return swf_data[:offset] + bytes([new_byte]) + swf_data[offset + 1:]


# ─── Hosts file management ───────────────────────────────────────────────────

def set_hosts_proxy():
    """Add hosts entry to redirect Prismata traffic to local proxy."""
    _update_hosts_entry(f"127.0.0.1 {PRISMATA_HOSTNAME}  {HOSTS_MARKER}")
    print("[+] Hosts file set to PROXY mode (127.0.0.1).")


def set_hosts_direct():
    """Restore hosts entry to point to real server (for dev mode SWF)."""
    _update_hosts_entry(
        f"{REAL_SERVER_IP} {PRISMATA_HOSTNAME}  "
        f"# Prismata dev mode - redirect dead amazonAlpha to live server"
    )
    print("[+] Hosts file restored to DIRECT mode.")


def _update_hosts_entry(new_line):
    """Replace or add the Prismata hosts entry."""
    try:
        with open(HOSTS_PATH, "r", encoding="utf-8-sig") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""

    # Remove any existing Prismata line
    lines = content.splitlines()
    filtered = [l for l in lines if PRISMATA_HOSTNAME not in l]
    filtered.append(new_line)

    new_content = "\n".join(filtered) + "\n"

    try:
        # Use WriteAllText equivalent — safe, atomic-ish write
        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
    except PermissionError:
        print("[!] Cannot write hosts file — need admin privileges.")
        sys.exit(1)

    # Flush DNS cache
    subprocess.run(
        ["ipconfig", "/flushdns"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


# ─── Sniffer proxy launcher ──────────────────────────────────────────────────

def find_sniffer():
    """Find prismata_sniffer.py relative to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sniffer = os.path.join(script_dir, "prismata_sniffer.py")
    if os.path.isfile(sniffer):
        return sniffer

    # Also check parent/tools/ in case running from project root
    for candidate in [
        os.path.join(script_dir, "..", "tools", "prismata_sniffer.py"),
        os.path.join(script_dir, "tools", "prismata_sniffer.py"),
    ]:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    print("[!] Cannot find prismata_sniffer.py")
    sys.exit(1)


def start_sniffer(sniffer_path):
    """Start the sniffer proxy as a subprocess."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, sniffer_path, "proxy"],
        env=env,
        # Inherit stdio so user sees sniffer output
    )
    return proc


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Prismata Replay Capture — patches SWF, proxies traffic, captures replay codes."
    )
    parser.add_argument(
        "--swf-dir",
        help="Path to the Prismata installation directory containing Prismata.swf",
    )
    parser.add_argument(
        "--no-patch",
        action="store_true",
        help="Skip SWF patching (if already using dev SWF)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Prismata Replay Capture Tool")
    print("=" * 60)
    print()

    # ── Admin check ──
    if not is_admin():
        elevate_and_relaunch()
        return  # unreachable, but clear

    # ── Find and patch SWF ──
    swf_path = None
    if not args.no_patch:
        swf_path = find_swf(args.swf_dir)
        patch_swf(swf_path)

    # ── Set hosts to proxy mode ──
    set_hosts_proxy()

    # ── Find and start sniffer ──
    sniffer_path = find_sniffer()
    print(f"[*] Starting proxy: {sniffer_path}")
    sniffer_proc = start_sniffer(sniffer_path)

    # ── Register cleanup ──
    cleaned_up = False

    def cleanup():
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        print()
        print("=" * 60)
        print("  Shutting down...")
        print("=" * 60)

        # Stop sniffer
        if sniffer_proc.poll() is None:
            sniffer_proc.terminate()
            try:
                sniffer_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                sniffer_proc.kill()
            print("[+] Sniffer stopped.")

        # Restore hosts
        set_hosts_direct()

        # Restore SWF
        if swf_path and not args.no_patch:
            restore_swf(swf_path)

        print()
        print("[+] All done! You can launch Prismata normally now.")
        print("[+] Captured replay codes are in: bin/prismata_capture_codes.txt")

    atexit.register(cleanup)

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGBREAK, signal_handler)

    # ── Wait for user ──
    print()
    print("=" * 60)
    print("  Ready! Launch Prismata and play/spectate games.")
    print("  Replay codes will be captured automatically.")
    print()
    print("  When done: close Prismata, then press Ctrl+C here.")
    print("=" * 60)
    print()

    try:
        sniffer_proc.wait()
    except (KeyboardInterrupt, SystemExit):
        pass

    # If sniffer died on its own, wait for user before cleaning up
    if not cleaned_up:
        print()
        input("[*] Press Enter to restore SWF and hosts file...")
        cleanup()


if __name__ == "__main__":
    main()
