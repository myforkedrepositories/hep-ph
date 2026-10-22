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
  citing      : papers by others citing an own paper with >= --cites-min citations or citing
                >= --cite-own-min own papers
Output: one JSON with, per paper, id, kind (R own / E external), title, arXiv, year, citations,
first author, author count and the INSPIRE ids it references; plus the co-author names.
"""
import argparse, json, math, sys, time, urllib.parse, urllib.request
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
    ap.add_argument("--out", default="network.json")
    a = ap.parse_args(); A = a.author_recid
    log = lambda s: print(s, file=sys.stderr, flush=True)

    own = search(f"authors.recid:{A} and ac 1->{a.max_authors}", META + ",authors.full_name,authors.record", 250)
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

    # important citing papers
    hits = Counter(); info = {}
    for m in own:
        for c in search(f"refersto:recid:{m['control_number']} and not authors.recid:{A}", "control_number,citation_count", 1000):
            hits[c["control_number"]] += 1; info[c["control_number"]] = c.get("citation_count") or 0
    imp = {k for k, n in hits.items() if n >= a.cite_own_min or info[k] >= a.cites_min}
    log(f"papers citing own papers: {len(hits)}; important: {len(imp)} ({len(imp & set(keep))} already coupled)")

    ext = set(keep) | imp
    E = by_recids(ext, META + ",authors.full_name")
    co = sorted({au["full_name"] for m in own for au in m.get("authors", [])
                 if not au.get("record", {}).get("$ref", "").endswith("/" + A)})
    for m in list(own) + list(E.values()):
        if m.get("authors"): m["authors"] = m["authors"][:1]
    net = {"format": "hep-network/1", "author": {"recid": A, "name": name}, "built": time.strftime("%Y-%m-%d"),
           "query": f"authors.recid:{A} and ac 1->{a.max_authors}",
           "params": {k: v for k, v in vars(a).items() if k not in ("out", "author_recid")},
           "counts": {"own": len(own), "external": len(E), "coupled": len(keep), "citing": len(imp)},
           "coauthors": co,
           "papers": [compact(m, "R") for m in own] + [compact(m, "E") for m in E.values()]}
    with open(a.out, "w") as f: json.dump(net, f, ensure_ascii=False, separators=(",", ":"))
    import os
    log(f"wrote {a.out}: {len(own)} own + {len(E)} external papers, {os.path.getsize(a.out) / 1024:.0f} KB")

if __name__ == "__main__":
    main()
