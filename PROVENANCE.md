# Provenance

What the git history of this repo is and isn't, and every change I made to it
while publishing. None of it should depend on nobody looking.

## What is real

- The code, the synthetic data generator, the tests and the accounting design.
- When I worked on it: September 2025 to January 2026, and a second pass in
  July and August 2026.
- Where it has lived: I first put it on GitHub in August 2026, under an
  earlier account I've since deleted, and moved it here on 1 October 2026.
- Every commit from `57a5df7` (14 October 2026) on, which is as recorded.

## What is reconstructed

I didn't keep a usable git history. The commits before 14 October 2026 are a
reconstruction from my working copy. They follow roughly the order I built
things in, but their dates, times of day, messages and intermediate contents
are approximations, not snapshots of what existed then.

The versions I pushed here on 1 October already show it. They contained a
lockfile resolved on 5 August 2026 inside a commit dated 13 September 2025,
and a `v0.1.0` tag created on 10 August 2026 for a release the changelog dates
9 January 2026. The README badge, from the commit dated 4 August 2026, points
at this repo, which was created on 1 October 2026.

## The force-pushes

Times are UTC, as in the Activity tab, where every "before" commit is still
linked and reachable.

| When | Before → after | What changed |
|---|---|---|
| 2026-10-01 11:58 | `752a74b` → `40a9498` | Removed the commit "commit uv.lock" (dated 13 September 2025), whose lockfile had packages published up to 5 August 2026, and added `uv.lock` to `.gitignore` in every commit. |
| 2026-10-13 09:25 | `40a9498` → `48970a5` | Changed the author and committer email on every commit from a personal address to the GitHub noreply one. Dropped "docs: point the CI badge at this repo" (1 October 2026), which had re-pointed the badge at `Maxxym404/intercompany-close-agent`, an earlier username of mine. |
| 2026-10-13 17:06 | `5215eda` → `fe83715` | Moved six commits from 4–5 August 2026 later by 9 to 21 hours, so that "pin starlette below 1.4, streamlit's gzip middleware breaks on it" (`e5d2937`) no longer predates starlette 1.4.0, published on 5 August 2026 at 09:36 UTC. It had been dated 4 August, 20:41 UTC. |
| 2026-10-14 08:37 | `fe83715` → `ab7bf63` | Renamed four commits from August 2026 so they no longer say "CI": "add ruff, fix what it flagged, wire up CI" became "add ruff, fix what it flagged, and draft the checks workflow", "add CI badge" became "docs: add the checks badge", and two `ci:` prefixes became `build:`. No content change. |

The last two are the ones I regret. Where a commit contradicted its date, I
changed the commit; the honest fix was to say the date was wrong, which is
what this file does instead.

## Other changes

- **The `v0.1.0` tag.** In the 1 October versions it was created on 10 August
  2026 (`78a1e9b`). On 13 October I deleted it and re-created it with its date
  set to 9 January 2026, the date in the changelog (`4859f8c`). On 14 October I
  deleted and re-created it again after the last force-push (`81b56a3`). Its
  date is the release date in the changelog, not when the tag was made.
- **CI runs.** I deleted runs #1 to #7, from the pushes between 1 and 13
  October 2026. The first run left is #8.
- **Email.** The versions pushed on 1 October were committed under a personal
  email address, and those orphaned commits still show it.
- **Contribution graph.** GitHub counted the commits of the rewritten-away
  versions as well, so the profile showed about three times the 2025 activity
  that this history contains.

## How to check

```bash
# every force-push and tag deletion, with the commits before and after it
gh api "repos/gabriel-fin-arch/intercompany-close-agent/activity?per_page=100" \
  --jq '.[] | select(.activity_type!="push") | [.timestamp, .activity_type, .ref, .before[0:7], .after[0:7]] | @tsv'

# when the original v0.1.0 tag was created
gh api repos/gabriel-fin-arch/intercompany-close-agent/git/tags/78a1e9bce2139e6a957c026c2474750fbe554e79 \
  --jq .tagger.date

# the newest package in the lockfile of the commit dated 13 September 2025
gh api "repos/gabriel-fin-arch/intercompany-close-agent/contents/uv.lock?ref=e2d188f" \
  --jq .content | base64 -d | grep -o 'upload-time = "[^"]*"' | sort | tail -1
```

## From here on

No force-pushes, no deleted CI runs, no re-created tags. New commits carry
their real dates, and a `Co-Authored-By` line when the assistant wrote them.
