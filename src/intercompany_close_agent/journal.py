"""The close's elimination entries as journal import files.

Two files, written from the eliminations a finalized close booked and from
nothing else. An item that was rejected, left undecided, or approved by the
preparer was never booked, so it isn't in them.

  journal.csv       generic: one row per journal line
  journal_d365.csv  the same entries laid out for the General journal data
                    entity of Microsoft Dynamics 365 Finance, imported
                    through Data management

docs/journal-export.md gives the columns, the assumptions behind the
Dynamics 365 file and what it leaves for whoever imports it. Neither file has
been imported into a live system. The Dynamics 365 layout is built from
Microsoft's published description of the entity, which says it doesn't
support intercompany transactions: the whole journal goes to one legal
entity, the one the group eliminates in, with the entity each line belongs to
carried as a financial dimension.
"""

from __future__ import annotations

import calendar
import csv
import io
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from intercompany_close_agent.models.elimination import Elimination, JournalLineType

GENERIC_COLUMNS = (
    "journal",
    "voucher",
    "line",
    "posting_date",
    "entity",
    "account",
    "debit",
    "credit",
    "currency",
    "reference",
    "description",
)

# The General journal entity's fields, in the order Microsoft lists them,
# limited to the ones a ledger-to-ledger elimination needs.
D365_COLUMNS = (
    "JOURNALBATCHNUMBER",
    "LINENUMBER",
    "JOURNALNAME",
    "DESCRIPTION",
    "ACCOUNTTYPE",
    "ACCOUNTDISPLAYVALUE",
    "TRANSDATE",
    "VOUCHER",
    "TEXT",
    "CURRENCYCODE",
    "DEBITAMOUNT",
    "CREDITAMOUNT",
)

# A journal name that has to exist in the target legal entity. The journal
# name supplies the header defaults the file leaves out, the posting layer
# among them.
D365_JOURNAL_NAME = "ICElim"
# Kept short, since the line text is a short field in the ledger; the full
# narrative is in the generic file.
D365_TEXT_LENGTH = 60

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class JournalRow:
    voucher: str
    line: int
    entity: str
    account: str
    debit: Decimal
    credit: Decimal
    reference: str
    description: str


def period_end(transaction_dates: list[date]) -> date:
    """The last day of the month the close is for, which is the date it posts at.

    That month is the one most legs fall in, the latest on a tie. Not the
    month of the latest leg: a timing gap is a leg booked after the cutoff,
    so in a September close the latest leg is often in October.
    """
    if not transaction_dates:
        raise ValueError("a journal needs a posting date, and the run has no transactions to take it from")
    months = Counter((day.year, day.month) for day in transaction_dates)
    year, month = max(months, key=lambda key: (months[key], key))
    return date(year, month, calendar.monthrange(year, month)[1])


def journal_id(posting_date: date) -> str:
    return f"IC-ELIM-{posting_date:%Y-%m}"


def journal_rows(eliminations: list[Elimination]) -> list[JournalRow]:
    """One row per journal line, one voucher per elimination, numbered in order."""
    rows: list[JournalRow] = []
    line = 0
    for number, elimination in enumerate(eliminations, start=1):
        voucher = f"ELIM-{number:04d}"
        for entry in elimination.lines:
            line += 1
            amount = entry.amount.quantize(ZERO)
            debit = amount if entry.line_type is JournalLineType.DEBIT else ZERO
            credit = amount if entry.line_type is JournalLineType.CREDIT else ZERO
            rows.append(
                JournalRow(
                    voucher=voucher,
                    line=line,
                    entity=entry.entity_code,
                    account=entry.account_code,
                    debit=debit,
                    credit=credit,
                    reference=elimination.reference,
                    description=elimination.narrative,
                )
            )
    return rows


def _reporting_currency(state: dict) -> str:
    currencies = {entity.reporting_currency for entity in state.get("entities", [])}
    if len(currencies) != 1:
        raise ValueError(f"one reporting currency is needed for the journal, found {sorted(currencies) or 'none'}")
    return currencies.pop()


def _posting_date(state: dict, posting_date: date | None) -> date:
    return posting_date or period_end([txn.transaction_date for txn in state.get("ic_transactions", [])])


def _csv(columns: tuple[str, ...], rows: list[list[object]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return out.getvalue()


def generic_csv(state: dict, posting_date: date | None = None) -> str:
    """The finalized run's eliminations as one CSV row per journal line.

    posting_date defaults to the end of the month the close is for (period_end).
    """
    posting_date = _posting_date(state, posting_date)
    currency = _reporting_currency(state)
    return _csv(
        GENERIC_COLUMNS,
        [
            [
                journal_id(posting_date),
                row.voucher,
                row.line,
                posting_date.isoformat(),
                row.entity,
                row.account,
                row.debit,
                row.credit,
                currency,
                row.reference,
                row.description,
            ]
            for row in journal_rows(state["eliminations"])
        ],
    )


def d365_csv(
    state: dict,
    main_accounts: Mapping[str, str] | None = None,
    journal_name: str = D365_JOURNAL_NAME,
    posting_date: date | None = None,
) -> str:
    """The same entries for the Dynamics 365 Finance General journal entity.

    ACCOUNTDISPLAYVALUE is the main account, then the line's entity as a
    dimension segment ("IC_PAYABLE-US01"), which assumes a ledger dimension
    format for integrating applications of that shape. main_accounts maps
    the group account codes to the main accounts the target uses; a code it
    doesn't map goes through as it is. JOURNALBATCHNUMBER and VOUCHER are
    placeholders, for the number sequences to replace on import and on
    posting.
    """
    mapping = dict(main_accounts or {})
    posting_date = _posting_date(state, posting_date)
    currency = _reporting_currency(state)
    batch = journal_id(posting_date)
    description = f"Intercompany eliminations {posting_date:%B %Y}"
    return _csv(
        D365_COLUMNS,
        [
            [
                batch,
                row.line,
                journal_name,
                description,
                "Ledger",
                f"{mapping.get(row.account, row.account)}-{row.entity}",
                posting_date.isoformat(),
                row.voucher,
                f"IC elimination {row.reference}"[:D365_TEXT_LENGTH],
                currency,
                row.debit,
                row.credit,
            ]
            for row in journal_rows(state["eliminations"])
        ],
    )
