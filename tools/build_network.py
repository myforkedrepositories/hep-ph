#!/usr/bin/env python3
"""Build a compact citation-network file for one INSPIRE author, for hep-ph-network-match.

  python3 -I build_network.py --author-recid 991924 [--max-authors 10] [--out network.json]

Selection (as in restrepo/hep-ph data/inspire/README.md):
  own papers  : authors.recid:<ID> and ac 1-><max-authors>
  core refs   : references cited by >= --min-shared own papers with <= --max-ref-cites citations
  coupling    : papers by others citing a core ref; the --candidates best (idf-weighted count of
                core refs cited) are compared by idf-weighted cosine of INSPIRE reference sets;
                collaboration papers and papers with > --max-cand-authors authors dropped; each own
                paper keeps its --top best with coupling >= --min-coupling
  citing      : papers by others citing an own paper with >= --cites-min citations, citing
                >= --cite-own-min own papers, or from the last --recent-years years (and the
                current one), so new papers citing recent work about the author's are linked
Output: one JSON with, per paper, id, kind (R own / E external), title, arXiv, year, citations,
first author, author count and the INSPIRE ids it references; plus the co-author names.
"""
import argparse, json, math, re, sys, time, urllib.parse, urllib.request
from collections import Counter, defaultdict

UA = {"User-Agent": "hep-network-builder/1.0 (academic literature alert)"}
API = "https://inspirehep.net/api/literature?"
META = "control_number,titles.title,arxiv_eprints.value,earliest_date,citation_count,author_count,collaborations,references.record"

def get(params, tries=5):
    url = API + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1: print(f"[warn] {e}: {url[:100]}", file=sys.stderr); return None
            time.sleep(4 * (i + 1))

def search(q, fields, size=500, limit=None):
    """All hits for q (pages through results)."""
    out, page = [], 1
    while True:
        d = get({"q": q, "fields": fields, "size": size, "page": page, "sort": "mostrecent"})
        time.sleep(0.35)
        if not d: break
        hits = d["hits"]["hits"]; out += [h["metadata"] for h in hits]
        if len(hits) < size or (limit and len(out) >= limit) or len(out) >= d["hits"]["total"] or page * size >= 10000: break
        page += 1
    return out

def refs(m): return [int(r["record"]["$ref"].rsplit("/", 1)[1]) for r in m.get("references", []) if "record" in r]

def compact(m, kind):
    return {"id": m["control_number"], "k": kind, "t": m["titles"][0]["title"],
            "a": (m.get("arxiv_eprints") or [{}])[0].get("value", ""),
            "y": int((m.get("earliest_date") or "0")[:4] or 0), "c": m.get("citation_count") or 0,
            "f": (m.get("authors") or [{"full_name": "?"}])[0]["full_name"].split(",")[0],
            "n": m.get("author_count") or len(m.get("authors", [])), "r": sorted(set(refs(m)))}

def by_recids(ids, fields):
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 50):
        for m in search(" or ".join(f"recid:{x}" for x in ids[i:i + 50]), fields, 100):
            out[m["control_number"]] = m
    return out

# ---------- shared technical phrases (topic weights for hep-ph-network-match) ----------
STOP = set("""a an the of and or in on at to for from by with without within into onto over under between among
as is are was were be been being this that these those it its their there here we our us they which who whom whose
can could may might must will would should shall do does did not no nor than then so such also both either each
all any some many most more much few other only own same very via per using use used based new recent show shows
shown find found study studied present presented discuss discussed consider considered obtain obtained provide
provided propose proposed investigate investigated analyze analysed analyzed explore explored allow allows allowed
while where when if whether however thus hence therefore moreover furthermore since because although even well
one two three first second paper work article letter case cases way ways result results possible possibly
particular particularly respectively give gives given let order one's i.e e.g eg ie probing probe simplest""".split())
GENERIC = {"parameter space", "this model", "large range", "wide range", "good agreement", "future experiment",
           "current experiment", "upcoming experiment", "experimental data", "experimental constraint",
           "phenomenological consequence", "phenomenological implication", "simple extension", "minimal extension",
           "free parameter", "benchmark point", "detailed analysis", "numerical analysis", "analytical expression",
           "et al", "model contain", "next generation"}
KEEP = {"higgs", "physics", "dynamics", "kinematics", "analysis", "basis", "axis", "lens", "bias", "gas", "mass",
        "boson", "cosmos", "plus", "status", "bonus", "focus", "nucleus", "radius", "genesis", "synthesis"}
MAP = {"vertices": "vertex", "violating": "violation", "matrices": "matrix"}

def norm_tok(t):
    t = t.replace("flavour", "flavor").replace("colour", "color")
    if t in MAP: return MAP[t]
    if t in KEEP or len(t) <= 4: return t
    if t.endswith("sses"): return t[:-2]
    if t.endswith("ies") and len(t) > 5: return t[:-3] + "y"
    if t.endswith("s") and not t.endswith(("ss", "us", "is", "ys")): return t[:-1]
    return t

def grams(text):
    """Normalized 2-5 word phrases in a title or abstract (math removed, no filler words at the ends)."""
    out = set()
    s = re.sub(r"\$[^$]*\$|\\\(.*?\\\)|\\[a-zA-Z]+|\{[^}]*\}", " | ", text).lower().replace("\u2019", "'")
    for part in re.split(r"[^a-z0-9'\- ]+", s):
        toks = [norm_tok(t.strip("-'")) for t in part.split() if t.strip("-'")]
        for n in (2, 3, 4, 5):
            for i in range(len(toks) - n + 1):
                g = toks[i:i + n]
                if g[0] in STOP or g[-1] in STOP or any(t in STOP and t not in ("of", "and") for t in g[1:-1]): continue
                if any(re.fullmatch(r"[0-9\-']+", t) or len(t) < 2 for t in g): continue
                out.add(" ".join(g))
    return out

def phrases(own, ext, a, log):
    """Phrases shared by >= a.phrase_min_own own papers and >= a.phrase_min_other others, weighted by how much more
    often the network uses them (own papers count a.phrase_own_weight times) than all of a.phrase_category."""
    df = {}
    for k, ms in ((0, own), (1, ext)):
        for m in ms:
            text = m["titles"][0]["title"] + " . " + " ".join(x["value"] for x in m.get("abstracts", [])[:1])
            for g in grams(text): df.setdefault(g, [0, 0])[k] += 1
    W, NO, NE = a.phrase_own_weight, len(own), len(ext)
    share = lambda c: (W * c[0] + c[1]) / (W * NO + NE)
    cand = {g: c for g, c in df.items() if c[0] >= a.phrase_min_own and c[1] >= a.phrase_min_other and g not in GENERIC}
    keep = dict(cand)       # fold a phrase that mostly appears inside a longer one into it
    for g in sorted(cand, key=lambda x: -len(x.split())):
        if g not in keep: continue
        for h in list(keep):
            if h != g and len(h.split()) < len(g.split()) and f" {h} " in f" {g} " and share(cand[g]) >= 0.7 * share(keep[h]):
                del keep[h]
    since = int(time.strftime("%Y")) - 10
    base = f"arxiv_eprints.categories:{a.phrase_category} and de > {since}"
    total = (get({"q": base, "size": 1, "fields": "control_number"}) or {"hits": {"total": 1}})["hits"]["total"]
    def variants(p):
        w = p.split(); last = w[-1]
        pl = last[:-1] + "ies" if last.endswith("y") and last[-2:-1] not in "aeiou" else last + ("es" if last.endswith(("s", "x", "ch", "sh")) else "s")
        v = {p, " ".join(w[:-1] + [pl])}
        return sorted(v | {x.replace("flavor", "flavour") for x in v} | {x.replace("violation", "violating") for x in v})
    out = []
    for g, c in sorted(keep.items(), key=lambda x: -share(x[1])):
        q = base + " and (" + " or ".join(f't "{v}" or abstracts.value:"{v}"' for v in variants(g)) + ")"
        d = get({"q": q, "size": 1, "fields": "control_number"}); time.sleep(0.3)
        bg = d["hits"]["total"] if d else total
        w = min(4.0, max(0.0, math.log(share(c) / (max(bg, 1) / total)) - math.log(3)))   # 0 below 3x enrichment
        if w > 0: out.append([g, round(w, 3), c[0], c[1], bg])
    log(f"shared phrases: {len(keep)}; {len(out)} enriched over {a.phrase_category} (background {total} papers since {since})")
    return {"category": a.phrase_category, "since": since, "total": total, "list": out}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--author-recid", required=True)
    ap.add_argument("--max-authors", type=int, default=10)
    ap.add_argument("--min-shared", type=int, default=3)
    ap.add_argument("--max-ref-cites", type=int, default=1000)
    ap.add_argument("--candidates", type=int, default=2000)
    ap.add_argument("--max-cand-authors", type=int, default=30)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--min-coupling", type=float, default=0.10)
    ap.add_argument("--cites-min", type=int, default=200)
    ap.add_argument("--cite-own-min", type=int, default=4)
    ap.add_argument("--recent-years", type=int, default=10,
                    help="also keep every citing paper from this many years before the current one (-1: none)")
    ap.add_argument("--phrase-own-weight", type=float, default=5, help="weight of an own paper when counting phrases")
    ap.add_argument("--phrase-min-own", type=int, default=3); ap.add_argument("--phrase-min-other", type=int, default=5)
    ap.add_argument("--phrase-category", default="hep-ph", help="arXiv category for the phrases' background frequency")
    ap.add_argument("--no-phrases", action="store_true")
    ap.add_argument("--out", default="network.json")
    a = ap.parse_args(); A = a.author_recid
    log = lambda s: print(s, file=sys.stderr, flush=True)

    own = search(f"authors.recid:{A} and ac 1->{a.max_authors}", META + ",authors.full_name,authors.record,abstracts.value", 250)
    ownid = {m["control_number"] for m in own}
    name = next((au["full_name"] for m in own for au in m.get("authors", [])
                 if au.get("record", {}).get("$ref", "").endswith("/" + A)), A)
    log(f"own papers: {len(own)} ({name})")

    # core references
    cnt = Counter(x for m in own for x in set(refs(m)))
    shared = [x for x, c in cnt.items() if c >= a.min_shared and x not in ownid]
    cc = {m["control_number"]: m.get("citation_count") or 0 for m in by_recids(shared, "control_number,citation_count").values()}
    core = [x for x in shared if cc.get(x, 10**9) <= a.max_ref_cites]
    log(f"references cited by >= {a.min_shared} own papers: {len(shared)}; core (<= {a.max_ref_cites} citations): {len(core)}")

    # candidates citing core refs
    w = {x: math.log(len(own) / cnt[x]) + 1 for x in core}
    cand = Counter()
    for j, x in enumerate(core):
        for m in search(f"refersto:recid:{x} and not authors.recid:{A}", "control_number", 1000):
            cand[m["control_number"]] += w[x]
        if j % 25 == 0: log(f"  core ref {j + 1}/{len(core)}; candidates so far {len(cand)}")
    top = [k for k, _ in cand.most_common(a.candidates) if k not in ownid]
    log(f"candidates: {len(cand)}; comparing the best {len(top)}")
    C = by_recids(top, META)
    C = {k: m for k, m in C.items() if not m.get("collaborations") and (m.get("author_count") or 0) <= a.max_cand_authors}

    # idf-weighted cosine over own + candidate reference sets
    docs = {m["control_number"]: set(refs(m)) for m in own} | {k: set(refs(m)) for k, m in C.items()}
    df = Counter(x for s in docs.values() for x in s); D = len(docs)
    idf = lambda x: math.log((D + 1) / (df[x] + 1)) + 1
    V = {k: {x: idf(x) for x in s} for k, s in docs.items()}
    nrm = {k: math.sqrt(sum(v * v for v in V[k].values())) or 1 for k in V}
    keep = {}
    for m in own:
        o = m["control_number"]; vo = V[o]
        sims = sorted(((sum(wt * V[k].get(x, 0) for x, wt in vo.items()) / (nrm[o] * nrm[k]), k) for k in C), reverse=True)
        for s, k in sims[:a.top]:
            if s >= a.min_coupling: keep[k] = max(keep.get(k, 0), s)
    log(f"coupled external papers: {len(keep)}")

    # citing papers: important ones, plus every recent one
    hits = Counter(); info = {}; year = {}
    since = int(time.strftime("%Y")) - a.recent_years if a.recent_years >= 0 else 10**4
    for m in own:
        for c in search(f"refersto:recid:{m['control_number']} and not authors.recid:{A}", "control_number,citation_count,earliest_date", 1000):
            k = c["control_number"]; hits[k] += 1; info[k] = c.get("citation_count") or 0
            year[k] = int((c.get("earliest_date") or "0")[:4] or 0)
    imp = {k for k, n in hits.items() if n >= a.cite_own_min or info[k] >= a.cites_min or year[k] >= since}
    log(f"papers citing own papers: {len(hits)}; kept: {len(imp)} ({sum(year[k] >= since for k in imp)} since {since}; "
        f"{len(imp & set(keep))} already coupled)")

    ext = set(keep) | imp
    E = by_recids(ext, META + ",authors.full_name,abstracts.value")
    ph = None if a.no_phrases else phrases(own, list(E.values()), a, log)
    co = sorted({au["full_name"] for m in own for au in m.get("authors", [])
                 if not au.get("record", {}).get("$ref", "").endswith("/" + A)})
    for m in list(own) + list(E.values()):
        if m.get("authors"): m["authors"] = m["authors"][:1]
    net = {"format": "hep-network/1", "author": {"recid": A, "name": name}, "built": time.strftime("%Y-%m-%d"),
           "query": f"authors.recid:{A} and ac 1->{a.max_authors}",
           "params": {k: v for k, v in vars(a).items() if k not in ("out", "author_recid")},
           "counts": {"own": len(own), "external": len(E), "coupled": len(keep), "citing": len(imp)},
           "coauthors": co,
           **({"phrases": ph} if ph else {}),
           "papers": [compact(m, "R") for m in own] + [compact(m, "E") for m in E.values()]}
    with open(a.out, "w") as f: json.dump(net, f, ensure_ascii=False, separators=(",", ":"))
    import os
    log(f"wrote {a.out}: {len(own)} own + {len(E)} external papers, {os.path.getsize(a.out) / 1024:.0f} KB")

if __name__ == "__main__":
    main()
