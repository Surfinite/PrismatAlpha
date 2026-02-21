"""Discord post helper - loads commentary messages onto clipboard one at a time.

Usage: python tools/discord_post_helper.py bin/commentary_WjhmP-WWdXx.txt
"""
import sys
import subprocess

def set_clipboard(text):
    p = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
    p.communicate(text.encode('utf-16-le'))

def main():
    if len(sys.argv) < 2:
        print("Usage: python discord_post_helper.py <commentary_file.txt>")
        sys.exit(1)

    with open(sys.argv[1], encoding='utf-8') as f:
        raw = f.read()

    # Split on == MESSAGE N == markers
    parts = raw.split('== MESSAGE ')
    messages = []
    for part in parts[1:]:
        # Strip the "N ==\n\n" header
        idx = part.find('==')
        if idx >= 0:
            content = part[idx+2:].strip()
            messages.append(content)

    print(f"Loaded {len(messages)} messages from {sys.argv[1]}\n")

    for i, msg in enumerate(messages, 1):
        print(f"--- Message {i}/{len(messages)} ({len(msg)} chars) ---")
        print(msg[:80] + "..." if len(msg) > 80 else msg)
        print()
        input(f"Press Enter to copy message {i} to clipboard...")
        set_clipboard(msg)
        print(f"Copied! Paste into Discord (Ctrl+V), send it, then come back.\n")

    print("All done!")

if __name__ == '__main__':
    main()
