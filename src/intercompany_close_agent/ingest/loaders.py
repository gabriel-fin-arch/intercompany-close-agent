"""Loaders for trial balance and intercompany ledger data.

Reads the CSV feeds a real close would pull from a consolidation tool
(Lucanet, Oracle EPM, or similar), and normalizes local GL account codes
onto the group's standard chart of accounts before anything downstream sees
them.

Anything wrong with a file is raised as a DataLoadError naming the file, and
the line where there is one. These feeds come from outside the pipeline, and
"KeyError: 'amount'" tells whoever is running the close nothing about which
of the three files to go and fix.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import ValidationError

from intercompany_close_agent.models.entity import Entity
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

ENTITY_COLUMNS = {"code", "name", "region", "local_currency"}
TRIAL_BALANCE_COLUMNS = {"entity_code", "account_code", "account_name", "balance"}
IC_LEDGER_COLUMNS = {"entity_code", "counterparty_code", "reference", "amount", "transaction_date"}


class DataLoadError(ValueError):
    """An input file that can't be used, described well enough to go and fix it."""


def map_account_code(local_code: str) -> str:
    """Map a local GL account code onto the group standard chart of accounts.

    Falls back to the local code itself when there's no mapping entry --
    an unmapped account should surface downstream as an oddity, not vanish
    silently into the wrong bucket.
    """
    return COA_MAPPING.get(local_code, local_code)


def _rows(path: Path, required: set[str]) -> Iterator[tuple[int, dict[str, str]]]:
    """(line number, row) for every data row, after checking the file is usable at all."""
    if not path.is_file():
        raise DataLoadError(f"{path} not found")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise DataLoadError(f"{path.name} is empty, not even a header row")
        missing = required - set(reader.fieldnames)
        if missing:
            raise DataLoadError(f"{path.name} is missing column(s): {', '.join(sorted(missing))}")
        for row in reader:
            yield reader.line_num, row


def _bad_row(path: Path, line: int, exc: ValueError) -> DataLoadError:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or "row"
        reason = f"{field}: {first['msg']}"
    else:
        reason = str(exc)
    return DataLoadError(f"{path.name} line {line}: {reason}")


def load_entities(path: Path) -> list[Entity]:
    """Load the legal entity master data."""
    entities: list[Entity] = []
    for line, row in _rows(path, ENTITY_COLUMNS):
        try:
            entities.append(Entity(**row))
        except ValueError as exc:
            raise _bad_row(path, line, exc) from exc
    return entities


def load_trial_balance(path: Path) -> list[TrialBalanceLine]:
    """Load and COA-map a trial balance CSV."""
    lines: list[TrialBalanceLine] = []
    for line, row in _rows(path, TRIAL_BALANCE_COLUMNS):
        try:
            lines.append(
                TrialBalanceLine(
                    entity_code=row["entity_code"],
                    account_code=map_account_code(row["account_code"]),
                    account_name=row["account_name"],
                    balance=_parse_decimal(row["balance"]),
                )
            )
        except ValueError as exc:
            raise _bad_row(path, line, exc) from exc
    return lines


def load_ic_transactions(path: Path) -> list[ICTransaction]:
    """Load the intercompany ledger CSV into individual transaction legs."""
    transactions: list[ICTransaction] = []
    for line, row in _rows(path, IC_LEDGER_COLUMNS):
        try:
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
        except ValueError as exc:
            raise _bad_row(path, line, exc) from exc
    return transactions


def load_dataset(data_dir: Path) -> tuple[list[Entity], list[TrialBalanceLine], list[ICTransaction]]:
    """All three feeds, checked against each other before anything runs on them.

    Two cross-file checks, both of which would otherwise pass quietly:

    - An IC ledger with no rows. Every downstream step handles an empty list
      without complaint, so the run "succeeds" and reports a close with
      nothing to review -- exactly the output of a clean month, produced by
      a feed that never arrived.
    - An entity code the master data doesn't know. Triage reads `interfaced`
      off the master data to decide whether a small break may be
      auto-eliminated; an entity missing from it would get the benefit of
      the doubt it is least entitled to.
    """
    entities = load_entities(data_dir / "entities.csv")
    trial_balance = load_trial_balance(data_dir / "trial_balance.csv")
    transactions = load_ic_transactions(data_dir / "ic_ledger.csv")

    if not transactions:
        raise DataLoadError("ic_ledger.csv has no transactions, so there is nothing to close")

    known = {entity.code for entity in entities}
    used = (
        {txn.entity_code for txn in transactions}
        | {txn.counterparty_code for txn in transactions}
        | {line.entity_code for line in trial_balance}
    )
    unknown = sorted(used - known)
    if unknown:
        raise DataLoadError(f"entity code(s) not in entities.csv: {', '.join(unknown)}")

    return entities, trial_balance, transactions


def _parse_decimal(raw: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"could not parse amount: {raw!r}") from exc
