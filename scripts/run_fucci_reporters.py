#!/usr/bin/env python3
"""Run the accepted FUCCI reporter method on explicit single-field or batch inputs."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir())/"fucci_reporter_mpl"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir())/"fucci_reporter_cache"))

import pandas as pd

from fucci_analysis.data import write_json
from fucci_analysis.reporter_inputs import inventory, read_manifest, preflight, match_components, identity
from fucci_analysis.reporter_runner import DEFAULT_MODEL, STATES, load_model, run_field


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    inv = subs.add_parser("inventory", help="Build a manifest from all new feature tables; edit paths before running")
    inv.add_argument("--features-root", type=Path, required=True, help="Extracted feature root, single CSV, or ZIP")
    inv.add_argument("--images-root", type=Path, required=True, help="Parent of ImageSet directories")
    inv.add_argument("--masks-root", type=Path, required=True)
    inv.add_argument("--output", type=Path, required=True, help="New manifest CSV; refuses overwriting")
    single = subs.add_parser("field", help="Classify one Date/FoF from a CSV or ZIP member")
    single.add_argument("--folder", default="dataset", help="Source folder tag, e.g. 2410")
    single.add_argument("--date", required=True)
    single.add_argument("--fof", required=True)
    single.add_argument("--features", type=Path, required=True)
    single.add_argument("--features-member", default="", help="CSV member when --features is a ZIP")
    single.add_argument("--images", type=Path, required=True, help="One FoF directory of *_zNN_chCC.tif planes")
    single.add_argument("--mask", type=Path, required=True, help="Integer Z/Y/X TIFF or a ZIP containing it")
    single.add_argument("--mask-member", default="")
    single.add_argument("--green-channel", default="00")
    single.add_argument("--red-channel", default="02")
    batch = subs.add_parser("batch", help="Run every field in an explicit manifest")
    batch.add_argument("--manifest", type=Path, required=True)
    for sub in [single, batch]:
        sub.add_argument("--output", type=Path, required=True)
        sub.add_argument("--model", type=Path, default=DEFAULT_MODEL)
        sub.add_argument("--check", action="store_true", help="Check table/mask matching and image layout; do not measure intensities")
        sub.add_argument("--resume", action="store_true", help="Reuse completed fields only if all input/code/output hashes match")
        sub.add_argument("--no-plots", action="store_true", help="Save classifications and sensitivity tables without figures")
    return parser.parse_args()


def main():
    args = arguments()
    if args.command == "inventory":
        if args.output.exists(): raise ValueError(f"Manifest exists: {args.output}")
        frame = inventory(args.features_root, args.images_root, args.masks_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False)
        print(f"Wrote {len(frame)} fields to {args.output}; inspect path_note and edit paths before batch --check.")
        return 0
    model, bootstrap, model_hash = load_model(args.model)
    if args.command == "field":
        spec = vars(args).copy()
        for c in ["features", "images", "mask"]: spec[c] = str(spec[c].expanduser().resolve())
        spec["folder"], spec["date"], spec["fof"] = identity(spec["folder"], spec["date"], spec["fof"])
        specs = [spec]
    else:
        specs = read_manifest(args.manifest)
    output = args.output.expanduser().resolve()
    if not args.check and args.command == "batch":
        if output.exists() and not args.resume:
            raise ValueError(f"Batch output exists: {output}; use a new directory or --resume")
        output.mkdir(parents=True, exist_ok=True)
    status, complete = [], []
    for spec in specs:
        field_id = f"{spec['folder']}/{spec['date']}/{spec['fof']}"
        destination = output if args.command == "field" else output/spec["folder"]/f"{spec['date']}_FoF{spec['fof']}"
        try:
            if args.check:
                frame, mask, files, provenance = preflight(spec)
                components, units = match_components(frame, mask)
                print(f"{field_id}: inputs match, {len(units)} original labels; raw intensity matching occurs during the full run", flush=True)
                del frame, mask, components, units, files, provenance
            else:
                summary = run_field(spec, destination, model, bootstrap, model_hash, args.resume, not args.no_plots)
                complete.append((destination, summary))
            status.append({"field_id": field_id, "status": "checked" if args.check else "complete", "error": ""})
        except (ValueError, OSError, KeyError, AssertionError, RuntimeError) as error:
            print(f"{field_id}: ERROR: {error}", file=sys.stderr, flush=True)
            status.append({"field_id": field_id, "status": "error", "error": f"{type(error).__name__}: {error}"})
    failed = sum(s["status"] == "error" for s in status)
    if args.command == "batch" and not args.check:
        pd.DataFrame(status).to_csv(output/"field_status.csv", index=False)
        summaries = [{"field_id": s["field_id"], "n": s["n"], "promoted_n": s["promoted_n"],
                      "fallback_n": s["fallback_n"], **{f"{c}_n": s["counts"][c] for c in STATES}}
                     for _, s in complete]
        pd.DataFrame(summaries, columns=["field_id", "n", "promoted_n", "fallback_n", *[f"{c}_n" for c in STATES]]).to_csv(output/"counts_by_field.csv", index=False)
        # Write a header even if no field succeeded, clearing stale combined data on resume.
        combined = pd.concat([pd.read_csv(p/"cell_reporter_states.csv") for p, _ in complete], ignore_index=True) if complete else pd.DataFrame(columns=["unit_id", "field_id", "reporter_state"])
        combined.to_csv(output/"all_cell_reporter_states.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
        write_json(output/"batch_summary.json", {"requested_fields": len(specs), "completed_fields": len(complete),
            "failed_fields": failed, "all_requested_fields_complete": failed == 0,
            "completed_labels": len(combined), "model_sha256": model_hash,
            "scope": "Combined tables contain completed fields only; field_status.csv lists every requested field."})
    print(f"{len(specs)-failed}/{len(specs)} fields {'checked' if args.check else 'complete'}; {failed} errors.", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
