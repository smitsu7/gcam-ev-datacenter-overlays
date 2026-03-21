#!/usr/bin/env python3
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


YEAR_RE = re.compile(r"^\d{4}$")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Combine baseline, EV, and EV+datacenter SSP batch-query CSV outputs."
    )
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--ev", type=Path, required=True)
    parser.add_argument("--ev-dc", type=Path, required=True, dest="ev_dc")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    return parser.parse_args()


def clean_header(value: str) -> str:
    return value.strip()


def clean_value(value: str) -> str:
    if value is None:
        return ""
    return value.strip()


def parse_number(value: str):
    value = clean_value(value)
    if value == "":
        return None
    return float(value)


def parse_batch_csv(path: Path):
    lines = path.read_text().splitlines()
    sections = []
    idx = 0
    while idx < len(lines):
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        if idx + 1 >= len(lines):
            break
        title = lines[idx].strip()
        header_line = lines[idx + 1]
        if "," in title or not header_line.startswith("scenario,"):
            idx += 1
            continue

        header = [clean_header(col) for col in next(csv.reader([header_line]))]
        while header and header[-1] == "":
            header.pop()

        idx += 2
        rows = []
        while idx < len(lines):
            line = lines[idx]
            if not line.strip():
                idx += 1
                break
            if idx + 1 < len(lines) and "," not in line and lines[idx + 1].startswith("scenario,"):
                break

            values = [clean_value(col) for col in next(csv.reader([line]))]
            while values and values[-1] == "":
                values.pop()
            if len(values) < len(header):
                values.extend([""] * (len(header) - len(values)))
            elif len(values) > len(header):
                values = values[:len(header)]
            rows.append(dict(zip(header, values)))
            idx += 1

        sections.append((title, rows))
    return sections


def normalize_records(path: Path):
    records = []
    observed_dims = set()

    for query_title, rows in parse_batch_csv(path):
        for row in rows:
            normalized = {clean_header(k): clean_value(v) for k, v in row.items() if k is not None}
            units = normalized.pop("Units", "")
            normalized.pop("", None)
            scenario_full = normalized.get("scenario", "")
            scenario_name = scenario_full.split(",date=")[0] if scenario_full else ""

            year_cols = sorted([key for key in normalized if YEAR_RE.match(key)])
            dim_cols = [key for key in normalized if key not in year_cols and key != "scenario"]
            observed_dims.update(dim_cols)

            for year in year_cols:
                records.append(
                    {
                        "query": query_title,
                        "scenario": scenario_name,
                        "year": year,
                        "units": units,
                        "value": parse_number(normalized[year]),
                        **{dim: normalized[dim] for dim in dim_cols},
                    }
                )

    return records, observed_dims


def difference(a, b):
    if a is None and b is None:
        return None
    return (0.0 if a is None else a) - (0.0 if b is None else b)


def merge_records(baseline_records, ev_records, ev_dc_records, dimension_fields):
    def make_key(rec):
        return tuple(
            [rec.get("query", ""), rec.get("scenario", ""), rec.get("year", ""), rec.get("units", "")]
            + [rec.get(dim, "") for dim in dimension_fields]
        )

    baseline_map = {make_key(rec): rec for rec in baseline_records}
    ev_map = {make_key(rec): rec for rec in ev_records}
    ev_dc_map = {make_key(rec): rec for rec in ev_dc_records}
    keys = sorted(set(baseline_map) | set(ev_map) | set(ev_dc_map))

    merged = []
    summary = defaultdict(lambda: {"baseline": 0.0, "ev": 0.0, "ev_dc": 0.0})

    for key in keys:
        baseline = baseline_map.get(key, {})
        ev = ev_map.get(key, {})
        ev_dc = ev_dc_map.get(key, {})

        baseline_value = baseline.get("value")
        ev_value = ev.get("value")
        ev_dc_value = ev_dc.get("value")

        row = {
            "query": key[0],
            "scenario": key[1],
            "year": key[2],
            "units": key[3],
            "baseline_value": baseline_value,
            "ev_value": ev_value,
            "ev_dc_value": ev_dc_value,
            "ev_minus_baseline": difference(ev_value, baseline_value),
            "ev_dc_minus_baseline": difference(ev_dc_value, baseline_value),
            "ev_dc_minus_ev": difference(ev_dc_value, ev_value),
        }
        for idx, dim in enumerate(dimension_fields, start=4):
            row[dim] = key[idx]
        merged.append(row)

        summary_key = (key[0], key[1], key[2], key[3])
        if baseline_value is not None:
            summary[summary_key]["baseline"] += baseline_value
        if ev_value is not None:
            summary[summary_key]["ev"] += ev_value
        if ev_dc_value is not None:
            summary[summary_key]["ev_dc"] += ev_dc_value

    summary_rows = []
    for (query, scenario, year, units), values in sorted(summary.items()):
        summary_rows.append(
            {
                "query": query,
                "scenario": scenario,
                "year": year,
                "units": units,
                "baseline_value": values["baseline"],
                "ev_value": values["ev"],
                "ev_dc_value": values["ev_dc"],
                "ev_minus_baseline": values["ev"] - values["baseline"],
                "ev_dc_minus_baseline": values["ev_dc"] - values["baseline"],
                "ev_dc_minus_ev": values["ev_dc"] - values["ev"],
            }
        )

    return merged, summary_rows


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    args = parse_args()
    baseline_records, baseline_dims = normalize_records(args.baseline)
    ev_records, ev_dims = normalize_records(args.ev)
    ev_dc_records, ev_dc_dims = normalize_records(args.ev_dc)
    dimension_fields = sorted(baseline_dims | ev_dims | ev_dc_dims)

    merged_rows, summary_rows = merge_records(
        baseline_records,
        ev_records,
        ev_dc_records,
        dimension_fields,
    )

    detail_fields = (
        ["query", "scenario"]
        + dimension_fields
        + [
            "year",
            "units",
            "baseline_value",
            "ev_value",
            "ev_dc_value",
            "ev_minus_baseline",
            "ev_dc_minus_baseline",
            "ev_dc_minus_ev",
        ]
    )
    summary_fields = [
        "query",
        "scenario",
        "year",
        "units",
        "baseline_value",
        "ev_value",
        "ev_dc_value",
        "ev_minus_baseline",
        "ev_dc_minus_baseline",
        "ev_dc_minus_ev",
    ]

    write_csv(args.out, merged_rows, detail_fields)
    write_csv(args.summary, summary_rows, summary_fields)

    print(f"Wrote detailed comparison to {args.out}")
    print(f"Wrote summary comparison to {args.summary}")


if __name__ == "__main__":
    main()
