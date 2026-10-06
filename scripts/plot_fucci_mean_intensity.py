"""Plot green versus red FUCCI mean intensity from either feature table set.

Usage:
    python scripts/plot_fucci_mean_intensity.py \
      --input-root '/path/to/Archive (6).zip' \
      --output-prefix figs4paper/fucci_mean_intensity_7_panels

    python scripts/plot_fucci_mean_intensity.py --source old

The input may be a ZIP archive or a directory containing the three date folders.
The default is the replacement archive supplied on 2026-10-06.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


X = "Intensity_MeanIntensity_green"
Y = "Intensity_MeanIntensity_red"
X_LIMITS = (5e-4, 1)
Y_LIMITS = (5e-3, 2e-1)
COLORS = {"231005": "#268c76", "2409": "#d28a2e", "2410": "#7158a8"}
SOURCES = {
    "newer": {
        "folders": ("231005", "2409", "2410"),
        "filename": "object_features_new_withCellCycle.csv",
        "examples": (("231005", "231005", "1"), ("2409", "240918", "1"),
                     ("2410", "241016", "1")),
        "fofs": 31,
        "title": "newer feature tables",
        "output": "fucci_mean_intensity_7_panels",
    },
    "old": {
        "folders": ("231005", "2409"),
        "filename": "object_cellCycle_CellProfilerJuly9th2025.csv",
        "examples": (("231005", "231005", "1"), ("231005", "231005", "2"),
                     ("2409", "240918", "1"), ("2409", "240918", "2")),
        "fofs": 8,
        "title": "old CellProfiler tables",
        "output": "fucci_mean_intensity_old_7_panels",
    },
}


def read_csv_input(root: Path, relative_path: str, **kwargs) -> pd.DataFrame:
    if root.is_file():
        with ZipFile(root) as archive, archive.open(relative_path) as handle:
            return pd.read_csv(handle, **kwargs)
    return pd.read_csv(root / relative_path, **kwargs)


def read_data(root: Path, source: dict) -> pd.DataFrame:
    frames = []
    for folder in source["folders"]:
        frame = read_csv_input(
            root,
            f"{folder}/{source['filename']}",
            usecols=["Date", "FoF", X, Y],
            dtype={"Date": str, "FoF": str},
        )
        frame["folder"] = folder
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    if not np.isfinite(data[[X, Y]].to_numpy()).all() or (data[[X, Y]] <= 0).any().any():
        raise ValueError("Logarithmic axes require finite, positive intensities; no rows were filtered")
    for column, limits in ((X, X_LIMITS), (Y, Y_LIMITS)):
        if data[column].min() < limits[0] or data[column].max() > limits[1]:
            raise ValueError(f"Expand the axis limits to include all values in {column}")
    return data


def scatter(ax: plt.Axes, frame: pd.DataFrame, color: str, label: str | None = None) -> None:
    ax.scatter(frame[X], frame[Y], s=5, alpha=0.22, color=color, linewidths=0,
               rasterized=True, label=label)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path,
                        default=Path.home() / "Downloads" / "Archive (6).zip",
                        help="Replacement ZIP archive or directory containing the date folders")
    parser.add_argument("--source", choices=SOURCES, default="newer")
    parser.add_argument("--output-prefix", type=Path)
    args = parser.parse_args()

    source = SOURCES[args.source]
    output_prefix = args.output_prefix or Path("figs4paper") / source["output"]
    data = read_data(args.input_root, source)
    n_fofs = data[["Date", "FoF"]].drop_duplicates().shape[0]
    if n_fofs != source["fofs"]:
        raise ValueError(f"Expected {source['fofs']} distinct Date/FoF pairs, found {n_fofs}")

    fig, axes = plt.subplots(2, 4, figsize=(16, 8), sharex=True, sharey=True,
                             constrained_layout=True)
    for folder in source["folders"]:
        subset = data[data.folder == folder]
        scatter(axes[0, 0], subset, COLORS[folder], folder)
    axes[0, 0].set_title(f"All {n_fofs} FoFs (n={len(data):,} cells)")
    axes[0, 0].legend(title="Folder", loc="upper right", markerscale=3,
                      frameon=True, fontsize=8, title_fontsize=8)

    for ax, folder in zip(axes[0, 1:], source["folders"]):
        subset = data[data.folder == folder]
        scatter(ax, subset, COLORS[folder])
        n = subset[["Date", "FoF"]].drop_duplicates().shape[0]
        ax.set_title(f"{folder}: {n} FoFs (n={len(subset):,})")

    if len(source["folders"]) < 3:
        axes[0, 3].set_visible(False)

    for ax, (folder, date, fof) in zip(axes[1], source["examples"]):
        subset = data[(data.folder == folder) & (data.Date == date) & (data.FoF == fof)]
        if subset.empty:
            raise ValueError(f"No rows for example FoF {fof} on {date}")
        scatter(ax, subset, COLORS[folder])
        ax.set_title(f"{folder}: FoF {fof}, {date} (n={len(subset):,})")
    if len(source["examples"]) < 4:
        axes[1, 3].set_visible(False)

    for ax in axes.flat:
        if not ax.get_visible():
            continue
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(*X_LIMITS)
        ax.set_ylim(*Y_LIMITS)
        ax.grid(True, which="major", alpha=0.18, linewidth=0.5)
        ax.set_xlabel("Mean green intensity (log scale)")
        ax.set_ylabel("Mean red intensity (log scale)")
    fig.suptitle(f"FUCCI mean intensity per cell — {source['title']}", fontsize=15)

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "pdf"):
        path = output_prefix.with_suffix(f".{extension}")
        fig.savefig(path, dpi=220, facecolor="white")
        print(path)
    plt.close(fig)

    archive_sha256 = None
    if args.input_root.is_file():
        digest = hashlib.sha256()
        with args.input_root.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        archive_sha256 = digest.hexdigest()
    provenance = {
        "input": str(args.input_root.resolve()),
        "archive_sha256": archive_sha256,
        "source": args.source,
        "rows": len(data),
        "fofs": n_fofs,
        "tables": {f"{folder}/{source['filename']}": int((data.folder == folder).sum())
                   for folder in source["folders"]},
        "x": X,
        "y": Y,
        "x_limits": X_LIMITS,
        "y_limits": Y_LIMITS,
        "scale": "log",
        "examples_folder_date_fof": source["examples"],
        "excluded_rows": 0,
        "subsampled": False,
    }
    provenance_path = output_prefix.with_name(output_prefix.name + "_source.json")
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"{provenance_path} ({len(data):,} rows, {n_fofs} FoFs; no exclusions)")


if __name__ == "__main__":
    main()
