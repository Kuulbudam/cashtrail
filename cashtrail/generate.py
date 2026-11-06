"""Make fake but realistic data, so the project runs without any real company data.

Some problems are planted on purpose (shortfalls, missing deposits, a duplicate,
a sudden drop, two late deposits) so you can see CashTrail catch them.
"""
import numpy as np
import pandas as pd

AGENTS = [
    ("A01", "Musa Ibrahim", "Monday Market"),
    ("A02", "Aisha Bukar", "Baga Road"),
    ("A03", "Danjuma Pwajok", "Gamboru"),
    ("A04", "Fatima Goni", "Bolori"),
    ("A05", "Yakubu Dalyop", "Custom Roundabout"),
    ("A06", "Zainab Kyari", "Shehu Laminu"),
    ("A07", "Ibrahim Lawan", "Zannari"),
    ("A08", "Hauwa Mustapha", "Mairi"),
    ("A09", "Emeka Obi", "London Ciki"),
    ("A10", "Halima Umar", "Pompomari"),
    ("A11", "Samuel Bitrus", "University Road"),
    ("A12", "Bala Kolo", "Dalori"),
]


def generate(days=60, end=None, seed=42):
    """Return (collections, deposits) as two DataFrames."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end) if end is not None else pd.Timestamp.today().normalize()
    dates = pd.date_range(end=end, periods=days)

    collections, deposits = [], []
    ref = 100000

    for aid, name, route in AGENTS:
        base = int(rng.integers(40, 90)) * 1000
        for pos, day in enumerate(dates):
            days_from_end = days - 1 - pos

            # Sundays are mostly off, and agents sometimes miss a day
            if day.dayofweek == 6 and rng.random() < 0.7:
                continue
            if rng.random() < 0.04:
                continue

            amount = int(round(base * rng.normal(1, 0.08), -2))

            # Planted problem: A09's collections fall hard in the last 5 days
            if aid == "A09" and days_from_end < 5:
                amount = int(round(amount * 0.55, -2))

            collections.append((day, aid, name, route, amount))

            deposit = amount
            skip_deposit = False

            # Planted problem: A03 deposits 5-10% less for the last 8 days
            if aid == "A03" and days_from_end < 8:
                deposit = int(round(amount * rng.uniform(0.90, 0.95), -2))

            # Planted problem: A05 has 3 days with no deposit
            if aid == "A05" and days_from_end in (3, 11, 20):
                skip_deposit = True

            # Planted problem: A02 deposits 2,000 extra one day
            if aid == "A02" and days_from_end == 6:
                deposit += 2000

            # Planted problem (not really a problem): A06 and A08 deposit the next morning
            deposit_day = day
            if (aid == "A06" and days_from_end == 14) or (aid == "A08" and days_from_end == 25):
                deposit_day = day + pd.Timedelta(days=1)

            if not skip_deposit:
                ref += 1
                deposits.append((deposit_day, aid, deposit, f"TRF{ref}"))
                # Planted problem: A07's deposit is posted twice
                if aid == "A07" and days_from_end == 9:
                    ref += 1
                    deposits.append((day, aid, deposit, f"TRF{ref}"))

    # Planted problem: a deposit from A11 with no collection record
    ref += 1
    deposits.append((dates[-4], "A11", 35000, f"TRF{ref}"))
    # remove A11's real record for that day so the deposit has nothing to match
    collections = [
        c for c in collections if not (c[1] == "A11" and c[0] == dates[-4])
    ]
    # ...and also remove A11's normal deposit for that day (keep only the odd one)
    deposits = [
        d for d in deposits
        if not (d[1] == "A11" and d[0] == dates[-4] and d[3] != f"TRF{ref}")
    ]

    c = pd.DataFrame(
        collections, columns=["date", "agent_id", "agent_name", "route", "amount"]
    )
    d = pd.DataFrame(deposits, columns=["date", "agent_id", "amount", "reference"])
    return c, d
