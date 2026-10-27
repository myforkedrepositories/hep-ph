# hep-ph network match

Daily pages ranking the arXiv **hep-ph** listing against the INSPIRE-HEP citation network of
author [991924](https://inspirehep.net/authors/991924).

- `docs/index.html` — links to the last 5 announcement days; `docs/hep-ph-YYYY-MM-DD.html` — one ranked listing per day
  (papers above the threshold, the network graph, then the next 20 papers by score in a collapsed list).
- `data/inspire/network_991924.json` — compact network (own papers with ≤ 10 authors, the papers most coupled to them, the important papers citing them and every paper citing them from the last 10 years and the current one).
- `tools/build_network.py` (hep-network-builder), `tools/hepph_match.py` + `tools/template.html`
  (hep-ph-network-match), `tools/build_site.py` (index and last-5-days logic).
- `skills/hep-network-builder/SKILL.md`, `skills/hep-ph-network-match/SKILL.md` — the two skills with the current code
  (upload it in claude.ai → Settings → Capabilities → Skills to update the skill).
- `.github/workflows/hep-ph-pages.yml` — runs once each weekday evening, 21:17 Bogotá, Monday–Friday (and on demand from the
  Actions tab), rebuilds the network when it is older than 7 days (so new papers citing yours join it), and commits `docs/`.

## GitHub Pages

Settings → Pages → *Build and deployment* → Source: **Deploy from a branch**, branch `main`, folder `/docs`.
The site is then at <https://restrepo.github.io/hep-ph/>.

## Run locally

```bash
python3 -I tools/build_network.py --author-recid 991924 --out data/inspire/network_991924.json   # 10–25 min
python3 -I tools/build_site.py --network data/inspire/network_991924.json --site docs --days 5
```
