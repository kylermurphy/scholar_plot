"""Tests for scholar_plot.py (no network access)."""

from __future__ import annotations

import json
import sys
import types
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scholar_plot as sp  # noqa: E402

FAKE_SCHOLAR = {
    "citedby": 3444,
    "citedby5y": 1968,
    "hindex": 34,
    "hindex5y": 25,
    "i10index": 73,
    "i10index5y": 62,
    "cites_per_year": {2010: 5, 2012: 20, 2026: 100},
}
TODAY = date(2026, 9, 27)


@pytest.fixture
def pubs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "_publications"
    d.mkdir()
    for name in [
        "2008-01-01-a.md",
        "2008-06-01-b.md",
        "2011-03-02-c.md",
        "2021-01-01-d.md",
        "2025-05-05-e.md",
        "2026-02-02-f.md",
        "README.md",  # no year prefix
        "draft-2020.md",  # no year prefix
        "2019-01-01-notes.txt",  # not markdown
    ]:
        (d / name).write_text("---\n---\n")
    return d


@pytest.fixture
def fake_chart(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []

    def render(data: dict, out_dir: Path) -> list[Path]:
        calls.append((data, out_dir))
        return []

    monkeypatch.setitem(sys.modules, "chart", types.SimpleNamespace(render=render))
    return calls


def test_count_publications_local(pubs_dir: Path) -> None:
    assert sp.count_publications(pubs_dir) == {2008: 2, 2011: 1, 2021: 1, 2025: 1, 2026: 1}


def test_count_publications_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sp.count_publications(tmp_path / "nope")


def test_build_data_schema(pubs_dir: Path) -> None:
    data = sp.build_data(FAKE_SCHOLAR, sp.count_publications(pubs_dir), TODAY)
    assert list(data) == [
        "updated", "profile", "scholar_id", "since_year", "totals", "per_year", "partial_year",
    ]
    assert data["updated"] == "2026-09-27"
    assert data["profile"] == "https://scholar.google.com/citations?user=n8I0sAwAAAAJ&hl=en"
    assert data["scholar_id"] == "n8I0sAwAAAAJ"
    assert data["since_year"] == 2021
    assert data["partial_year"] == 2026
    assert data["totals"] == {
        "citations": {"all": 3444, "since": 1968},
        "h_index": {"all": 34, "since": 25},
        "i10_index": {"all": 73, "since": 62},
        "publications": {"all": 6, "since": 3},
    }
    for row in data["per_year"]:
        assert set(row) == {"year", "citations", "publications"}
        assert all(isinstance(v, int) for v in row.values())


def test_build_data_zero_fill(pubs_dir: Path) -> None:
    data = sp.build_data(FAKE_SCHOLAR, sp.count_publications(pubs_dir), TODAY)
    years = [r["year"] for r in data["per_year"]]
    assert years == list(range(2008, 2027))  # min over both series -> current year
    by_year = {r["year"]: r for r in data["per_year"]}
    assert by_year[2008] == {"year": 2008, "citations": 0, "publications": 2}
    assert by_year[2009] == {"year": 2009, "citations": 0, "publications": 0}
    assert by_year[2012] == {"year": 2012, "citations": 20, "publications": 0}
    assert by_year[2026] == {"year": 2026, "citations": 100, "publications": 1}
    assert sum(r["publications"] for r in data["per_year"]) == data["totals"]["publications"]["all"]


def test_build_data_extends_to_current_year() -> None:
    scholar = dict(FAKE_SCHOLAR, cites_per_year={2015: 3})
    data = sp.build_data(scholar, {2016: 1}, TODAY)
    assert data["per_year"][0]["year"] == 2015
    assert data["per_year"][-1] == {"year": 2026, "citations": 0, "publications": 0}


def test_write_json(tmp_path: Path) -> None:
    data = sp.build_data(FAKE_SCHOLAR, {2020: 1}, TODAY)
    path = sp.write_json(data, tmp_path / "out")
    assert path == tmp_path / "out" / "data" / "scholar.json"
    text = path.read_text()
    assert text.endswith("}\n")
    assert json.loads(text) == data
    assert list(path.parent.iterdir()) == [path]  # no temp files left behind


def test_main_scholar_unavailable_exits_2(
    tmp_path: Path, pubs_dir: Path, fake_chart: list, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    def boom(scholar_id: str) -> dict:
        raise sp.ScholarUnavailable("blocked")

    monkeypatch.setattr(sp, "fetch_scholar", boom)
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        sp.main(["--pubs-dir", str(pubs_dir), "--out-dir", str(out)])
    assert exc.value.code == 2
    assert not out.exists()
    assert fake_chart == []
    assert "Google Scholar unavailable" in capsys.readouterr().err


def test_main_success(
    tmp_path: Path, pubs_dir: Path, fake_chart: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sp, "fetch_scholar", lambda scholar_id: FAKE_SCHOLAR)
    out = tmp_path / "out"
    sp.main(["--pubs-dir", str(pubs_dir), "--out-dir", str(out)])
    data = json.loads((out / "data" / "scholar.json").read_text())
    assert data["totals"]["publications"]["all"] == 6
    assert len(fake_chart) == 1 and fake_chart[0][1] == out


def test_main_from_json(
    tmp_path: Path, pubs_dir: Path, fake_chart: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_fetch(scholar_id: str) -> dict:
        raise AssertionError("must not fetch Scholar with --from-json")

    monkeypatch.setattr(sp, "fetch_scholar", no_fetch)
    src = tmp_path / "old.json"
    old = sp.build_data(FAKE_SCHOLAR, {2008: 9}, date(2025, 3, 1))
    src.write_text(json.dumps(old))
    out = tmp_path / "out"
    sp.main(["--from-json", str(src), "--pubs-dir", str(pubs_dir), "--out-dir", str(out)])
    data = json.loads((out / "data" / "scholar.json").read_text())
    assert data["updated"] == "2025-03-01"
    assert data["totals"]["citations"] == old["totals"]["citations"]
    assert data["totals"]["publications"]["all"] == 6  # recounted
    by_year = {r["year"]: r for r in data["per_year"]}
    assert by_year[2012]["citations"] == 20


def test_main_from_json_keeps_counts_when_recount_fails(
    tmp_path: Path, fake_chart: list
) -> None:
    src = tmp_path / "old.json"
    old = sp.build_data(FAKE_SCHOLAR, {2008: 9, 2024: 2}, date(2026, 1, 5))
    src.write_text(json.dumps(old))
    out = tmp_path / "out"
    sp.main(["--from-json", str(src), "--pubs-dir", str(tmp_path / "missing"), "--out-dir", str(out)])
    data = json.loads((out / "data" / "scholar.json").read_text())
    assert data == old


def test_fetch_scholar_wraps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        def search_author_id(self, scholar_id: str) -> dict:
            raise RuntimeError("captcha")

    monkeypatch.setitem(sys.modules, "scholarly", types.SimpleNamespace(scholarly=Boom()))
    with pytest.raises(sp.ScholarUnavailable, match="captcha"):
        sp.fetch_scholar("x")


def test_fetch_scholar_import_error_is_not_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken scholarly install must not be reported as 'Scholar blocked'."""
    monkeypatch.setitem(sys.modules, "scholarly", None)  # makes the import raise ImportError
    with pytest.raises(ImportError):
        sp.fetch_scholar("x")


def test_count_publications_github(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    class Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> list:
            return [
                {"name": "2010-01-01-a.md", "type": "file"},
                {"name": "2010-02-01-b.md", "type": "file"},
                {"name": "index.md", "type": "file"},
                {"name": "2011-x", "type": "dir"},
            ]

    def get(url: str, headers: dict, timeout: float) -> Resp:
        seen.update(url=url, headers=headers)
        return Resp()

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=get))
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    assert sp.count_publications() == {2010: 2}
    assert seen["url"] == sp.PUBS_API_URL
    assert seen["headers"]["Authorization"] == "Bearer tok"


def test_chart_render_writes_both_themes(tmp_path):
    """Real chart module: renders light + dark PNGs at 3x the sidebar size."""
    import importlib
    import sys as _sys
    _sys.modules.pop("chart", None)
    chart = importlib.import_module("chart")
    data = {
        "per_year": [
            {"year": 2019, "citations": 120, "publications": 3},
            {"year": 2020, "citations": 180, "publications": 5},
            {"year": 2021, "citations": 60, "publications": 1},
        ],
        "partial_year": 2021,
    }
    paths = chart.render(data, tmp_path)
    assert [p.name for p in paths] == ["scholar_light.png", "scholar_dark.png"]
    from PIL import Image
    for p in paths:
        with Image.open(p) as im:
            assert im.size == (600, 450)
            assert im.mode == "RGBA"


def test_shared_scales_are_tight():
    import chart
    c_max, c_step, p_max, p_step = chart._shared_scales(410, 11)
    assert c_max // c_step == p_max // p_step
    assert 410 <= c_max <= 600 and 11 <= p_max <= 15
