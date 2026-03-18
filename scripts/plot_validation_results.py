#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FINAL_QUERY = "total final energy by aggregate sector"
PRIMARY_QUERY = "primary energy consumption by region (direct equivalent)"
SCENARIOS = [f"GCAM_SSP{i}" for i in range(1, 6)]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create validation plots for baseline vs EV SSP comparisons."
    )
    parser.add_argument("--detail", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ["baseline_value", "ev_value", "delta_value", "pct_change"]:
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
        "missing_primary_fuel_rows": [],
    }

    for query in [FINAL_QUERY, PRIMARY_QUERY]:
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
        for query in [FINAL_QUERY, PRIMARY_QUERY]:
            subset = summary_df[
                (summary_df["query"] == query) & (summary_df["scenario"] == scenario)
            ]
            seen_years = sorted(subset["year"].dropna().astype(int).unique().tolist())
            if seen_years != years:
                report["missing_summary_series"].append(
                    {"scenario": scenario, "query": query, "years": seen_years}
                )

        transport = detail_df[
            (detail_df["query"] == FINAL_QUERY)
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


def plot_overview(summary_df: pd.DataFrame, out_path: Path):
    fig, axes = plt.subplots(2, 5, figsize=(22, 8), sharex="col")

    total_final = summary_df[summary_df["query"] == FINAL_QUERY].copy()
    total_primary = summary_df[summary_df["query"] == PRIMARY_QUERY].copy()

    for idx, scenario in enumerate(SCENARIOS):
        final = total_final[total_final["scenario"] == scenario].sort_values("year")
        primary = total_primary[total_primary["scenario"] == scenario].sort_values("year")

        ax_final = axes[0, idx]
        ax_primary = axes[1, idx]

        ax_final.plot(final["year"], final["baseline_value"], color="#4d4d4d", linewidth=2, label="Baseline")
        ax_final.plot(final["year"], final["ev_value"], color="#1f78b4", linewidth=2, label="EV")
        ax_final.set_title(scenario.replace("GCAM_", ""))
        apply_common_axis_style(ax_final)

        ax_primary.plot(primary["year"], primary["baseline_value"], color="#4d4d4d", linewidth=2, label="Baseline")
        ax_primary.plot(primary["year"], primary["ev_value"], color="#33a02c", linewidth=2, label="EV")
        apply_common_axis_style(ax_primary)

        if idx == 0:
            ax_final.set_ylabel("Total final energy (EJ)")
            ax_primary.set_ylabel("Primary energy (EJ)")

        ax_primary.set_xlabel("Year")

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        ncol=2,
        frameon=False,
    )
    fig.suptitle("Baseline vs EV overlay across all SSPs and years", fontsize=16, y=1.03)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_final_sector_delta(detail_df: pd.DataFrame, out_path: Path):
    final = detail_df[detail_df["query"] == FINAL_QUERY].copy()
    sectors = [
        sector
        for sector in ["building", "industry", "transportation"]
        if sector in set(final["sector"].dropna().astype(str))
    ]
    colors = {
        "building": "#7570b3",
        "industry": "#d95f02",
        "transportation": "#1b9e77",
    }

    fig, axes = plt.subplots(1, 5, figsize=(22, 4.8), sharey=True)
    for idx, scenario in enumerate(SCENARIOS):
        ax = axes[idx]
        subset = final[final["scenario"] == scenario]
        for sector in sectors:
            series = subset[subset["sector"] == sector].sort_values("year")
            ax.plot(
                series["year"],
                series["delta_value"],
                linewidth=2,
                label=sector,
                color=colors.get(sector, None),
            )
        ax.axhline(0, color="#999999", linewidth=1)
        ax.set_title(scenario.replace("GCAM_", ""))
        ax.set_xlabel("Year")
        apply_common_axis_style(ax)
        if idx == 0:
            ax.set_ylabel("EV - baseline (EJ)")

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        ncol=len(sectors),
        frameon=False,
    )
    fig.suptitle("Final energy delta by aggregate sector", fontsize=16, y=1.04)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_primary_fuel_heatmap(detail_df: pd.DataFrame, out_path: Path):
    primary = detail_df[detail_df["query"] == PRIMARY_QUERY].copy()
    fuels = sorted(primary["fuel"].dropna().astype(str).unique().tolist())
    years = sorted(primary["year"].dropna().astype(int).unique().tolist())

    vmax = primary["delta_value"].abs().max()
    vmax = 1.0 if pd.isna(vmax) or vmax == 0 else float(vmax)

    fig, axes = plt.subplots(1, 5, figsize=(24, 8), sharey=True, constrained_layout=True)
    for idx, scenario in enumerate(SCENARIOS):
        ax = axes[idx]
        subset = primary[primary["scenario"] == scenario]
        pivot = (
            subset.pivot(index="fuel", columns="year", values="delta_value")
            .reindex(index=fuels, columns=years)
        )
        image = ax.imshow(
            pivot.to_numpy(),
            aspect="auto",
            cmap="RdBu_r",
            vmin=-vmax,
            vmax=vmax,
        )
        ax.set_title(scenario.replace("GCAM_", ""))
        ax.set_xlabel("Year")
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels(years, rotation=90, fontsize=8)
        if idx == 0:
            ax.set_yticks(range(len(fuels)))
            ax.set_yticklabels(fuels, fontsize=9)
            ax.set_ylabel("Primary fuel")
        else:
            ax.set_yticks(range(len(fuels)))
            ax.set_yticklabels([])

    cbar = fig.colorbar(image, ax=axes, fraction=0.02, pad=0.02)
    cbar.set_label("EV - baseline (EJ)")
    fig.suptitle("Primary energy delta by fuel across all SSPs and years", fontsize=16, y=1.04)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    args = parse_args()
    detail_df = load_csv(args.detail)
    summary_df = load_csv(args.summary)

    report = validate_outputs(detail_df, summary_df)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "validation_report.json").write_text(
        json.dumps(report, indent=2)
    )

    plot_overview(summary_df, args.out_dir / "overview_before_after.png")
    plot_final_sector_delta(detail_df, args.out_dir / "final_energy_sector_delta.png")
    plot_primary_fuel_heatmap(detail_df, args.out_dir / "primary_energy_fuel_delta.png")

    print(f"Wrote validation report to {args.out_dir / 'validation_report.json'}")
    print(f"Wrote plot to {args.out_dir / 'overview_before_after.png'}")
    print(f"Wrote plot to {args.out_dir / 'final_energy_sector_delta.png'}")
    print(f"Wrote plot to {args.out_dir / 'primary_energy_fuel_delta.png'}")


if __name__ == "__main__":
    main()
