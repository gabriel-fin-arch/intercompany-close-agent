"""docs/controls.md names code, tests and evidence files; this keeps it honest.

A controls matrix that drifts from the code is worse than none: it reads as
assurance. Each row has to name things that exist, prove itself with at
least one test, and point at evidence the pack actually writes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from intercompany_close_agent.evidence import PACK_FILES

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "intercompany_close_agent"
DOC = ROOT / "docs" / "controls.md"

REFERENCE = re.compile(r"`([\w./]+\.py)(?:::(\w+))?`")
EVIDENCE = re.compile(r"`([\w]+\.(?:csv|json|txt))`")


def _rows() -> list[list[str]]:
    rows = []
    for line in DOC.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0].isdigit():
            rows.append(cells)
    return rows


def _resolve(path: str) -> Path:
    for base in (ROOT, PACKAGE):
        if (base / path).is_file():
            return base / path
    raise AssertionError(f"docs/controls.md names {path}, which doesn't exist")


def _references() -> list[tuple[str, str | None]]:
    return REFERENCE.findall(DOC.read_text(encoding="utf-8"))


def test_the_matrix_has_rows():
    assert len(_rows()) >= 10


@pytest.mark.parametrize(("path", "name"), _references(), ids=lambda value: value or "")
def test_every_file_and_name_it_cites_exists(path: str, name: str):
    source = _resolve(path).read_text(encoding="utf-8")
    if name:
        assert re.search(rf"^\s*(?:def|class)\s+{name}\b|^{name}\s*[:=]", source, re.MULTILINE), (
            f"docs/controls.md cites {path}::{name}, which isn't defined there"
        )


def test_every_control_is_proved_by_a_named_test():
    for number, _objective, _enforced, proved_by, _evidence in _rows():
        tests = [path for path, name in REFERENCE.findall(proved_by) if path.startswith("tests/") and name]
        assert tests, f"control {number} names no test"


def test_every_evidence_file_it_cites_is_one_the_pack_writes():
    cited = {name for row in _rows() for name in EVIDENCE.findall(row[4])}

    assert cited
    assert cited <= set(PACK_FILES), f"not written by the pack: {sorted(cited - set(PACK_FILES))}"
