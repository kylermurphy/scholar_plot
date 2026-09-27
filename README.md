# scholar_plot

Builds the research-impact numbers and chart used on
[kylermurphy.github.io](https://kylermurphy.github.io):

1. fetches citation metrics (citations, h-index, i10-index, citations per year) from
   Google Scholar with [scholarly][2];
2. counts publications per year from the site's `_publications/` folder
   (files named `YYYY-MM-DD-Name.md`; year = first 4 characters);
3. writes `data/scholar.json` and renders `figures/scholar_light.png` / `figures/scholar_dark.png`.

A monthly GitHub Action runs `scholar_plot.py` and commits the outputs to `master`.
The site only *reads* these files; nothing is ever written to the site repo.

## Outputs

| Path | What |
|---|---|
| `data/scholar.json` | numbers (schema below) |
| `figures/scholar_light.png` | chart for the light theme, transparent background, 3x resolution |
| `figures/scholar_dark.png` | chart for the dark theme, transparent background, 3x resolution |

Public raw URLs:

```
https://raw.githubusercontent.com/kylermurphy/scholar_plot/master/data/scholar.json
https://raw.githubusercontent.com/kylermurphy/scholar_plot/master/figures/scholar_light.png
https://raw.githubusercontent.com/kylermurphy/scholar_plot/master/figures/scholar_dark.png
```

## `data/scholar.json` schema

Exact keys; integers unless noted.

```json
{
  "updated": "2026-09-27",                       // ISO date string, date of the run
  "profile": "https://scholar.google.com/citations?user=n8I0sAwAAAAJ&hl=en",
  "scholar_id": "n8I0sAwAAAAJ",
  "since_year": 2021,                             // Google Scholar's own "since" year for the *5y fields (= current year - 5)
  "totals": {
    "citations":    {"all": 3444, "since": 1968}, // scholarly: citedby, citedby5y
    "h_index":      {"all": 34,   "since": 25},   // hindex, hindex5y
    "i10_index":    {"all": 73,   "since": 62},   // i10index, i10index5y
    "publications": {"all": 108,  "since": 30}    // counted from site _publications filenames; since = year >= since_year
  },
  "per_year": [                                   // sorted ascending, every year from min(first pub, first citation) to current year, gaps filled with 0
    {"year": 2008, "citations": 0, "publications": 2}
  ],
  "partial_year": 2026                            // current calendar year at run time (its values are year-to-date)
}
```

## Running locally

```
pip install -r requirements.txt
python scholar_plot.py --pubs-dir ../kylermurphy.github.io/_publications
```

Options:

- `--pubs-dir PATH` — local `_publications` folder. Without it, the folder is listed through the
  GitHub API (`kylermurphy/kylermurphy.github.io`, branch `master`); set `GITHUB_TOKEN` for a
  higher rate limit.
- `--out-dir DIR` — where `data/` and `figures/` are written (default: repo root).
- `--from-json FILE` — skip Google Scholar and re-render from an existing `scholar.json`, keeping
  its Scholar numbers and date but recounting publications. Handy for offline previews.
- `--scholar-id ID` — Google Scholar user id (default `n8I0sAwAAAAJ`).

Exit codes: `0` success; `1` any other error; `2` Google Scholar unavailable — nothing is written,
so the previously committed outputs stay in place.

Google Scholar frequently blocks requests from cloud IPs (including GitHub Actions runners). If the
monthly Action exits with code 2, run the command above from a local machine and commit
`data/` and `figures/`.

GitHub pauses scheduled workflows in public repos after 60 days without repository activity. If
Scholar keeps blocking the runner, nothing gets committed and the schedule will eventually be
paused; a local run and push re-activates it, or re-enable it from the Actions tab.

`scholar_plot.ipynb` walks through the same steps interactively. Tests: `python -m pytest -q`.

## Credits

Google Scholar data via [scholarly][2], installable from PyPI (`pip install scholarly`) or GitHub:

```
pip install -U git+https://github.com/OrganicIrradiation/scholarly.git
```

[2]:https://github.com/OrganicIrradiation/scholarly
