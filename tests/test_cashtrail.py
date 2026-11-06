import pandas as pd

from cashtrail.anomalies import shortfall_streaks, sudden_drops
from cashtrail.reconcile import reconcile


def make(collections, deposits):
    c = pd.DataFrame(collections, columns=["date", "agent_id", "agent_name", "route", "amount"])
    d = pd.DataFrame(deposits, columns=["date", "agent_id", "amount", "reference"])
    c["date"] = pd.to_datetime(c["date"])
    d["date"] = pd.to_datetime(d["date"])
    return c, d


def status_of(recon, agent, day):
    row = recon[(recon.agent_id == agent) & (recon.date == pd.Timestamp(day))]
    return row.iloc[0]["status"]


def test_matched_short_over():
    c, d = make(
        [("2026-01-01", "A1", "Ada", "R", 1000),
         ("2026-01-01", "A2", "Bola", "R", 1000),
         ("2026-01-01", "A3", "Chi", "R", 1000)],
        [("2026-01-01", "A1", 1000, "T1"),
         ("2026-01-01", "A2", 900, "T2"),
         ("2026-01-01", "A3", 1200, "T3")],
    )
    r = reconcile(c, d)
    assert status_of(r, "A1", "2026-01-01") == "MATCHED"
    assert status_of(r, "A2", "2026-01-01") == "SHORT"
    assert status_of(r, "A3", "2026-01-01") == "OVER"


def test_tolerance_allows_small_difference():
    c, d = make([("2026-01-01", "A1", "Ada", "R", 1000)],
                [("2026-01-01", "A1", 950, "T1")])
    assert status_of(reconcile(c, d, tolerance=100), "A1", "2026-01-01") == "MATCHED"
    assert status_of(reconcile(c, d, tolerance=0), "A1", "2026-01-01") == "SHORT"


def test_missing_deposit_and_missing_record():
    c, d = make([("2026-01-01", "A1", "Ada", "R", 1000)],
                [("2026-01-01", "A2", 500, "T1")])
    r = reconcile(c, d)
    assert status_of(r, "A1", "2026-01-01") == "NO_DEPOSIT"
    assert status_of(r, "A2", "2026-01-01") == "NO_RECORD"


def test_duplicate_deposit():
    c, d = make([("2026-01-01", "A1", "Ada", "R", 1000)],
                [("2026-01-01", "A1", 1000, "T1"), ("2026-01-01", "A1", 1000, "T2")])
    r = reconcile(c, d)
    assert status_of(r, "A1", "2026-01-01") == "DUPLICATE_DEPOSIT"
    assert r.iloc[0]["variance"] == 1000


def test_shortfall_streak_needs_three_days():
    days = pd.date_range("2026-01-01", periods=4)
    c, d = make(
        [(x, "A1", "Ada", "R", 1000) for x in days],
        [(x, "A1", 900, f"T{i}") for i, x in enumerate(days)],
    )
    streaks = shortfall_streaks(reconcile(c, d), min_days=3)
    assert len(streaks) == 1
    assert "4 working days" in streaks.iloc[0]["detail"]


def test_streak_breaks_on_matched_day():
    days = pd.date_range("2026-01-01", periods=5)
    amounts = [900, 900, 1000, 900, 900]
    c, d = make(
        [(x, "A1", "Ada", "R", 1000) for x in days],
        [(x, "A1", a, f"T{i}") for i, (x, a) in enumerate(zip(days, amounts))],
    )
    assert shortfall_streaks(reconcile(c, d), min_days=3).empty


def test_sudden_drop_found():
    days = pd.date_range("2026-01-01", periods=20)
    amounts = [1000 + (i % 3) * 20 for i in range(19)] + [400]
    c, _ = make([(x, "A1", "Ada", "R", a) for x, a in zip(days, amounts)], [])
    drops = sudden_drops(c)
    assert len(drops) == 1
    assert drops.iloc[0]["date"] == days[-1]


def test_late_deposit_on_a_day_with_no_record():
    # Saturday cash is deposited Sunday, when the agent did not work
    c, d = make([("2026-01-03", "A1", "Ada", "R", 1000)],
                [("2026-01-04", "A1", 1000, "T1")])
    r = reconcile(c, d, grace_days=2)
    assert len(r) == 1
    assert r.iloc[0]["status"] == "LATE_DEPOSIT"
    assert r.iloc[0]["days_late"] == 1


def test_late_deposit_mixed_with_next_day_deposit():
    # Day 1 cash (1000) is deposited together with day 2 cash (1500)
    c, d = make([("2026-01-01", "A1", "Ada", "R", 1000),
                 ("2026-01-02", "A1", "Ada", "R", 1500)],
                [("2026-01-02", "A1", 1500, "T1"), ("2026-01-02", "A1", 1000, "T2")])
    r = reconcile(c, d, grace_days=2)
    assert status_of(r, "A1", "2026-01-01") == "LATE_DEPOSIT"
    assert status_of(r, "A1", "2026-01-02") == "MATCHED"


def test_late_deposit_ignored_when_grace_is_zero_or_too_late():
    c, d = make([("2026-01-01", "A1", "Ada", "R", 1000)],
                [("2026-01-05", "A1", 1000, "T1")])
    r0 = reconcile(c, d, grace_days=0)
    r2 = reconcile(c, d, grace_days=2)
    assert status_of(r0, "A1", "2026-01-01") == "NO_DEPOSIT"
    assert status_of(r2, "A1", "2026-01-01") == "NO_DEPOSIT"  # 4 days late, outside grace
    assert status_of(r2, "A1", "2026-01-05") == "NO_RECORD"
