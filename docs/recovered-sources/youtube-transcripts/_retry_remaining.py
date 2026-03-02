"""
Retry script for 8 remaining YouTube transcript fetches (WDIL Season 2).
YouTube rate-limited the IP after 23 successful fetches.
Run this after the IP block expires (typically 1-2 hours).

Usage: python _retry_remaining.py
"""
import re, os, time, sys

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("pip install youtube-transcript-api")
    sys.exit(1)

outdir = os.path.dirname(os.path.abspath(__file__))

videos = [
    ('TagZB3SEV8k', 'Prismata Why Did I Lose: sano vs Lyra33', 'Why Did I Lose, Season 2'),
    ('SMD1nQF5Pno', 'Prismata Why Did I Lose: DrabEmordnilap vs Shadourow', 'Why Did I Lose, Season 2'),
    ('iE8W2HpCSqU', 'Prismata Why Did I Lose: TheOtterOne vs Slavo', 'Why Did I Lose, Season 2'),
    ('diV-9HXmGg0', 'Prismata Why Did I Lose: StrShPl vs main_gi', 'Why Did I Lose, Season 2'),
    ('7pq6JNfYAMo', 'Prismata Why Did I Lose: London vs 1durbow', 'Why Did I Lose, Season 2'),
    ('t1YEnuBonho', 'Prismata Why Did I Lose: stubbscroll vs EN', 'Why Did I Lose, Season 2'),
    ('iV_N0vbsdRU', 'Prismata Why Did I Lose: Nonsensinator vs Cogito', 'Why Did I Lose, Season 2'),
    ('yDLg_pTJDUE', 'Prismata Why Did I Lose: xnor_ vs Silene_Undulata', 'Why Did I Lose, Season 2'),
]

def make_slug(title, max_len=80):
    s = title.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s.strip())
    s = re.sub(r'-+', '-', s)
    return s[:max_len].rstrip('-')

api = YouTubeTranscriptApi()
success = 0
skipped = 0
failed = []
total_words = 0

for vid_id, title, playlist in videos:
    slug = make_slug(title)
    fname = f'amalloy-{slug}.txt'
    fpath = os.path.join(outdir, fname)
    
    if os.path.exists(fpath):
        skipped += 1
        print(f'SKIP | already exists | {fname}')
        continue
    
    try:
        t = api.fetch(vid_id)
        text = ' '.join([s.text for s in t])
        words = len(text.split())
        total_words += words
        
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(f'# {slug}\n')
            f.write(f'# YouTube ID: {vid_id}\n')
            f.write(f'# Playlist: {playlist}\n')
            f.write(f'# Words: {words}\n')
            f.write(f'\n{text}\n')
        
        success += 1
        print(f'OK  {success}/8 | {words:5d}w | {fname}')
    except Exception as e:
        etype = type(e).__name__
        failed.append((vid_id, title, etype))
        print(f'FAIL      | {vid_id} | {etype}')
        if etype == 'IpBlocked':
            print('\nIP still blocked by YouTube. Try again later.')
            break
    
    time.sleep(2)

print(f'\nResults: {success} new, {skipped} skipped, {len(failed)} failed')
print(f'Total new words: {total_words:,}')
