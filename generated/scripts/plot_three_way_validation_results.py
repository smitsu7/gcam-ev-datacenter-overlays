#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


FINAL_SECTOR_QUERY = "total final energy by sector"
FINAL_AGG_QUERY = "total final energy by aggregate sector"
PRIMARY_QUERY = "primary energy consumption by region (direct equivalent)"
DATACENTER_SECTOR = "comm datacenter sector"
SCENARIOS = [f"GCAM_SSP{i}" for i in range(1, 6)]
CASE_COLORS = {
    "baseline_value": "#4d4d4d",
    "ev_value": "#1f78b4",
    "ev_dc_value": "#d95f02",
}
CASE_LABELS = {
    "baseline_value": "Baseline",
    "ev_value": "EV",
    "ev_dc_value": "EV+DC",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create three-way validation plots for baseline, EV, and EV+datacenter SSP comparisons."
    )
    parser.add_argument("--detail", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    numeric_cols = [
        "baseline_value",
        "ev_value",
        "ev_dc_value",
        "ev_minus_baseline",
        "ev_dc_minus_baseline",
        "ev_dc_minus_ev",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df


def validate_outputs(detail_df: pd.DataFrame, summary_df: pd.DataFrame):
    report = {
        "required_queries_present": {},
        "missing_summary_series": [],
        "missing_transport_series": [],
        "missing_datacenter_series": [],
        "missing_primary_fuel_rows": [],
    }

    required_queries = [FINAL_SECTOR_QUERY, FINAL_AGG_QUERY, PRIMARY_QUERY]
    for query in required_queries:
        report["required_queries_present"][query] = (
            query in set(detail_df["query"]) and query in set(summary_df["query"])
        )

    years = sorted(summary_df["year"].dropna().astype(int).unique().tolist())
    primary_fuels = sorted(
        detail_df.loc[detail_df["query"] == PRIMARY_QUERY, "fuel"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    for scenario in SCENARIOS:
        for query in [FINAL_AGG_QUERY, PRIMARY_QUERY]:
            subset = summary_df[
                (summary_df["query"] == query) & (summary_df["scenario"] == scenario)
            ]
            seen_years = sorted(subset["year"].dropna().astype(int).unique().tolist())
            if seen_years != years:
                report["missing_summary_series"].append(
                    {"scenario": scenario, "query": query, "years": seen_years}
                )

        transport = detail_df[
            (detail_df["query"] == FINAL_AGG_QUERY)
            & (detail_df["scenario"] == scenario)
            & (detail_df["sector"] == "transportation")
        ]
        transport_years = sorted(
            transport["year"].dropna().astype(int).unique().tolist()
        )
        if transport_years != years:
            report["missing_transport_series"].append(
                {"scenario": scenario, "years": transport_years}
            )

        datacenter = detail_df[
            (detail_df["query"] == FINAL_SECTOR_QUERY)
            & (detail_df["scenario"] == scenario)
            & (detail_df["sector"] == DATACENTER_SECTOR)
        ]
        datacenter_years = sorted(
            datacenter["year"].dropna().astype(int).unique().tolist()
        )
        if datacenter_years != years:
            report["missing_datacenter_series"].append(
                {"scenario": scenario, "years": datacenter_years}
            )

        primary = detail_df[
            (detail_df["query"] == PRIMARY_QUERY)
            & (detail_df["scenario"] == scenario)
        ]
        for fuel in primary_fuels:
            fuel_years = sorted(
                primary.loc[primary["fuel"] == fuel, "year"]
                .dropna()
                .astype(int)
                .unique()
                .tolist()
            )
            if fuel_years != years:
                report["missing_primary_fuel_rows"].append(
                    {"scenario": scenario, "fuel": fuel, "years": fuel_years}
                )

    report["required_queries_present"] = {
        key: bool(val) for key, val in report["required_queries_present"].items()
    }
    report["all_checks_passed"] = (
        all(report["required_queries_present"].values())
        and not report["missing_summary_series"]
        and not report["missing_transport_series"]
        and not report["missing_datacenter_series"]
        and not report["missing_primary_fuel_rows"]
    )
    report["years"] = years
    report["scenarios"] = SCENARIOS
    report["primary_fuels"] = primary_fuels
    return report


def apply_common_axis_style(ax):
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_total_overview(summary_df: pd.DataFrame, out_path: Path):
    fig, axes = plt.subplots(2, 5, figsize=(22, 8), sharex="col")
    total_final = summary_df[summary_df["query"] == FINAL_AGG_QUERY].copy()
    total_primary = summary_df[summary_df["query"] == PRIMARY_QUERY].copy()

    for idx, scenario in enumerate(SCENARIOS):
        final = total_final[total_final["scenario"] == scenario].sort_values("year")
        primary = total_primary[total_primary["scenario"] == scenario].sort_values("year")

        ax_final = axes[0, idx]
        ax_primary = axes[1, idx]

        for col in ["baseline_value", "ev_value", "ev_dc_value"]:
            ax_final.plot(
                final["year"],
                final[col],
                color=CASE_COLORS[col],
                linewidth=2,
                label=CASE_LABELS[col],
            )
            ax_primary.plot(
                primary["year"],
                primary[col],
                color=CASE_COLORS[col],
                linewidth=2,
                label=CASE_LABELS[col],
            )

        ax_final.set_title(scenario.replace("GCAM_", ""))
        apply_common_axis_style(ax_final)
        apply_common_axis_style(ax_primary)
        if idx == 0:
            ax_final.set_ylabel("Total final energy (EJ)")
            ax_primary.set_ylabel("Primary energy (EJ)")
        ax_primary.set_xlabel("Year")

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.98), ncol=3, frameon=False)
    fig.suptitle("Baseline, EV, and EV+datacenter total energy across all SSPs", fontsize=16, y=1.03)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_total_deltas(summary_df: pd.DataFrame, out_path: Path):
    fig, axes = plt.subplots(2, 5, figsize=(22, 8), sharex="col")
    total_final = summary_df[summary_df["query"] == FINAL_AGG_QUERY].copy()
    total_primary = summary_df[summary_df["query"] == PRIMARY_QUERY].copy()

    for idx, scenario in enumerate(SCENARIOS):
        final = total_final[total_final["scenario"] == scenario].sort_values("year")
        primary = total_primary[total_primary["scenario"] == scenario].sort_values("year")

        ax_final = axes[0, idx]
        ax_primary = axes[1, idx]

        ax_final.plot(
            final["year"],
            final["ev_minus_baseline"],
            color=CASE_COLORS["ev_value"],
            linewidth=2,
            label="EV - Baseline",
        )
        ax_final.plot(
            final["year"],
            final["ev_dc_minus_baseline"],
            color=CASE_COLORS["ev_dc_value"],
            linewidth=2,
            label="EV+DC - Baseline",
        )
        ax_primary.plot(
            primary["year"],
            primary["ev_minus_baseline"],
            color=CASE_COLORS["ev_value"],
            linewidth=2,
            label="EV - Baseline",
        )
        ax_primary.plot(
            primary["year"],
            primary["ev_dc_minus_baseline"],
            color=CASE_COLORS["ev_dc_value"],
            linewidth=2,
            label="EV+DC - Baseline",
        )

        ax_final.axhline(0, color="#999999", linewidth=1)
        ax_primary.axhline(0, color="#999999", linewidth=1)
        ax_final.set_title(scenario.replace("GCAM_", ""))
        apply_common_axis_style(ax_final)
        apply_common_axis_style(ax_primary)
        if idx == 0:
            ax_final.set_ylabel("Final delta (EJ)")
            ax_primary.set_ylabel("Primary delta (EJ)")
        ax_primary.set_xlabel("Year")

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.98), ncol=2, frameon=False)
    fig.suptitle("Total energy deltas relative to stock SSP runs", fontsize=16, y=1.03)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_transport_and_datacenter(detail_df: pd.DataFrame, out_path: Path):
    fig, axes = plt.subplots(2, 5, figsize=(22, 8), sharex="col")
    transport = detail_df[
        (detail_df["query"] == FINAL_AGG_QUERY)
        & (detail_df["sector"] == "transportation")
    ].copy()
    datacenter = detail_df[
        (detail_df["query"] == FINAL_SECTOR_QUERY)
        & (detail_df["sector"] == DATACENTER_SECTOR)
    ].copy()

    for idx, scenario in enumerate(SCENARIOS):
        transport_case = transport[transport["scenario"] == scenario].sort_values("year")
        datacenter_case = datacenter[datacenter["scenario"] == scenario].sort_values("year")

        ax_transport = axes[0, idx]
        ax_dc = axes[1, idx]

        for col in ["baseline_value", "ev_value", "ev_dc_value"]:
            ax_transport.plot(
                transport_case["year"],
                transport_case[col],
                color=CASE_COLORS[col],
                linewidth=2,
                label=CASE_LABELS[col],
            )
            dc_series = datacenter_case[col].fillna(0.0)
            ax_dc.plot(
                datacenter_case["year"],
                dc_series,
                color=CASE_COLORS[col],
                linewidth=2,
                label=CASE_LABELS[col],
            )

        ax_transport.set_title(scenario.replace("GCAM_", ""))
        apply_common_axis_style(ax_transport)
        apply_common_axis_style(ax_dc)
        if idx == 0:
            ax_transport.set_ylabel("Transport final energy (EJ)")
            ax_dc.set_ylabel("Datacenter final energy (EJ)")
        ax_dc.set_xlabel("Year")

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.98), ncol=3, frameon=False)
    fig.suptitle("Transport and datacenter sector final energy", fontsize=16, y=1.03)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_primary_fuel_shift(detail_df: pd.DataFrame, out_path: Path):
    primary = detail_df[detail_df["query"] == PRIMARY_QUERY].copy()
    fuel_order = (
        primary.groupby("fuel")["ev_dc_minus_ev"]
        .apply(lambda s: s.abs().max())
        .sort_values(ascending=False)
    )
    fuels = fuel_order.head(6).index.tolist()

    fig, axes = plt.subplots(1, 5, figsize=(22, 4.8), sharey=True)
    for idx, scenario in enumerate(SCENARIOS):
        ax = axes[idx]
        subset = primary[primary["scenario"] == scenario]
        for fuel in fuels:
            series = subset[subset["fuel"] == fuel].sort_values("year")
            ax.plot(
                series["year"],
                series["ev_dc_minus_ev"],
                linewidth=2,
                label=fuel,
            )
        ax.axhline(0, color="#999999", linewidth=1)
        ax.set_title(scenario.replace("GCAM_", ""))
        ax.set_xlabel("Year")
        apply_common_axis_style(ax)
        if idx == 0:
            ax.set_ylabel("EV+DC - EV (EJ)")

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.02), ncol=3, frameon=False)
    fig.suptitle("Primary fuel shifts from adding datacenter load on top of EV", fontsize=16, y=1.08)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    args = parse_args()
    detail_df = load_csv(args.detail)
    summary_df = load_csv(args.summary)
    report = validate_outputs(detail_df, summary_df)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_total_overview(summary_df, out_dir / "overview_total_final_primary.png")
    plot_total_deltas(summary_df, out_dir / "delta_total_final_primary.png")
    plot_transport_and_datacenter(detail_df, out_dir / "transport_and_datacenter_final_energy.png")
    plot_primary_fuel_shift(detail_df, out_dir / "primary_fuel_shift_evdc_minus_ev.png")

    report_path = out_dir / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote plots under {out_dir}")
    print(f"Wrote validation report to {report_path}")


if __name__ == "__main__":
    main()
