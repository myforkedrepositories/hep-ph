---
name: "hep-ph-network-match"
description: "Ranks the arXiv hep-ph listing (yesterday's announcement by default, or a given date) by how strongly each paper belongs to an author's INSPIRE reference and citation network (a network file from hep-network-builder, or Diego Restrepo's by default), and publishes an HTML page listing the papers above a score threshold (default 10) with title, authors and abstract, plus the next 10 papers by score in a collapsed list."
---

# hep-ph network match

Use when the user asks which new hep-ph papers are close to their network, to "read the new
articles", to filter or rank the arXiv listing against their papers, or names this skill.

## Inputs

- **Date**: default is **yesterday**: the most recent announcement day listed in
  `https://arxiv.org/list/hep-ph/recent` that is dated before today (in `--tz`, default
  America/Bogota). By then its papers are normally all on INSPIRE with references. If the
  user gives a date (any form: "last Monday", "2026-10-20"), convert it to `YYYY-MM-DD` using
  today's date and pass `--date`; `--date latest` uses today's listing
  (`https://arxiv.org/list/hep-ph/new`), which INSPIRE may not have harvested yet. A dated
  run reads `https://arxiv.org/catchup/hep-ph/<date>` (that day's announcement: new,
  cross-lists, replacements). Weekends have no announcement; if the script says no papers
  were found, tell the user and offer the previous announcement day. arXiv often answers 429 to the
  catchup page from cloud machines; the script then reads that day's new submissions and
  cross-lists from `https://arxiv.org/list/hep-ph/recent?skip=0&show=2000` (no replacements; a
  paper counts as cross-list when its primary category is not hep-ph). `--recent-html FILE` passes
  a saved copy of that page, so several days cost one request.
- **Threshold**: `--threshold`, default 10 (scores go from 0 to 100).
- **Category**: `--category`, default `hep-ph`.
- **Sections**: `--sections new,cross,replacement` (default all three; use `new,cross` if the
  user wants no replacements).

## 1. Get the network data

Preferred: a compact network file made by the `hep-network-builder` skill. If the project has a
doc `claude/network_<ID>.json` (check `project_info`), read it with `Projects` `project_read`,
copy the returned `local_file` into the working folder (`cp <local_file> network.json`) and
pass `--network network.json`. It holds the own papers, the external papers and the co-authors,
so nothing else is needed, and the author name and ID come from it. If several network files
exist, use the one the user names, else the most recently created.

Fallback, when no network file exists:

1. Own papers: if the project doc `claude/restrepo_inspire_ac1-10.json` is available,
   read it with `Projects` `project_read`, copy the returned `local_file` into the working
   folder (`cp <local_file> own.json`) and pass `--own own.json`. Otherwise (no project, or a
   scheduled run) leave out `--own`: the script downloads the same set from INSPIRE
   (`authors.recid:991924 and ac 1->10`).
2. External papers: attach the public repository with `add_repo` (owner `restrepo`,
   repo `hep-ph`), then clone it with a generous timeout:
   `GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/restrepo/hep-ph /home/claude/restrepo/hep-ph`
   (skip if it is already cloned there). The file is
   `/home/claude/restrepo/hep-ph/data/inspire/restrepo_network_external_papers.json.gz`;
   pass it as `--external`. Never add it to the project (too large).

## 2. Write the generator and run it

Write the two bundled files below into one folder (copy each block exactly), then run:

```bash
python3 -I hepph_match.py --network network.json \
  [--date YYYY-MM-DD|latest] [--threshold 10] --work hepph_work --out 'hep-ph-{date}.html'
```

(or `[--own own.json] --external <path to the .gz>` in place of `--network`). `{date}` in `--out` becomes the listing date. It takes 1–3 minutes. It prints the ranked list (matches plus the next five) and writes
`hep-ph-<date>.html` and `hep-ph-<date>.json` (all papers with scores and components).
What it does:

- Listing papers come from the arXiv listing page; titles, authors and abstracts from the
  arXiv API.
- References: the INSPIRE record when it is already harvested; otherwise the arXiv source is
  downloaded, the bibliography is read (.bbl, inline `thebibliography`, or the cited entries
  of .bib files) and each entry is matched to INSPIRE by arXiv number, DOI and texkey.
  INSPIRE sometimes answers 502 for a batch; those warnings only lose a few DOI matches.
- Score (0–100): 40% direct citations of network papers (own papers 1, other network papers
  0.6, network papers with over 1,000 citations 0.06, saturating as 1 − e^−x); 35%
  idf-weighted bibliographic coupling with the own papers (best and mean of top three,
  0.30 = full); 15% best coupling with the other network papers (0.35 = full); 10%
  authorship (the author by name, or co-authors from the own papers).
- The page lists every paper at or above the threshold first, highest score first, each with
  section, score, title, authors, full abstract (math rendered with MathJax), the reasons
  (cited network papers, closest own paper and network paper with shared references), the
  four score components and links (INSPIRE, arXiv, PDF, and arXiv's experimental HTML
  version when it exists). Below it, the network laid out by year (citations solid,
  coupling-only links dashed) with a detail panel; then, collapsed (`<details>`), the next 10
  papers by score below the threshold, with the same reasons, a folded abstract and links, not
  drawn in the network; then the method notes.

## 3. Check once and publish

If the session can screenshot the page (e.g. Playwright), take one look and fix what it shows
in one pass. Publish the HTML with the Artifact tool (`icon: "graph"`, a one-sentence
`description` naming the listing date). For a later date, publish a new file name so each
day keeps its own page; to redo the same day, publish the same path.

In a scheduled run with nobody watching, publish without asking, then send the reply below
with `SendUserMessage` so it reaches the user.

## 4. Reply

One line on the listing (date, how many papers, how many matched), then the matches as a
short table: rank, score, section, arXiv number, short title, the main link (cited network
papers, co-authors, or the closest own paper). Name the papers just below the threshold in one
line. Mention how many references came from arXiv sources rather than INSPIRE, and any paper
whose bibliography had no machine-readable identifiers (score near 0 for that reason). Do not
paste the artifact URL.

## Bundled file: hepph_match.py

```python
#!/usr/bin/env python3
"""Rank an arXiv listing by how strongly each paper belongs to a citation network.

  python3 -I hepph_match.py (--network NETWORK.json | [--own OWN.json] --external EXT.json.gz)
         [--date YYYY-MM-DD|yesterday|latest]
         [--tz America/Bogota] [--category hep-ph] [--threshold 10] [--sections new,cross,replacement]
         [--author-recid 991924] [--author-name "Restrepo, Diego"]
         [--work DIR] [--recent-html FILE] --out PAGE.html

--network   compact network file from build_network.py (own + external papers, co-authors)
--own       INSPIRE search response with the author's own papers (hits.hits[n].metadata)
--external  INSPIRE search response (optionally .gz) with the other network papers
--date      announcement date; default 'yesterday' = the latest announcement day in
            arxiv.org/list/<cat>/recent dated before today in --tz; 'latest' = arxiv.org/list/<cat>/new
If the catchup page for --date is refused, the day's new submissions and cross-lists are read from
arxiv.org/list/<cat>/recent instead (replacements are then missing).
Writes PAGE.html (self-contained page, with the next 10 papers below the threshold in a collapsed
list) and PAGE.json (all scored papers).
"""
import argparse, gzip, io, json, math, os, re, sys, tarfile, time, unicodedata
import urllib.parse, urllib.request, xml.etree.ElementTree as ET
from collections import Counter

UA = {"User-Agent": "hepph-network-match/1.0 (academic literature alert)"}
HERE = os.path.dirname(os.path.abspath(__file__))

def http(url, binary=False, tries=4, timeout=120):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                b = r.read()
                return b if binary else b.decode("utf8", "ignore")
        except Exception as e:
            if i == tries - 1:
                print(f"[warn] {url[:90]}: {e}", file=sys.stderr); return None
            time.sleep(3 * (i + 1))

def load_json(p):
    return json.load(gzip.open(p, "rt") if p.endswith(".gz") else open(p))

# ---------- 1. listing ----------
def previous_day(cat, tz):
    """Latest announcement day in arxiv.org/list/<cat>/recent dated before today (in tz)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo(tz)).date()
    h = http(f"https://arxiv.org/list/{cat}/recent")
    if not h: sys.exit("could not fetch the recent listing")
    for d in re.findall(r'<a href="/list/[^"]*recent\?skip=[^"]*">\s*([^<]+?)\s*</a>', h):
        try: day = datetime.strptime(d.strip(), "%a, %d %b %Y").date()
        except ValueError: continue
        if day < today: return day.isoformat()
    sys.exit("no announcement day before today in the recent listing")

def from_recent(cat, date, recent_html=None):
    """One day's papers from arxiv.org/list/<cat>/recent (new submissions and cross-lists, no replacements).
    Used when the catchup page is refused (arXiv often answers 429 to it from cloud machines)."""
    from datetime import datetime
    h = open(recent_html).read() if recent_html and os.path.exists(recent_html) else \
        http(f"https://arxiv.org/list/{cat}/recent?skip=0&show=2000")
    if not h: return []
    parts = re.split(r"<h3>([^<]*)</h3>", h)
    for i in range(1, len(parts), 2):
        m = re.match(r"\s*(\w{3}, \d{1,2} \w{3} \d{4})", parts[i])
        if m and datetime.strptime(m.group(1), "%a, %d %b %Y").date().isoformat() == date:
            ids = dict.fromkeys(re.findall(r'href\s*=\s*"/abs/(\d{4}\.\d{4,5})', parts[i + 1]))
            return [{"arxiv": a, "section": "new", "guess": True} for a in ids]
    return []

def listing(cat, date, work, recent_html=None):
    url = f"https://arxiv.org/catchup/{cat}/{date}" if date else f"https://arxiv.org/list/{cat}/new"
    h = http(url, tries=2 if date else 4)
    if not h and date:
        out = from_recent(cat, date, recent_html)
        if not out: sys.exit(f"could not fetch {url}, and {date} is not in the recent listing")
        print(f"[warn] {url} refused; using the recent listing (no replacements)", file=sys.stderr)
        return out, time.strftime("%A, %d %B %Y", time.strptime(date, "%Y-%m-%d")), url
    if not h: sys.exit(f"could not fetch {url}")
    open(os.path.join(work, "listing.html"), "w").write(h)
    m = re.search(r"(?:Showing new listings for|New submissions for)\s*([^<]+)", h)
    label = m.group(1).strip() if m else (date or "latest")
    if date and not m:
        label = time.strftime("%A, %d %B %Y", time.strptime(date, "%Y-%m-%d"))
    parts = re.split(r"<h3>\s*(New submissions|Cross submissions|Cross-lists|Replacement submissions|Replacements)", h)
    out, seen = [], set()
    for i in range(1, len(parts), 2):
        sec = {"new": "new", "cross": "cross", "replacement": "replacement", "replacements": "replacement",
               "cross-lists": "cross"}[parts[i].split()[0].lower()]
        for a in re.findall(r'href\s*=\s*"/abs/(\d{4}\.\d{4,5})', parts[i + 1]):
            if a not in seen: seen.add(a); out.append({"arxiv": a, "section": sec})
    if not out: sys.exit(f"no papers found in {url} (no announcement that day?)")
    return out, label, url

def arxiv_meta(ids):
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    out = {}
    for i in range(0, len(ids), 100):
        x = http("https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"id_list": ",".join(ids[i:i + 100]), "max_results": 200}), binary=True)
        if not x: continue
        for e in ET.fromstring(x).findall("a:entry", ns):
            aid = re.sub(r"v\d+$", "", e.find("a:id", ns).text.rsplit("/abs/", 1)[1])
            out[aid] = {"title": " ".join(e.find("a:title", ns).text.split()),
                        "abstract": " ".join(e.find("a:summary", ns).text.split()),
                        "authors": [a.find("a:name", ns).text for a in e.findall("a:author", ns)],
                        "primary": e.find("x:primary_category", ns).get("term")}
        time.sleep(3)
    return out

# ---------- 2. INSPIRE records / references ----------
def inspire(q, size=250, fields=None):
    p = {"q": q, "size": size}
    if fields: p["fields"] = fields
    t = http("https://inspirehep.net/api/literature?" + urllib.parse.urlencode(p))
    try: return json.loads(t)["hits"]["hits"] if t else []
    except Exception: return []

def inspire_records(ids):
    out = {}
    for i in range(0, len(ids), 25):
        for h in inspire(" or ".join(f"arxiv:{x}" for x in ids[i:i + 25]), 100):
            m = h["metadata"]
            for e in m.get("arxiv_eprints", []):
                if e["value"] in ids: out[e["value"]] = m
        time.sleep(0.5)
    return out

AX = re.compile(r"(?<![\d.])((?:0[7-9]|[1-3]\d)(?:0[1-9]|1[0-2])\.\d{4,5})(?!\d)|((?:hep-ph|hep-th|hep-ex|hep-lat|astro-ph|gr-qc|nucl-th|nucl-ex|physics|quant-ph|cond-mat|math-ph)(?:\.[A-Z]{2})?/\d{7})")
DOI = re.compile(r"(10\.\d{4,9}/[^\s{}\"\\,;<>]+)")
TK = re.compile(r"^[A-Za-z][A-Za-z'\-. ]*:\d{4}[a-z]{2,3}$")
CITE = re.compile(r"\\(?:no)?cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}")

def src_files(raw):
    try:
        t = tarfile.open(fileobj=io.BytesIO(raw))
        return {m.name: t.extractfile(m).read().decode("utf8", "ignore") for m in t.getmembers()
                if m.isfile() and m.name.lower().endswith((".tex", ".bbl", ".bib"))}
    except tarfile.TarError: pass
    try: raw = gzip.decompress(raw)
    except Exception: pass
    return {} if raw[:4] == b"%PDF" else {"main.tex": raw.decode("utf8", "ignore")}

def nocomment(s): return re.sub(r"(?<!\\)%.*", "", s)

def bibitems(s):
    s = nocomment(s); i = s.find("\\begin{thebibliography}")
    if i < 0: return []
    p = re.split(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", s[i:])
    return [(p[k].strip(), p[k + 1]) for k in range(1, len(p), 2)]

def bibentries(s):
    e = [(m.group(1), m.start()) for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,", s)]
    return [(k, s[p:(e[j + 1][1] if j + 1 < len(e) else len(s))]) for j, (k, p) in enumerate(e)]

def refs_from_source(a, srcdir):
    p = os.path.join(srcdir, a)
    if not os.path.exists(p):
        raw = http(f"https://arxiv.org/src/{a}", binary=True)
        if raw is None: return []
        open(p, "wb").write(raw); time.sleep(1)
    F = src_files(open(p, "rb").read())
    tex = [t for n, t in F.items() if n.lower().endswith(".tex")]
    cited = set()
    for t in tex:
        for m in CITE.finditer(nocomment(t)): cited |= {k.strip() for k in m.group(1).split(",") if k.strip()}
    items = [it for n, t in F.items() if n.lower().endswith(".bbl") for it in bibitems(t)]
    if not items: items = [it for t in tex for it in bibitems(t)]
    if not items:
        items = [(k, b) for n, t in F.items() if n.lower().endswith(".bib") for k, b in bibentries(t) if k in cited]
    out = []
    for k, b in items:
        out.append({"arxiv": [x for x in ((m.group(1) or m.group(2)) for m in AX.finditer(b)) if x != a][:3],
                    "doi": [m.group(1).rstrip(".}").lower() for m in DOI.finditer(b)][:2],
                    "texkey": k if TK.match(k) else None})
    return out

def resolve(refsets):
    want = {"arxiv": set(), "doi": set(), "texkeys": set()}
    for refs in refsets.values():
        for r in refs:
            want["arxiv"] |= set(r["arxiv"]); want["doi"] |= set(r["doi"])
            if r["texkey"]: want["texkeys"].add(r["texkey"])
    M = {k: {} for k in want}
    for field, vals in want.items():
        vals = sorted(vals); vs = set(vals)
        for i in range(0, len(vals), 40):
            q = " or ".join(f"arxiv:{v}" if field == "arxiv" else f'{field}:"{v}"' for v in vals[i:i + 40])
            for h in inspire(q, 250, "control_number,arxiv_eprints,dois,texkeys"):
                m = h["metadata"]; rid = str(m["control_number"])
                if field == "arxiv": hits = [e["value"] for e in m.get("arxiv_eprints", [])]
                elif field == "doi": hits = [e["value"].lower() for e in m.get("dois", [])]
                else: hits = m.get("texkeys", [])
                for v in hits:
                    if v in vs: M[field][v] = rid
            time.sleep(0.3)
    out = {}
    for a, refs in refsets.items():
        s = set()
        for r in refs:
            rid = next((M["arxiv"][x] for x in r["arxiv"] if x in M["arxiv"]), None) or \
                  next((M["doi"][x] for x in r["doi"] if x in M["doi"]), None) or \
                  (M["texkeys"].get(r["texkey"]) if r["texkey"] else None)
            if rid: s.add(rid)
        out[a] = (len(refs), s)
    return out

# ---------- 3. network ----------
def recid(r): return r["record"]["$ref"].rsplit("/", 1)[1]

def network(own, ext, me_recid):
    """Return (papers, co-author names) from a compact network file or from two INSPIRE responses."""
    d0 = load_json(own) if own else None
    if d0 and d0.get("format") == "hep-network/1":
        net = {str(p["id"]): {"kind": p["k"], "refs": {str(x) for x in p["r"]}, "title": p["t"], "arxiv": p["a"],
                              "year": p["y"], "cites": p["c"], "first": p["f"], "nauth": p["n"]} for p in d0["papers"]}
        return net, d0.get("coauthors", []), d0["author"]["name"], str(d0["author"]["recid"])
    net, co = {}, set()
    for kind, d in (("R", d0), ("E", load_json(ext))):
        for h in d["hits"]["hits"]:
            m = h["metadata"]; k = str(m["control_number"])
            if k in net: continue
            net[k] = {"kind": kind, "refs": {recid(r) for r in m.get("references", []) if "record" in r},
                      "title": m["titles"][0]["title"], "arxiv": (m.get("arxiv_eprints") or [{}])[0].get("value", ""),
                      "year": int((m.get("earliest_date") or "0")[:4] or 0), "cites": m.get("citation_count") or 0,
                      "first": (m.get("authors") or [{"full_name": "?"}])[0]["full_name"].split(",")[0],
                      "nauth": m.get("author_count", len(m.get("authors", [])))}
            if kind == "R":
                co |= {a["full_name"] for a in m.get("authors", [])
                       if a.get("record", {}).get("$ref", "").rsplit("/", 1)[-1] != me_recid}
    return net, sorted(co), None, None

def namekey(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    if "," in n: last, first = [s.strip() for s in n.split(",", 1)]
    else: p = n.split(); last, first = (p[-1], " ".join(p[:-1])) if p else ("", "")
    return last + "|" + first[:1]

# ---------- 4. score ----------
def score_all(rows, net, co, me_name):
    D = len(net); df = Counter()
    for v in net.values(): df.update(v["refs"])
    idf = lambda x: math.log((D + 1) / (df.get(x, 0) + 1)) + 1.0
    NV = {k: {x: idf(x) for x in v["refs"]} for k, v in net.items()}
    NN = {k: math.sqrt(sum(w * w for w in v.values())) or 1 for k, v in NV.items()}
    cok = {namekey(n): n for n in co}; mek = namekey(me_name)
    for r in rows:
        refs = r["refs"]; v = {x: idf(x) for x in refs}; vn = math.sqrt(sum(w * w for w in v.values())) or 1
        cs = {k: sum(w * NV[k][x] for x, w in v.items() if x in NV[k]) / (vn * NN[k]) for k in net}
        citR = [k for k in refs if k in net and net[k]["kind"] == "R"]
        citE = sorted((k for k in refs if k in net and net[k]["kind"] == "E"), key=lambda k: -idf(k))
        topR = sorted(((c, k) for k, c in cs.items() if net[k]["kind"] == "R"), reverse=True)[:5]
        topE = sorted(((c, k) for k, c in cs.items() if net[k]["kind"] == "E"), reverse=True)[:5]
        ak = [namekey(x) for x in r["authors"]]
        isme = mek in ak; coa = [cok[k] for k in ak if k in cok]
        wE = sum(1.0 if net[k]["cites"] <= 1000 else 0.1 for k in citE)
        s_dir = 1 - math.exp(-(1.0 * len(citR) + 0.6 * wE))
        cR = topR[0][0] if topR else 0; mR = sum(c for c, _ in topR[:3]) / 3
        s_cpl = min(1, (0.6 * cR + 0.4 * mR) / 0.30)
        s_cplE = min(1, (topE[0][0] if topE else 0) / 0.35)
        s_auth = 1.0 if isme else min(1, 0.5 * len(coa))
        r.update(citR=citR, citE=citE, topR=topR, topE=topE, isme=isme, coauthors=coa,
                 parts=[round(x, 2) for x in (s_dir, s_cpl, s_cplE, s_auth)],
                 score=round(100 * (0.40 * s_dir + 0.35 * s_cpl + 0.15 * s_cplE + 0.10 * s_auth), 1))
    rows.sort(key=lambda r: -r["score"])

# ---------- 5. page ----------
def why(r, net):
    """One-line reasons a listing paper belongs to the network."""
    lab = lambda k: f"{net[k]['first']} {net[k]['year']}"
    refs = r["refs"]; bits = []
    if r["isme"]: bits.append("You are an author.")
    if r["coauthors"]: bits.append("Co-authors of yours: " + ", ".join(c.split(",")[0] for c in r["coauthors"]) + ".")
    if r["citR"]: bits.append("Cites your papers: " + ", ".join(lab(x) for x in r["citR"]) + ".")
    spec = [x for x in r["citE"] if net[x]["cites"] <= 1000]; gen = [x for x in r["citE"] if net[x]["cites"] > 1000]
    if spec: bits.append(f"Cites {len(spec)} network paper{'s' if len(spec) > 1 else ''}: " +
                         ", ".join(lab(x) for x in spec[:6]) + ("…" if len(spec) > 6 else "") + ".")
    if gen: bits.append("Also cites widely used network papers: " + ", ".join(lab(x) for x in gen) + ".")
    for (c, b), who in ((r["topR"][0], "your papers"), (r["topE"][0], "network paper")):
        if c > 0: bits.append(f"Closest {'of ' if who == 'your papers' else ''}{who}: {lab(b)} "
                              f"(coupling {c:.2f}, {len(refs & net[b]['refs'])} shared references).")
    return " ".join(bits)

def build(rows, net, th, meta, out, nnext=10):
    rel = [r for r in rows if r["score"] >= th]
    nodes, edges = {}, set()
    for rank, r in enumerate(rel, 1):
        k = "new:" + r["arxiv"]; refs = r["refs"]
        au = r["authors"]
        nodes[k] = {"id": r["recid"], "arxiv": r["arxiv"], "title": r["title"],
                    "first": au[0].split()[-1] if au else "?", "nauth": len(au), "year": meta["year"], "cites": 0,
                    "role": "repl" if r["section"] == "replacement" else "today", "note": why(r, net),
                    "score": r["score"], "rank": rank, "section": r["section"], "parts": r["parts"],
                    "abstract": r["abstract"], "authors": ", ".join(au), "nlinked": len(refs), "nref": r["nref"], "src": r["src"]}
        for x in r["citR"] + r["citE"]: edges.add((k, x, "c"))
        for c, x in r["topR"][:3] + r["topE"][:3]:
            if c >= 0.03 and x not in refs: edges.add((k, x, "k"))
    for _, t, _ in list(edges):
        if t not in nodes:
            v = net[t]
            nodes[t] = {"id": t, "arxiv": v["arxiv"], "title": v["title"], "first": v["first"], "nauth": v["nauth"],
                        "year": v["year"], "cites": v["cites"], "role": "seed" if v["kind"] == "R" else "other", "note": "", "score": None}
    for a in list(nodes):
        if not a.startswith("new:"):
            for b in net[a]["refs"]:
                if b in nodes and b != a: edges.add((a, b, "c"))
    for k, nd in nodes.items():   # arXiv's experimental HTML version, when it exists
        if k.startswith("new:"):
            try:
                req = urllib.request.Request(f"https://arxiv.org/html/{nd['arxiv']}", headers=UA, method="HEAD")
                nd["html"] = urllib.request.urlopen(req, timeout=30).status == 200
            except Exception: nd["html"] = False
    nxt = [{"arxiv": r["arxiv"], "id": r["recid"], "title": r["title"], "authors": ", ".join(r["authors"]),
            "score": r["score"], "section": r["section"], "rank": len(rel) + j, "parts": r["parts"],
            "note": why(r, net), "abstract": r["abstract"]}
           for j, r in enumerate((r for r in rows if r["score"] < th), 1) if j <= nnext]
    keys = list(nodes); idx = {k: i for i, k in enumerate(keys)}
    data = {"n": [nodes[k] for k in keys], "e": [[idx[s], idx[t], ty] for s, t, ty in edges], "next": nxt,
            "meta": {**meta, "threshold": th, "nrel": len(rel), "nlist": len(rows),
                     "counts": {s: sum(1 for r in rows if r["section"] == s) for s in ("new", "cross", "replacement")},
                     "below": [{"arxiv": r["arxiv"], "title": r["title"], "score": r["score"]}
                               for r in rows if th > r["score"] >= th / 2][:6]}}
    tpl = open(os.path.join(HERE, "template.html")).read()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    open(out, "w").write(tpl.replace("__DATA__", blob).replace("__CAT__", meta["cat"]))
    return len(rel), len(nodes), len(edges)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--own", help="own papers JSON; default: download authors.recid:<author-recid> and ac 1->10 from INSPIRE"); ap.add_argument("--external")
    ap.add_argument("--network", help="compact network file made by build_network.py (replaces --own and --external)")
    ap.add_argument("--date", help="YYYY-MM-DD, 'yesterday' (default) or 'latest'")
    ap.add_argument("--tz", default="America/Bogota"); ap.add_argument("--category", default="hep-ph")
    ap.add_argument("--threshold", type=float, default=10)
    ap.add_argument("--sections", default="new,cross,replacement")
    ap.add_argument("--author-recid", default="991924"); ap.add_argument("--author-name", default="Restrepo, Diego")
    ap.add_argument("--work", default="hepph_work"); ap.add_argument("--out", required=True)
    ap.add_argument("--recent-html", help="saved arxiv.org/list/<cat>/recent?show=2000 page, used if the catchup page is refused")
    a = ap.parse_args()
    a.author_name_given = any(x.startswith("--author-name") for x in sys.argv)
    if not a.network and not a.external: ap.error("give --network, or --external (with or without --own)")
    os.makedirs(os.path.join(a.work, "src"), exist_ok=True)
    if a.date in (None, "", "yesterday"): a.date = previous_day(a.category, a.tz)
    elif a.date == "latest": a.date = None
    L, label, url = listing(a.category, a.date, a.work, a.recent_html)
    a.out = a.out.replace("{date}", a.date or time.strftime("%Y-%m-%d"))
    A = arxiv_meta([o["arxiv"] for o in L])
    for o in L:   # recent-listing fallback: new submission if the primary category is ours, else cross-list
        if o.pop("guess", False) and A.get(o["arxiv"], {}).get("primary", a.category) != a.category: o["section"] = "cross"
    secs = set(a.sections.split(",")); L = [o for o in L if o["section"] in secs]
    ids = [o["arxiv"] for o in L]
    print(f"{label}: {len(ids)} papers {dict(Counter(o['section'] for o in L))}", file=sys.stderr)
    F = inspire_records(ids)
    print(f"INSPIRE has {len(F)} of {len(ids)}; reading arXiv sources for the rest", file=sys.stderr)
    raw = {x: refs_from_source(x, os.path.join(a.work, "src")) for x in ids if x not in F}
    R = resolve(raw)
    rows = []
    for o in L:
        x = o["arxiv"]; m = A.get(x, {})
        if x in F:
            refs = {recid(r) for r in F[x].get("references", []) if "record" in r}
            nref, rid, src = len(F[x].get("references", [])), str(F[x]["control_number"]), "INSPIRE"
            if not m:
                m = {"title": F[x]["titles"][0]["title"], "abstract": (F[x].get("abstracts") or [{"value": ""}])[0]["value"],
                     "authors": [" ".join(reversed(au["full_name"].split(", ", 1))) for au in F[x].get("authors", [])]}
        else:
            nref, refs = R.get(x, (0, set())); rid, src = "", "arXiv source"
        rows.append({"arxiv": x, "section": o["section"], "recid": rid, "src": src, "nref": nref, "refs": refs,
                     "title": m.get("title", x), "authors": m.get("authors", []), "abstract": m.get("abstract", "")})
    if not a.network and not a.own:
        a.own = os.path.join(a.work, "own.json")
        if not os.path.exists(a.own):
            t = http("https://inspirehep.net/api/literature?" + urllib.parse.urlencode(
                {"q": f"authors.recid:{a.author_recid} and ac 1->10", "size": 250, "sort": "mostrecent"}), timeout=300)
            if not t: sys.exit("could not download the own papers from INSPIRE")
            open(a.own, "w").write(t)
    net, co, nname, nrecid = network(a.network or a.own, a.external, a.author_recid)
    if nname and not a.author_name_given: a.author_name, a.author_recid = nname, nrecid
    score_all(rows, net, co, a.author_name)
    yr = int("20" + ids[0][:2]) if ids else int(time.strftime("%Y"))
    meta = {"date": label, "url": url, "cat": a.category, "year": yr, "built": time.strftime("%Y-%m-%d"),
            "nown": sum(1 for v in net.values() if v["kind"] == "R"), "next": sum(1 for v in net.values() if v["kind"] == "E"),
            "onInspire": len(F)}
    nr, nn, ne = build(rows, net, a.threshold, meta, a.out)
    json.dump([{**{k: v for k, v in r.items() if k not in ("refs",)},
                "topR": [(round(c, 3), k) for c, k in r["topR"][:3]], "topE": [(round(c, 3), k) for c, k in r["topE"][:3]]}
               for r in rows], open(os.path.splitext(a.out)[0] + ".json", "w"), ensure_ascii=False, indent=0)
    print(f"{nr} papers with score >= {a.threshold}; graph {nn} nodes, {ne} links -> {a.out}", file=sys.stderr)
    for r in rows[:nr + 5]:
        print(f"{r['score']:5.1f}  {r['section'][:5]:5s} {r['arxiv']}  {r['title'][:80]}")

if __name__ == "__main__":
    main()
```

## Bundled file: template.html

```html
<title>__CAT__ Network Match</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: header; the full listing of matching papers (title, authors, abstract) first; then the network by year beside a detail panel; method notes last. */
:root{--bg:#f6f7f9;--surface:#fff;--fg:#14171c;--fg-2:#4a5160;--fg-3:#6f7686;--line:#dde1e8;--edge:#8d95a5;--other:#a9b0bd;
 --seed:#2a78d6;--today:#d95a22;--repl:#178f65;--bar:#d95a22;--track:#eceff3;
 --f-display:"Spectral",Georgia,"Times New Roman",serif;--f-body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--f-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111317;--surface:#181b20;--fg:#eceef2;--fg-2:#b4bac6;--fg-3:#8b92a0;--line:#2a2f37;--edge:#6c7484;--other:#5d6472;--seed:#3987e5;--today:#e8703a;--repl:#22b07e;--bar:#e8703a;--track:#23272e;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111317;--surface:#181b20;--fg:#eceef2;--fg-2:#b4bac6;--fg-3:#8b92a0;--line:#2a2f37;--edge:#6c7484;--other:#5d6472;--seed:#3987e5;--today:#e8703a;--repl:#22b07e;--bar:#e8703a;--track:#23272e;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--f-body);font-size:15px;line-height:1.55}
.wrap{max-width:1180px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:24px 40px;display:grid;gap:24px}
.wrap>*{min-width:0}
header{display:grid;gap:6px}
.eyebrow{font-family:var(--f-mono);font-size:12px;color:var(--fg-3);letter-spacing:.04em}
.eyebrow a{color:inherit}
h1{font-family:var(--f-display);font-weight:600;font-size:clamp(1.5rem,3.2vw,2.2rem);line-height:1.15;margin:0;text-wrap:balance}
.dek{color:var(--fg-2);max-width:80ch;margin:0}
h3{font-family:var(--f-display);font-weight:600;font-size:1.25rem;margin:0 0 10px}
.list{display:grid;gap:14px}
.paper{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px 20px;display:grid;gap:8px}
.paper.sel{outline:2px solid var(--fg);outline-offset:-1px}
.role{font-size:12px;letter-spacing:.08em;text-transform:uppercase;font-weight:600;font-variant-numeric:tabular-nums}
.paper h2{font-family:var(--f-display);font-weight:600;font-size:1.3rem;line-height:1.3;margin:0;text-wrap:balance}
.authors{font-family:var(--f-mono);font-size:13px;color:var(--fg-2)}
.abs{margin:0;max-width:95ch}
.why{margin:0;font-size:13px;color:var(--fg-2);border-top:1px solid var(--line);padding-top:8px;max-width:110ch}
.row{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;font-size:13px;color:var(--fg-3)}
.row span{display:inline-flex;align-items:center;gap:6px}
.mb{display:inline-block;width:46px;height:5px;border-radius:3px;background:var(--track);overflow:hidden}
.mb i{display:block;height:100%;background:var(--bar)}
.links{display:flex;gap:14px;font-size:14px}
.links a,.panel a{color:var(--seed)}
.linkbtn{font:inherit;font-size:14px;background:none;border:0;padding:0;color:var(--seed);text-decoration:underline;cursor:pointer}
button:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid var(--seed);outline-offset:2px}
.empty{background:var(--surface);border:1px dashed var(--line);border-radius:10px;padding:18px 20px;color:var(--fg-2)}
.controls{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center}
input[type=search]{font:inherit;font-size:13px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--fg);width:min(260px,100%)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--fg-2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block;flex:none}
.main{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px;align-items:start}
@media (max-width:860px){.main{grid-template-columns:minmax(0,1fr)}}
.chart{background:var(--surface);border:1px solid var(--line);border-radius:10px;position:relative;overflow:hidden}
#svg{display:block;width:100%;height:auto}
.axis text{fill:var(--fg-3);font-family:var(--f-mono);font-size:11px}.axis line,.axis path{stroke:var(--line)}
.grid line{stroke:var(--line);stroke-dasharray:2 4}
.edge{fill:none;stroke:var(--edge);stroke-width:.7;stroke-opacity:.22}
.edge.k{stroke-dasharray:3 3;stroke-opacity:.35}
.edge.hot{stroke-opacity:.9;stroke-width:1.4}.edge.hot.in{stroke:var(--seed)}.edge.hot.out{stroke:var(--today)}
.dim .edge:not(.hot){stroke-opacity:.04}
.node{stroke:var(--surface);stroke-width:1.5;cursor:pointer}.dim .node:not(.on){opacity:.18}
.node.match{stroke:var(--fg);stroke-width:2.2}.node.sel{stroke:var(--fg);stroke-width:2.5}
.nlabel{font-size:11px;font-weight:500;fill:var(--fg);paint-order:stroke;stroke:var(--surface);stroke-width:3px;stroke-linejoin:round;pointer-events:none}
.dim .nlabel:not(.on){opacity:.25}
.dir{font-size:12px;color:var(--fg-3);padding:8px 14px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:4px 18px}
.dir b{font-weight:500;color:var(--fg-2)}.sw{display:inline-block;width:18px;height:0;border-top:2px solid;vertical-align:middle;margin-right:6px}
.tip{position:absolute;pointer-events:none;background:var(--fg);color:var(--bg);font-size:12px;padding:6px 9px;border-radius:6px;max-width:280px;line-height:1.35}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px;display:grid;gap:10px;min-width:0;font-size:14px}
.panel h4{font-family:var(--f-display);font-weight:600;font-size:1.08rem;line-height:1.3;margin:0;text-wrap:balance}
.panel .meta{font-family:var(--f-mono);font-size:12px;color:var(--fg-2)}.panel p{margin:0}
.panel .stats{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;color:var(--fg-2);font-variant-numeric:tabular-nums}
.more{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:0 20px}
.more>summary{cursor:pointer;padding:14px 0;font-family:var(--f-display);font-weight:600;font-size:1.1rem;list-style-position:outside}
.more>summary span{font-family:var(--f-body);font-weight:400;font-size:13px;color:var(--fg-3);margin-left:8px}
.nextlist{list-style:none;margin:0;padding:0 0 8px;display:grid}
.nextlist li{display:grid;gap:4px;padding:12px 0;border-top:1px solid var(--line)}
.nextlist .t{font-family:var(--f-display);font-weight:600;font-size:1.05rem;line-height:1.3}
.nextlist .abs{font-size:14px}.nextlist .abs summary{cursor:pointer;color:var(--fg-3);font-size:13px}
.foot{font-size:12px;color:var(--fg-3);max-width:100ch;display:grid;gap:6px}
.foot p{margin:0}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style>
<div class="wrap">
<header>
  <div class="eyebrow" id="eyebrow"></div>
  <h1>New papers that belong to your citation network</h1>
  <p class="dek" id="dek"></p>
</header>
<section aria-label="Matching papers"><div class="list" id="list"></div></section>
<section>
  <h3>Where they sit in the network</h3>
  <div class="controls">
    <input type="search" id="q" placeholder="Search author, title or arXiv ID" aria-label="Search papers in the network">
    <div class="legend" id="legend"></div>
  </div>
</section>
<div class="main" id="mainnet">
  <div class="chart" id="chart"><svg id="svg" role="img" aria-label="Matching papers linked to network papers, laid out by publication year"></svg><div class="tip" id="tip" hidden></div>
    <div class="dir"><span><b>← older · newer →</b></span><span><i class="sw" style="border-color:var(--edge)"></i>cites</span><span><i class="sw" style="border-color:var(--edge);border-top-style:dashed"></i>shares references (no direct citation)</span><span><i class="sw" style="border-color:var(--today)"></i>links from the selected paper</span><span><i class="sw" style="border-color:var(--seed)"></i>links to it</span></div></div>
  <aside class="panel" id="panel" aria-live="polite"></aside>
</div>
<details class="more" id="more" hidden><summary>Next papers by score <span id="moresub"></span></summary><ol class="nextlist" id="nextlist"></ol></details>
<div class="foot" id="foot"></div>
</div>
<script>window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']]},svg:{fontCache:'global'},startup:{typeset:false}};</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-svg.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
const RAW = __DATA__;
const M = RAW.meta;
const N = RAW.n.map((a,i)=>({i,...a,out:[],inn:[]}));
const E = RAW.e.map(([s,t,k])=>({s,t,k}));
E.forEach(e=>{N[e.s].out.push(e.t);N[e.t].inn.push(e.s)});
N.forEach(n=>n.deg=n.out.length+n.inn.length);
const ROLE={today:'Listing: new or cross-list',repl:'Listing: replacement',seed:'Your paper',other:'Network paper (other authors)'};
const RANK={today:0,repl:1,seed:2,other:3};
const SEC={new:'New',cross:'Cross-list',replacement:'Replacement'};
const col=n=>`var(--${n.role})`;
const isNew=n=>n.role==='today'||n.role==='repl';
const r=n=>isNew(n)?4+n.score/9:2.6+1.5*Math.log10(1+n.cites)+(n.role==='seed'?1:0);
const auth=n=>n.first+(n.nauth>2?' et al.':n.nauth===2?' + 1':'');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const plain=s=>String(s).replace(/\$/g,'').replace(/\\([a-zA-Z]+)/g,'$1').replace(/[{}^_]/g,'');
const tex=el=>{if(window.MathJax&&MathJax.typesetPromise)MathJax.typesetPromise([el]).catch(()=>{})};
const NEWS=N.filter(isNew).sort((a,b)=>a.rank-b.rank);
document.getElementById('eyebrow').innerHTML=`arXiv ${esc(M.cat)} · <a href="${esc(M.url)}" target="_blank" rel="noopener">${esc(M.date)}</a>`;
document.getElementById('dek').textContent=`${M.nrel} of the ${M.nlist} papers in this listing (${M.counts.new} new, ${M.counts.cross} cross-lists, ${M.counts.replacement} replacements) score ${M.threshold} or more for belonging to the reference and citation network of your ${M.nown} papers and the ${M.next} papers by other authors around them. Highest score first.`;
document.getElementById('foot').innerHTML=`<p><b>Score (0–100).</b> 40% direct citations of network papers (each of your papers counts 1, each other network paper 0.6, network papers with over 1,000 citations 0.06; saturating as 1 − e<sup>−x</sup>); 35% bibliographic coupling with your own papers (idf-weighted cosine of INSPIRE-linked reference sets, best match and mean of the top three, 0.30 = full marks); 15% best coupling with the other network papers (0.35 = full marks); 10% authorship (you, or your co-authors).</p>
<p><b>Data.</b> Network: INSPIRE records supplied with the project. Listing papers: INSPIRE records where already harvested (${M.onInspire} of ${M.nlist}); for the rest the reference list was read from the arXiv source and matched to INSPIRE by arXiv number, DOI and texkey. Only links between papers on this page are drawn. Built ${esc(M.built)}.</p>`;
const P=['Direct citations','Coupling to your papers','Coupling to network','Authorship'];
function list(){const box=document.getElementById('list');
  if(!NEWS.length){box.innerHTML=`<div class="empty">No paper in this listing reaches a score of ${M.threshold}.</div>`;document.getElementById('mainnet').hidden=true;return}
  NEWS.forEach(n=>{const d=document.createElement('article');d.className='paper';d.id='p'+n.i;
    d.innerHTML=`<div class="role" style="color:${col(n)}">#${n.rank} · ${esc(SEC[n.section])} · score ${n.score.toFixed(1)}</div>
    <h2>${esc(n.title)}</h2>
    <div class="authors">${esc(n.authors)} · arXiv:${esc(n.arxiv)}</div>
    <p class="abs">${esc(n.abstract)}</p>
    <p class="why">${esc(n.note)}</p>
    <div class="row">${n.parts.map((v,j)=>`<span>${P[j]} <span class="mb"><i style="width:${Math.round(v*100)}%"></i></span></span>`).join('')}<span>${n.nlinked} of ${n.nref} references linked to INSPIRE</span><span>refs from ${esc(n.src)}</span></div>
    <div class="links">${n.id?`<a href="https://inspirehep.net/literature/${n.id}" target="_blank" rel="noopener">INSPIRE</a>`:''}<a href="https://arxiv.org/abs/${esc(n.arxiv)}" target="_blank" rel="noopener">arXiv</a><a href="https://arxiv.org/pdf/${esc(n.arxiv)}" target="_blank" rel="noopener">PDF</a>${n.html?`<a href="https://arxiv.org/html/${esc(n.arxiv)}" target="_blank" rel="noopener">HTML (experimental)</a>`:''}<button class="linkbtn" type="button">Show in network</button></div>`;
    d.querySelector('.linkbtn').addEventListener('click',()=>pick(n,true));box.appendChild(d)});
  tex(box)}
let sel=NEWS[0]||null, hover=null, query='', G;
const svg=d3.select('#svg'), tip=document.getElementById('tip');
function draw(){
  if(!NEWS.length)return;
  const RNG=d3.randomLcg(11);
  const W=Math.max(300,document.getElementById('chart').clientWidth), H=W<600?500:480, m={l:16,r:16,t:20,b:34};
  svg.attr('viewBox',`0 0 ${W} ${H}`); svg.selectAll('*').remove();
  const yrs=d3.extent(N,n=>n.year);
  const x=d3.scaleLinear().domain([yrs[0]-.5,yrs[1]+1.2]).range([m.l+8,W-m.r-8]);
  const ticks=x.ticks(W<600?6:12).filter(t=>Number.isInteger(t)&&t<=yrs[1]);
  svg.append('g').attr('class','grid').selectAll('line').data(ticks).join('line').attr('x1',d=>x(d)).attr('x2',d=>x(d)).attr('y1',m.t).attr('y2',H-m.b);
  svg.append('g').attr('class','axis').attr('transform',`translate(0,${H-m.b})`).call(d3.axisBottom(x).tickValues(ticks).tickFormat(d3.format('d')).tickSizeOuter(0));
  const cy=(m.t+H-m.b)/2, xf=n=>isNew(n)?x(yrs[1]+.75):x(n.year);
  const sim=N.map(n=>({n,x:xf(n)+(RNG()-.5)*4,y:cy+(RNG()-.5)*H*.5}));
  const links=E.map(e=>({source:sim[e.s],target:sim[e.t],s:e.s,t:e.t,k:e.k}));
  d3.forceSimulation(sim).force('x',d3.forceX(s=>xf(s.n)).strength(1)).force('y',d3.forceY(cy).strength(.04))
    .force('link',d3.forceLink(links).strength(.03)).force('charge',d3.forceManyBody().strength(-40))
    .force('col',d3.forceCollide(s=>r(s.n)+2)).stop().tick(320);
  sim.forEach(s=>{s.y=Math.max(m.t+8,Math.min(H-m.b-8,s.y));s.x=Math.max(m.l+4,Math.min(W-m.r-4,s.x))});
  G=svg.append('g');
  G.append('g').selectAll('path').data(links).join('path').attr('class',l=>'edge '+l.k)
    .attr('d',l=>{const a=l.source,b=l.target;return `M${a.x},${a.y}Q${(a.x+b.x)/2},${(a.y+b.y)/2-Math.abs(a.x-b.x)*.12} ${b.x},${b.y}`});
  G.append('g').selectAll('circle').data([...sim].sort((a,b)=>RANK[b.n.role]-RANK[a.n.role])).join('circle')
    .attr('class','node').attr('cx',s=>s.x).attr('cy',s=>s.y).attr('r',s=>r(s.n)).attr('fill',s=>col(s.n))
    .on('pointerenter',(ev,s)=>{hover=s.n;showTip(ev,s.n);paint()}).on('pointermove',(ev,s)=>showTip(ev,s.n))
    .on('pointerleave',()=>{hover=null;tip.hidden=true;paint()}).on('click',(ev,s)=>pick(s.n,false));
  const lab=sim.filter(s=>isNew(s.n)||s.n.role==='seed'||s.n.deg>=3);
  const L=lab.map(s=>{const right=s.x>W*.8,t=isNew(s.n)?`#${s.n.rank} ${s.n.first}`:`${s.n.first} ${s.n.year}`,w=t.length*6.2;return{s,t,right,x0:right?s.x-r(s.n)-4-w:s.x+r(s.n)+4,w,y:s.y+4}}).sort((a,b)=>a.y-b.y);
  const placed=[];L.forEach(l=>{let k=0;while(k<40&&placed.some(p=>l.x0<p.x0+p.w&&p.x0<l.x0+l.w&&Math.abs(l.y-p.y)<13)){l.y+=13*(k%2?-1:1)*(1+Math.floor(k/2));k++;l.y=Math.max(m.t+10,Math.min(H-m.b-4,l.y))}placed.push(l)});
  G.append('g').selectAll('text').data(L).join('text').attr('class','nlabel').attr('x',l=>l.right?l.s.x-r(l.s.n)-4:l.s.x+r(l.s.n)+4).attr('y',l=>l.y)
    .attr('text-anchor',l=>l.right?'end':'start').text(l=>l.t);
  paint();
}
function showTip(ev,n){const b=document.getElementById('chart').getBoundingClientRect();tip.hidden=false;tip.textContent=`${auth(n)} (${n.year}) — ${plain(n.title)}`+(isNew(n)?` · score ${n.score}`:'');
  let L=ev.clientX-b.left+12;if(L>b.width-290)L=ev.clientX-b.left-290;tip.style.left=Math.max(4,L)+'px';tip.style.top=(ev.clientY-b.top+12)+'px'}
function paint(){if(!G)return;const f=hover||sel,on=new Set();if(f){on.add(f.i);f.out.forEach(i=>on.add(i));f.inn.forEach(i=>on.add(i))}
  svg.classed('dim',!!f);
  G.selectAll('path.edge').attr('class',l=>'edge '+l.k+(!f?'':l.s===f.i?' hot out':l.t===f.i?' hot in':''));G.selectAll('path.edge.hot').raise();
  G.selectAll('circle').classed('on',s=>on.has(s.n.i)).classed('sel',s=>sel&&s.n.i===sel.i).classed('match',s=>query&&`${s.n.first} ${s.n.title} ${s.n.arxiv} ${s.n.authors||''}`.toLowerCase().includes(query));
  G.selectAll('text.nlabel').classed('on',l=>on.has(l.s.n.i))}
function panel(){const p=document.getElementById('panel'),n=sel;
  if(!n){p.innerHTML='<p>Select a paper in the network.</p>';return}
  const links=`<div class="links">${n.id?`<a href="https://inspirehep.net/literature/${n.id}" target="_blank" rel="noopener">INSPIRE</a>`:''}${n.arxiv?`<a href="https://arxiv.org/abs/${esc(n.arxiv)}" target="_blank" rel="noopener">arXiv</a>`:''}</div>`;
  if(isNew(n)) p.innerHTML=`<div class="role" style="color:${col(n)}">#${n.rank} · ${esc(SEC[n.section])} · score ${n.score.toFixed(1)}</div><h4>${esc(n.title)}</h4>
   <div class="meta">${esc(auth(n))} · arXiv:${esc(n.arxiv)}</div><p>${esc(n.note)}</p><div class="links"><a href="#p${n.i}">Back to abstract</a></div>`;
  else p.innerHTML=`<div class="role" style="color:${col(n)}">${esc(ROLE[n.role])}</div><h4>${esc(n.title)}</h4>
   <div class="meta">${esc(auth(n))} · ${n.year}${n.arxiv?' · arXiv:'+esc(n.arxiv):''}</div>
   <div class="stats"><span>${n.cites.toLocaleString()} citations</span><span>${n.inn.filter(i=>isNew(N[i])).length} of the matches link here</span></div>${links}`;
  tex(p)}
function pick(n,scroll){sel=n;panel();paint();document.querySelectorAll('.paper').forEach(el=>el.classList.toggle('sel',el.id==='p'+n.i));if(scroll)document.getElementById('chart').scrollIntoView({behavior:'smooth',block:'nearest'})}
const present=new Set(N.map(n=>n.role));
document.getElementById('legend').innerHTML=['today','repl','seed','other'].filter(k=>present.has(k)).map(k=>`<span><i class="dot" style="background:var(--${k})"></i>${esc(ROLE[k])}</span>`).join('')+'<span style="color:var(--fg-3)">Listing papers: size ∝ score; others: size ∝ log(citations)</span>';
document.getElementById('q').addEventListener('input',e=>{query=e.target.value.trim().toLowerCase();paint()});
svg.on('click',ev=>{if(ev.target.tagName!=='circle'){sel=null;panel();paint()}});
let rt;window.addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,200)});
function nextList(){const X=RAW.next||[];if(!X.length)return;const box=document.getElementById('nextlist'),more=document.getElementById('more');
  more.hidden=false;more.querySelector('summary').firstChild.textContent=`The next ${X.length} papers by score `;
  document.getElementById('moresub').textContent=`below the threshold of ${M.threshold}, not drawn in the network`;
  box.innerHTML=X.map(n=>`<li><div class="role" style="color:var(--${n.section==='replacement'?'repl':'today'})">#${n.rank} · ${esc(SEC[n.section])} · score ${n.score.toFixed(1)}</div>
    <div class="t">${esc(n.title)}</div><div class="authors">${esc(n.authors)} · arXiv:${esc(n.arxiv)}</div>
    ${n.note?`<p class="why">${esc(n.note)}</p>`:''}
    <details class="abs"><summary>Abstract</summary><p class="abs">${esc(n.abstract)}</p></details>
    <div class="links">${n.id?`<a href="https://inspirehep.net/literature/${n.id}" target="_blank" rel="noopener">INSPIRE</a>`:''}<a href="https://arxiv.org/abs/${esc(n.arxiv)}" target="_blank" rel="noopener">arXiv</a><a href="https://arxiv.org/pdf/${esc(n.arxiv)}" target="_blank" rel="noopener">PDF</a></div></li>`).join('');
  more.addEventListener('toggle',()=>{if(more.open)tex(box)})}
list();nextList();draw();panel();
window.addEventListener('load',()=>{tex(document.getElementById('list'));tex(document.getElementById('panel'))});
</script>
```