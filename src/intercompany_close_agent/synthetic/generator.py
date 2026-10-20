"""Synthetic intercompany close dataset generator.

Produces a trial balance and an intercompany ledger for a small fictional
life-sciences group, then deliberately breaks a slice of the intercompany
population the way a real close breaks: an FX conversion mismatch, a cutoff
timing gap, a missing counterparty booking, a wrong counterparty code, a
rounding difference, a flipped sign, an affiliate reporting in its own local
currency instead of group USD, an entity mapped as its own counterparty, a
reference reused by an unrelated transaction, and manual re-keying noise
from the group's one non-interfaced entity.

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

# Resolved relative to the current working directory, not this file's
# location. Every documented way of running this project (`uv run ...`) is
# invoked from the repo root, so cwd already gives the right answer there --
# and unlike walking a fixed number of parents up from __file__, it doesn't
# assume a src/-layout checkout that wouldn't exist if this package were
# ever installed non-editable (e.g. from a built wheel).
OUTPUT_DIR = Path.cwd() / "data" / "synthetic"

ENTITIES: list[Entity] = [
    Entity(code="US01", name="Vireon Biosciences US Inc", region="US", local_currency="USD", interfaced=True),
    Entity(code="DE01", name="Vireon Pharma GmbH", region="EMEA", local_currency="EUR", interfaced=True),
    Entity(code="GB01", name="Vireon Life Sciences UK Ltd", region="EMEA", local_currency="GBP", interfaced=True),
    Entity(code="IE01", name="Vireon Ireland Manufacturing Ltd", region="EMEA", local_currency="EUR", interfaced=True),
    Entity(
        code="BR01",
        name="Vireon Farmaceutica do Brasil Ltda",
        region="LATAM",
        local_currency="BRL",
        interfaced=True,
    ),
    Entity(code="MX01", name="Vireon Mexico SA de CV", region="LATAM", local_currency="MXN", interfaced=True),
    Entity(code="ZA01", name="Vireon South Africa Pty Ltd", region="AFRICA", local_currency="ZAR", interfaced=False),
]

# A larger group keeps the seven entities above, and so the sample's one
# manually loaded entity, ZA01, and adds interfaced ones from these countries
# in turn: FR01, NL01, ... then FR02, NL02, and so on. Invented like the rest.
EXTRA_COUNTRIES: list[tuple[str, str, str, str]] = [
    ("FR", "France", "EMEA", "EUR"),
    ("NL", "Netherlands", "EMEA", "EUR"),
    ("IT", "Italy", "EMEA", "EUR"),
    ("ES", "Spain", "EMEA", "EUR"),
    ("CH", "Switzerland", "EMEA", "CHF"),
    ("SE", "Sweden", "EMEA", "SEK"),
    ("PL", "Poland", "EMEA", "PLN"),
    ("JP", "Japan", "APAC", "JPY"),
    ("CN", "China", "APAC", "CNY"),
    ("IN", "India", "APAC", "INR"),
    ("AU", "Australia", "APAC", "AUD"),
    ("SG", "Singapore", "APAC", "SGD"),
    ("KR", "Korea", "APAC", "KRW"),
    ("CA", "Canada", "US", "CAD"),
    ("AR", "Argentina", "LATAM", "ARS"),
    ("CL", "Chile", "LATAM", "CLP"),
    ("CO", "Colombia", "LATAM", "COP"),
    ("NG", "Nigeria", "AFRICA", "NGN"),
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


def entities_for(count: int) -> list[Entity]:
    """The group's legal entities: the seven of the sample, then more up to count."""
    if count < len(ENTITIES):
        raise ValueError(f"a group needs at least the sample's {len(ENTITIES)} entities, not {count}")
    extra: list[Entity] = []
    for i in range(count - len(ENTITIES)):
        country, country_name, region, currency = EXTRA_COUNTRIES[i % len(EXTRA_COUNTRIES)]
        number = 1 + i // len(EXTRA_COUNTRIES)
        extra.append(
            Entity(
                code=f"{country}{number:02d}",
                name=f"Vireon {country_name} {number:02d}",
                region=region,
                local_currency=currency,
                interfaced=True,
            )
        )
    return [*ENTITIES, *extra]


@dataclass
class ICPair:
    """The two legs of one clean intercompany balance, before any anomaly."""

    entity_code: str
    counterparty_code: str
    reference: str
    amount: Decimal
    booking_date: date
    description: str


def generate_ic_pairs(rng: random.Random, count: int, entities: list[Entity] = ENTITIES) -> list[ICPair]:
    pairs: list[ICPair] = []
    codes = [e.code for e in entities]
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
    """A manual-load entity re-keyed the reference and dropped a hyphen.

    This is the one anomaly whose story is specific to *who* booked the leg:
    only an entity that keys its data in by hand re-types a reference and
    slips. So it no-ops on a balance between two interfaced entities -- same
    guard idiom as anomaly_local_currency skipping a USD entity -- which
    keeps it from firing on a pair whose story it doesn't fit when it comes
    up in the general pool. On the shipped dataset that ties the re-keying to
    ZA01, the group's one non-interfaced entity, exactly as the data README
    describes it.
    """
    by_code = {e.code: e for e in ENTITIES}
    involved = (rows[0]["entity_code"], rows[0]["counterparty_code"])
    if not any(code in by_code and not by_code[code].interfaced for code in involved):
        return rows
    rows[1]["reference"] = rows[1]["reference"].replace("-", "_", 1)
    return rows


def anomaly_local_currency(rows: list[dict], rng: random.Random) -> list[dict]:
    """The counterparty reported in its own local currency instead of USD.

    The amount still looks plausible, which is what makes this one nasty:
    netted at an implicit 1:1 it would appear to reconcile.
    """
    by_code = {e.code: e for e in ENTITIES}
    entity = by_code.get(rows[1]["entity_code"])
    if entity is None or entity.local_currency == "USD":
        return rows
    rows[1]["currency"] = entity.local_currency
    return rows


def anomaly_self_dealing(rows: list[dict], rng: random.Random) -> list[dict]:
    """The counterparty's booking mapped the balance to itself instead of the real entity.

    A mapping error upstream, not a genuine intercompany balance: the legs
    still net to zero, which is exactly why the matcher checks for this
    explicitly rather than trusting a clean net.
    """
    rows[1]["counterparty_code"] = rows[1]["entity_code"]
    return rows


def anomaly_duplicate_reference(rows: list[dict], rng: random.Random) -> list[dict]:
    """An unrelated transaction, from a different entity pair, reused this reference number."""
    original_entities = {rows[0]["entity_code"], rows[0]["counterparty_code"]}
    third_code = rng.choice([e.code for e in ENTITIES if e.code not in original_entities])
    third_counterparty = rng.choice([e.code for e in ENTITIES if e.code != third_code])
    extra_leg = {
        "entity_code": third_code,
        "counterparty_code": third_counterparty,
        "reference": rows[0]["reference"],
        "amount": rows[0]["amount"],
        "currency": "USD",
        "transaction_date": rows[0]["transaction_date"],
        "description": f"Reference collision, unrelated to {rows[0]['entity_code']}->{rows[0]['counterparty_code']}",
    }
    return [*rows, extra_leg]


ANOMALY_INJECTORS = {
    "fx_mismatch": anomaly_fx_mismatch,
    "timing": anomaly_timing,
    "missing_counterparty": anomaly_missing_counterparty,
    "wrong_counterparty_code": anomaly_wrong_counterparty_code,
    "rounding": anomaly_rounding,
    "sign_flip": anomaly_sign_flip,
    "non_interfaced_noise": anomaly_non_interfaced_noise,
    "local_currency": anomaly_local_currency,
    "self_dealing": anomaly_self_dealing,
    "duplicate_reference": anomaly_duplicate_reference,
}

# self_dealing and duplicate_reference are rare at anomaly_rate alone -- one
# of ten injectors, picked ~35% of the time works out to under one expected
# occurrence at the default pair_count. They're also the two exception types
# docs/human-in-the-loop.md leans on hardest to make its case (an entity
# can't be its own counterparty; a reference can't mean two things), so
# leaving them to chance meant most runs of this generator never actually
# demonstrated them. Forced onto one pair each instead of left to the same
# per-pair roll as everything else.
FORCED_ANOMALIES = ("self_dealing", "duplicate_reference")


def build_ic_ledger_rows(pairs: list[ICPair], rng: random.Random, anomaly_rate: float = 0.35) -> list[dict]:
    rows: list[dict] = []
    anomaly_names = list(ANOMALY_INJECTORS)

    # Forced pairs are chosen from the ones ZA01 isn't part of, so the
    # non-interfaced noise check below can't re-key the reference out from
    # under a duplicate_reference anomaly that depends on it staying put.
    forceable = [i for i, pair in enumerate(pairs) if "ZA01" not in (pair.entity_code, pair.counterparty_code)]
    forced_indices = rng.sample(forceable, min(len(FORCED_ANOMALIES), len(forceable)))
    forced = dict(zip(forced_indices, FORCED_ANOMALIES, strict=False))

    for i, pair in enumerate(pairs):
        pair_rows = rows_from_pair(pair)

        # ZA01 is the group's one non-interfaced entity -- give it a standing
        # chance of manual re-keying noise on top of whatever else lands on it.
        if "ZA01" in (pair.entity_code, pair.counterparty_code) and rng.random() < 0.5:
            pair_rows = anomaly_non_interfaced_noise(pair_rows, rng)

        injector_name = forced.get(i)
        if injector_name is None and rng.random() < anomaly_rate:
            injector_name = rng.choice(anomaly_names)
        if injector_name is not None:
            pair_rows = ANOMALY_INJECTORS[injector_name](pair_rows, rng)

        rows.extend(pair_rows)
    return rows


def build_trial_balance_rows(
    rng: random.Random, ic_rows: list[dict], entities: list[Entity] = ENTITIES
) -> list[dict]:
    """Build the trial balance, with the IC control accounts derived from the ledger.

    The intercompany receivable and payable accounts aren't random: in a real
    close they're the general ledger's own view of the same balances that sit
    in the intercompany subledger, so the two have to agree. Everything else
    on the trial balance is filler -- nothing in this project reads it.

    One entity is then deliberately knocked out of balance, because a tie-out
    check that can never fail isn't a check.
    """
    ic_receivable: dict[str, Decimal] = {e.code: Decimal("0") for e in entities}
    ic_payable: dict[str, Decimal] = {e.code: Decimal("0") for e in entities}

    for row in ic_rows:
        amount = Decimal(row["amount"])
        bucket = ic_receivable if amount > 0 else ic_payable
        bucket[row["entity_code"]] += amount

    # A posting that reached the GL but never made it into the IC subledger --
    # the everyday cause of a control account that won't tie at close.
    broken_entity = rng.choice([e.code for e in entities])
    ic_receivable[broken_entity] += (Decimal(rng.randrange(100_000, 900_000)) / 100).quantize(Decimal("1.00"))

    rows: list[dict] = []
    for entity in entities:
        for account_code, account_name in TB_ACCOUNTS:
            if account_code == "1000-IC-REC":
                balance = ic_receivable[entity.code]
            elif account_code == "2000-IC-PAY":
                balance = ic_payable[entity.code]
            else:
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
    # The csv module ends rows with \r\n on every platform unless told
    # otherwise. The committed sample is LF (.gitattributes), so a CRLF rewrite
    # of identical data left all three files showing as modified after anyone
    # followed the README and regenerated it.
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate(
    seed: int = 14,
    pair_count: int = 26,
    out_dir: Path = OUTPUT_DIR,
    entity_count: int = len(ENTITIES),
    anomaly_rate: float = 0.35,
) -> None:
    # 14 isn't special to the generator -- it's just the seed (out of the
    # first 50 tried) whose random draw happens to exercise all eight
    # exception types in one committed dataset, missing_counterparty through
    # duplicate_reference, instead of leaving some of them to only ever show
    # up in tests/test_matching.py's hand-built fixtures.
    #
    # entity_count and anomaly_rate are for larger runs (see `scale-run`); at
    # their defaults the draw, and so the committed sample, is unchanged.
    rng = random.Random(seed)
    entities = entities_for(entity_count)

    ic_pairs = generate_ic_pairs(rng, pair_count, entities)
    ic_rows = build_ic_ledger_rows(ic_pairs, rng, anomaly_rate)
    tb_rows = build_trial_balance_rows(rng, ic_rows, entities)

    _write_csv(
        out_dir / "ic_ledger.csv",
        ic_rows,
        fieldnames=[
            "entity_code",
            "counterparty_code",
            "reference",
            "amount",
            "currency",
            "transaction_date",
            "description",
        ],
    )
    _write_csv(
        out_dir / "trial_balance.csv",
        tb_rows,
        fieldnames=["entity_code", "account_code", "account_name", "balance"],
    )
    _write_csv(
        out_dir / "entities.csv",
        [e.model_dump() for e in entities],
        fieldnames=["code", "name", "region", "local_currency", "reporting_currency", "interfaced"],
    )

    print(f"wrote {len(ic_rows)} IC ledger rows from {len(ic_pairs)} pairs -> {out_dir / 'ic_ledger.csv'}")
    print(f"wrote {len(tb_rows)} trial balance rows across {len(entities)} entities -> {out_dir / 'trial_balance.csv'}")
    print(f"wrote {len(entities)} entities -> {out_dir / 'entities.csv'}")
