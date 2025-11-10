"""Synthetic intercompany close dataset generator.

Produces a trial balance and an intercompany ledger for a small fictional
life-sciences group, then deliberately breaks a slice of the intercompany
population the way a real close breaks: an FX conversion mismatch, a cutoff
timing gap, a missing counterparty booking, a wrong counterparty code, a
rounding difference, a flipped sign, and manual re-keying noise from the
group's one non-interfaced entity.

Everything here is invented. None of the entity names, amounts, or
references correspond to any real company, and the numbers are randomly
generated from a fixed seed -- reproducible, not real.

Lives in the package (rather than only as a script) so both the CLI's
`generate-data` command and `scripts/generate_synthetic_data.py` can call
the same code.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from intercompany_close_agent.models.entity import Entity

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic"

ENTITIES: list[Entity] = [
    Entity(code="US01", name="Vireon Biosciences US Inc", region="US", local_currency="USD", interfaced=True),
    Entity(code="DE01", name="Vireon Pharma GmbH", region="EMEA", local_currency="EUR", interfaced=True),
    Entity(code="GB01", name="Vireon Life Sciences UK Ltd", region="EMEA", local_currency="GBP", interfaced=True),
    Entity(code="IE01", name="Vireon Ireland Manufacturing Ltd", region="EMEA", local_currency="EUR", interfaced=True),
    Entity(code="BR01", name="Vireon Farmaceutica do Brasil Ltda", region="LATAM", local_currency="BRL", interfaced=True),
    Entity(code="MX01", name="Vireon Mexico SA de CV", region="LATAM", local_currency="MXN", interfaced=True),
    Entity(code="ZA01", name="Vireon South Africa Pty Ltd", region="AFRICA", local_currency="ZAR", interfaced=False),
]

REFERENCE_PREFIXES = ["MGMT-FEE", "PRODUCT", "ROYALTY", "LOAN-INT", "RECHARGE"]

CLOSE_DATE = date(2025, 9, 30)

TB_ACCOUNTS = [
    ("1000-IC-REC", "Intercompany Receivable"),
    ("2000-IC-PAY", "Intercompany Payable"),
    ("1100-CASH", "Cash and Equivalents"),
    ("3000-EQ", "Retained Earnings"),
    ("4000-REV", "Revenue"),
    ("5000-COGS", "Cost of Goods Sold"),
    ("6000-OPEX", "Operating Expenses"),
]


@dataclass
class ICPair:
    """The two legs of one clean intercompany balance, before any anomaly."""

    entity_code: str
    counterparty_code: str
    reference: str
    amount: Decimal
    booking_date: date
    description: str


def generate_ic_pairs(rng: random.Random, count: int) -> list[ICPair]:
    pairs: list[ICPair] = []
    codes = [e.code for e in ENTITIES]
    for i in range(count):
        entity_code, counterparty_code = rng.sample(codes, 2)
        prefix = rng.choice(REFERENCE_PREFIXES)
        reference = f"{prefix}-2025-{1000 + i}"
        amount = (Decimal(rng.randrange(50_000, 25_000_000)) / 100).quantize(Decimal("1.00"))
        booking_date = CLOSE_DATE - timedelta(days=rng.randint(0, 20))
        description = f"{prefix.replace('-', ' ').title()} {entity_code}->{counterparty_code}"
        pairs.append(ICPair(entity_code, counterparty_code, reference, amount, booking_date, description))
    return pairs


def rows_from_pair(pair: ICPair) -> list[dict]:
    """Turn one clean IC pair into its two mirrored ledger legs."""
    return [
        {
            "entity_code": pair.entity_code,
            "counterparty_code": pair.counterparty_code,
            "reference": pair.reference,
            "amount": str(pair.amount),
            "currency": "USD",
            "transaction_date": pair.booking_date.isoformat(),
            "description": pair.description,
        },
        {
            "entity_code": pair.counterparty_code,
            "counterparty_code": pair.entity_code,
            "reference": pair.reference,
            "amount": str(-pair.amount),
            "currency": "USD",
            "transaction_date": pair.booking_date.isoformat(),
            "description": pair.description,
        },
    ]


# --- anomaly injectors -----------------------------------------------------
# Each injector mutates a copy of the two clean legs so the anomaly is
# reproducible from the seed and each failure mode is easy to reason about
# on its own. They only ever touch the counterparty's leg (index 1) -- that
# mirrors how these things actually happen: one entity books it right, the
# other's version of the same balance is what's off.


def anomaly_fx_mismatch(rows: list[dict], rng: random.Random) -> list[dict]:
    """The counterparty's leg was converted to USD at a slightly different rate."""
    drift = Decimal(str(round(rng.uniform(0.002, 0.02), 4)))
    original = Decimal(rows[1]["amount"])
    rows[1]["amount"] = str((original * (1 + drift)).quantize(Decimal("1.00")))
    return rows


def anomaly_timing(rows: list[dict], rng: random.Random) -> list[dict]:
    """The counterparty booked its leg after the close cutoff."""
    booked = date.fromisoformat(rows[1]["transaction_date"])
    rows[1]["transaction_date"] = (booked + timedelta(days=rng.randint(3, 10))).isoformat()
    return rows


def anomaly_missing_counterparty(rows: list[dict], rng: random.Random) -> list[dict]:
    """The counterparty never booked its mirror leg at all."""
    return [rows[0]]


def anomaly_wrong_counterparty_code(rows: list[dict], rng: random.Random) -> list[dict]:
    """The counterparty booked the leg against the wrong group entity."""
    excluded = {rows[0]["entity_code"], rows[0]["counterparty_code"]}
    wrong_code = rng.choice([e.code for e in ENTITIES if e.code not in excluded])
    rows[1]["counterparty_code"] = wrong_code
    return rows


def anomaly_rounding(rows: list[dict], rng: random.Random) -> list[dict]:
    """A small rounding difference, well inside a sane tolerance."""
    original = Decimal(rows[1]["amount"])
    bump = Decimal(rng.choice(["0.01", "-0.01", "0.02", "-0.02"]))
    rows[1]["amount"] = str(original + bump)
    return rows


def anomaly_sign_flip(rows: list[dict], rng: random.Random) -> list[dict]:
    """The counterparty booked its leg with the wrong sign -- a payable posted as a receivable."""
    original = Decimal(rows[1]["amount"])
    rows[1]["amount"] = str(-original)
    return rows


def anomaly_non_interfaced_noise(rows: list[dict], rng: random.Random) -> list[dict]:
    """A manual-load entity re-keyed the reference and dropped a hyphen."""
    rows[1]["reference"] = rows[1]["reference"].replace("-", "_", 1)
    return rows


ANOMALY_INJECTORS = {
    "fx_mismatch": anomaly_fx_mismatch,
    "timing": anomaly_timing,
    "missing_counterparty": anomaly_missing_counterparty,
    "wrong_counterparty_code": anomaly_wrong_counterparty_code,
    "rounding": anomaly_rounding,
    "sign_flip": anomaly_sign_flip,
    "non_interfaced_noise": anomaly_non_interfaced_noise,
}


def build_ic_ledger_rows(pairs: list[ICPair], rng: random.Random, anomaly_rate: float = 0.35) -> list[dict]:
    rows: list[dict] = []
    anomaly_names = list(ANOMALY_INJECTORS)
    for pair in pairs:
        pair_rows = rows_from_pair(pair)

        # ZA01 is the group's one non-interfaced entity -- give it a standing
        # chance of manual re-keying noise on top of whatever else lands on it.
        if "ZA01" in (pair.entity_code, pair.counterparty_code) and rng.random() < 0.5:
            pair_rows = anomaly_non_interfaced_noise(pair_rows, rng)

        if rng.random() < anomaly_rate:
            injector_name = rng.choice(anomaly_names)
            pair_rows = ANOMALY_INJECTORS[injector_name](pair_rows, rng)

        rows.extend(pair_rows)
    return rows


def build_trial_balance_rows(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for entity in ENTITIES:
        for account_code, account_name in TB_ACCOUNTS:
            balance = (Decimal(rng.randrange(-50_000_000, 200_000_000)) / 100).quantize(Decimal("1.00"))
            rows.append(
                {
                    "entity_code": entity.code,
                    "account_code": account_code,
                    "account_name": account_name,
                    "balance": str(balance),
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate(seed: int = 42, pair_count: int = 26, out_dir: Path = OUTPUT_DIR) -> None:
    rng = random.Random(seed)

    ic_pairs = generate_ic_pairs(rng, pair_count)
    ic_rows = build_ic_ledger_rows(ic_pairs, rng)
    tb_rows = build_trial_balance_rows(rng)

    _write_csv(
        out_dir / "ic_ledger.csv",
        ic_rows,
        fieldnames=["entity_code", "counterparty_code", "reference", "amount", "currency", "transaction_date", "description"],
    )
    _write_csv(
        out_dir / "trial_balance.csv",
        tb_rows,
        fieldnames=["entity_code", "account_code", "account_name", "balance"],
    )
    _write_csv(
        out_dir / "entities.csv",
        [e.model_dump() for e in ENTITIES],
        fieldnames=["code", "name", "region", "local_currency", "reporting_currency", "interfaced"],
    )

    print(f"wrote {len(ic_rows)} IC ledger rows from {len(ic_pairs)} pairs -> {out_dir / 'ic_ledger.csv'}")
    print(f"wrote {len(tb_rows)} trial balance rows across {len(ENTITIES)} entities -> {out_dir / 'trial_balance.csv'}")
    print(f"wrote {len(ENTITIES)} entities -> {out_dir / 'entities.csv'}")
