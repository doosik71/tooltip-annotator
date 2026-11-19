"""Print per-dataset train/val/test frame counts and label counts per source.

For each split of each dataset under data/dataset/:

- frames:  image files in images/{split}/, and their share of the dataset.
- default: frames with a label in annotation/{split}/ (final labels kept by
           annotation-editor).
- manual:  frames with a label in annotation-manual/{split}/ (human corrected).
- one column per other annotation-<name>/ directory (monai, opus, qwen, ...),
  found on disk like the editor's tabs.

Label ratios are relative to the split's frame count.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from tooltip.annotation import ANNOTATION_SUFFIX
from tooltip.dataset_paths import (
    annotation_dir,
    annotation_manual_dir,
    images_dir,
    list_datasets,
)


SPLIT_NAMES = ("train", "val", "test")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
AUTO_DIR_PREFIX = "annotation-"
CELL_WIDTH = 17


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print train/val/test frame counts and label counts for every "
            "annotation source of each dataset."
        )
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Dataset name to report. Defaults to every dataset found.",
    )
    return parser.parse_args()


def stems(directory: Path, extensions: set[str]) -> set[str]:
    """File stems in `directory` with one of `extensions`; empty if missing."""
    if not directory.is_dir():
        return set()
    # os.scandir: splits hold ~100k files, so avoid building Path objects.
    with os.scandir(directory) as entries:
        return {
            stem
            for stem, ext in (os.path.splitext(e.name) for e in entries)
            if ext.lower() in extensions
        }


def cell(part: int, whole: int) -> str:
    """`part` followed by its share of `whole` in parentheses."""
    ratio = f"{100.0 * part / whole:5.1f}%" if whole else "     -"
    return f"{part:>8,} ({ratio})"


def annotation_sources(dataset: str) -> list[tuple[str, Path]]:
    """(column name, root) for default, manual, then each annotation-<name>/ dir."""
    default_root = annotation_dir(dataset)
    manual_root = annotation_manual_dir(dataset)
    sources = [("default", default_root), ("manual", manual_root)]
    for path in sorted(default_root.parent.glob(f"{AUTO_DIR_PREFIX}*")):
        if not path.is_dir() or path.name == manual_root.name:
            continue
        sources.append((path.name.removeprefix(AUTO_DIR_PREFIX), path))
    return sources


def report(dataset: str) -> None:
    sources = annotation_sources(dataset)
    rows = []
    for split in SPLIT_NAMES:
        counts = [len(stems(images_dir(dataset) / split, IMAGE_EXTENSIONS))]
        counts += [len(stems(root / split, {ANNOTATION_SUFFIX})) for _, root in sources]
        rows.append((split, counts))

    totals = [sum(counts[i] for _, counts in rows) for i in range(len(sources) + 1)]
    rows.append(("total", totals))
    n_total = totals[0]

    names = ["frames", *(name for name, _ in sources)]
    print(f"[{dataset}]")
    print(f"  {'split':<6}" + "".join(f"  {name + ' (ratio)':>{CELL_WIDTH}}" for name in names))
    for split, (n_frames, *n_labels) in rows:
        cells = [cell(n_frames, n_total), *(cell(n, n_frames) for n in n_labels)]
        print(f"  {split:<6}" + "".join(f"  {c:>{CELL_WIDTH}}" for c in cells))
    print()


def main() -> int:
    args = parse_args()
    datasets = [args.dataset] if args.dataset else list_datasets()
    if not datasets:
        print("No datasets found under data/dataset-src or data/dataset.")
        return 1
    for dataset in datasets:
        report(dataset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
