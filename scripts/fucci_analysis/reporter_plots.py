"""Field-independent inspection figures for the accepted reporter classifier."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
from skimage.segmentation import find_boundaries

from .outputs import save
from .reporter_runner import STATES

COLORS = {"green_only": "#23a765", "red_only": "#e34c5b", "both": "#c6a52a", "neither": "#7394ba"}


def render(data, geometry, display, limits, thresholds, z, out):
    field = data.field_id.iloc[0]
    legend = [Patch(color=COLORS[s], label=s.replace("_", " ")) for s in STATES]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    for ax, column, title in zip(axes, ["original_reporter_state", "reporter_state"], ["Original classifier, rerun", "Neither → both refinement"]):
        for state in ["neither", "both", "red_only", "green_only"]:
            d = data[data[column].eq(state)]
            ax.scatter(d.forced_green_score, d.forced_red_score, s=14, c=COLORS[state], alpha=.65, edgecolors="none", rasterized=True)
        ax.axvline(thresholds["green"]["high"], color=COLORS["green_only"], lw=1)
        ax.axhline(thresholds["red"]["high"], color=COLORS["red_only"], lw=1)
        if column == "reporter_state":
            ax.plot([thresholds["green"]["low"]]*2, [0, thresholds["red"]["high"]], "--", color=COLORS["green_only"], lw=1)
            ax.plot([0, thresholds["green"]["high"]], [thresholds["red"]["low"]]*2, "--", color=COLORS["red_only"], lw=1)
        ax.set_xscale("symlog", linthresh=.003); ax.set_yscale("symlog", linthresh=.003)
        ax.set(title=title, xlabel="Green mean above local reference", ylabel="Red mean above local reference")
        ax.grid(alpha=.12)
    fig.suptitle(f"{field} · all {len(data)} original labels, dominant components")
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.5, .03), ncol=4, frameon=False)
    fig.text(.5, .008, "Solid: original gates. Dashed: lower gates used only within original neither. No labels excluded.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .10, 1, .94)); save(fig, out/"reporter_scatter")

    scaled = {c: np.clip((display[c]-limits[c]["low"])/(limits[c]["high"]-limits[c]["low"]), 0, 1) for c in display}
    merged = np.stack([scaled["red"], scaled["green"], np.zeros_like(scaled["green"])], axis=-1)
    visible = data[data.geometry_id.isin(np.unique(geometry))]
    selected = np.zeros(int(geometry.max())+1, bool)
    selected[visible.geometry_id.to_numpy(int)] = True
    boundary = find_boundaries(geometry, mode="inner") & selected[geometry]
    merged[boundary] = .25*merged[boundary]+.75
    panels = [merged]
    for column in ["original_reporter_state", "reporter_state"]:
        palette = np.zeros((len(selected), 3))
        palette[visible.geometry_id.to_numpy(int)] = np.asarray([to_rgb(COLORS[s]) for s in visible[column]]).reshape(-1, 3)
        panels.append(palette[geometry])
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    for ax, im, title in zip(axes, panels, ["A  Green + red with cell boundaries", "B  Original reporter states", "C  Neither → both refinement"]):
        ax.imshow(im, interpolation="nearest"); ax.axis("off"); ax.set_title(title, loc="left", fontsize=12)
    for ax, column in zip(axes[1:], ["original_reporter_state", "reporter_state"]):
        counts = " / ".join(str(int(visible[column].eq(s).sum())) for s in STATES)
        ax.text(.5, -.035, f"Green / red / both / neither: {counts}", ha="center", transform=ax.transAxes)
    fig.suptitle(f"{field} · z={z} (zero-based) · {len(visible)} intersecting dominant components")
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.5, .04), ncol=4, frameon=False)
    fig.text(.5, .015, "Calls use 3D measurements. Display contrast is for inspection only; background and excluded fragments are black in B/C.", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .94)); save(fig, out/"reporter_map_middle_z")

    variants = pd.read_csv(out/"measurement_stability.csv")
    bootstrap = pd.read_csv(out/"bootstrap_counts.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    v = variants[variants.variant.ne("primary")]
    axes[0].barh(v.variant.str.replace("_", " "), v.changed_n, color=COLORS["both"])
    axes[0].invert_yaxis()
    axes[0].set(xlabel="Final state changes among finite pairs", title="11 measurement settings · fixed gates")
    axes[1].hist(bootstrap.both_n, bins=20, color=COLORS["both"], edgecolor="white")
    axes[1].axvline(data.reporter_state.eq("both").sum(), color="black", ls="--")
    axes[1].set(xlabel=f"Labels called both / {len(data)}", ylabel="Bootstrap fits", title="500 frozen FoF5 calibration resamples")
    fig.suptitle(f"{field} · sensitivity annotations")
    fig.text(.5, .015, "Missing variant scores are counted in measurement_stability.csv. FoF5 bootstrap frequencies do not establish transfer accuracy.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, .94)); save(fig, out/"classification_stability")
