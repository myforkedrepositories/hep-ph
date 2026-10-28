# hep-ph network match

Daily pages ranking the arXiv **hep-ph** listing against the INSPIRE-HEP citation network of an
author: by default [991924](https://inspirehep.net/authors/991924), or the one set in the repository
variable `INSPIRE_AUTHOR`.

- `tools/build_network.py` (hep-network-builder), `tools/hepph_match.py` + `tools/template.html`
  (hep-ph-network-match), `tools/build_site.py` (index and last-5-days logic).
- `skills/hep-network-builder/SKILL.md`, `skills/hep-ph-network-match/SKILL.md` — the two skills with the current code
  (upload them in claude.ai → Settings → Capabilities → Skills to update the skills).
- `.github/workflows/hep-ph-pages.yml` — runs once each weekday evening, 21:17 Bogotá, Monday–Friday (and on demand from the
  Actions tab), rebuilds the network when it is older than 7 days (so new papers citing the author join it), builds the
  pages and publishes them to GitHub Pages.
- Branch **`site`** (made and updated by the workflow, never edited by hand) — the generated files:
  `index.html`, one `hep-ph-YYYY-MM-DD.html` per day (papers above the threshold, the network graph, then the next 20
  papers by score in a collapsed list) and `network_<author>.json`, the compact network (own papers with ≤ 10 authors,
  the papers most coupled to them, the important papers citing them and every paper citing them from the last 10 years
  and the current one), with the technical phrases they share most (used for the 10% "shared topics" part of
  the score). `main` holds only code and data, so forks can sync without conflicts.

## GitHub Pages

Settings → Pages → *Build and deployment* → Source: **GitHub Actions**.
The site is then at <https://restrepo.github.io/hep-ph/>.

## Fork this repository for another INSPIRE author

Anyone can run the same daily pages for a different physicist. No file has to be edited: the author
is a repository variable.

1. **Find the INSPIRE author id.** Open the person's profile on INSPIRE: the id is the number at the
   end of the address, `https://inspirehep.net/authors/<id>` (for example `1045947`). The network
   starts from their papers with at most 10 authors, so the person should have a good number of them.
2. **Fork.** On <https://github.com/restrepo/hep-ph> click **Fork**. Keep the name `hep-ph`; the
   default "Copy the `main` branch only" is fine.
3. **Set the author.** In the fork: **Settings → Secrets and variables → Actions → Variables →
   New repository variable**, name `INSPIRE_AUTHOR`, value the id from step 1.
4. **Enable the workflow.** Open the fork's **Actions** tab and click "I understand my workflows, go
   ahead and enable them" (forks start with workflows, including scheduled ones, disabled).
5. **Enable GitHub Pages.** **Settings → Pages → Build and deployment → Source: GitHub Actions**.
6. **Enable the scheduled runs and do the first run.** **Actions → hep-ph network pages.** GitHub
   shows that scheduled workflows are disabled in forks: click **Enable workflow** (without this the
   site is never updated automatically). Then **Run workflow** (branch `main`). It builds the
   author's citation network from INSPIRE (10–25 minutes), then the pages for the last 5 arXiv hep-ph
   announcement days, creates the `site` branch with the generated files and publishes them.
7. **Open the site** at `https://<github-user>.github.io/hep-ph/` (the run's *deploy* step shows the
   address). From then on it updates by itself every weekday evening (21:17 Bogotá) and rebuilds the
   network weekly.

**Optional settings.** Add any of these as repository variables, next to `INSPIRE_AUTHOR`
(Settings → Secrets and variables → Actions → Variables). Unset means the default.

*Network size* — a change rebuilds the network on the next run:

| Variable | Default | What it does |
|---|---|---|
| `RECENT_YEARS` | `10` | Every paper citing the author's papers from this many past years (and the current one) joins the network. Lower is more conservative: `2` keeps the daily list close to the original selection, `-1` keeps only the important citing papers (≥ 200 citations or citing ≥ 4 of the author's papers). |
| `MAX_AUTHORS` | `10` | The network starts from the author's papers with at most this many authors. Raise it for someone who mostly writes in larger groups. |
| `COUPLED_PER_PAPER` | `5` | For each of the author's papers, this many papers by others that share the most references with it are kept. |
| `NETWORK_MAX_AGE` | `7` | Days before the network is rebuilt, so new citing papers join. |

*Listing* — a change rebuilds the pages on the next run:

| Variable | Default | What it does |
|---|---|---|
| `ARXIV_CATEGORY` | `hep-ph` | arXiv listing to rank, e.g. `hep-th`, `astro-ph.CO`, `gr-qc`. |
| `SCORE_THRESHOLD` | `10` | Papers scoring at least this (0–100) are listed in full on each day's page. |
| `NEXT_PAPERS` | `20` | Papers just below the threshold shown in each page's folded list. |
| `DAYS` | `5` | Announcement days shown on the site. |
| `TIMEZONE` | `America/Bogota` | Time zone that decides which day is "today". |

The time of the daily run (21:17 Bogotá) is the one setting that cannot be a variable: GitHub needs
it written in `.github/workflows/hep-ph-pages.yml` (`cron`, in UTC). Editing that line is fine, but it
may then need a quick conflict fix when syncing the fork.

**Keeping the fork up to date.** When this repository gets improvements, click **Sync fork** on the
fork's main page. `main` holds only code and data and the author lives in the variable, so syncing
never conflicts; the next run uses the new code.

**Troubleshooting.**
- The run fails at "Save the site on its branch" with a 403: **Settings → Actions → General →
  Workflow permissions → Read and write permissions**, then run the workflow again.
- The deploy step fails saying Pages is not enabled: check step 5 (Source must be **GitHub Actions**,
  not a branch).
- To rebuild the network at once (instead of waiting a week), run the workflow with
  "Rebuild the INSPIRE network file" ticked.

**With the Claude skills** (claude.ai): give hep-network-builder the INSPIRE id to make that author's
network file, then hep-ph-network-match ranks a day's listing against it. No fork is needed for that.

## Run locally

```bash
python3 -I tools/build_network.py --author-recid 991924 --out network_991924.json   # 10–25 min
python3 -I tools/build_site.py --network network_991924.json --site site --days 5
```
