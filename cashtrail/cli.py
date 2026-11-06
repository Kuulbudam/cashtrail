"""Command line: `python -m cashtrail demo` or `python -m cashtrail run ...`"""
import argparse
from pathlib import Path

from .anomalies import find_anomalies
from .generate import generate
from .reconcile import load_collections, load_deposits, reconcile
from .report import text_summary, write_excel


def run_pipeline(collections, deposits, out_dir, tolerance, grace_days=2):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    recon = reconcile(collections, deposits, tolerance=tolerance, grace_days=grace_days)
    anomalies = find_anomalies(recon, collections)

    xlsx = out_dir / "cashtrail_report.xlsx"
    write_excel(recon, anomalies, xlsx)
    summary = text_summary(recon, anomalies)
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")

    print(summary)
    print(f"\nExcel report: {xlsx}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="cashtrail", description="Daily cash reconciliation")
    sub = p.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="Make fake data and run everything")
    demo.add_argument("--out", default="reports")
    demo.add_argument("--days", type=int, default=60)

    run = sub.add_parser("run", help="Reconcile your own CSV files")
    run.add_argument("--collections", required=True)
    run.add_argument("--deposits", required=True)
    run.add_argument("--out", default="reports")
    run.add_argument("--tolerance", type=float, default=0,
                     help="Differences up to this amount (N) count as matched")
    run.add_argument("--grace-days", type=int, default=2,
                     help="How many days late a deposit can be and still match (0 = same day only)")

    args = p.parse_args(argv)

    if args.cmd == "demo":
        c, d = generate(days=args.days)
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        c.to_csv(data_dir / "sample_collections.csv", index=False)
        d.to_csv(data_dir / "sample_deposits.csv", index=False)
        print(f"Sample data saved in {data_dir}/\n")
        run_pipeline(c, d, args.out, tolerance=0)
    else:
        c = load_collections(args.collections)
        d = load_deposits(args.deposits)
        run_pipeline(c, d, args.out, tolerance=args.tolerance, grace_days=args.grace_days)
