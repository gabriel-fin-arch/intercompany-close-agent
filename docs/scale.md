# A close at the size of a real group

The committed sample has 7 entities and 53 IC ledger lines, which shows every
exception type but says nothing about a group of the size this is meant for.
`scale-run` generates one, closes it offline and times each step:

```
uv run python -m intercompany_close_agent.cli scale-run
```

What it printed on 18 October 2026:

```
Group: 60 entities, 1,500 balances, 3,005 IC ledger lines (seed 14, anomaly rate 0.05)
Found: 1,440 clean pairs, 76 exceptions, 68 for review; entities not tying out: 1 of 60
Booked: 1,448 eliminations, with every item on the worklist rejected
Time: load 0.05 s, to the worklist 0.14 s, finalize 0.15 s
Machine: Windows-10-10.0.19045-SP0, Intel64 Family 6 Model 140 Stepping 1, GenuineIntel, 8 CPUs, Python 3.11.15
Offline: rule-based triage, no API calls.
```

What the lines mean:

- **Group.** The sample's seven entities, with ZA01 still the one loaded by
  hand, plus 53 generated interfaced ones (FR01, NL01, and so on). 1,500
  balances make 3,005 ledger lines: two legs each, and a few more or fewer
  where an anomaly adds or drops one. 5% of balances are broken on purpose;
  the sample breaks 35%, so that 26 balances show every exception type.
- **Found.** Matching, the control-account tie-out and triage, the same
  code as any other run.
- **Booked.** The run rejects every item on the worklist so it can finalize
  without a reviewer. The 1,448 eliminations are the 1,440 clean pairs and
  the 8 exceptions triage auto-resolved.
- **Time.** Wall-clock, from `time.perf_counter`, on the machine in the next
  line. Load is reading and checking the three CSVs; "to the worklist" is
  matching, tie-out and triage; finalize is booking the entries.

The first three lines follow from the seed. `tests/test_scale.py` runs the
same command in CI and fails if they differ from the ones above. The times
aren't checked anywhere and aren't quoted in the README: they're one run on
one machine.

## What it doesn't measure

- **Live triage.** Each of the 68 items for review would be a model call,
  and the time would mostly be the network's. `scale-run` always runs
  offline, whatever the environment holds.
- **The dashboard.** Rendering a 68-item worklist in Streamlit is a
  different question from closing 3,005 lines.
- **A pause between processes.** The paused run is held in memory
  (`MemorySaver`); a persistent checkpointer would add its own cost.
