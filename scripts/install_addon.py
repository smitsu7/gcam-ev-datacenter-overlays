#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path


def parse_args():
    script_dir = Path(__file__).resolve().parent
    addon_root = script_dir.parent
    default_gcam = addon_root.parent / "gcam-v7.0-Mac_arm64-Release-Package"
    parser = argparse.ArgumentParser(description="Install generated EV SSP add-on files into a GCAM package.")
    parser.add_argument("--gcam-root", type=Path, default=default_gcam)
    return parser.parse_args()


def copy_tree(src_root: Path, dst_root: Path):
    for src in src_root.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(src_root)
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Installed {rel}")


def main():
    args = parse_args()
    addon_root = Path(__file__).resolve().parents[1]
    generated_root = addon_root / "generated"
    if not generated_root.exists():
        raise SystemExit(f"Generated files not found: {generated_root}")
    if not args.gcam_root.exists():
        raise SystemExit(f"GCAM root not found: {args.gcam_root}")
    copy_tree(generated_root, args.gcam_root)


if __name__ == "__main__":
    main()
