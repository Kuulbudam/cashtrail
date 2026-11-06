"""Find patterns that a day-by-day match cannot see on its own."""
import numpy as np
import pandas as pd

LOSS_STATUSES = {"SHORT", "NO_DEPOSIT"}


def shortfall_streaks(recon, min_days=3):
    """Agents who were short (or skipped a deposit) several working days in a row."""
    rows = []

    def close(run):
        if len(run) >= min_days:
            first, last = run[0], run[-1]
            rows.append({
                "date": last["date"],
                "agent_id": last["agent_id"],
                "agent_name": last["agent_name"],
                "type": "SHORTFALL_STREAK",
                "detail": (
                    f"{len(run)} working days in a row with missing money, "
                    f"{first['date']:%d %b} to {last['date']:%d %b}. "
                    f"Total missing: N{-sum(r['variance'] for r in run):,.0f}"
                ),
            })

    for _, g in recon.sort_values("date").groupby("agent_id"):
        run = []
        for r in g.to_dict("records"):
            if r["status"] in LOSS_STATUSES:
                run.append(r)
            else:
                close(run)
                run = []
        close(run)
    return pd.DataFrame(rows)


def sudden_drops(collections, window=14, z_limit=3.0, min_history=7, min_drop=0.25):
    """Days where an agent's recorded collection is far below their own normal.

    The money may match the deposit perfectly here. The problem is that less
    money was collected in the first place.
    """
    daily = (
        collections.groupby(["agent_id", "agent_name", "date"], as_index=False)["amount"]
        .sum()
        .sort_values(["agent_id", "date"])
    )
    grp = daily.groupby("agent_id")["amount"]
    # shift(1) so a day is compared with the days BEFORE it, not itself
    daily["avg"] = grp.transform(lambda s: s.shift(1).rolling(window, min_periods=min_history).mean())
    daily["std"] = grp.transform(lambda s: s.shift(1).rolling(window, min_periods=min_history).std())
    daily["z"] = (daily["amount"] - daily["avg"]) / daily["std"].replace(0, np.nan)
    daily["drop_pct"] = 1 - daily["amount"] / daily["avg"]

    hit = daily[(daily["z"] < -z_limit) & (daily["drop_pct"] >= min_drop)].copy()
    if hit.empty:
        return pd.DataFrame(columns=["date", "agent_id", "agent_name", "type", "detail"])
    hit["type"] = "SUDDEN_DROP"
    hit["detail"] = hit.apply(
        lambda r: f"Collected N{r['amount']:,.0f} vs usual N{r['avg']:,.0f} "
                  f"({r['drop_pct']:.0%} lower)",
        axis=1,
    )
    return hit[["date", "agent_id", "agent_name", "type", "detail"]]


def find_anomalies(recon, collections, min_streak=3):
    parts = [shortfall_streaks(recon, min_days=min_streak), sudden_drops(collections)]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame(columns=["date", "agent_id", "agent_name", "type", "detail"])
    return pd.concat(parts).sort_values(["date", "agent_id"]).reset_index(drop=True)
