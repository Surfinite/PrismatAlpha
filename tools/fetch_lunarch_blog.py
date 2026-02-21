import subprocess, re, os, sys, time

OUTPUT_DIR = os.path.join('c:', os.sep, 'libraries', 'PrismataAI', 'docs', 'recovered-sources')

ARTICLES = [
    ('http://blog.lunarchstudios.com/2015/05/22/balancing-prismata-openings-part-1', 'lunarch-blog-balancing-openings-part1.txt'),
    ('http://blog.lunarchstudios.com/2015/05/27/balancing-prismata-openings-part-2', 'lunarch-blog-balancing-openings-part2.txt'),
    ('http://blog.lunarchstudios.com/2015/06/10/balancing-prismata-openings-part-3', 'lunarch-blog-balancing-openings-part3.txt'),
    ('http://blog.lunarchstudios.com/2015/07/08/balancing-prismata-openings-through-unit-design-part-4', 'lunarch-blog-balancing-openings-part4.txt'),
    ('http://blog.lunarchstudios.com/2015/10/21/shalevs-rule-in-prismata', 'lunarch-blog-shalevs-rule.txt'),
    ('http://blog.lunarchstudios.com/2014/10/24/prismatas-tech-trees', 'lunarch-blog-tech-trees.txt'),
    ('http://blog.lunarchstudios.com/2014/08/19/the-prismata-base-set', 'lunarch-blog-base-set.txt'),
    ('http://blog.lunarchstudios.com/2016/04/15/economic-win-conditions-prismata', 'lunarch-blog-economic-win-conditions.txt'),
    ('http://blog.lunarchstudios.com/2016/04/29/annotated-prismata-openings-will-ma', 'lunarch-blog-annotated-openings-will-ma.txt'),
    ('http://blog.lunarchstudios.com/2015/07/14/defending-against-frostbites-in-prismata', 'lunarch-blog-defending-frostbites.txt'),
    ('http://blog.lunarchstudios.com/2015/07/21/the-shadowfang-flame-animus-rush', 'lunarch-blog-shadowfang-rush.txt'),
    ('http://blog.lunarchstudios.com/2014/09/30/how-to-stop-sucking-at-prismata-6-common-mistakes-you-might-be-making', 'lunarch-blog-stop-sucking.txt'),
    ('http://blog.lunarchstudios.com/2014/12/17/the-prismata-ai', 'lunarch-blog-prismata-ai.txt'),
    ('http://blog.lunarchstudios.com/2014/07/22/stepping-away-from-unit-on-unit-combat', 'lunarch-blog-no-combat.txt'),
    ('http://blog.lunarchstudios.com/2014/07/15/luck-in-games', 'lunarch-blog-luck-in-games.txt'),
    ('http://blog.lunarchstudios.com/2014/10/03/sniping-mechanic', 'lunarch-blog-sniping-mechanic.txt'),
    ('http://blog.lunarchstudios.com/2015/07/10/thorium-dynamo-the-craziest-prismata-econ-unit', 'lunarch-blog-thorium-dynamo.txt'),
    ('http://blog.lunarchstudios.com/2015/09/09/vivid-drone', 'lunarch-blog-vivid-drone.txt'),
    ('http://blog.lunarchstudios.com/2015/09/15/longer-build-times-in-prismata', 'lunarch-blog-longer-build-times.txt'),
    ('http://blog.lunarchstudios.com/2014/08/12/game-prismata-rules', 'lunarch-blog-rules.txt'),
    ('http://blog.lunarchstudios.com/2014/11/25/why-doesnt-prismata-have-decks', 'lunarch-blog-no-decks.txt'),
    ('http://blog.lunarchstudios.com/2014/12/02/removing-rng-eliminating-luck-can-benefit-strategy-card-games', 'lunarch-blog-removing-rng.txt'),
    ('http://blog.lunarchstudios.com/2016/03/01/codex-vs-prismata', 'lunarch-blog-codex-comparison.txt'),
    ('http://blog.lunarchstudios.com/2014/09/25/introducing-a-new-feature-in-prismata-the-grandmaster-set', 'lunarch-blog-grandmaster-set.txt'),
    ('http://blog.lunarchstudios.com/2015/12/01/prismata-december-balance-patch-part-1', 'lunarch-blog-balance-dec2015-part1.txt'),
    ('http://blog.lunarchstudios.com/2015/12/09/prismata-december-balance-patch-full-details', 'lunarch-blog-balance-dec2015-full.txt'),
    ('http://blog.lunarchstudios.com/2016/02/11/february-2016-unit-patch-notes-part-1', 'lunarch-blog-balance-feb2016-part1.txt'),
    ('http://blog.lunarchstudios.com/2016/02/14/february-2016-patch-notes-part-2', 'lunarch-blog-balance-feb2016-part2.txt'),
    ('http://blog.lunarchstudios.com/2018/04/01/unit-balance-patch-details', 'lunarch-blog-balance-apr2018.txt'),
    ('http://blog.lunarchstudios.com/2018/04/04/unit-balance-patch-details-real-time', 'lunarch-blog-balance-apr2018-realtime.txt'),
    ('http://blog.lunarchstudios.com/2016/09/29/prismata-k-factor-adjustments-vivid-drone-revamp', 'lunarch-blog-vivid-drone-revamp.txt'),
]


def clean_html(html):
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|h[1-6]|li|tr|blockquote)>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<(p|div|h[1-6]|li|tr|blockquote)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<hr[^>]*>', '\n---\n', text, flags=re.IGNORECASE)
    entity_map = {
        '&nbsp;': ' ', '&#8217;': "'", '&#8216;': "'", '&#8211;': '-',
        '&#8212;': '--', '&#8220;': '"', '&#8221;': '"', '&#8230;': '...',
        '&#8226;': '-', '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"',
        '&#038;': '&', '&rsquo;': "'", '&lsquo;': "'", '&rdquo;': '"',
        '&ldquo;': '"', '&mdash;': '--', '&ndash;': '-', '&hellip;': '...',
        '&bull;': '-', '&trade;': '(TM)', '&copy;': '(c)', '&reg;': '(R)',
        '&#8594;': '->', '&rarr;': '->', '&#215;': 'x', '&times;': 'x',
    }
    for old, new in entity_map.items():
        text = text.replace(old, new)
    def decode_entity(m):
        try:
            return chr(int(m.group(1)))
        except (ValueError, OverflowError):
            return m.group(0)
    text = re.sub(r'&#(\d+);', decode_entity, text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text


def extract_article_content(text):
    title_match = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', text, re.DOTALL | re.IGNORECASE)
    if not title_match:
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.DOTALL | re.IGNORECASE)
    content_match = re.search(r'class="entry-content"[^>]*>', text, re.IGNORECASE)
    if title_match and content_match:
        start = title_match.start()
        end_patterns = [
            r'<div[^>]*id="comments"', r'<footer',
            r'<div[^>]*class="[^"]*post-navigation',
            r'<nav[^>]*class="[^"]*post-navigation',
            r'<div[^>]*class="[^"]*sidebar', r'<aside',
        ]
        end = len(text)
        for ep in end_patterns:
            m = re.search(ep, text[start:], re.IGNORECASE)
            if m and (start + m.start()) < end:
                end = start + m.start()
        return text[start:end]
    return text


def fetch_article(url, filename):
    try:
        result = subprocess.run(
            ['curl', '-ksSL', '--max-time', '30', url],
            capture_output=True, text=True, timeout=45,
            encoding='utf-8', errors='replace'
        )
        if result.returncode != 0:
            return None, "curl error {}: {}".format(result.returncode, result.stderr[:200])
        html = result.stdout
        if not html or len(html) < 500:
            return None, "Too short ({} bytes)".format(len(html))
        if '404' in html[:1000] and 'not found' in html[:1000].lower():
            return None, "404 Not Found"
        article_html = extract_article_content(html)
        title_match = re.search(r'<title>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        title = clean_html(title_match.group(1)).strip() if title_match else filename.replace('.txt', '')
        title = re.sub(r'\s*[\|\u2013-]\s*Lunarch Studios.*$', '', title, flags=re.IGNORECASE).strip()
        text = clean_html(article_html)
        words = len(text.split())
        if words < 50:
            return None, "Too few words ({})".format(words)
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("# {}\n".format(title))
            f.write("# Source: {}\n".format(url))
            f.write("# Words: {}\n\n".format(words))
            f.write(text)
        return words, None
    except subprocess.TimeoutExpired:
        return None, "Timeout (45s)"
    except Exception as e:
        return None, str(e)


def main():
    total_words = 0
    success = 0
    failed = []
    print("Fetching {} articles...".format(len(ARTICLES)))
    for i, (url, filename) in enumerate(ARTICLES, 1):
        sys.stdout.write("[{:2d}/{}] {}... ".format(i, len(ARTICLES), filename))
        sys.stdout.flush()
        words, error = fetch_article(url, filename)
        if words is not None:
            print("OK ({:,} words)".format(words))
            total_words += words
            success += 1
        else:
            print("FAILED: {}".format(error))
            failed.append((filename, url, error))
        if i < len(ARTICLES):
            time.sleep(0.3)
    print("\n" + "=" * 60)
    print("RESULTS: {}/{} articles fetched".format(success, len(ARTICLES)))
    print("Total words: {:,}".format(total_words))
    if failed:
        print("\nFAILED ({}):".format(len(failed)))
        for fname, url, err in failed:
            print("  - {}: {}".format(fname, err))
            print("    {}".format(url))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
