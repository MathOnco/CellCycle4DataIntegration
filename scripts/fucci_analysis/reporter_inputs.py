"""Explicit, portable inputs for the accepted FUCCI reporter classifier."""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage
from skimage import measure
import tifffile

from .data import sha256
from .review import normalized_plane

BOXES = [f"AreaShape_BoundingBox{side}_{axis}" for side in ["Minimum", "Maximum"] for axis in "XYZ"]
MEANS = [f"Intensity_{stat}_{c}" for c in ["green", "red"] for stat in ["MeanIntensity", "IntegratedIntensity"]]
REQUIRED = ["Date", "FoF", "ObjectNumber", "CellposeLabel", "AreaShape_Volume", *BOXES, *MEANS]
OPTIONAL = ["CellID", "ImageSet", "FileName_mask"]
INPUT_COLUMNS = ["folder", "date", "fof", "features", "features_member", "images", "mask", "mask_member", "green_channel", "red_channel"]


def identity(folder, date, fof):
    folder = str(folder or "dataset")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", folder) or not re.fullmatch(r"\d+", str(date)) or not re.fullmatch(r"\d+", str(fof)):
        raise ValueError("folder must contain letters/digits/_/-, and date and fof must contain digits")
    return folder, str(int(date)), str(int(fof))


@lru_cache(maxsize=8)
def feature_table(path_string, member=""):
    path = Path(path_string)
    if member:
        with zipfile.ZipFile(path) as archive:
            payload = archive.read(member)
        source = io.BytesIO(payload)
        digest = hashlib.sha256(payload).hexdigest()
    else:
        if path.suffix.lower() == ".zip":
            raise ValueError("Specify features_member for a feature ZIP")
        source = path
        digest = sha256(path)
    frame = pd.read_csv(source, usecols=lambda c: c in REQUIRED+OPTIONAL, dtype={"Date": str, "FoF": str})
    missing = set(REQUIRED)-set(frame)
    if missing:
        raise ValueError(f"Feature table missing columns: {sorted(missing)}")
    return frame, {"path": str(path), "member": member, "table_sha256": digest}


def select_field(spec):
    folder, date, fof = identity(spec.get("folder", ""), spec["date"], spec["fof"])
    table, provenance = feature_table(str(Path(spec["features"]).resolve()), spec.get("features_member", ""))
    frame = table[table.Date.eq(date) & table.FoF.eq(fof)].copy().sort_values("ObjectNumber")
    if frame.empty:
        raise ValueError(f"No feature rows for {folder}/{date}/{fof}")
    for column in ["ObjectNumber", "CellposeLabel", "AreaShape_Volume", *BOXES]:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(float)
        if not np.isfinite(values).all() or not np.equal(values, np.floor(values)).all() or (values < 0).any():
            raise ValueError(f"Expected nonnegative integers in {column}")
        frame[column] = values.astype(np.int64)
    if (frame[["ObjectNumber", "CellposeLabel", "AreaShape_Volume"]] <= 0).any().any():
        raise ValueError("Object numbers, parent labels and volumes must be positive")
    if frame.ObjectNumber.duplicated().any():
        raise ValueError("Duplicate ObjectNumber within the selected field")
    if not np.isfinite(frame[MEANS].to_numpy(float)).all():
        raise ValueError("Nonfinite source intensity measurements")
    frame["folder"] = folder
    frame["field_id"] = f"{folder}/{date}/{fof}"
    return frame.reset_index(drop=True), provenance


def read_mask(path, member=""):
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            if not member:
                candidates = [name for name in archive.namelist() if not name.startswith("__MACOSX/")
                              and not Path(name).name.startswith("._")
                              and name.lower().endswith((".tif", ".tiff")) and "mask" in Path(name).name.lower()]
                if len(candidates) != 1:
                    raise ValueError("Mask ZIP must have exactly one mask TIFF, or specify mask_member")
                member = candidates[0]
            payload = archive.read(member)
        mask = tifffile.imread(io.BytesIO(payload))
        digest = hashlib.sha256(payload).hexdigest()
    else:
        if member: raise ValueError("mask_member is only valid with a ZIP")
        mask = tifffile.imread(path)
        digest = sha256(path)
    if mask.ndim != 3 or not np.issubdtype(mask.dtype, np.integer) or (mask < 0).any():
        raise ValueError("Mask must be a nonnegative integer TIFF in Z,Y,X order, with background 0")
    if not mask.any(): raise ValueError("Mask contains no labeled objects")
    return mask, {"path": str(path.resolve()), "member": member, "tiff_sha256": digest, "shape_zyx": list(mask.shape)}


def match_components(frame, mask):
    # Preserve distinct integer labels while splitting disconnected pieces,
    # exactly as in the exporter and accepted FoF5 verification.
    components = measure.label(mask, background=0, connectivity=3).astype(np.int32)
    ids = frame.ObjectNumber.to_numpy(int)
    if not np.array_equal(ids, np.arange(1, int(components.max())+1)):
        raise ValueError("Mask component IDs do not match every ObjectNumber in the selected table")
    volumes = np.bincount(components.ravel())
    if not np.array_equal(volumes[ids], frame.AreaShape_Volume):
        raise ValueError("Mask component volumes differ from the feature table")
    if frame.CellposeLabel.max() > np.iinfo(mask.dtype).max:
        raise ValueError("CellposeLabel exceeds the mask's integer range")
    parents = np.zeros(len(volumes), dtype=mask.dtype)
    parents[ids] = frame.CellposeLabel.to_numpy()
    for z in range(len(mask)):
        if not np.array_equal(parents[components[z]], mask[z]):
            raise ValueError("CellposeLabel does not match the original mask labels")
    boxes = ndimage.find_objects(components)
    for axis, position in zip("XYZ", [2, 1, 0]):
        for side, attr in [("Minimum", "start"), ("Maximum", "stop")]:
            if not np.array_equal([getattr(box[position], attr) for box in boxes], frame[f"AreaShape_BoundingBox{side}_{axis}"]):
                raise ValueError(f"Mask/table bounding-box mismatch: {side}_{axis}")
    # Stable tie break: smaller ObjectNumber, equivalent to first occurrence in
    # the original table's component ordering when volumes tie.
    units = frame.sort_values(["AreaShape_Volume", "ObjectNumber"], ascending=[False, True]).drop_duplicates("CellposeLabel").sort_values("CellposeLabel").copy()
    by = frame.groupby("CellposeLabel")
    units["n_components"] = units.CellposeLabel.map(by.size())
    units["parent_volume"] = units.CellposeLabel.map(by.AreaShape_Volume.sum())
    units["volume"] = units.AreaShape_Volume
    units["dominant_fraction"] = units.volume/units.parent_volume
    units["geometry_id"] = units.ObjectNumber
    units["unit_id"] = units.field_id+"/mask_"+units.CellposeLabel.astype(str)
    return components, units.reset_index(drop=True)


def image_files(directory, channel, depth):
    found = {}
    if not re.fullmatch(r"\d+", str(channel)): raise ValueError("Channel identifiers must contain digits")
    pattern = re.compile(rf"_z(\d+)_ch{re.escape(str(channel))}\.tiff?$", re.IGNORECASE)
    for path in Path(directory).iterdir():
        match = pattern.search(path.name)
        if match:
            z = int(match.group(1))
            if z in found: raise ValueError(f"Duplicate z={z}, channel {channel} in {directory}")
            found[z] = path
    if set(found) != set(range(depth)):
        raise ValueError(f"Channel {channel} must contain exactly z=0..{depth-1}; missing={sorted(set(range(depth))-set(found))}, extra={sorted(set(found)-set(range(depth)))}")
    return [found[z] for z in range(depth)]


def read_plane(path, shape):
    with tifffile.TiffFile(path) as tif:
        if len(tif.pages) != 1 or tif.pages[0].dtype != np.dtype("uint16"):
            raise ValueError(f"Expected one uint16 plane (normalization /65535): {path}")
    plane = normalized_plane(path)
    if plane.shape != tuple(shape): raise ValueError(f"Image/mask dimensions differ: {path}")
    return plane


def preflight(spec):
    frame, features = select_field(spec)
    mask, mask_info = read_mask(spec["mask"], spec.get("mask_member", ""))
    files, records = {}, []
    if spec.get("green_channel", "00") == spec.get("red_channel", "02"):
        raise ValueError("Green and red must be different channels")
    for c, default in [("green", "00"), ("red", "02")]:
        files[c] = image_files(spec["images"], spec.get(f"{c}_channel", default), len(mask))
        for z, path in enumerate(files[c]):
            with tifffile.TiffFile(path) as tif:
                if len(tif.pages) != 1 or tif.pages[0].shape != mask.shape[1:] or tif.pages[0].dtype != np.dtype("uint16"):
                    raise ValueError(f"Expected uint16 plane with mask X/Y dimensions: {path}")
            records.append({"channel": c, "z": z, "path": str(path.resolve()), "sha256": sha256(path)})
    return frame, mask, files, {"features": features, "mask": mask_info, "image_files": records}


def read_manifest(path):
    path = Path(path).resolve()
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not {"date", "fof", "features", "images", "mask"} <= set(table):
        raise ValueError("Manifest requires date, fof, features, images, mask columns")
    specs, keys = [], set()
    for row in table.to_dict("records"):
        row = {k: row.get(k, "").strip() for k in INPUT_COLUMNS}
        row["folder"], row["date"], row["fof"] = identity(row["folder"], row["date"], row["fof"])
        key = (row["folder"], row["date"], row["fof"])
        if key in keys: raise ValueError(f"Duplicate field in manifest: {key}")
        keys.add(key)
        for c in ["features", "images", "mask"]:
            if not row[c]: raise ValueError(f"Missing {c} path for {key}")
            p = Path(row[c]).expanduser()
            row[c] = str((path.parent/p).resolve() if not p.is_absolute() else p.resolve())
        row["green_channel"] = row["green_channel"] or "00"
        row["red_channel"] = row["red_channel"] or "02"
        specs.append(row)
    if not specs: raise ValueError("Empty field manifest")
    return specs


def inventory(features_root, images_root, masks_root):
    root = Path(features_root).expanduser().resolve()
    if root.is_file() and root.suffix.lower() == ".zip":
        with zipfile.ZipFile(root) as archive:
            sources = [(root, name) for name in sorted(archive.namelist())
                       if Path(name).name == "object_features_new.csv" and not name.startswith("__MACOSX/")]
    elif root.is_file():
        sources = [(root, "")]
    else:
        sources = [(path, "") for path in sorted(root.rglob("object_features_new.csv"))]
    if not sources: raise ValueError("No object_features_new.csv tables found")
    rows = []
    for path, member in sources:
        table, _ = feature_table(str(path), member)
        if not {"ImageSet", "FileName_mask"} <= set(table):
            raise ValueError("Inventory requires ImageSet and FileName_mask; alternatively write a manifest manually")
        folder = Path(member).parent.name if member else path.parent.name
        for (date, fof), frame in table.groupby(["Date", "FoF"], sort=True):
            if frame.ImageSet.nunique() != 1 or frame.FileName_mask.nunique() != 1:
                raise ValueError(f"Multiple image/mask sets for {date}/{fof}; supply an explicit manifest")
            image_set, mask_name = str(frame.ImageSet.iloc[0]), Path(str(frame.FileName_mask.iloc[0])).name
            if Path(image_set).name != image_set: raise ValueError("ImageSet must be a directory name")
            images = Path(images_root).expanduser().resolve()/image_set
            base = Path(masks_root).expanduser().resolve()
            candidates = [base/image_set/mask_name, base/mask_name, base/f"{image_set}.zip"]
            present = [p for p in candidates if p.exists()]
            mask = present[0] if len(present) == 1 else candidates[0]
            rows.append({"folder": folder, "date": date, "fof": fof, "features": str(path),
                         "features_member": member, "images": str(images), "mask": str(mask), "mask_member": "",
                         "green_channel": "00", "red_channel": "02", "images_exist": images.is_dir(),
                         "mask_candidates_found": len(present), "path_note": "choose mask explicitly" if len(present)>1 else ("" if present else "mask missing; edit path")})
    result = pd.DataFrame(rows)
    if result.duplicated(["folder", "date", "fof"]).any(): raise ValueError("Duplicate field across source tables")
    return result
