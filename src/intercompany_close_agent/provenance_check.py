"""The published history, checked against the real dates on record.

On 15 October 2026 this repository's history was rewritten one last time, to
put the real commit times back (PROVENANCE.md says how; REMEDIATION.md, in the
profile repository, says why). `.github/provenance.toml` pins what that
restoration left and the dates published about it. This reads the history CI
checked out and fails if any of the following stops being true:

1. The restored commit is in the history. Its SHA covers every commit before
   it, their content, messages and author and committer dates, so rewriting
   any of that history, or pushing a backdated version of it again, loses it.
2. The history has one root, the first commit on record, so an older history
   can't be merged in alongside it.
3. No commit after the restoration is dated before it, so nothing can be
   backdated into the period the restored history covers.
4. No commit is dated in the future.
5. The commit counts published for given days and times still match the
   history.
6. On a push, the branch's previous tip is still in the new history, so a
   force-push fails whatever it rewrote.

It only reads; it changes nothing. It needs git and the whole history (CI
checks out with fetch-depth 0). Locally, from the repository root:

    python src/intercompany_close_agent/provenance_check.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / ".github" / "provenance.toml"
# A commit's clock can run a little ahead of CI's; more than this is a future date.
CLOCK_SLACK = timedelta(hours=1)
NO_COMMIT = "0" * 40  # what GitHub sends as the previous tip when a branch is created
SHOWN = 30  # problems listed in the report; a rewritten history can produce hundreds


@dataclass(frozen=True)
class Commit:
    sha: str
    authored: datetime
    committed: datetime
    parents: tuple[str, ...]


@dataclass(frozen=True)
class Published:
    """A count of commits published for a span of time: start included, end excluded, UTC author dates."""

    claim: str
    start: datetime
    end: datetime
    commits: int


@dataclass(frozen=True)
class Record:
    first_commit: str
    restored: str
    published: list[Published]


def load_record(path: Path = RECORD) -> Record:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    history = data["history"]
    published = [
        Published(p["claim"], _utc(p["from"]), _utc(p["to"]), int(p["commits"])) for p in data.get("published", [])
    ]
    return Record(str(history["first_commit"]), str(history["restored"]), published)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{value} has no time zone; write it in UTC, ending in Z")
    return value.astimezone(UTC)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def read_history(repo: Path, rev: str = "HEAD") -> list[Commit]:
    commits = []
    for line in git(repo, "log", "--format=%H %at %ct %P", rev).splitlines():
        sha, authored, committed, *parents = line.split()
        commits.append(
            Commit(
                sha,
                datetime.fromtimestamp(int(authored), UTC),
                datetime.fromtimestamp(int(committed), UTC),
                tuple(parents),
            )
        )
    return commits


def _has_commit(repo: Path, sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo, capture_output=True).returncode == 0


def _is_ancestor(repo: Path, older: str, newer: str = "HEAD") -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=repo).returncode == 0


def problems(repo: Path, record: Record, now: datetime, previous: str | None = None) -> list[str]:
    """Everything in the history that contradicts the record; empty when it all holds."""
    history = read_history(repo)
    by_sha = {c.sha: c for c in history}
    found: list[str] = []

    restored = by_sha.get(record.restored)
    if restored is None:
        found.append(
            f"The restored commit {record.restored[:7]} is not in this history: the history it covers "
            "has been rewritten, or this is a different history."
        )
    roots = sorted(c.sha for c in history if not c.parents)
    if roots != [record.first_commit]:
        found.append(
            f"The history should have one first commit, {record.first_commit[:7]}; it has "
            f"{', '.join(r[:7] for r in roots)}."
        )

    if restored is not None:
        covered = set(git(repo, "rev-list", restored.sha).split())
        floor = restored.committed
        for c in history:
            if c.sha not in covered and min(c.authored, c.committed) < floor:
                found.append(
                    f"{c.sha[:7]} is dated {_show(min(c.authored, c.committed))}, before the restoration "
                    f"({_show(floor)}); nothing added after it can be dated earlier."
                )

    for c in history:
        if max(c.authored, c.committed) > now + CLOCK_SLACK:
            found.append(f"{c.sha[:7]} is dated {_show(max(c.authored, c.committed))}, in the future.")

    for p in record.published:
        count = sum(1 for c in history if p.start <= c.authored < p.end)
        if count != p.commits:
            found.append(f"Published: {p.claim} The history has {count}.")

    if previous and previous != NO_COMMIT:
        if not _has_commit(repo, previous):
            subprocess.run(["git", "fetch", "--quiet", "origin", previous], cwd=repo, capture_output=True)
        if not _has_commit(repo, previous) or not _is_ancestor(repo, previous):
            found.append(
                f"The branch's previous tip {previous[:7]} is not in the new history: this push rewrote it."
            )
    return found


def _show(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def report(repo: Path, record: Record, found: list[str]) -> list[str]:
    history = read_history(repo)
    lines = ["## The history against the real dates on record", ""]
    if found:
        lines += [f"**{len(found)} problem(s).** The check only reads; it changes nothing.", ""]
        lines += [f"- {problem}" for problem in found[:SHOWN]]
        if len(found) > SHOWN:
            lines.append(f"- ... and {len(found) - SHOWN} more of the same kinds.")
        return lines
    lines.append(
        f"No problems in {len(history)} commits. The restored history ({record.restored[:7]}) is intact, "
        f"with one first commit ({record.first_commit[:7]}); nothing added since is dated before it or in "
        f"the future; and the {len(record.published)} published count(s) match:"
    )
    lines += ["", *(f"- {p.claim}" for p in record.published)]
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--previous", default="", help="the branch's tip before this push, if any")
    parser.add_argument("--record", type=Path, default=RECORD)
    args = parser.parse_args(argv)
    record = load_record(args.record)
    found = problems(ROOT, record, datetime.now(UTC), args.previous or None)
    print("\n".join(report(ROOT, record, found)))
    if found:
        sys.exit(1)


if __name__ == "__main__":
    main()
