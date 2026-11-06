"""Turn results into an Excel workbook and a short text summary."""
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .reconcile import PROBLEM_STATUSES

STATUS_COLORS = {
    "MATCHED": "E2F0D9",
    "SHORT": "F8CBAD",
    "NO_DEPOSIT": "F4B183",
    "NO_RECORD": "FFE699",
    "OVER": "FFF2CC",
    "DUPLICATE_DEPOSIT": "FFE699",
    "LATE_DEPOSIT": "DDEBF7",
}


def scorecard(recon):
    """One row per agent: how clean is their record overall?"""
    g = recon.groupby(["agent_id", "agent_name", "route"])
    out = g.agg(
        days=("date", "count"),
        recorded=("recorded", "sum"),
        deposited=("deposited", "sum"),
        net_variance=("variance", "sum"),
        problem_days=("status", lambda s: s.isin(PROBLEM_STATUSES).sum()),
    ).reset_index()
    out["match_rate"] = (1 - out["problem_days"] / out["days"]).round(3)
    return out.sort_values("net_variance").reset_index(drop=True)


def summary_table(recon, anomalies):
    problems = recon[recon["status"].isin(PROBLEM_STATUSES)]
    missing = -recon.loc[recon["variance"] < 0, "variance"].sum()
    extra = recon.loc[recon["variance"] > 0, "variance"].sum()
    rows = [
        ("Period", f"{recon['date'].min():%d %b %Y} to {recon['date'].max():%d %b %Y}"),
        ("Agent-days checked", len(recon)),
        ("Total recorded (N)", f"{recon['recorded'].sum():,.0f}"),
        ("Total deposited (N)", f"{recon['deposited'].sum():,.0f}"),
        ("Money missing (N)", f"{missing:,.0f}"),
        ("Extra money (N)", f"{extra:,.0f}"),
        ("Late but matched deposits", int((recon["status"] == "LATE_DEPOSIT").sum())),
        ("Days needing review", len(problems)),
        ("Match rate", f"{1 - len(problems) / len(recon):.1%}"),
        ("Anomalies found", len(anomalies)),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value"])


def text_summary(recon, anomalies, top=5):
    """Short message you can read in the terminal or paste into WhatsApp/email."""
    s = summary_table(recon, anomalies)
    lines = ["CASHTRAIL SUMMARY", "=" * 40]
    lines += [f"{m}: {v}" for m, v in zip(s["Metric"], s["Value"])]

    card = scorecard(recon)
    worst = card[card["net_variance"] < 0].head(top)
    if not worst.empty:
        lines += ["", f"Biggest net shortfalls (top {top}):"]
        for r in worst.itertuples():
            lines.append(f"  {r.agent_id} {r.agent_name} ({r.route}): N{-r.net_variance:,.0f} short")

    if not anomalies.empty:
        lines += ["", "Anomalies:"]
        for r in anomalies.itertuples():
            lines.append(f"  [{r.type}] {r.agent_id} {r.agent_name}: {r.detail}")
    return "\n".join(lines)


def write_excel(recon, anomalies, path):
    problems = recon[recon["status"].isin(PROBLEM_STATUSES)]
    sheets = {
        "Summary": summary_table(recon, anomalies),
        "Exceptions": problems,
        "Anomalies": anomalies,
        "Agent Scorecard": scorecard(recon),
        "All Days": recon,
    }
    with pd.ExcelWriter(path, engine="openpyxl", datetime_format="DD-MMM-YYYY") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
            style_sheet(xw.sheets[name], df)


def style_sheet(ws, df):
    head_fill = PatternFill("solid", fgColor="1F3864")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"

    for i, col in enumerate(df.columns, start=1):
        longest = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)])
        ws.column_dimensions[get_column_letter(i)].width = min(longest + 3, 70)

        if df[col].dtype.kind in "if" and col not in ("days", "problem_days", "match_rate", "deposit_count"):
            for cell in ws[get_column_letter(i)][1:]:
                cell.number_format = "#,##0"

    if "status" in df.columns:
        idx = list(df.columns).index("status") + 1
        for row in ws.iter_rows(min_row=2, min_col=idx, max_col=idx):
            for cell in row:
                color = STATUS_COLORS.get(cell.value)
                if color:
                    cell.fill = PatternFill("solid", fgColor=color)
