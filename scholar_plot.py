"""Collect Google Scholar + publication counts and render the impact chart.

Pipeline (see README.md for the JSON schema):

1. Fetch citation metrics from Google Scholar with ``scholarly``.
2. Count publications per year from the site's ``_publications`` folder
   (a local checkout, or the GitHub API listing by default).
3. Build the ``data/scholar.json`` dictionary.
4. Write the JSON, then render ``figures/scholar_{light,dark}.png`` via
   ``chart.render``.

Exit codes: 0 success, 1 other error, 2 Google Scholar unavailable (in which
case nothing is written).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

DEFAULT_SCHOLAR_ID = "n8I0sAwAAAAJ"
PUBS_API_URL = (
    "https://api.github.com/repos/kylermurphy/kylermurphy.github.io/"
    "contents/_publications?ref=master"
)
REPO_ROOT = Path(__file__).resolve().parent
JSON_RELPATH = Path("data") / "scholar.json"

_YEAR_RE = re.compile(r"^(\d{4})")
_SCHOLAR_FIELDS = (
    "citedby",
    "citedby5y",
    "hindex",
    "hindex5y",
    "i10index",
    "i10index5y",
)


class ScholarUnavailable(RuntimeError):
    """Raised when Google Scholar data cannot be retrieved (blocked, missing, ...)."""


def profile_url(scholar_id: str) -> str:
    """Return the public Google Scholar profile URL for ``scholar_id``."""
    return f"https://scholar.google.com/citations?user={scholar_id}&hl=en"


def fetch_scholar(scholar_id: str = DEFAULT_SCHOLAR_ID) -> dict[str, Any]:
    """Fetch citation metrics for ``scholar_id`` from Google Scholar.

    Returns a dict with the integer fields ``citedby``, ``citedby5y``,
    ``hindex``, ``hindex5y``, ``i10index``, ``i10index5y`` and
    ``cites_per_year`` (``{year: count}`` with integer keys).

    Raises:
        ScholarUnavailable: when Google Scholar can't be reached or returns
            incomplete data (network block, captcha, missing fields).
        ImportError: if ``scholarly`` isn't installed correctly. This is a
            setup problem, not a Scholar outage, so it is not wrapped.
    """
    # Imported outside the try so a broken install fails loudly (exit 1)
    # instead of looking like "Google Scholar blocked" (exit 2).
    from scholarly import scholarly  # lazy: not needed for --from-json

    try:
        author = scholarly.search_author_id(scholar_id)
        author = scholarly.fill(author, sections=["basics", "indices", "counts"])
    except Exception as exc:  # scholarly raises many different types
        raise ScholarUnavailable(
            f"Could not fetch Google Scholar profile {scholar_id}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if not author:
        raise ScholarUnavailable(f"Google Scholar returned no data for {scholar_id}")
    missing = [k for k in (*_SCHOLAR_FIELDS, "cites_per_year") if k not in author]
    if missing:
        raise ScholarUnavailable(
            f"Google Scholar response for {scholar_id} is missing fields: "
            + ", ".join(missing)
        )

    try:
        result: dict[str, Any] = {k: int(author[k]) for k in _SCHOLAR_FIELDS}
        result["cites_per_year"] = {
            int(y): int(c) for y, c in (author["cites_per_year"] or {}).items()
        }
    except (TypeError, ValueError) as exc:
        raise ScholarUnavailable(
            f"Unexpected Google Scholar data for {scholar_id}: {exc}"
        ) from exc
    return result


def _count_years(names: Iterable[str]) -> dict[int, int]:
    """Count ``*.md`` names by the 4-digit year they start with."""
    counts: Counter[int] = Counter()
    for name in names:
        if not name.endswith(".md"):
            continue
        match = _YEAR_RE.match(name)
        if match:
            counts[int(match.group(1))] += 1
    return dict(sorted(counts.items()))


def _list_github_publications(url: str = PUBS_API_URL) -> list[str]:
    """Return the file names in the site's ``_publications`` folder via the GitHub API."""
    import requests

    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    listing = resp.json()
    if not isinstance(listing, list):
        raise RuntimeError(f"Unexpected GitHub API response from {url}: {listing!r}")
    return [
        item["name"]
        for item in listing
        if isinstance(item, dict) and item.get("type", "file") == "file" and "name" in item
    ]


def count_publications(pubs_dir: Optional[os.PathLike | str] = None) -> dict[int, int]:
    """Count publications per year.

    Args:
        pubs_dir: a local ``_publications`` folder. When ``None`` the GitHub
            API listing of ``kylermurphy/kylermurphy.github.io`` is used
            (``GITHUB_TOKEN`` is sent as a Bearer token if set).

    Returns:
        ``{year: count}`` sorted by year. Only ``*.md`` files whose name
        starts with a 4-digit year (``YYYY-MM-DD-*.md``) are counted.
    """
    if pubs_dir is None:
        names = _list_github_publications()
    else:
        path = Path(pubs_dir)
        if not path.is_dir():
            raise FileNotFoundError(f"Publications folder not found: {path}")
        names = [p.name for p in path.glob("*.md") if p.is_file()]
    return _count_years(names)


def build_data(
    scholar: dict[str, Any],
    pubs: dict[int, int],
    today: date,
    scholar_id: str = DEFAULT_SCHOLAR_ID,
) -> dict[str, Any]:
    """Assemble the ``data/scholar.json`` dictionary.

    Args:
        scholar: output of :func:`fetch_scholar`.
        pubs: output of :func:`count_publications`.
        today: run date; sets ``updated``, ``since_year`` (``today.year - 5``)
            and ``partial_year``.
        scholar_id: Google Scholar user id.
    """
    cites = {int(y): int(c) for y, c in scholar.get("cites_per_year", {}).items()}
    pubs = {int(y): int(c) for y, c in pubs.items()}
    since_year = today.year - 5

    years = set(cites) | set(pubs)
    first = min(years) if years else today.year
    # Normally ends at the current year; extended only if a series has a later
    # (e.g. future-dated) year so per_year always sums to the totals.
    last = max([today.year, *years])
    per_year = [
        {"year": y, "citations": cites.get(y, 0), "publications": pubs.get(y, 0)}
        for y in range(first, last + 1)
    ]

    return {
        "updated": today.isoformat(),
        "profile": profile_url(scholar_id),
        "scholar_id": scholar_id,
        "since_year": since_year,
        "totals": {
            "citations": {"all": int(scholar["citedby"]), "since": int(scholar["citedby5y"])},
            "h_index": {"all": int(scholar["hindex"]), "since": int(scholar["hindex5y"])},
            "i10_index": {"all": int(scholar["i10index"]), "since": int(scholar["i10index5y"])},
            "publications": {
                "all": sum(pubs.values()),
                "since": sum(c for y, c in pubs.items() if y >= since_year),
            },
        },
        "per_year": per_year,
        "partial_year": today.year,
    }


def write_json(data: dict[str, Any], out_dir: os.PathLike | str) -> Path:
    """Write ``data`` to ``<out_dir>/data/scholar.json`` atomically; return the path."""
    target = Path(out_dir) / JSON_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".scholar.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.chmod(tmp, 0o644)  # mkstemp creates 0600
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def scholar_from_data(data: dict[str, Any]) -> dict[str, Any]:
    """Recover a :func:`fetch_scholar`-style dict from an existing scholar.json."""
    totals = data["totals"]
    return {
        "citedby": totals["citations"]["all"],
        "citedby5y": totals["citations"]["since"],
        "hindex": totals["h_index"]["all"],
        "hindex5y": totals["h_index"]["since"],
        "i10index": totals["i10_index"]["all"],
        "i10index5y": totals["i10_index"]["since"],
        "cites_per_year": {
            int(row["year"]): int(row["citations"])
            for row in data.get("per_year", [])
            if row.get("citations")
        },
    }


def pubs_from_data(data: dict[str, Any]) -> dict[int, int]:
    """Recover ``{year: publications}`` from an existing scholar.json."""
    return {
        int(row["year"]): int(row["publications"])
        for row in data.get("per_year", [])
        if row.get("publications")
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Build data/scholar.json and figures/scholar_{light,dark}.png."
    )
    parser.add_argument(
        "--pubs-dir",
        type=Path,
        default=None,
        help="local _publications folder (default: GitHub API listing of the site repo)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT,
        help="output root; writes data/scholar.json and figures/*.png (default: repo root)",
    )
    parser.add_argument(
        "--from-json",
        type=Path,
        default=None,
        metavar="FILE",
        help="skip Google Scholar; reuse Scholar numbers from an existing scholar.json",
    )
    parser.add_argument(
        "--scholar-id",
        default=DEFAULT_SCHOLAR_ID,
        help=f"Google Scholar user id (default: {DEFAULT_SCHOLAR_ID})",
    )
    return parser.parse_args(argv)


def data_from_json(path: os.PathLike | str, pubs_dir: Optional[Path] = None) -> dict[str, Any]:
    """Rebuild the data dict from an existing scholar.json, recounting publications.

    Scholar numbers and ``updated`` (hence ``since_year``/``partial_year``)
    come from the file; publication counts are recounted, falling back to the
    file's counts if recounting fails.
    """
    path = Path(path)
    old = json.loads(path.read_text(encoding="utf-8"))
    try:
        pubs = count_publications(pubs_dir)
    except Exception as exc:
        print(
            f"warning: could not recount publications ({exc}); "
            f"keeping the counts in {path}",
            file=sys.stderr,
        )
        pubs = pubs_from_data(old)
    updated = date.fromisoformat(old["updated"])
    return build_data(
        scholar_from_data(old),
        pubs,
        updated,
        scholar_id=old.get("scholar_id", DEFAULT_SCHOLAR_ID),
    )


def main(argv: Optional[list[str]] = None) -> None:
    """CLI entry point. Exits 0 on success, 2 if Scholar is unavailable, 1 otherwise."""
    args = parse_args(argv)
    try:
        if args.from_json is not None:
            data = data_from_json(args.from_json, args.pubs_dir)
        else:
            try:
                scholar = fetch_scholar(args.scholar_id)
            except ScholarUnavailable as exc:
                print(f"error: Google Scholar unavailable: {exc}", file=sys.stderr)
                print(
                    "Nothing was written. Google Scholar often blocks cloud IPs; "
                    "run locally or use --from-json.",
                    file=sys.stderr,
                )
                sys.exit(2)
            pubs = count_publications(args.pubs_dir)
            data = build_data(scholar, pubs, date.today(), scholar_id=args.scholar_id)

        json_path = write_json(data, args.out_dir)
        print(f"wrote {json_path}")

        import chart  # lazy: matplotlib is only needed for rendering

        for fig_path in chart.render(data, Path(args.out_dir)):
            print(f"wrote {fig_path}")
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
