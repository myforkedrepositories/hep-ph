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
Writes PAGE.html (self-contained page, with the next --next (20) papers below the threshold in a collapsed
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
    """One-line reasons a listing paper belongs to the network. Each network paper appears as [[INSPIRE id]];
    the page shows it as 'Author Year' with a pop-up of its authors, year and title."""
    lab = lambda k: f"[[{k}]]"
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

def build(rows, net, th, meta, out, nnext=20):
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
    cited = {k for x in [nd.get("note", "") for nd in nodes.values()] + [x["note"] for x in nxt] for k in re.findall(r"\[\[(\d+)\]\]", x)}
    refs = {k: {"first": net[k]["first"], "year": net[k]["year"], "nauth": net[k]["nauth"], "title": net[k]["title"],
                "role": "seed" if net[k]["kind"] == "R" else "other"} for k in cited}
    data = {"n": [nodes[k] for k in keys], "e": [[idx[s], idx[t], ty] for s, t, ty in edges], "next": nxt, "refs": refs,
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
    ap.add_argument("--next", type=int, default=20, help="papers below the threshold shown in the collapsed list")
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
    nr, nn, ne = build(rows, net, a.threshold, meta, a.out, a.next)
    json.dump([{**{k: v for k, v in r.items() if k not in ("refs",)},
                "topR": [(round(c, 3), k) for c, k in r["topR"][:3]], "topE": [(round(c, 3), k) for c, k in r["topE"][:3]]}
               for r in rows], open(os.path.splitext(a.out)[0] + ".json", "w"), ensure_ascii=False, indent=0)
    print(f"{nr} papers with score >= {a.threshold}; graph {nn} nodes, {ne} links -> {a.out}", file=sys.stderr)
    for r in rows[:nr + 5]:
        print(f"{r['score']:5.1f}  {r['section'][:5]:5s} {r['arxiv']}  {r['title'][:80]}")

if __name__ == "__main__":
    main()
