# Exporting the elimination journal

A finalized close writes the entries it booked as two journal files, in the
evidence pack (`evidence.py`), from `run` when the close finalizes without
review, and as downloads on the dashboard after the reviewer submits. Both
are built in `journal.py` from the run's eliminations and nothing else: an
item rejected, left without a decision, or approved by the preparer was never
booked, so it isn't in them. Tests check that every voucher balances, that
the file reads back to the run's totals, and that those items are absent.

Neither file has been imported into a live system. The Dynamics 365 layout
is built from Microsoft's published description of the General journal data
entity (listed at the end), read on 19 October 2026.

## `journal.csv`: one row per journal line

| Column | What it holds |
|---|---|
| `journal` | One journal per run, `IC-ELIM-<year>-<month>` |
| `voucher` | One voucher per elimination, `ELIM-0001` onwards |
| `line` | Line number across the journal |
| `posting_date` | The end of the month the close is for |
| `entity` | The legal entity the line belongs to |
| `account` | The group account, after the chart-of-accounts mapping in `ingest/loaders.py` |
| `debit`, `credit` | One of the two, to two decimals |
| `currency` | The group reporting currency |
| `reference` | The intercompany reference being eliminated |
| `description` | The elimination's narrative, including who approved it |

The posting date is the end of the month most ledger lines fall in, the later
month on a tie. It is not the month of the latest line: a timing gap is a leg
booked after the cutoff, so a September close usually has an October line in
it. `generic_csv` and `d365_csv` take an explicit `posting_date` where a group
needs a different one.

## `journal_d365.csv`: Dynamics 365 Finance, General journal entity

For import through Data management with the **General journal** entity
(`LedgerJournalEntity`). Columns, in the order Microsoft lists them:

| Column | Value written | Note |
|---|---|---|
| `JOURNALBATCHNUMBER` | `IC-ELIM-<year>-<month>` | A placeholder; the entity allows one, to be replaced from the number sequence on import |
| `LINENUMBER` | 1 onwards | Required |
| `JOURNALNAME` | `ICElim` | Header value, the same on every row |
| `DESCRIPTION` | `Intercompany eliminations <month> <year>` | Header value, the same on every row |
| `ACCOUNTTYPE` | `Ledger` | Every line is a ledger line |
| `ACCOUNTDISPLAYVALUE` | `<main account>-<entity>` | See the assumptions below |
| `TRANSDATE` | The posting date, `YYYY-MM-DD` | Required; the same for every line of a voucher |
| `VOUCHER` | `ELIM-0001` onwards | Required; a placeholder, replaced on posting. Two lines each, under the ten Microsoft recommends |
| `TEXT` | `IC elimination <reference>` | Kept to 60 characters; the full narrative is in `journal.csv` |
| `CURRENCYCODE` | The group reporting currency | Required |
| `DEBITAMOUNT`, `CREDITAMOUNT` | One of the two, to two decimals | |

### What it assumes

- **One legal entity.** Microsoft states that this entity doesn't support
  intercompany transactions. The journal is meant for the one legal entity the
  group eliminates in, a consolidation or elimination company, and every line
  goes there.
- **The entity as a dimension.** Each line's legal entity is carried as the
  second segment of `ACCOUNTDISPLAYVALUE`, which assumes a ledger dimension
  format for integrating applications of main account, then a dimension that
  holds the entity code. A group with another format reorders the segments.
- **Main accounts.** The main account is the group account code as the tool
  holds it (`IC_RECEIVABLE`, `IC_PAYABLE`). `d365_csv` takes a mapping to the
  target's main account numbers; without one, the codes go through as they are
  and have to be mapped before import.
- **The journal name exists.** `ICElim` has to exist as a journal name in the
  target legal entity. It supplies the header defaults the file leaves out, the
  posting layer among them.
- **Number sequences.** Batch numbers and vouchers are placeholders, so the
  target's number sequences must be set to replace them, not to manual.
- **Dates.** `TRANSDATE` is written as `YYYY-MM-DD`; the CSV source data
  format in Data management has to read that format.
- **Currency.** Amounts are in the group reporting currency. The run refuses
  to write a journal for a group with more than one.

### What it leaves for whoever imports it

The main account mapping, the dimension format, the journal name and its
posting layer, the number sequences, and the decision to post. The file is a
journal to review in the target system, not a posting.

## A group that consolidates in a dedicated tool

A group that consolidates in a dedicated consolidation tool, Lucanet for
example, books its eliminations there rather than in an ERP: Lucanet runs its
own debt, income and expense consolidation from the intercompany data it is
given, and takes further adjustments as postings in its journals. Lucanet's
public documentation describes those journals but not a field-level format for
importing postings, which is set up per installation, so there is no Lucanet
file here. The generic `journal.csv` holds what such a posting needs: entity,
account, debit or credit, reference and description.

## Sources

- [General journal entity](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-general-journal), Microsoft Learn
- [LedgerJournalHeader entity](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-general-journal-ledgerjournalheader), Microsoft Learn
- [Postings in Journals](https://support.lucanet.com/en/documentation/consolidation-financial-planning/imports-journals/journale/postings-journals) and [Import and Journals](https://support.lucanet.com/en/documentation/consolidation-financial-planning/imports-journals/), Lucanet documentation
