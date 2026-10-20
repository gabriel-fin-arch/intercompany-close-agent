<!-- One PR per issue. Fill in every section; "nothing" is a valid answer. -->

Closes #

## What the issue asked

<!-- The acceptance criteria, in a line or two. -->

## What the assistant drafted

<!-- What Claude Code wrote here (code, tests, docs, this description) and with
which model. -->

## What I changed or rejected in review

<!-- What I decided, rewrote, sent back or turned down, and why. Filled in by me
when I review. -->

## How it was verified

- [ ] `uv run ruff check .`
- [ ] `uv run pytest -q` with `ANTHROPIC_API_KEY` empty
- [ ] The offline pipeline still runs (`generate-data`, then `run`) and leaves
      no tracked file changed
- [ ] CI green on this PR, in both jobs (`test` and `lowest-versions`)
- [ ] Every number or claim in the changed text checked against the output it
      comes from
