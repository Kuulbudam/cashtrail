"""Match what was recorded against what was deposited, per agent per day."""
import numpy as np
import pandas as pd

COLLECTION_COLS = ["date", "agent_id", "agent_name", "route", "amount"]
DEPOSIT_COLS = ["date", "agent_id", "amount", "reference"]

# Statuses that need a human to look at them
PROBLEM_STATUSES = ["SHORT", "OVER", "NO_DEPOSIT", "NO_RECORD", "DUPLICATE_DEPOSIT"]


def load_collections(path):
    df = pd.read_csv(path)
    return clean(df, COLLECTION_COLS, "collections")


def load_deposits(path):
    df = pd.read_csv(path)
    return clean(df, DEPOSIT_COLS, "deposits")


def clean(df, required, name):
    """Check the columns, fix types, and drop rows that cannot be used."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{name} file is missing columns: {', '.join(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["agent_id"] = df["agent_id"].astype(str).str.strip().str.upper()
    bad = df["date"].isna() | df["amount"].isna()
    if bad.any():
        print(f"Warning: dropped {int(bad.sum())} bad row(s) from {name}.")
    return df[~bad].reset_index(drop=True)


def reconcile(collections, deposits, tolerance=0, grace_days=0):
    """Return one row per agent per day with recorded, deposited, variance, status.

    variance = deposited - recorded (negative means money is missing).
    tolerance = small difference (in Naira) that still counts as matched.
    grace_days = how many days late a deposit can be and still match its collection.
    """
    rec = collections.groupby(["date", "agent_id"], as_index=False).agg(
        recorded=("amount", "sum")
    )
    dep = deposits.groupby(["date", "agent_id"], as_index=False).agg(
        deposited=("amount", "sum"), deposit_count=("amount", "size")
    )

    # Same agent, same day, same amount, more than once = likely double posting
    dup = deposits[
        deposits.duplicated(["date", "agent_id", "amount"], keep=False)
    ][["date", "agent_id"]].drop_duplicates()
    dup["has_duplicate"] = True

    df = rec.merge(dep, on=["date", "agent_id"], how="outer")
    df = df.merge(dup, on=["date", "agent_id"], how="left")
    df["recorded"] = df["recorded"].fillna(0)
    df["deposited"] = df["deposited"].fillna(0)
    df["deposit_count"] = df["deposit_count"].fillna(0).astype(int)
    df["has_duplicate"] = df["has_duplicate"].fillna(False).astype(bool)
    df["variance"] = df["deposited"] - df["recorded"]

    # Order matters: the first matching rule wins
    conditions = [
        (df["recorded"] == 0) & (df["deposited"] > 0),
        (df["recorded"] > 0) & (df["deposited"] == 0),
        df["has_duplicate"],
        df["variance"] < -tolerance,
        df["variance"] > tolerance,
    ]
    labels = ["NO_RECORD", "NO_DEPOSIT", "DUPLICATE_DEPOSIT", "SHORT", "OVER"]
    df["status"] = np.select(conditions, labels, default="MATCHED")

    # Bring back names and routes
    people = collections[["agent_id", "agent_name", "route"]].drop_duplicates("agent_id")
    df = df.merge(people, on="agent_id", how="left")
    df["agent_name"] = df["agent_name"].fillna("(unknown)")
    df["route"] = df["route"].fillna("(unknown)")

    df["days_late"] = 0
    if grace_days > 0:
        df = match_late_deposits(df, grace_days, tolerance)

    cols = ["date", "agent_id", "agent_name", "route", "recorded", "deposited",
            "variance", "deposit_count", "days_late", "status"]
    return df[cols].sort_values(["date", "agent_id"]).reset_index(drop=True)


def match_late_deposits(df, grace_days, tolerance):
    """Pair a NO_DEPOSIT day with a deposit that arrived 1..grace_days later.

    The late money can show up in two ways:
      - on a day with no collection record (NO_RECORD): the whole row is the late deposit
      - on a day with its own collection (OVER): the extra amount is the late deposit
    A pair is made only when the amounts agree within the tolerance.
    """
    df = df.copy()
    to_drop = []

    for _, g in df.groupby("agent_id"):
        missing = g[g["status"] == "NO_DEPOSIT"].sort_values("date")
        used = set()
        for i, m in missing.iterrows():
            later = g[(g["date"] > m["date"])
                      & (g["date"] <= m["date"] + pd.Timedelta(days=grace_days))]
            for j, t in later.sort_values("date").iterrows():
                if j in used or t["status"] not in ("NO_RECORD", "OVER"):
                    continue
                available = t["deposited"] if t["status"] == "NO_RECORD" else t["variance"]
                if abs(available - m["recorded"]) > tolerance:
                    continue

                # the missing day is now covered
                df.loc[i, "deposited"] = available
                df.loc[i, "variance"] = available - m["recorded"]
                df.loc[i, "deposit_count"] = 1
                df.loc[i, "days_late"] = (t["date"] - m["date"]).days
                df.loc[i, "status"] = "LATE_DEPOSIT"

                # take the money off the day it landed on
                if t["status"] == "NO_RECORD":
                    to_drop.append(j)
                else:
                    new_dep = t["deposited"] - available
                    new_var = new_dep - t["recorded"]
                    df.loc[j, "deposited"] = new_dep
                    df.loc[j, "variance"] = new_var
                    if abs(new_var) <= tolerance:
                        df.loc[j, "status"] = "MATCHED"
                used.add(j)
                break

    return df.drop(index=to_drop)
