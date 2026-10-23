#!/usr/bin/env python3
"""Build the GitHub Pages site: one hep-ph-network-match page per announcement day + an index.

  python3 -I tools/build_site.py --network data/inspire/network_991924.json --site docs [--days 5]

Days: the --days latest hep-ph announcement days dated before today (in --tz), read from
arxiv.org/list/<cat>/recent (the last weekdays when that page cannot be fetched). A day whose
listing cannot be fetched after --retries tries is left for the next run. hepph_match.py reads a
day from the saved recent page when arXiv refuses its catchup page (HTTP 429).
A day's page is (re)built when it is missing or was built less than --settle days after the
listing date (INSPIRE may not have harvested every paper yet). Pages of older days are kept
and listed in the archive. Writes <site>/index.html, <site>/days.json and <site>/.nojekyll.
"""
import argparse, html, json, os, re, subprocess, sys, time, urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "hepph-network-match/1.0 (academic literature alert)"}
HEAD = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n')

def recent_days(cat, save):
    """Announcement days in arxiv.org/list/<cat>/recent; the page (all entries) is saved for hepph_match.py."""
    h = ""
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"https://arxiv.org/list/{cat}/recent?skip=0&show=2000",
                                                               headers=UA), timeout=120) as r:
                h = r.read().decode("utf8", "ignore"); break
        except Exception as e:
            print(f"[warn] recent listing: {e}", file=sys.stderr); time.sleep(20 * (i + 1))
    if h: open(save, "w").write(h)
    out = []
    for d in re.findall(r'<a href="/list/[^"]*recent\?skip=[^"]*">\s*([^<]+?)\s*</a>', h) + \
             re.findall(r'<h3>\s*(\w{3}, \d{1,2} \w{3} \d{4})', h):
        try: out.append(datetime.strptime(d.strip(), "%a, %d %b %Y").date())
        except ValueError: pass
    return sorted(set(out))

def standalone(page, day, back="index.html"):
    """Turn the artifact-style page from hepph_match.py into a complete HTML document with a back link."""
    s = open(page).read()
    if s.lstrip().lower().startswith("<!doctype"): return
    nav = (f'<nav style="max-width:1180px;margin:0 auto;padding:16px 16px 0;font-family:\'IBM Plex Mono\',ui-monospace,monospace;font-size:13px">'
           f'<a href="{back}" style="color:var(--seed)">← All days</a></nav>\n')
    s = s.replace("<title>", f"<title>{day} · ", 1)
    i = s.find('<div class="wrap">')
    s = HEAD + s[:i] + "</head>\n<body>\n" + nav + s[i:] + "\n</body>\n</html>\n"
    open(page, "w").write(s)

def summary(js, th):
    rows = json.load(open(js))
    return {"nlist": len(rows), "nrel": sum(r["score"] >= th for r in rows),
            "top": [{"arxiv": r["arxiv"], "title": r["title"], "score": r["score"], "section": r["section"]}
                    for r in rows if r["score"] >= th][:3]}

def index(site, man, net, args):
    e = html.escape
    t = lambda x: e(re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"[\\{}^_]", "", m.group(1)), x))   # plain text for $...$
    days = sorted(man.values(), key=lambda d: d["date"], reverse=True)
    cur, old = days[:args.days], days[args.days:]
    def card(d):
        tops = "".join(f'<li><span class="sc">{x["score"]:.0f}</span> <a href="https://arxiv.org/abs/{e(x["arxiv"])}">{t(x["title"])}</a></li>'
                       for x in d["top"]) or '<li class="none">No paper reached the threshold.</li>'
        wd = datetime.strptime(d["date"], "%Y-%m-%d").strftime("%A")
        return (f'<article class="day"><div class="when"><span class="wd">{wd}</span> {e(d["date"])}</div>'
                f'<h2><a href="{e(d["page"])}">{d["nrel"]} of {d["nlist"]} papers match</a></h2><ol>{tops}</ol>'
                f'<a class="open" href="{e(d["page"])}">Open the ranked listing →</a></article>')
    arch = "".join(f'<li><a href="{e(d["page"])}">{e(d["date"])}</a> · {d["nrel"]} of {d["nlist"]}</li>' for d in old)
    a = net["author"]; c = net["counts"]
    who = " ".join(reversed(a["name"].split(", ", 1)))
    body = f"""{HEAD}<title>hep-ph Network Match</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#f6f7f9;--surface:#fff;--fg:#14171c;--fg-2:#4a5160;--fg-3:#6f7686;--line:#dde1e8;--accent:#2a78d6;--hot:#d95a22;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#111317;--surface:#181b20;--fg:#eceef2;--fg-2:#b4bac6;--fg-3:#8b92a0;--line:#2a2f37;--accent:#3987e5;--hot:#e8703a;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#111317;--surface:#181b20;--fg:#eceef2;--fg-2:#b4bac6;--fg-3:#8b92a0;--line:#2a2f37;--accent:#3987e5;--hot:#e8703a;color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 "IBM Plex Sans",system-ui,sans-serif}}
.wrap{{max-width:1000px;margin:0 auto;padding:32px 16px 48px;display:grid;gap:24px}}
.eyebrow{{font:12px "IBM Plex Mono",monospace;color:var(--fg-3);letter-spacing:.04em}}
h1{{font-family:Spectral,Georgia,serif;font-weight:600;font-size:clamp(1.6rem,3.4vw,2.3rem);line-height:1.15;margin:4px 0 8px;text-wrap:balance}}
.dek{{color:var(--fg-2);max-width:75ch;margin:0}}
a{{color:var(--accent)}}
.days{{display:grid;gap:14px}}
.day{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 20px;display:grid;gap:6px}}
.when{{font:13px "IBM Plex Mono",monospace;color:var(--fg-3)}}.wd{{color:var(--hot);font-weight:500}}
.day h2{{font-family:Spectral,Georgia,serif;font-weight:600;font-size:1.25rem;margin:0}}
.day h2 a{{color:var(--fg);text-decoration:none}}.day h2 a:hover{{text-decoration:underline}}
.day ol{{list-style:none;margin:0;padding:0;display:grid;gap:4px;font-size:14px}}
.day li{{display:flex;gap:10px;align-items:baseline}}.day li a{{color:var(--fg-2);text-decoration:none}}.day li a:hover{{text-decoration:underline}}
.sc{{font:500 12px "IBM Plex Mono",monospace;color:var(--hot);min-width:2.2em;text-align:right;flex:none}}
.none{{color:var(--fg-3)}}.open{{font-size:14px}}
h3{{font-family:Spectral,Georgia,serif;font-weight:600;font-size:1.1rem;margin:0 0 6px}}
.arch{{margin:0;padding-left:18px;color:var(--fg-2);font-size:14px;columns:2 220px}}
.foot{{font-size:12.5px;color:var(--fg-3);display:grid;gap:6px;max-width:95ch}}.foot p{{margin:0}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="eyebrow">arXiv {e(args.category)} · INSPIRE author {e(str(a["recid"]))}</div>
  <h1>New {e(args.category)} papers close to the citation network of {e(who)}</h1>
  <p class="dek">The last {len(cur)} announcement day{"s" if len(cur) != 1 else ""} of the arXiv {e(args.category)} listing (new submissions, cross-lists and replacements), each ranked by how strongly a paper cites, shares references with or is written by members of the network. Scores run from 0 to 100; a page lists every paper scoring {args.threshold:g} or more.</p>
</header>
<section class="days" aria-label="Latest announcement days">{"".join(card(d) for d in cur) or '<p>No pages yet.</p>'}</section>
{f'<section><h3>Earlier days</h3><ul class="arch">{arch}</ul></section>' if arch else ''}
<footer class="foot">
  <p><b>Network.</b> {c["own"]} papers by {e(who)} with at most {net["params"]["max_authors"]} authors and {c["external"]} papers by others around them ({c["coupled"]} by bibliographic coupling, {c["citing"]} important citing papers), built from INSPIRE-HEP on {e(net["built"])}. File: <a href="https://github.com/{e(args.repo)}/blob/main/{e(args.network)}">{e(os.path.basename(args.network))}</a>.</p>
  <p><b>Method.</b> Pages made with the hep-network-builder and hep-ph-network-match tools in <a href="https://github.com/{e(args.repo)}/tree/main/tools">tools/</a>; rebuilt twice a day, Monday to Saturday, by a GitHub Actions workflow. Updated {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}.</p>
</footer>
</div>
</body>
</html>
"""
    open(os.path.join(site, "index.html"), "w").write(body)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", required=True); ap.add_argument("--site", default="docs")
    ap.add_argument("--days", type=int, default=5); ap.add_argument("--threshold", type=float, default=10)
    ap.add_argument("--category", default="hep-ph"); ap.add_argument("--tz", default="America/Bogota")
    ap.add_argument("--settle", type=int, default=2, help="rebuild a page built less than this many days after its date")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "restrepo/hep-ph"))
    ap.add_argument("--work", default="hepph_work")
    ap.add_argument("--retries", type=int, default=1, help="retries per day when arXiv or INSPIRE cannot be fetched")
    ap.add_argument("--pause", type=int, default=30, help="seconds between days (multiplied on each retry)")
    args = ap.parse_args()
    os.makedirs(args.site, exist_ok=True)
    open(os.path.join(args.site, ".nojekyll"), "w").close()
    mpath = os.path.join(args.site, "days.json")
    man = {d["date"]: d for d in json.load(open(mpath))} if os.path.exists(mpath) else {}
    net = json.load(open(args.network))

    today = datetime.now(ZoneInfo(args.tz)).date()
    os.makedirs(args.work, exist_ok=True)
    recent = os.path.join(args.work, "recent.html")
    cand = sorted((d for d in recent_days(args.category, recent) if d < today), reverse=True)
    if not cand:                                  # 'recent' unreachable: assume weekdays are announcement days
        d = today
        while len(cand) < args.days:
            d -= timedelta(days=1)
            if d.weekday() < 5: cand.append(d)
    cand = cand[:args.days]

    # arXiv answers 429 to bursts from cloud runners: pause between days, wait longer on each retry,
    # and leave a day that still fails for the next run (an older day never takes its place).
    first = True
    for d in cand:
        ds = d.isoformat(); page = f"hep-ph-{ds}.html"; out = os.path.join(args.site, page)
        old = man.get(ds)
        if old and old.get("nlist", 0) and os.path.exists(out) and \
           (date.fromisoformat(old["built"]) - d).days >= args.settle:
            print(f"{ds}: up to date", file=sys.stderr); continue
        for attempt in range(args.retries + 1):
            if not first: time.sleep(args.pause * (attempt + 1))
            first = False
            print(f"{ds}: building (attempt {attempt + 1})", file=sys.stderr, flush=True)
            p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "hepph_match.py"), "--network", args.network,
                                "--date", ds, "--threshold", str(args.threshold), "--category", args.category,
                                "--work", os.path.join(args.work, ds), "--recent-html", recent, "--out", out],
                               stderr=subprocess.PIPE, text=True)
            sys.stderr.write(p.stderr)
            if p.returncode == 0 or "no papers found" in p.stderr: break
        if p.returncode != 0 or not os.path.exists(out):
            print(f"{ds}: not built ({'no announcement' if 'no papers found' in p.stderr else 'fetch failed'})", file=sys.stderr)
            continue
        standalone(out, ds)
        man[ds] = {"date": ds, "page": page, "built": today.isoformat(), **summary(os.path.splitext(out)[0] + ".json", args.threshold)}
    json.dump(sorted(man.values(), key=lambda x: x["date"], reverse=True), open(mpath, "w"), ensure_ascii=False, indent=1)
    index(args.site, man, net, args)
    print(f"index: {len(man)} days -> {args.site}/index.html", file=sys.stderr)

if __name__ == "__main__":
    main()
