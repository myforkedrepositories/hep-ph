---
name: "hep-network-builder"
description: "Builds, from an INSPIRE author ID, a compact citation-network file (own papers with up to 10 authors, their most coupled papers, and the important and recent papers by others that cite them, with INSPIRE reference lists) and saves it in the project for hep-ph-network-match."
---

# HEP network builder

Use when the user wants to set up (or refresh) the network that `hep-ph-network-match` ranks
new papers against, for themselves or another physicist, given an INSPIRE author ID, profile
link or name.

## 1. Find the INSPIRE author ID

The ID is the number in `https://inspirehep.net/authors/<ID>`. If the user gives a name, BAI
(e.g. `J.Smith.1`) or ORCID instead, look it up:
`https://inspirehep.net/api/authors?q=<name or ids.value:BAI/ORCID>&fields=control_number,name,ids,positions`
and confirm the person with the user if more than one profile matches (current institution
helps). Ask for the maximum number of authors only if the user mentions it; default 10.

## 2. Write the builder and run it

Write the bundled `build_network.py` below into a folder (copy the block exactly) and run it
in the background (Bash `run_in_background`), since it takes 10–25 minutes and makes a few
hundred INSPIRE requests:

```bash
python3 -I build_network.py --author-recid <ID> [--max-authors 10] --out network_<ID>.json
```

It logs each stage to stderr. Selection, as in the original study:

- **Own papers**: `authors.recid:<ID> and ac 1-><max-authors>`.
- **Coupled papers**: references cited by at least 3 own papers and with at most 1,000
  citations are the core; papers by others citing a core reference are candidates; the 2,000
  best (idf-weighted count of core references cited) are compared with each own paper by
  idf-weighted cosine of their INSPIRE reference sets; collaboration papers and papers with
  more than 30 authors are dropped; each own paper keeps its 5 best with coupling ≥ 0.10.
- **Citing papers**: papers by others that cite an own paper and have at least 200
  citations or cite at least 4 own papers (the important ones), plus **every** citing paper
  from the last 2 years and the current one (`--recent-years 2`). New listing papers that cite
  recent work about the author's are then linked to the network, without the score inflation
  that keeping all citing papers causes (`--recent-years -1` turns this off).

All thresholds are options (`--min-shared`, `--max-ref-cites`, `--candidates`,
`--max-cand-authors`, `--top`, `--min-coupling`, `--cites-min`, `--cite-own-min`, `--recent-years`).

The output keeps only what the matcher uses: for each paper its INSPIRE id, kind (own or
external), title, arXiv number, year, citations, first author, number of authors and the
INSPIRE ids it references; plus the co-authors' names, the author and the parameters. For
about 300 papers it is a few hundred KB.

## 3. Save it in the project

If a project is attached, save the file with `Projects` `project_write`
(`path: "claude/network_<ID>.json"`, `local_path` = the output file). Replacing an existing
file of the same name is the way to refresh it. Project knowledge has a size limit (shown by
`project_info` as `max_knowledge_size`); if the save is refused for size, tell the user which
large docs take the space (an older full INSPIRE dump, for example) and let them decide what
to remove. Without a project, send the file with `SendUserFile` so the user can add it.

## 4. Reply

State the author, the counts (own papers, coupled papers, citing papers, total),
the file size and where it was saved, and that `hep-ph-network-match` will use it
(`--network`). If the network looks thin (fewer than 20 own papers or 30 external papers),
suggest raising `--max-authors` or lowering `--min-shared`.

## Bundled file: build_network.py

```python
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
    ap.add_argument("--recent-years", type=int, default=2,
                    help="also keep every citing paper from this many years before the current one (-1: none)")
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
```