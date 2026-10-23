# INSPIRE-HEP data

## `restrepo_network_external_papers.json.gz`

Full INSPIRE-HEP literature records (all fields, including complete reference
lists) for the **251 papers by other authors** in the coupling and citation
network built around the papers of INSPIRE author 991924.
Retrieved from the INSPIRE REST API on 2026-10-21.

- Compressed: 14 MB (gzip). Uncompressed: 59 MB.
- Format: same shape as an INSPIRE API search response,
  `{"hits": {"total": 251, "hits": [ {record}, ... ]}}`, newest first.
  Each record's metadata is in `hits.hits[n].metadata`.
- SHA-256 of the uncompressed JSON starts with `b0a5c8caf50fce87`.

### Which papers are included

The starting set is the author's 65 papers with 1–10 authors:
`authors.recid:991924 and ac 1->10`. That file, `restrepo_inspire_ac1-10.json`,
is kept separately. The 251 papers here are not by that author and come from two
sources:

1. **Related by bibliographic coupling (178 papers).** Candidates are papers citing
   at least one of the 244 references that are cited by 3 or more of the 65 papers
   and have at most 1,000 citations. The 2,000 best-scoring candidates were compared
   by idf-weighted cosine similarity of their INSPIRE-linked reference sets.
   Collaboration papers and papers with more than 30 authors were dropped. Each of
   the 65 papers keeps its 5 most coupled external papers with coupling >= 0.10.
2. **Important citing papers (73 more papers).** These come from the 1,309 papers
   by other authors citing at least one of the 65. A paper counts as important
   when it has at least 200 citations or cites at least 4 of the 65 papers. Of the
   96 that qualify, 23 were already among the coupled papers.

## Download

```bash
curl -L -o restrepo_network_external_papers.json.gz \
  https://github.com/restrepo/hep-ph/raw/main/data/inspire/restrepo_network_external_papers.json.gz
gunzip restrepo_network_external_papers.json.gz
```

If the repository is private, download it from the GitHub web page while signed in,
or use `gh api` or an authenticated `curl`.

```python
import gzip, json
d = json.load(gzip.open("restrepo_network_external_papers.json.gz", "rt"))
papers = [h["metadata"] for h in d["hits"]["hits"]]
```

INSPIRE metadata is released under CC0.
