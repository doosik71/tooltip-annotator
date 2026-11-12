"""Print per-dataset train/val/test frame counts and manual/auto label counts.

For each split of each dataset under data/dataset/:

- frames: image files in images/{split}/, and their share of the dataset.
- manual: frames with a label in annotation-manual/{split}/ (human corrected).
- auto:   frames with a label in annotation/{split}/ but none in
          annotation-manual/{split}/ (generated, incl. detector relabels).

The manual/auto ratios are relative to the split's frame count.
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print train/val/test frame counts and manual/auto label counts "
            "for each dataset."
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
    return f"{part:>9,} ({ratio})"


def report(dataset: str) -> None:
    rows = []
    for split in SPLIT_NAMES:
        frames = stems(images_dir(dataset) / split, IMAGE_EXTENSIONS)
        labels = stems(annotation_dir(dataset) / split, {ANNOTATION_SUFFIX})
        manual = stems(annotation_manual_dir(dataset) / split, {ANNOTATION_SUFFIX})
        rows.append((split, len(frames), len(manual), len(labels - manual)))

    total = tuple(sum(row[i] for row in rows) for i in (1, 2, 3))
    rows.append(("total", *total))
    n_total = total[0]

    print(f"[{dataset}]")
    print(
        f"  {'split':<6} {'frames (ratio)':>18}"
        f"   {'manual (ratio)':>18}   {'auto (ratio)':>18}"
    )
    for split, n_frames, n_manual, n_auto in rows:
        print(
            f"  {split:<6} {cell(n_frames, n_total)}"
            f"   {cell(n_manual, n_frames)}   {cell(n_auto, n_frames)}"
        )
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
