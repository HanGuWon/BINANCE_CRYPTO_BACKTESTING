"""Compare frozen cohort membership before and after the integrity repair."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd


KEY_COLUMNS = ["market", "universe_month", "symbol", "selected_top20", "selected_top50", "selected_top100"]


def _normalized_membership(frame):
    columns = frame[KEY_COLUMNS].copy()
    for name in ("selected_top20", "selected_top50", "selected_top100"):
        columns[name] = columns[name].astype(bool)
    return columns.sort_values(["market", "universe_month", "symbol"]).reset_index(drop=True)


def membership_hash(frame):
    ordered = _normalized_membership(frame)
    lines = []
    for row in ordered.itertuples(index=False, name=None):
        fields = [str(value).lower() if isinstance(value, bool) else str(value) for value in row]
        joined = "|".join(fields)
        lines.append(joined)
    payload = chr(10).join(lines)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest


def membership_changes(before, after):
    old_names = {name: name + "_old" for name in KEY_COLUMNS[3:]}
    new_names = {name: name + "_new" for name in KEY_COLUMNS[3:]}
    old = _normalized_membership(before).rename(columns=old_names)
    new = _normalized_membership(after).rename(columns=new_names)
    merged = old.merge(new, on=["market", "universe_month", "symbol"], how="outer")
    changed = merged[
        merged["selected_top20_old"].fillna(False).ne(merged["selected_top20_new"].fillna(False))
        | merged["selected_top50_old"].fillna(False).ne(merged["selected_top50_new"].fillna(False))
        | merged["selected_top100_old"].fillna(False).ne(merged["selected_top100_new"].fillna(False))
    ].copy()
    changed["membership_changed"] = True
    return changed


def _write_text(path, content):
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("campaigns/r1_final_panel_v1"))
    args = parser.parse_args()
    before = pd.read_csv(args.before)
    after = pd.read_csv(args.after)
    before_hash = membership_hash(before)
    after_hash = membership_hash(after)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    before_path = args.output_dir / "cohort_membership_before_fix.sha256"
    after_path = args.output_dir / "cohort_membership_after_fix.sha256"
    _write_text(before_path, before_hash + chr(10))
    _write_text(after_path, after_hash + chr(10))
    changed = membership_changes(before, after)
    changed.to_csv(args.output_dir / "cohort_membership_diff.csv", index=False)
    print({"before_sha256": before_hash, "after_sha256": after_hash, "changed_membership_rows": int(len(changed))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
