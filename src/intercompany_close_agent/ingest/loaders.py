"""Loaders for trial balance and intercompany ledger data.

Reads the CSV feeds a real close would pull from a consolidation tool
(Lucanet, Oracle EPM, or similar), and normalizes local GL account codes
onto the group's standard chart of accounts before anything downstream sees
them.
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from intercompany_close_agent.models.ledger import ICTransaction, TrialBalanceLine

# A handful of local-system account codes mapped onto the group's standard
# chart of accounts. Real mappings run into the thousands of lines and live
# inside the consolidation tool itself; this is a stand-in sized for the
# synthetic dataset this project ships with.
COA_MAPPING: dict[str, str] = {
    "1000-IC-REC": "IC_RECEIVABLE",
    "2000-IC-PAY": "IC_PAYABLE",
    "1100-CASH": "CASH",
    "3000-EQ": "RETAINED_EARNINGS",
    "4000-REV": "REVENUE",
    "5000-COGS": "COGS",
    "6000-OPEX": "OPEX",
}


def map_account_code(local_code: str) -> str:
    """Map a local GL account code onto the group standard chart of accounts.

    Falls back to the local code itself when there's no mapping entry --
    an unmapped account should surface downstream as an oddity, not vanish
    silently into the wrong bucket.
    """
    return COA_MAPPING.get(local_code, local_code)


def load_trial_balance(path: Path) -> list[TrialBalanceLine]:
    """Load and COA-map a trial balance CSV."""
    lines: list[TrialBalanceLine] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            lines.append(
                TrialBalanceLine(
                    entity_code=row["entity_code"],
                    account_code=map_account_code(row["account_code"]),
                    account_name=row["account_name"],
                    balance=_parse_decimal(row["balance"]),
                )
            )
    return lines


def load_ic_transactions(path: Path) -> list[ICTransaction]:
    """Load the intercompany ledger CSV into individual transaction legs."""
    transactions: list[ICTransaction] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            transactions.append(
                ICTransaction(
                    entity_code=row["entity_code"],
                    counterparty_code=row["counterparty_code"],
                    reference=row["reference"],
                    amount=_parse_decimal(row["amount"]),
                    currency=row.get("currency") or "USD",
                    transaction_date=row["transaction_date"],
                    description=row.get("description") or "",
                )
            )
    return transactions


def _parse_decimal(raw: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"could not parse amount: {raw!r}") from exc
