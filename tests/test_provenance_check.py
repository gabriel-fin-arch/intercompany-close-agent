"""The provenance check (provenance_check.py), on small histories built for each case.

CI runs the check itself on this repository's whole history, in its own job.
These tests hold it to what it promises: a history that keeps the record
passes, and each way of breaking it fails, with a problem that says which.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from intercompany_close_agent.provenance_check import NO_COMMIT, Published, Record, load_record, problems

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def _git(repo: Path, *args: str, when: str | None = None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    if when:
        env |= {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True).stdout


def _commit(repo: Path, when: str, message: str) -> str:
    _git(repo, "commit", "--quiet", "--allow-empty", "-m", message, when=when)
    return _git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Record]:
    """Built on 5 August, restored on 15 October, one commit since."""
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "--quiet", "--initial-branch=main")
    first = _commit(path, "2026-08-05T09:47:49Z", "init")
    _commit(path, "2026-08-05T10:00:00Z", "the pipeline")
    restored = _commit(path, "2026-10-15T14:19:58Z", "restore the real dates")
    _commit(path, "2026-10-20T10:00:00Z", "a change since")
    published = [Published("2 commits on 5 August 2026.", _at("2026-08-05"), _at("2026-08-06"), 2)]
    return path, Record(first, restored, published)


def _at(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=UTC)


def test_a_history_that_keeps_the_record_has_no_problems(repo):
    path, record = repo
    assert problems(path, record, NOW) == []


def test_the_same_history_rebuilt_with_other_dates_fails(repo, tmp_path):
    _, record = repo
    rebuilt = tmp_path / "rebuilt"
    rebuilt.mkdir()
    _git(rebuilt, "init", "--quiet", "--initial-branch=main")
    for when, message in [
        ("2025-09-08T09:47:49Z", "init"),
        ("2025-10-01T10:00:00Z", "the pipeline"),
        ("2026-10-15T14:19:58Z", "restore the real dates"),
    ]:
        _commit(rebuilt, when, message)
    found = problems(rebuilt, record, NOW)
    assert found[0].startswith(f"The restored commit {record.restored[:7]} is not in this history")
    assert any("one first commit" in p for p in found)
    assert "Published: 2 commits on 5 August 2026. The history has 0." in found


def test_an_older_history_merged_in_alongside_fails(repo, tmp_path):
    path, record = repo
    old = tmp_path / "old"
    old.mkdir()
    _git(old, "init", "--quiet", "--initial-branch=main")
    _commit(old, "2025-09-08T09:00:00Z", "backdated")
    _git(path, "fetch", "--quiet", str(old), "main:old")
    merge = ("merge", "--quiet", "--allow-unrelated-histories", "-s", "ours", "-m", "merge", "old")
    _git(path, *merge, when="2026-10-21T10:00:00Z")
    found = problems(path, record, NOW)
    assert any(p.startswith(f"The history should have one first commit, {record.first_commit[:7]}") for p in found)
    assert any("2025-09-08 09:00:00 UTC, before the restoration" in p for p in found)


def test_a_commit_backdated_into_the_restored_period_fails(repo):
    path, record = repo
    sha = _commit(path, "2026-08-07T10:00:00Z", "backdated")
    assert problems(path, record, NOW) == [
        f"{sha[:7]} is dated 2026-08-07 10:00:00 UTC, before the restoration (2026-10-15 14:19:58 UTC); "
        "nothing added after it can be dated earlier."
    ]


def test_a_commit_dated_in_the_future_fails(repo):
    path, record = repo
    sha = _commit(path, "2026-11-30T10:00:00Z", "from the future")
    assert problems(path, record, NOW) == [f"{sha[:7]} is dated 2026-11-30 10:00:00 UTC, in the future."]


def test_a_published_count_the_history_no_longer_shows_fails(repo):
    path, record = repo
    wrong = Published("3 commits on 5 August 2026.", _at("2026-08-05"), _at("2026-08-06"), 3)
    record = Record(record.first_commit, record.restored, [wrong])
    assert problems(path, record, NOW) == ["Published: 3 commits on 5 August 2026. The history has 2."]


def test_a_push_that_rewrote_the_branch_fails_and_one_that_added_to_it_does_not(repo):
    path, record = repo
    tip = _commit(path, "2026-10-22T10:00:00Z", "pushed, then rewritten away")
    _git(path, "reset", "--quiet", "--hard", "HEAD~1")
    _commit(path, "2026-10-22T10:05:00Z", "the rewrite")
    assert problems(path, record, NOW, previous=tip) == [
        f"The branch's previous tip {tip[:7]} is not in the new history: this push rewrote it."
    ]
    earlier = _git(path, "rev-parse", "HEAD~1").strip()
    assert problems(path, record, NOW, previous=earlier) == []
    assert problems(path, record, NOW, previous=NO_COMMIT) == []


def test_the_record_needs_utc_times(tmp_path):
    path = tmp_path / "provenance.toml"
    head = '[history]\nfirst_commit = "a"\nrestored = "b"\n\n[[published]]\nclaim = "c"\ncommits = 1\n'
    path.write_text(head + "from = 2026-08-05T00:00:00Z\nto = 2026-08-06T00:00:00Z\n", encoding="utf-8")
    assert load_record(path) == Record("a", "b", [Published("c", _at("2026-08-05"), _at("2026-08-06"), 1)])
    path.write_text(head + "from = 2026-08-05T00:00:00\nto = 2026-08-06T00:00:00Z\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no time zone"):
        load_record(path)
