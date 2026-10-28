# The business case, from the desk that would run it

I run the consolidation of a group of about 50 legal entities. This page
says what the close looks like from my chair, what this project would
change, what it would not, and what it would take to run it for real.
Figures are mine, rounded, and deliberately anonymous.

## The problem today

The close runs from WD-3 to WD+7/8 — about two working weeks door to
door. I work normal 8-hour days the rest of the month; across the close
I put in roughly 10–15 extra hours. My part: I run the group
consolidation, chase the intercompany differences with the entities, and
support the matching alongside the external audit firm's tooling. I do
not investigate every break myself — the regional controllers clear
their own differences — and the disputes that do not close at entity
level escalate to the Senior Director of Consolidation, who is also the
person who reviews and approves my SOX controls.

Intercompany is the part of that calendar that never behaves. Every
house books its own side, in its own words, on its own timeline; the
close then spends days finding out that two entities recorded the same
operation under different references, or that one side never booked
the mirror leg. On the sample data in this repo the same story fits in
seven entities and 53 legs: one entity does not tie out and the
exception list has eighteen items. Scale that to fifty entities and
the list is the close.

## What the tool would change

The matching and the tie-out would run before WD-3, not during it. I
would start the close week from a worklist with a reason on each item —
the way `demo` produces one here — instead of building that list by
hand while the calendar burns.

The saving I can defend honestly is the calendar, not a spreadsheet of
hours. If clearing the matching off the critical path moves the close
even one working day earlier at ~50 entities, that is about two and a
half working weeks a year on a monthly close — before counting the
10–15 extra hours, the audit-firm hours, or the disputes that age a
whole close because nobody chased them at WD+2.

The bigger prize is earlier: a break found at WD-3 costs an email; the
same break found at WD+5 costs a reopen.

## What it doesn't solve

It does not decide anything. A missing mirror leg does not say whose
booking is wrong; a counterparty mismatch does not say which house
mapped the counterparty incorrectly. Those calls stay with the
regional controllers, and the escalations stay with the Senior
Director. The tool shortens the chase; it does not replace the
judgment at the end of it. And if an entity keys its data in by hand,
the tool will find the breaks the keying creates — it will not make the
keying better.

## What it would take to run it in a real close

- **Data:** an intercompany subledger and a trial-balance extract per
  entity, on a fixed format, delivered by WD-3. No format, no matching.
- **Access:** read access to those extracts for the machine; no
  write-back to anything without a human sign-off.
- **Controls:** the same preparer/approver split I already work under —
  the tool prepares, I verify (my `recalc/ic_recalc.sql` is that
  verification, done by hand), the Senior Director approves. An
  independent recalculation is a control a SOX reviewer already
  understands.
- **Ownership:** me as preparer, the Senior Director as approver, the
  audit firm reading the same exception list instead of building one.
