# hep-ph network match

Daily pages ranking the arXiv **hep-ph** listing against the INSPIRE-HEP citation network of
author [991924](https://inspirehep.net/authors/991924) (Diego Restrepo).

- `docs/index.html` — links to the last 5 announcement days; `docs/hep-ph-YYYY-MM-DD.html` — one ranked listing per day.
- `data/inspire/network_991924.json` — compact network (own papers with ≤ 10 authors, coupled and important citing papers).
- `tools/build_network.py` (hep-network-builder), `tools/hepph_match.py` + `tools/template.html`
  (hep-ph-network-match), `tools/build_site.py` (index and last-5-days logic).
- `.github/workflows/hep-ph-pages.yml` — runs Monday–Saturday at 07:17 Bogotá (and on demand from the
  Actions tab), rebuilds the network when it is older than 30 days, and commits `docs/`.

## GitHub Pages

Settings → Pages → *Build and deployment* → Source: **Deploy from a branch**, branch `main`, folder `/docs`.
The site is then at `https://restrepo.github.io/hep-ph/`.

## Run locally

```bash
python3 -I tools/build_network.py --author-recid 991924 --out data/inspire/network_991924.json   # 10–25 min
python3 -I tools/build_site.py --network data/inspire/network_991924.json --site docs --days 5
```
