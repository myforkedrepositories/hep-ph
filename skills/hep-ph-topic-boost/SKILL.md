---
name: "hep-ph-topic-boost"
description: "Raises the score of a particular arXiv paper on the hep-ph network-match pages (restrepo/hep-ph or a fork) by proposing watch topics: phrases from the paper's title and abstract, with the weights needed to lift it above the threshold, for the repository variable EXTRA_TOPICS. Use whenever the user asks why an arXiv paper scored low or how to increase its score, wants a paper (or papers like it) to appear in the main list, or asks to add watch topics or keywords to the listing."
---

# hep-ph topic boost: lift a paper with watch topics

The daily pages score each listing paper 35% direct citations of network papers, 30% coupling to the
author's papers, 15% coupling to the network, 10% authorship and **10% shared topics**. The topic
part is 1 − e^(−Σw/3) over the weighted phrases found in the title and abstract: the network's
phrases plus the user's **watch topics**, the repository variable `EXTRA_TOPICS`
(`phrase=weight; phrase=weight`, weight ≤ 4; 2–5 words, no filler words such as "into" or "the").
A paper bibliographically far from the network can only gain through the topic part (at most 10
points), so this works for papers just below the threshold.

## 1. Analyse the paper

Write the bundled `boost_topics.py` (copy the block exactly) and run it:

```bash
python3 -I boost_topics.py --arxiv 2605.20162 --out boost.json \
  [--site https://<user>.github.io/hep-ph/] [--threshold 10]
```

Default site: <https://restrepo.github.io/hep-ph/>; use the fork's address for another author and the
repository's `SCORE_THRESHOLD` if it was changed. The script:

- finds the paper in the site's days (score, score parts, matched topics); if it is not there (older
  than the days shown) it takes title and abstract from arXiv and only lists candidates;
- computes the **extra topic weight needed** to reach the threshold (`null` when topics alone cannot
  lift it: then suggest lowering `SCORE_THRESHOLD`; `0` when it is already above);
- lists candidate phrases from the title and abstract that are not already network topics, with
  how many hep-ph papers since 10 years use each (one INSPIRE count each) and which other papers in
  the site's days contain it (they would gain too); fragments of longer phrases and non-topic words
  ("has reported", "naturally", "interpretation") are left out of the suggestions;
- proposes `suggested_EXTRA_TOPICS`: two phrases on different concepts, used by 20–500 hep-ph
  papers (rarer only ever matches this paper, more common lifts unrelated papers), each with half
  the needed weight (the paper contains both, so their weights add).

`--phrases "a; b"` evaluates phrases the user proposes instead.

## 2. Choose the watch topics

Review the suggestion against the candidate table and the abstract: keep phrases that name the
**physics the user wants to follow** (e.g. "thermal dark matter", "neutrino background", "MeV
range"), not wording accidents. Prefer phrases that also catch similar future papers, and check
`other_papers_in_site_days` so the change does not lift unrelated papers. Use the weights the script
computed (raise them a little for a margin; never above 4). If the repository already has
`EXTRA_TOPICS`, append to it with `;`.

## 3. Reply

Give, in this order: the paper's current score, its score parts and why it is low (no citations of
network papers, little coupling, which topics matched); the extra weight needed; a short table of the
proposed phrases (hep-ph papers, other recent papers they would lift); and the exact value:

```
EXTRA_TOPICS = thermal dark matter=0.5; neutrino background=0.5
```

Then how to apply it: **Settings → Secrets and variables → Actions → Variables** → `EXTRA_TOPICS`
(new or edit), then **Actions → hep-ph network pages → Run workflow** (or wait for the evening run);
the pages are rebuilt and matching papers list "Your watch topics: …". With the Claude skills alone,
pass the same value to hep-ph-network-match as `--extra-topics`. If topics cannot lift the paper,
say so and suggest `SCORE_THRESHOLD` instead.

## Bundled file: boost_topics.py

```python
#!/usr/bin/env python3
"""Suggest watch topics (EXTRA_TOPICS) that lift one arXiv paper above the threshold on the hep-ph network pages.

  python3 -I boost_topics.py --arxiv 2605.20162 [--site https://restrepo.github.io/hep-ph/] [--threshold 10]
         [--phrases "neutrino portal; mev dark matter"] [--top 8] [--out boost.json]

1. Finds the paper in the site's days (days.json and hep-ph-<date>.json): score, score parts, matched topics.
2. Computes the extra topic weight it needs: the shared-topics part is 10% of the score and equals 1 - exp(-x/3),
   x the sum of the weights of the phrases found in the title and abstract.
3. Lists candidate phrases from its title and abstract (2-5 words, normalized like hepph_match.py), leaving out the
   network's topics: how common each is in hep-ph since 10 years (one INSPIRE count each) and which other papers
   in the site's days contain it (they would gain too). --phrases evaluates given phrases instead.
4. Proposes an EXTRA_TOPICS value: the most specific candidates, with the weight needed.
Writes the analysis as JSON (--out) and prints a summary.
"""
import argparse, json, math, re, sys, time, urllib.parse, urllib.request

UA = {"User-Agent": "hep-ph-topic-boost/1.0 (academic literature alert)"}
STOP = set("""a an the of and or in on at to for from by with without within into onto over under between among
as is are was were be been being this that these those it its their there here we our us they which who whom whose
can could may might must will would should shall do does did not no nor than then so such also both either each
all any some many most more much few other only own same very via per using use used based new recent show shows
shown find found study studied present presented discuss discussed consider considered obtain obtained provide
provided propose proposed investigate investigated analyze analysed analyzed explore explored allow allows allowed
while where when if whether however thus hence therefore moreover furthermore since because although even well
one two three first second paper work article letter case cases way ways result results possible possibly
particular particularly respectively give gives given let order one's i.e e.g eg ie probing probe simplest""".split())
KEEP = {"higgs", "physics", "dynamics", "kinematics", "analysis", "basis", "axis", "lens", "bias", "gas", "mass",
        "boson", "cosmos", "plus", "status", "bonus", "focus", "nucleus", "radius", "genesis", "synthesis"}
MAP = {"vertices": "vertex", "violating": "violation", "matrices": "matrix"}
GENERIC = {"parameter space", "standard model", "this signal", "coming year", "future experiment", "experimental data"}
# words that make a phrase a sentence fragment rather than a topic (not suggested as watch topics)
FILLER = set("""has have had reported report reports naturally fit fits fitting dominantly small large rich including
include includes indication interpretation interpret prediction predictions excess able coming point pointing
mainly strongly recently new novel possible""".split())
LOW, HIGH = 20, 500     # hep-ph papers since 10 years: below, it only matches this paper; above, it is too broad

def norm_tok(t):   # same normalization as hepph_match.py
    t = t.replace("flavour", "flavor").replace("colour", "color")
    if t in MAP: return MAP[t]
    if t in KEEP or len(t) <= 4: return t
    if t.endswith("sses"): return t[:-2]
    if t.endswith("ies") and len(t) > 5: return t[:-3] + "y"
    if t.endswith("s") and not t.endswith(("ss", "us", "is", "ys")): return t[:-1]
    return t

def grams(text):
    out = set()
    s = re.sub(r"\$[^$]*\$|\\\(.*?\\\)|\\[a-zA-Z]+|\{[^}]*\}", " | ", text).lower().replace("’", "'")
    for part in re.split(r"[^a-z0-9'\- ]+", s):
        toks = [norm_tok(t.strip("-'")) for t in part.split() if t.strip("-'")]
        for n in (2, 3, 4, 5):
            for i in range(len(toks) - n + 1):
                g = toks[i:i + n]
                if g[0] in STOP or g[-1] in STOP or any(t in STOP and t not in ("of", "and") for t in g[1:-1]): continue
                if any(re.fullmatch(r"[0-9\-']+", t) or len(t) < 2 for t in g): continue
                out.add(" ".join(g))
    return out

def get_json(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r: return json.load(r)
        except Exception as e:
            if i == tries - 1: print(f"[warn] {url[:90]}: {e}", file=sys.stderr); return None
            time.sleep(3 * (i + 1))

def inspire_count(q):
    d = get_json("https://inspirehep.net/api/literature?" + urllib.parse.urlencode({"q": q, "size": 1, "fields": "control_number"}))
    return d["hits"]["total"] if d else None

def variants(p):
    w = p.split(); last = w[-1]
    pl = last[:-1] + "ies" if last.endswith("y") and last[-2:-1] not in "aeiou" else last + ("es" if last.endswith(("s", "x", "ch", "sh")) else "s")
    v = {p, " ".join(w[:-1] + [pl])}
    return sorted(v | {x.replace("flavor", "flavour") for x in v} | {x.replace("violation", "violating") for x in v})

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arxiv", required=True); ap.add_argument("--site", default="https://restrepo.github.io/hep-ph/")
    ap.add_argument("--threshold", type=float, default=10); ap.add_argument("--category", default="hep-ph")
    ap.add_argument("--phrases", help="evaluate these phrases ('a; b') instead of extracting candidates")
    ap.add_argument("--top", type=int, default=8); ap.add_argument("--out")
    a = ap.parse_args(); site = a.site.rstrip("/") + "/"; aid = re.sub(r"v\d+$", "", a.arxiv.replace("arXiv:", "").strip())

    days = get_json(site + "days.json") or []
    paper, day, rows_all = None, None, []
    for d in days[:10]:
        rows = get_json(site + d["page"].replace(".html", ".json")) or []
        rows_all += [(d["date"], r) for r in rows]
        for r in rows:
            if r["arxiv"] == aid and paper is None: paper, day = r, d["date"]
    netname = re.search(r'href="(network_[^"]+\.json)"', urllib.request.urlopen(urllib.request.Request(site, headers=UA), timeout=60).read().decode("utf8", "ignore"))
    net = get_json(site + netname.group(1)) if netname else {}
    known = {x[0] for x in (net.get("phrases") or {}).get("list", [])}

    if paper:
        title, abstract = paper["title"], paper.get("abstract", "")
    else:   # not on the site: take title and abstract from arXiv
        x = urllib.request.urlopen(urllib.request.Request("https://export.arxiv.org/api/query?id_list=" + aid, headers=UA), timeout=60).read().decode()
        title = " ".join(re.findall(r"<title>(.*?)</title>", x, re.S)[-1].split())
        abstract = " ".join((re.search(r"<summary>(.*?)</summary>", x, re.S) or [None, ""])[1].split())
    score = paper["score"] if paper else None
    parts = paper.get("parts", []) if paper else []
    s_top = parts[4] if len(parts) > 4 else 0.0
    need = None
    if paper:
        delta = a.threshold - score
        if delta <= 0: need = 0.0
        else:
            s_new = s_top + delta / 10 + 0.005          # topics are 10% of the score
            need = None if s_new >= 0.999 else round(-3 * math.log(1 - s_new) + 3 * math.log(1 - min(s_top, 0.999)), 2)

    cands = sorted(p for p in grams(title + " . " + abstract) if p not in known and p not in GENERIC) if not a.phrases else \
        [" ".join(norm_tok(t) for t in p.lower().split()) for p in a.phrases.split(";") if p.strip()]
    since = int(time.strftime("%Y")) - 10
    base = f"arxiv_eprints.categories:{a.category} and de > {since}"
    total = inspire_count(base) or 1
    info = []
    for p in cands[:60]:
        q = base + " and (" + " or ".join(f't "{v}" or abstracts.value:"{v}"' for v in variants(p)) + ")"
        bg = inspire_count(q); time.sleep(0.3)
        others = [(dd, r["arxiv"], r["score"], r["title"]) for dd, r in rows_all
                  if r["arxiv"] != aid and p in grams(r["title"] + " . " + r.get("abstract", ""))]
        info.append({"phrase": p, "hep_ph_papers": bg, "hep_ph_share": round((bg or 0) / total, 5),
                     "other_papers_in_site_days": len(others),
                     "others": [{"date": dd, "arxiv": x, "score": s, "title": t} for dd, x, s, t in others[:10]]})
    # fold a fragment into a longer candidate used by almost as many hep-ph papers ("supernova neutrino background"
    # into "diffuse supernova neutrino background"); keep topics, not sentence fragments
    bgs = {i["phrase"]: i["hep_ph_papers"] or 0 for i in info}
    folded = {h for h in bgs for g in bgs if g != h and f" {h} " in f" {g} " and bgs[g] >= 0.8 * bgs[h]}
    for i in info:
        i["suggestable"] = (i["phrase"] not in folded and not set(i["phrase"].split()) & FILLER
                            and LOW <= (i["hep_ph_papers"] or 0) <= HIGH)
    # topical but not unique: used by enough hep-ph papers to catch similar ones, few enough to mean something
    useful = sorted((i for i in info if i["suggestable"]), key=lambda i: -i["hep_ph_papers"])
    pick = []
    for i in useful:            # two different concepts: no shared words
        if not any(set(i["phrase"].split()) & set(j["phrase"].split()) for j in pick): pick.append(i)
        if len(pick) == 2: break
    if a.phrases: pick = info
    # the paper contains every picked phrase, so their weights add up: split the needed weight among them
    w = max(0.5, min(4.0, math.ceil(need * 10 / len(pick)) / 10)) if (pick and need is not None) else (1.0 if pick else None)
    proposal = "; ".join(f"{i['phrase']}={w:g}" for i in pick) if (pick and w) else ""
    out = {"arxiv": aid, "title": title, "on_site": bool(paper), "date": day, "score": score, "threshold": a.threshold,
           "parts": dict(zip(["direct_citations", "coupling_own", "coupling_network", "authorship", "topics"], parts)),
           "matched_topics": (paper or {}).get("topics", []), "watch_topics_matched": (paper or {}).get("watch", []),
           "extra_topic_weight_needed": need, "candidates": info, "suggested_EXTRA_TOPICS": proposal,
           "note": ("already above the threshold" if need == 0 else
                    "topics alone cannot lift it (they are 10% of the score): lower SCORE_THRESHOLD instead"
                    if paper and need is None else None)}
    if a.out: json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{aid}: {title[:80]}")
    if paper:
        print(f"  {day}: score {score} (threshold {a.threshold}); topic part {s_top:.2f}; matched {out['matched_topics']}")
        print(f"  extra topic weight needed: {need if need is not None else 'not reachable with topics alone'}")
    else: print("  not on the site's days: score unknown; candidates only")
    print("  suggestable candidates (hep-ph papers since %d | other papers in the site's days):" % since)
    for i in (useful if not a.phrases else info)[:a.top]:
        print(f"    {i['phrase']:40s} {i['hep_ph_papers']!s:>6} | {i['other_papers_in_site_days']}")
    print(f"  suggested EXTRA_TOPICS: {proposal or '(none)'}")

if __name__ == "__main__":
    main()
```
