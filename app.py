"""CashTrail dashboard. Run with:  streamlit run app.py"""

from io import BytesIO

import pandas as pd
import streamlit as st

from cashtrail.anomalies import find_anomalies
from cashtrail.generate import generate
from cashtrail.reconcile import (
    PROBLEM_STATUSES,
    clean,
    COLLECTION_COLS,
    DEPOSIT_COLS,
    reconcile,
)
from cashtrail.report import scorecard, summary_table, write_excel

st.set_page_config(page_title="CashTrail", layout="wide")
st.title(" CashTrail")
st.caption("Daily cash reconciliation and anomaly detection")

# ---------- Sidebar: data and settings ----------
with st.sidebar:
    st.header("Data")
    source = st.radio("Use", ["Demo data", "Upload my CSV files"])
    collections = deposits = None

    if source == "Demo data":
        collections, deposits = generate()
        collections = clean(collections, COLLECTION_COLS, "collections")
        deposits = clean(deposits, DEPOSIT_COLS, "deposits")
        st.info("Fake data with problems planted on purpose.")
    else:
        up_c = st.file_uploader("Collections CSV", type="csv")
        up_d = st.file_uploader("Deposits CSV", type="csv")
        st.caption(
            "collections: date, agent_id, agent_name, route, amount\n\n"
            "deposits: date, agent_id, amount, reference"
        )
        if up_c and up_d:
            try:
                collections = clean(pd.read_csv(up_c), COLLECTION_COLS, "collections")
                deposits = clean(pd.read_csv(up_d), DEPOSIT_COLS, "deposits")
            except ValueError as err:
                st.error(str(err))

    st.header("Rules")
    tolerance = st.number_input(
        "Tolerance (N)",
        min_value=0,
        value=0,
        step=100,
        help="Differences up to this amount count as matched.",
    )
    grace_days = st.slider(
        "Late deposit window (days)",
        0,
        5,
        2,
        help="How many days late a deposit can be and still match.",
    )
    min_streak = st.slider("Shortfall streak (working days)", 2, 7, 3)

if collections is None or deposits is None:
    st.warning("Upload both CSV files in the sidebar to begin.")
    st.stop()

# ---------- Run the checks ----------
recon = reconcile(collections, deposits, tolerance=tolerance, grace_days=grace_days)
anomalies = find_anomalies(recon, collections, min_streak=min_streak)
problems = recon[recon["status"].isin(PROBLEM_STATUSES)]
missing = -recon.loc[recon["variance"] < 0, "variance"].sum()


def show(df):
    """Dates without the 00:00:00 part, for display only."""
    df = df.copy()
    if "date" in df.columns:
        df["date"] = df["date"].dt.date
    return df


# ---------- Top numbers ----------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Money missing", f"N{missing:,.0f}")
k2.metric("Days needing review", len(problems))
k3.metric("Match rate", f"{1 - len(problems) / len(recon):.1%}")
k4.metric("Anomalies", len(anomalies))

tab1, tab2, tab3, tab4 = st.tabs(["Exceptions", "Anomalies", "Agents", "Trends"])

with tab1:
    statuses = sorted(problems["status"].unique())
    pick = st.multiselect("Filter by status", statuses, default=statuses)
    view = problems[problems["status"].isin(pick)]
    st.dataframe(show(view), use_container_width=True, hide_index=True)
    st.caption(f"{len(view)} row(s)")

with tab2:
    if anomalies.empty:
        st.success("No anomalies found.")
    else:
        st.dataframe(show(anomalies), use_container_width=True, hide_index=True)

with tab3:
    card = scorecard(recon)
    st.bar_chart(card.set_index("agent_id")["net_variance"], y_label="Net variance (N)")
    st.dataframe(card, use_container_width=True, hide_index=True)

with tab4:
    daily = recon.groupby("date")[["recorded", "deposited"]].sum()
    st.line_chart(daily, y_label="Naira")
    agent = st.selectbox("Look at one agent", sorted(recon["agent_id"].unique()))
    one = recon[recon["agent_id"] == agent].set_index("date")[["recorded", "deposited"]]
    st.line_chart(one, y_label="Naira")

# ---------- Download ----------
buffer = BytesIO()
write_excel(recon, anomalies, buffer)
st.download_button(
    "Download Excel report",
    buffer.getvalue(),
    file_name="cashtrail_report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
