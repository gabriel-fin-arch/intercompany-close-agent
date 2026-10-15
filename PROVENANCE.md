# Provenance

What the git history of this repo is and isn't, every change I made to it
while publishing, and the things I said about it here that weren't true. None
of it should depend on nobody looking.

On 15 October 2026 I rewrote the history one last time to put back the real
commit times; [Restoring the real dates](#restoring-the-real-dates) says how.
Unless a section says otherwise, the SHAs in this file are from the history as
it stood before that. They are still reachable (`git fetch origin <sha>`), the
force-pushes are linked from the Activity tab, and the [commit map](#commit-map)
gives the new SHA for each.

## What happened

- I designed this project on 5 August 2026 and built it with Claude Code during
  August 2026. None of it existed before then.
- The commits were backdated as they were made, and the default branch kept
  those dates until 15 October 2026. The prompt I gave the assistant asked it
  to date every commit between September 2025 and February 2026, spread over
  months with gaps, so the history would look like long-running work. The
  dates in July and August 2026 weren't reliable either: nine commits were
  dated between 28 July and 4 August, before the day I started.
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
- On 15 October 2026 I put the real times back, from my Claude Code session
  logs. Of the 90 commits I pushed here on 1 October, 69 were made on 5
  August 2026, 3 on 6 August, 8 on 10 August, 9 on 13 August and 1 on
  1 October. Most of the project was built in a day, which is what happened.

What is real: the code, the synthetic data generator, the tests and the
accounting design. Since 15 October 2026 the history is too: every commit's
author date is the time it was made. The commits from 14 October 2026 on
(`57a5df7` and after) always had their real dates.

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
| 2026-10-13 09:25 | `40a9498` → `48970a5` | Changed the author and committer email on every commit from a personal address to the GitHub noreply one. Dropped "docs: point the CI badge at this repo" (1 October 2026), which had re-pointed the badge at `Maxxym404/intercompany-close-agent`, an earlier username of mine. It was also the only commit in that history with a `Co-Authored-By` line (Claude Opus 5): the nine commits of 13 August had lost theirs before 1 October (see [Before 1 October](#before-1-october)). |
| 2026-10-13 17:06 | `5215eda` → `fe83715` | Moved six commits from 4–5 August 2026 later by 9 to 21 hours, so that "pin starlette below 1.4, streamlit's gzip middleware breaks on it" (`e5d2937`) no longer predates starlette 1.4.0, published on 5 August 2026 at 09:36 UTC. It had been dated 4 August, 20:41 UTC. |
| 2026-10-14 08:37 | `fe83715` → `ab7bf63` | Renamed four commits from August 2026 so they no longer say "CI": "add ruff, fix what it flagged, wire up CI" became "add ruff, fix what it flagged, and draft the checks workflow", "add CI badge" became "docs: add the checks badge", and two `ci:` prefixes became `build:`. No content change. |
| 2026-10-15 | `6e9001c` → the current `main` | Restored the real dates: every commit of the version pushed on 1 October, and every one pushed since, rebuilt on its own tree with its own message and the time it was made as its author date; what each earlier force-push changed in the files recorded as a bridge commit; the `Co-Authored-By` line of the nine commits of 13 August put back. No file changed. See [Restoring the real dates](#restoring-the-real-dates). |

The first four kept the invented dates. The ones of 13 October 17:06 and 14
October are those I regret most: where a commit contradicted its date, I
changed the commit. The honest fix was to say the dates were invented, which
this file did from 14 October, and then to put the real ones back, which the
last one did.

## What I said here that wasn't true

| Commit | Where | What it said |
|---|---|---|
| `57a5df7` (14 Oct 2026) | README | "Imported from an older private workspace in Oct 2026. Commit dates are preserved." Nothing was imported, and the dates were invented. |
| `c15a26f` (14 Oct 2026) | README | That I built it between September 2025 and January 2026, and that the history was reconstructed when I published it. |
| `7d0a171` (14 Oct 2026) | README and this file | The same dates, and that I hadn't kept a usable git history and rebuilt one from my working copy. No history was lost; it was backdated from the first commit. |
| `1e45d51` (15 Oct 2026) | this file and `CHANGELOG.md` | That "docs: point the CI badge at this repo" was the only commit with a `Co-Authored-By` line. The nine commits of 13 August 2026 were made with one; it was removed before 1 October. |

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
  rest. On 15 October, after restoring the real dates, I re-created it once
  more (`f058109`): on the rebuilt `efb9338`, now `416c680`, with the tagger
  time of the original, 10 August 2026 at 07:43:32 UTC, which is also when my
  session log shows the `git tag` call. Its message is the original one plus a
  line saying it was re-created.
- **CI runs.** I deleted runs #1 to #7, from the pushes between 1 and 13
  October 2026. The first run left is #8.
- **Email.** The versions pushed on 1 October were committed under a personal
  email address, and those orphaned commits still show it. The restored
  history uses the GitHub noreply address throughout.
- **Contribution graph.** My profile's graph shows 106 commits in 2025 for this
  repo. There was no work on it in 2025: they are the backdated commits,
  counted once for every rewritten version. Only GitHub can rebuild the graph.
  With no commit on the default branch dated 2025 any more, I'll ask GitHub
  Support to recount it; until they do, it still shows them. Deleting or
  hiding these repos would also remove the evidence this file points at.
- **`Co-Authored-By`.** `57a5df7`, the first commit as recorded, was drafted by
  the assistant and has no `Co-Authored-By` line. Every commit after it that the
  assistant drafted has one. Before it, the nine commits of 13 August 2026 and
  `752a74b` were made with one; the restored history has all ten.

## Restoring the real dates

Until 15 October 2026 this file said the dates were invented, but the history
still carried them, and so did my contribution graph. So I rewrote the default
branch one last time, to make the history itself true rather than only the note
about it.

**Where the times come from.** My Claude Code session logs record every
`git commit` the assistant ran. Each commit's author date is now the time the
tool call that made it returned, to the second (git stores whole seconds).
Where several commits came from one call, they share its time. Where git
recorded the time itself because no date was forced (10 August and 1 October),
that time is kept; it falls inside the same call. The commit map below gives
the source of every date.

**Author date and committer date.** The author date is when the commit was
made. The committer date is when I rebuilt the history, so it is 15 October
2026 on every commit. `git log --format='%ad | %cd'` shows both.

**Nothing in the files changed.** Each commit was rebuilt with `git
commit-tree` on the tree of the commit it replaces, with its message byte for
byte:

1. the 90 commits of the version pushed here on 1 October (`752a74b`);
2. a bridge commit for each later force-push that changed files: 1 October
   11:58 and 13 October 09:25;
3. the 8 commits pushed on 13 October, as they were pushed that day;
4. the 9 commits from 14 October on, unchanged.

A bridge commit is dated at its force-push, is titled "history: what the
force-push of … changed", and has the tree that force-push left, so `git show`
on it shows exactly what the rewrite did to the files. The force-pushes of 13
October 17:06 and 14 October 08:37 left the files as they were and have no
bridge; what they changed in older commits is in [the table
above](#the-force-pushes).

The only messages that differ from the 1 October version are the nine of 13
August, which have their `Co-Authored-By` line back (next section). Author and
committer are `Gabriel S. <121440470+gabriel-fin-arch@users.noreply.github.com>`
throughout. The `v0.1.0` tag was re-created on the rebuilt commit (see [Other
changes](#other-changes)).

### Before 1 October

Three rewrites happened before I first pushed here, and this file didn't list
them until now:

- **5 August, 10:10 UTC.** `git reset --soft HEAD~2` undid two commits, "graph
  nodes: human_review (native interrupt) and finalize" and "wire the close
  pipeline into a LangGraph StateGraph". Their changes went into the commits
  after them; neither was published.
- **5 August, 19:03 UTC.** `git-filter-repo` removed `TASKS.md` from every
  commit. It also dropped the two commits that had only touched it,
  "checkpoint progress notes" and "update tasks after maintenance pass", and
  renamed the eight commit messages that mentioned it, for example "add TASKS
  and CHANGELOG" to "add changelog". The restored history keeps the renamed
  messages, which match their trees.
- **13 August, between 08:41 and 08:58 UTC.** The nine commits made that
  morning each had the line `Co-Authored-By: Claude Opus 4.8
  <noreply@anthropic.com>` and were on the earlier account. They were
  rewritten without it, keeping the same trees, authors and dates, and the
  rewritten copies were force-pushed over them at 08:57:59 UTC. My local copy
  still has the originals and that push in its reflog. The restored commits
  use the original messages.

### Commits without a session log

The nine commits of 13 August 2026 (`e14b670` to `0491ad8` in the 1 October
version) were made in a Claude Code session whose log I don't have. Their
author dates, 07:55:31 to 08:41:24 UTC, are the times git recorded. I've kept
them as first evidence rather than a logged time. What supports them:

- the second of them, "gitignore: keep local tooling and cache dirs out of the
  repo" (07:55:37), ignores `chat_history_*.md`, and the only such file in my
  copy was created at 07:44:18 UTC that day;
- the copies without the `Co-Authored-By` line were pushed at 08:57:59 UTC;
- the commits of 10 August were made without a forced date, as their session
  log shows;
- the nine dates are in order, and author date equals committer date on each.

### What the real dates show

69 commits on 5 August 2026, between 09:47 and 20:51 UTC, many of them minutes
or seconds apart; 3 on 6 August; 8 on 10 August; 9 on 13 August; and 1 on 1
October. The lockfile in "commit uv.lock" has packages published up to 09:36
UTC on 5 August, and that commit is now dated 09:49 the same day. The
`v0.1.0` tag is from 10 August, five days after the commit it marks.

### Commit map

<details>
<summary>Every commit: new SHA, its version pushed on 1 October, its version
in <code>main</code> until 15 October, author date and source (109
rows)</summary>

| New | 1 October | In `main` until 15 October | Author date (UTC) | Source |
|---|---|---|---|---|
| `a4e1088` | `f84313b` | `0d3efea` | 2026-08-05 09:47:49 | Claude Code session log, tool call at 09:47:49 UTC |
| `6a4efaf` | `590aac7` | `ff242c1` | 2026-08-05 09:47:56 | Claude Code session log, tool call at 09:47:56 UTC |
| `bdd8ed9` | `ac9550d` | `0f74d69` | 2026-08-05 09:47:59 | Claude Code session log, tool call at 09:47:59 UTC |
| `25cf638` | `eea622a` | `6479e49` | 2026-08-05 09:48:16 | Claude Code session log, tool call at 09:48:16 UTC |
| `df9b116` | `02b357f` | `f6da577` | 2026-08-05 09:48:29 | Claude Code session log, tool call at 09:48:29 UTC |
| `4daa3c0` | `0e90362` | `1676afe` | 2026-08-05 09:49:31 | Claude Code session log, tool call at 09:49:31 UTC (2 commits in one call) |
| `52e0170` | `e2d188f` | — | 2026-08-05 09:49:31 | Claude Code session log, tool call at 09:49:31 UTC (2 commits in one call) |
| `9c31227` | `b31aa11` | `68b788d` | 2026-08-05 09:51:02 | Claude Code session log, tool call at 09:51:02 UTC |
| `57f7fb6` | `01579d2` | `7427c25` | 2026-08-05 09:51:22 | Claude Code session log, tool call at 09:51:22 UTC |
| `719003f` | `2c3d7d3` | `43c2e23` | 2026-08-05 09:52:18 | Claude Code session log, tool call at 09:52:18 UTC |
| `42c36fa` | `a91f2af` | `725dd66` | 2026-08-05 09:52:21 | Claude Code session log, tool call at 09:52:21 UTC |
| `804f66d` | `f7818ea` | `0e43973` | 2026-08-05 09:52:42 | Claude Code session log, tool call at 09:52:42 UTC |
| `81d564e` | `9373ae9` | `d7b4179` | 2026-08-05 09:53:08 | Claude Code session log, tool call at 09:53:08 UTC |
| `bd95ebe` | `42c5653` | `87a1760` | 2026-08-05 09:53:32 | Claude Code session log, tool call at 09:53:32 UTC |
| `47f7688` | `64c4403` | `1d27b1d` | 2026-08-05 09:53:48 | Claude Code session log, tool call at 09:53:48 UTC |
| `b826b68` | `51953ca` | `39a0252` | 2026-08-05 09:56:04 | Claude Code session log, tool call at 09:56:04 UTC |
| `69d6809` | `efd70c0` | `af3ffd8` | 2026-08-05 09:56:29 | Claude Code session log, tool call at 09:56:29 UTC |
| `c706550` | `ff69f11` | `e8507c6` | 2026-08-05 09:57:11 | Claude Code session log, tool call at 09:57:11 UTC |
| `f1c7bce` | `67d0778` | `c0f0bb4` | 2026-08-05 09:58:09 | Claude Code session log, tool call at 09:58:09 UTC |
| `38bbe57` | `70448ba` | `3230cc0` | 2026-08-05 09:58:29 | Claude Code session log, tool call at 09:58:29 UTC |
| `795c1c2` | `2b6abb6` | `a756817` | 2026-08-05 09:59:00 | Claude Code session log, tool call at 09:59:00 UTC |
| `1e988be` | `aa62701` | `ade3bc2` | 2026-08-05 09:59:13 | Claude Code session log, tool call at 09:59:13 UTC |
| `47e5f97` | `8a34fda` | `74bd159` | 2026-08-05 10:00:00 | Claude Code session log, tool call at 10:00:00 UTC |
| `81edd82` | `2c8584c` | `b8a5f94` | 2026-08-05 10:00:15 | Claude Code session log, tool call at 10:00:15 UTC |
| `66cb3e6` | `de64634` | `bd893c0` | 2026-08-05 10:00:38 | Claude Code session log, tool call at 10:00:38 UTC |
| `8491cf0` | `a666f1e` | `a58a480` | 2026-08-05 10:00:49 | Claude Code session log, tool call at 10:00:49 UTC |
| `360ccbb` | `e691cf1` | `22dd17d` | 2026-08-05 10:04:18 | Claude Code session log, tool call at 10:04:18 UTC |
| `6879b25` | `1d0df74` | `6949e8d` | 2026-08-05 10:04:51 | Claude Code session log, tool call at 10:04:51 UTC |
| `9bb3b8f` | `f916746` | `0aa8b54` | 2026-08-05 10:05:56 | Claude Code session log, tool call at 10:05:56 UTC |
| `06124d1` | `635cb49` | `d45e1c5` | 2026-08-05 10:06:35 | Claude Code session log, tool call at 10:06:35 UTC |
| `732cec4` | `5144ca3` | `decf7b6` | 2026-08-05 10:06:46 | Claude Code session log, tool call at 10:06:46 UTC |
| `4f04b6c` | `b885cd5` | `9fcbec5` | 2026-08-05 10:07:05 | Claude Code session log, tool call at 10:07:05 UTC |
| `ce4df76` | `7e0183f` | `879d9b5` | 2026-08-05 10:10:41 | Claude Code session log, tool call at 10:10:41 UTC |
| `c3adc05` | `0175ab5` | `1f9ab89` | 2026-08-05 10:11:00 | Claude Code session log, tool call at 10:11:00 UTC |
| `815297b` | `860306a` | `72d4cee` | 2026-08-05 10:11:12 | Claude Code session log, tool call at 10:11:12 UTC |
| `da4e6e1` | `f2e3961` | `36997ae` | 2026-08-05 10:12:41 | Claude Code session log, tool call at 10:12:41 UTC |
| `1f91d29` | `cf49549` | `3267290` | 2026-08-05 10:13:02 | Claude Code session log, tool call at 10:13:02 UTC |
| `f57127a` | `1a44c08` | `abaa93a` | 2026-08-05 10:14:32 | Claude Code session log, tool call at 10:14:32 UTC |
| `b518272` | `d57d3b3` | `6fd500c` | 2026-08-05 10:15:18 | Claude Code session log, tool call at 10:15:18 UTC |
| `6f6fbbe` | `dd65560` | `b31e0cf` | 2026-08-05 18:16:09 | Claude Code session log, tool call at 18:16:09 UTC |
| `5472b0e` | `adaebbf` | `160cb37` | 2026-08-05 18:16:42 | Claude Code session log, tool call at 18:16:42 UTC |
| `9ee3894` | `2956c8b` | `77856db` | 2026-08-05 18:18:20 | Claude Code session log, tool call at 18:18:20 UTC |
| `29f5932` | `68d8ba4` | `b5a9edf` | 2026-08-05 18:18:37 | Claude Code session log, tool call at 18:18:37 UTC |
| `2cc76bb` | `fca2e5a` | `ae92599` | 2026-08-05 18:18:50 | Claude Code session log, tool call at 18:18:50 UTC |
| `88ab721` | `ece766b` | `a0b2d17` | 2026-08-05 18:19:35 | Claude Code session log, tool call at 18:19:35 UTC |
| `edef2cb` | `2c9bc69` | `764e5a1` | 2026-08-05 18:20:08 | Claude Code session log, tool call at 18:20:08 UTC |
| `b7f9ba4` | `23a1bac` | `b4e1eaa` | 2026-08-05 18:20:42 | Claude Code session log, tool call at 18:20:42 UTC |
| `9409036` | `969e658` | `c007c7e` | 2026-08-05 18:21:04 | Claude Code session log, tool call at 18:21:04 UTC |
| `e1196be` | `2c038f3` | `8cd0d6a` | 2026-08-05 18:21:32 | Claude Code session log, tool call at 18:21:32 UTC |
| `747df70` | `7248faf` | `fc54d4b` | 2026-08-05 18:21:52 | Claude Code session log, tool call at 18:21:52 UTC |
| `a013654` | `1520353` | `1d6c4a4` | 2026-08-05 18:22:25 | Claude Code session log, tool call at 18:22:25 UTC |
| `62af3e3` | `3cc4573` | `f394e7b` | 2026-08-05 18:23:27 | Claude Code session log, tool call at 18:23:27 UTC |
| `e2c1569` | `0e18585` | `242eabf` | 2026-08-05 18:23:31 | Claude Code session log, tool call at 18:23:31 UTC |
| `68cc761` | `adcdc2b` | `f6c6592` | 2026-08-05 18:23:47 | Claude Code session log, tool call at 18:23:47 UTC |
| `416c680` | `efb9338` | `9565587` | 2026-08-05 18:23:57 | Claude Code session log, tool call at 18:23:57 UTC |
| `57acc57` | `e214157` | `f13095a` | 2026-08-05 18:24:18 | Claude Code session log, tool call at 18:24:18 UTC |
| `ce9857c` | `129595e` | `2cc5061` | 2026-08-05 18:24:28 | Claude Code session log, tool call at 18:24:28 UTC |
| `7faa289` | `414886e` | `9673364` | 2026-08-05 19:07:47 | Claude Code session log, tool call at 19:07:47 UTC |
| `ea860a0` | `f177c14` | `8e090f2` | 2026-08-05 19:09:24 | Claude Code session log, tool call at 19:09:24 UTC |
| `f83987e` | `ae043cc` | `6d8a4a1` | 2026-08-05 19:11:44 | Claude Code session log, tool call at 19:11:44 UTC |
| `b4c7240` | `71fe72c` | `03cd532` | 2026-08-05 19:12:36 | Claude Code session log, tool call at 19:12:36 UTC |
| `872c99e` | `24cbfa9` | `f9fe7d6` | 2026-08-05 19:14:47 | Claude Code session log, tool call at 19:14:47 UTC |
| `ead9633` | `177405e` | `c3230f6` | 2026-08-05 19:31:32 | Claude Code session log, tool call at 19:31:32 UTC |
| `c5cf045` | `cf68ea8` | `d0969a3` | 2026-08-05 20:21:41 | Claude Code session log, tool call at 20:21:41 UTC |
| `8c5156d` | `d50b514` | `9803dd6` | 2026-08-05 20:23:57 | Claude Code session log, tool call at 20:23:57 UTC |
| `920496d` | `e5b416d` | `5559f6d` | 2026-08-05 20:25:57 | Claude Code session log, tool call at 20:25:57 UTC |
| `617f943` | `d2078aa` | `e5d2937` | 2026-08-05 20:29:18 | Claude Code session log, tool call at 20:29:18 UTC |
| `55815c3` | `0c1f7b6` | `9844267` | 2026-08-05 20:36:22 | Claude Code session log, tool call at 20:36:22 UTC |
| `91df3aa` | `abf2c34` | `0f10d4a` | 2026-08-05 20:51:29 | Claude Code session log, tool call at 20:51:29 UTC |
| `3d8ca30` | `70f812c` | `6afee27` | 2026-08-06 08:11:35 | Claude Code session log, tool call at 08:11:35 UTC |
| `152a46a` | `94fdbb1` | `b8c5a47` | 2026-08-06 08:14:36 | Claude Code session log, tool call at 08:14:36 UTC |
| `feb1256` | `147bdc4` | `08bd27b` | 2026-08-06 08:18:45 | Claude Code session log, tool call at 08:18:45 UTC |
| `61ec3e5` | `b561c99` | `e43b5a1` | 2026-08-10 08:08:53 | git's own timestamp; Claude Code session log, tool call at 08:08:53 UTC |
| `e451773` | `01c81d8` | `bb8a40a` | 2026-08-10 08:09:10 | git's own timestamp; Claude Code session log, tool call at 08:09:10 UTC |
| `896ab17` | `9bd681e` | `8b38b8e` | 2026-08-10 08:09:26 | git's own timestamp; Claude Code session log, tool call at 08:09:26 UTC |
| `cdce0b2` | `774e7fc` | `4655367` | 2026-08-10 08:09:42 | git's own timestamp; Claude Code session log, tool call at 08:09:42 UTC |
| `d239e6f` | `0eb9367` | `b3f910e` | 2026-08-10 08:28:29 | git's own timestamp; Claude Code session log, tool call at 08:28:30 UTC |
| `76a7468` | `57214cd` | `062cc36` | 2026-08-10 08:28:36 | git's own timestamp; Claude Code session log, tool call at 08:28:36 UTC |
| `b3a9ebc` | `946f719` | `5765ecd` | 2026-08-10 08:28:45 | git's own timestamp; Claude Code session log, tool call at 08:28:46 UTC |
| `3e3ea64` | `7b5f43f` | `bf7b4e5` | 2026-08-10 08:33:34 | git's own timestamp; Claude Code session log, tool call at 08:33:34 UTC |
| `c69434c` | `e14b670` | `4c25abd` | 2026-08-13 07:55:31 | no session log; git's own timestamp, first evidence (see above) |
| `43c016a` | `4535502` | `06bf1d0` | 2026-08-13 07:55:37 | no session log; git's own timestamp, first evidence (see above) |
| `3492132` | `f512136` | `536bff4` | 2026-08-13 07:57:21 | no session log; git's own timestamp, first evidence (see above) |
| `280627f` | `e899a36` | `782f7a7` | 2026-08-13 07:59:05 | no session log; git's own timestamp, first evidence (see above) |
| `25f8a69` | `51aa948` | `14f292f` | 2026-08-13 08:02:22 | no session log; git's own timestamp, first evidence (see above) |
| `22d2aca` | `1c87072` | `0210859` | 2026-08-13 08:25:31 | no session log; git's own timestamp, first evidence (see above) |
| `409020f` | `9455396` | `17b409d` | 2026-08-13 08:27:58 | no session log; git's own timestamp, first evidence (see above) |
| `bb27c7c` | `71b7473` | `b44b2e5` | 2026-08-13 08:29:05 | no session log; git's own timestamp, first evidence (see above) |
| `b1b9500` | `0491ad8` | `fde7e07` | 2026-08-13 08:41:24 | no session log; git's own timestamp, first evidence (see above) |
| `b5d3a02` | `752a74b` | — | 2026-10-01 09:52:09 | git's own timestamp; Claude Code session log, tool call at 09:52:12 UTC |
| `95b056a` | — | — | 2026-10-01 11:58:24 | bridge: Activity, force-push at 11:58:24 UTC leaving `40a9498` |
| `3870a8a` | — | — | 2026-10-13 09:25:49 | bridge: Activity, force-push at 09:25:49 UTC leaving `48970a5` |
| `df4a49e` | — | `e39adc6` | 2026-10-13 11:30:57 | unchanged; content and message as pushed on 13 October (`67ed737`) |
| `581fb1a` | — | `d4c5eed` | 2026-10-13 11:33:06 | unchanged; content and message as pushed on 13 October (`e1c8c91`) |
| `643a743` | — | `2fbd51b` | 2026-10-13 11:35:55 | unchanged; content and message as pushed on 13 October (`342e2ab`) |
| `82166b3` | — | `9f2fafe` | 2026-10-13 11:37:32 | unchanged; content and message as pushed on 13 October (`63c222f`) |
| `c4b0995` | — | `40e9e03` | 2026-10-13 11:39:14 | unchanged; content and message as pushed on 13 October (`4b70f9e`) |
| `ed8e2d7` | — | `91d7c77` | 2026-10-13 11:39:31 | unchanged; content and message as pushed on 13 October (`da4e0f0`) |
| `b1768f5` | — | `6cea8df` | 2026-10-13 11:43:19 | unchanged; content and message as pushed on 13 October (`878fa7f`) |
| `4929061` | — | `ab7bf63` | 2026-10-13 11:58:12 | unchanged; content and message as pushed on 13 October (`5215eda`) |
| `2bf52f3` | — | `57a5df7` | 2026-10-14 10:08:41 | unchanged |
| `e7a17ac` | — | `c15a26f` | 2026-10-14 13:08:18 | unchanged |
| `4c4bc76` | — | `e2f15bf` | 2026-10-14 14:26:40 | unchanged |
| `70f0885` | — | `7d0a171` | 2026-10-14 14:30:38 | unchanged |
| `ad42501` | — | `b9204d5` | 2026-10-15 07:05:43 | unchanged |
| `aa367c6` | — | `c36249d` | 2026-10-15 07:56:03 | unchanged |
| `19989db` | — | `1147eaf` | 2026-10-15 08:20:48 | unchanged |
| `ba1e851` | — | `1e45d51` | 2026-10-15 12:25:24 | unchanged |
| `393627b` | — | `6e9001c` | 2026-10-15 12:46:38 | unchanged |

</details>

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

The restoration of 15 October, from a clone. `393627b`, `b5d3a02` and the two
bridges are rebuilt commits; the other SHAs are from before it and need
fetching first:

```bash
git fetch origin 6e9001c84c5153e7d79105118f6b2d1e51d199af \
  752a74b67bdca0bbc29e05ea1f5e66a394689b7e \
  40a94985077a36353ed9740bb0fca357ccbdd975 48970a574bd9fee89458fb177d3dd2d2848ab3c7

# no file changed: the last commit before the restoration and the last rebuilt
# one have the same tree (prints nothing)
git diff 6e9001c 393627b

# the 90 commits pushed on 1 October: same trees and subjects, in order (prints nothing)
diff <(git log --reverse --format='%T %s' 752a74b) <(git log --reverse --format='%T %s' b5d3a02)

# same messages, apart from the nine Co-Authored-By lines of 13 August (prints only those)
diff <(git log --reverse --format=%B 752a74b) <(git log --reverse --format=%B b5d3a02)

# each bridge has the tree its force-push left (two pairs of equal lines)
git rev-parse 95b056a^{tree} 40a9498^{tree} 3870a8a^{tree} 48970a5^{tree}

# when each commit was made, and when the history was rebuilt
git log --reverse --format='%h %ad | %cd | %s' --date=iso main
```

## From here on

No force-pushes, no deleted CI runs, no re-created tags. The restoration of 15
October 2026 was the one exception, made only to put the real dates back, and
there won't be another. New commits carry their real dates, and a
`Co-Authored-By` line when the assistant wrote them.
