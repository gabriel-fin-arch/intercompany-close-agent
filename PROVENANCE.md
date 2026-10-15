# Provenance

What the git history of this repo is and isn't, every change I made to it
while publishing, and the things I said about it here that weren't true. None
of it should depend on nobody looking.

## What happened

- I designed this project on 5 August 2026 and built it with Claude Code during
  August 2026. None of it existed before then.
- The commits were backdated as they were made. The prompt I gave the assistant
  asked it to date every commit between September 2025 and February 2026,
  spread over months with gaps, so the history would look like long-running
  work. The dates in July and August 2026 aren't reliable either: nine commits
  are dated between 28 July and 4 August, before the day I started.
- The same prompt set how the history should look, so it would read as months
  of hand-written work: no Sundays, a holiday gap, one to four commits a day,
  casual messages with the odd "wip", and nothing in the files that could date
  them (loose version floors, no model IDs, no future dates). `d2078aa`, the 1
  October version of `e5d2937`, is dated 12 seconds after the newest package in
  its own lockfile was published. My design notes of 5 August had a section on
  making the repo look "100% human": practitioner asides in the README, a few
  rough corners, no tells that an AI wrote it. I've dropped all of that.
- I first published it in August 2026 under a new account, also named
  gabriel-fin-arch, that I've since deleted. On 1 October 2026 I pushed it to
  this account, which I opened in 2022 as Maxxym404, and later renamed this
  account to gabriel-fin-arch.

What is real: the code, the synthetic data generator, the tests and the
accounting design, and every commit from `57a5df7` (14 October 2026) on, which
is as recorded.

## What the 1 October versions already showed

They contained a lockfile resolved on 5 August 2026 inside a commit dated 13
September 2025, and a `v0.1.0` tag created on 10 August 2026 for a release the
changelog dated 9 January 2026. The README badge pointed at
`gabriel-fin-arch/intercompany-close-agent`, which in August was the copy on the
earlier account; the commit that re-pointed it at `Maxxym404` on 1 October says
so ("This copy lives on a different account").

## The force-pushes

Times are UTC, as in the Activity tab, where every "before" commit is still
linked and reachable.

| When | Before → after | What changed |
|---|---|---|
| 2026-10-01 11:58 | `752a74b` → `40a9498` | Removed the commit "commit uv.lock" (dated 13 September 2025), whose lockfile had packages published up to 5 August 2026, and added `uv.lock` to `.gitignore` in every commit. |
| 2026-10-13 09:25 | `40a9498` → `48970a5` | Changed the author and committer email on every commit from a personal address to the GitHub noreply one. Dropped "docs: point the CI badge at this repo" (1 October 2026), which had re-pointed the badge at `Maxxym404/intercompany-close-agent`, an earlier username of mine. It was also the only commit in the history with a `Co-Authored-By` line (Claude Opus 5). |
| 2026-10-13 17:06 | `5215eda` → `fe83715` | Moved six commits from 4–5 August 2026 later by 9 to 21 hours, so that "pin starlette below 1.4, streamlit's gzip middleware breaks on it" (`e5d2937`) no longer predates starlette 1.4.0, published on 5 August 2026 at 09:36 UTC. It had been dated 4 August, 20:41 UTC. |
| 2026-10-14 08:37 | `fe83715` → `ab7bf63` | Renamed four commits from August 2026 so they no longer say "CI": "add ruff, fix what it flagged, wire up CI" became "add ruff, fix what it flagged, and draft the checks workflow", "add CI badge" became "docs: add the checks badge", and two `ci:` prefixes became `build:`. No content change. |

Every one of them kept the invented dates. The last two are the ones I regret
most: where a commit contradicted its date, I changed the commit. The honest
fix was to say the dates were invented, which is what this file does now.

## What I said here that wasn't true

| Commit | Where | What it said |
|---|---|---|
| `57a5df7` (14 Oct 2026) | README | "Imported from an older private workspace in Oct 2026. Commit dates are preserved." Nothing was imported, and the dates were invented. |
| `c15a26f` (14 Oct 2026) | README | That I built it between September 2025 and January 2026, and that the history was reconstructed when I published it. |
| `7d0a171` (14 Oct 2026) | README and this file | The same dates, and that I hadn't kept a usable git history and rebuilt one from my working copy. No history was lost; it was backdated from the first commit. |

My profile README made the same claims in `4593a4f`, `8e6ce4f`, `62e8d62` and
`e6822c6`.

## Other changes

- **The `v0.1.0` tag.** In the version first pushed on 1 October it was
  `f996ff8`, created on 10 August 2026. The first two force-pushes re-created it
  on the rewritten commit with the same tagger date (`75f4135` on 1 October,
  `78a1e9b` on 13 October); the Activity tab doesn't record those. On 13 October
  I deleted it and re-created it with its date set to 9 January 2026, the date
  the changelog gave (`4859f8c`). On 14 October I deleted and re-created it
  again after the last force-push (`81b56a3`). That date was invented like the
  rest. I'm leaving the tag as it is rather than re-creating it once more; the
  changelog now gives 10 August 2026, when it was first made.
- **CI runs.** I deleted runs #1 to #7, from the pushes between 1 and 13
  October 2026. The first run left is #8.
- **Email.** The versions pushed on 1 October were committed under a personal
  email address, and those orphaned commits still show it.
- **Contribution graph.** My profile's graph shows 106 commits in 2025 for this
  repo. There was no work on it in 2025: they are the backdated commits,
  counted once for every rewritten version. Only GitHub can rebuild the graph,
  and the ways to remove them myself would mean deleting or hiding these repos,
  which would also remove the evidence this file points at, so I've left it as
  it is and said so here and on my profile.
- **`Co-Authored-By`.** `57a5df7`, the first commit as recorded, was drafted by
  the assistant and has no `Co-Authored-By` line. Every commit after it that the
  assistant drafted has one.

## How to check

```bash
# every force-push and tag deletion, with the commits before and after it
gh api "repos/gabriel-fin-arch/intercompany-close-agent/activity?per_page=100" \
  --jq '.[] | select(.activity_type!="push") | [.timestamp, .activity_type, .ref, .before[0:7], .after[0:7]] | @tsv'

# when the original v0.1.0 tag was created, and that its commit is in the
# version first pushed on 1 October ("ahead")
gh api repos/gabriel-fin-arch/intercompany-close-agent/git/tags/f996ff85fb579ccd1c2aac6dd21a91acf74d4f90 \
  --jq '[.tagger.date, .object.sha[0:7]] | @tsv'
gh api repos/gabriel-fin-arch/intercompany-close-agent/compare/efb9338...752a74b --jq .status

# the 1 October version of the starlette pin, and the newest package in its lockfile
gh api repos/gabriel-fin-arch/intercompany-close-agent/commits/d2078aa --jq .commit.author.date
gh api "repos/gabriel-fin-arch/intercompany-close-agent/contents/uv.lock?ref=d2078aa" \
  --jq .content | base64 -d | grep -o 'upload-time = "[^"]*"' | sort | tail -1

# the newest package in the lockfile of the commit dated 13 September 2025
gh api "repos/gabriel-fin-arch/intercompany-close-agent/contents/uv.lock?ref=e2d188f" \
  --jq .content | base64 -d | grep -o 'upload-time = "[^"]*"' | sort | tail -1

# the 1 October commit that re-pointed the badge, and why
gh api repos/gabriel-fin-arch/intercompany-close-agent/commits/752a74b --jq .commit.message

# this account's earlier username still redirects here
gh api repos/Maxxym404/intercompany-close-agent --jq .full_name
```

## From here on

No force-pushes, no deleted CI runs, no re-created tags. New commits carry
their real dates, and a `Co-Authored-By` line when the assistant wrote them.
