#!/usr/bin/env python3
"""Execute the FUCCI implementation plan in auditable stages."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "fucci_mpl_cache"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "fucci_xdg_cache"))
import matplotlib
matplotlib.use("Agg")
import pandas as pd

from fucci_analysis.data import load_inputs, aggregate_mask_labels, audit_units, image_inventory, write_json
from fucci_analysis.evaluate import evaluate_models, sensitivity, export_predictions
from fucci_analysis.outputs import figures, feature_diagnostics, report
from fucci_analysis.review import check_raw_images, create_review_sheets


def main():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "fucci_analysis/config.json")
    parser.add_argument("--stage", choices=["all", "audit", "fit", "review", "report"], default="all")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.archive:
        config["archive"] = str(args.archive)
    out = repo / "results/fucci_classification"
    figs = repo / "figs4paper/fucci_classification"
    out.mkdir(parents=True, exist_ok=True); figs.mkdir(parents=True, exist_ok=True)
    print("Stage 1: validate source rows and reproduce supplied gates", flush=True)
    previous_manifest = json.loads((out / "input_manifest.json").read_text()) if (out / "input_manifest.json").exists() else None
    objects, manifest = load_inputs(config, out)
    if args.stage not in ["all", "audit"] and previous_manifest and previous_manifest["archive_sha256"] != manifest["archive_sha256"]:
        raise ValueError("Input archive changed; run --stage all to regenerate dependent artifacts")
    labels = aggregate_mask_labels(objects)
    audit_units(objects, labels, out)
    feature_diagnostics(objects, labels, out)
    print(f"  {len(objects):,} objects; {len(labels):,} mask labels; all supplied labels reproduced", flush=True)
    if args.stage in ["all", "audit"]:
        print("Stages 2–3: masks, image compatibility, and measurement audit", flush=True)
        inventory = image_inventory(objects, labels, repo, out)
        inventory = check_raw_images(objects, inventory, config, out)
        print(f"  {inventory.mask_components_match.sum()} compatible masks; {inventory.image_measurements_match.sum()} fields pass sampled raw-image checks", flush=True)
    if args.stage == "audit":
        return
    if args.stage in ["all", "fit"]:
        print("Stages 4–5: candidate reporter models and grouped validation", flush=True)
        selected, fitted, oof, selection = evaluate_models(labels, config, out)
        print(f"  selected {selected}; running sensitivity comparisons", flush=True)
        object_p, gate_sensitive = sensitivity(labels, objects, fitted, selected, config, out)
        labels, predicted = export_predictions(objects, labels, fitted, oof, object_p, config, out, gate_sensitive)
    else:
        labels = pd.read_csv(out / "mask_label_predictions.csv.gz", dtype={c: str for c in ["folder", "Date", "FoF", "CellposeLabel"]})
        selection = json.loads((out / "model_selection.json").read_text())
    if args.stage == "fit":
        print("  predictions and all source mappings saved", flush=True)
        return
    inventory = pd.read_csv(out / "image_inventory.csv", dtype={"field_id": str}).fillna({"image_dir": "", "mask_path": ""})
    if args.stage in ["all", "review"]:
        print("Stage 6: review panels and annotation templates", flush=True)
        review_count = create_review_sheets(labels, objects, inventory, config, out, figs)
    else:
        review_count = len(pd.read_csv(out / "image_review_annotations.csv"))
    print("Stage 7: figures, results, and reproducibility record", flush=True)
    figures(objects, labels, out, figs)
    metrics = report(objects, labels, inventory, selection, config, repo, out, figs, review_count)
    source_files = [Path(__file__)] + sorted((Path(__file__).parent / "fucci_analysis").glob("*.py"))
    write_json(out / "implementation_versions.json", {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files})
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
