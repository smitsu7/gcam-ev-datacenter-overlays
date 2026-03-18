#!/usr/bin/env python3
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_args():
    script_dir = Path(__file__).resolve().parent
    addon_root = script_dir.parent
    default_gcam = addon_root.parent / "gcam-v7.0-Mac_arm64-Release-Package"
    parser = argparse.ArgumentParser(
        description="Verify that batch_SSP_EV.xml only adds SSP-specific EV overlays on top of batch_SSP_REF.xml."
    )
    parser.add_argument("--gcam-root", type=Path, default=default_gcam)
    return parser.parse_args()


def collect_filesets(root: ET.Element):
    out = {}
    for fileset in root.findall("./ComponentSet/FileSet"):
        values = []
        for value in fileset.findall("./Value"):
            values.append((value.get("name"), (value.text or "").strip()))
        out[fileset.get("name")] = set(values)
    return out


def main():
    args = parse_args()
    ref_path = args.gcam_root / "exe" / "batch_SSP_REF.xml"
    ev_path = args.gcam_root / "exe" / "batch_SSP_EV.xml"

    ref = collect_filesets(ET.parse(ref_path).getroot())
    ev = collect_filesets(ET.parse(ev_path).getroot())

    expected_ssps = {"SSP1", "SSP2", "SSP3", "SSP4", "SSP5"}
    failures = []

    for name in sorted(expected_ssps):
        ref_values = ref.get(name, set())
        ev_values = ev.get(name, set())
        extra = ev_values - ref_values
        missing = ref_values - ev_values
        expected_extra = {("trn_ev", f"../input/gcamdata/xml/transportation_EV_{name}.xml")}

        if missing or extra != expected_extra:
            failures.append((name, sorted(extra), sorted(missing)))

    if failures:
        for name, extra, missing in failures:
            print(f"{name}: unexpected batch mismatch")
            print(f"  extra: {extra}")
            print(f"  missing: {missing}")
        raise SystemExit(1)

    print("batch_SSP_EV.xml is aligned with batch_SSP_REF.xml for SSP1-SSP5.")
    print("The only additional input in each SSP fileset is the EV transport overlay.")


if __name__ == "__main__":
    main()
