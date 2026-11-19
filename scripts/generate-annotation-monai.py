from __future__ import annotations

import argparse
from pathlib import Path

from tqdm import tqdm

from tooltip.annotation import (
    ANNOTATION_SUFFIX,
    CV2_IMPORT_ERROR,
    NUMPY_IMPORT_ERROR,
    build_auto_payload,
    load_binary_mask,
    write_annotation,
)
from tooltip.dataset_paths import (
    DATA_ROOT,
    resolve_path,
    segmentation_dir,
)


SPLIT_NAMES = ("train", "val", "test")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def annotation_monai_dir(name: str) -> Path:
    return DATA_ROOT / "dataset" / name / "annotation-monai"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate surgical-tool tip annotations from binary segmentation masks."
        )
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help=(
            "Dataset name, e.g. 'erop' or 'cholec80'. Used to resolve default "
            "--input/--output when not given explicitly."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Root directory containing train/val/test segmentation masks. Defaults to data/dataset/<dataset>/segmentation.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Root directory where train/val/test annotation JSON files will be saved. Defaults to data/dataset/<dataset>/annotation-monai.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate existing JSON files instead of skipping them.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if CV2_IMPORT_ERROR is not None:
        raise RuntimeError(
            "opencv-python is required to read segmentation masks. "
            "Install it and run the script again."
        ) from CV2_IMPORT_ERROR
    if NUMPY_IMPORT_ERROR is not None:
        raise RuntimeError(
            "numpy is required to analyze segmentation contours. "
            "Install it and run the script again."
        ) from NUMPY_IMPORT_ERROR

    if not args.input.exists():
        raise FileNotFoundError(f"Input directory does not exist: {args.input}")
    if not args.input.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {args.input}")

    for split_name in SPLIT_NAMES:
        split_dir = args.input / split_name
        if not split_dir.exists():
            raise FileNotFoundError(f"Split directory does not exist: {split_dir}")
        if not split_dir.is_dir():
            raise NotADirectoryError(f"Split path is not a directory: {split_dir}")


def ensure_output_dirs(output_root: Path) -> None:
    for split_name in SPLIT_NAMES:
        (output_root / split_name).mkdir(parents=True, exist_ok=True)


def _all_outputs_up_to_date(input_root: Path, output_root: Path) -> bool:
    for split_name in SPLIT_NAMES:
        for image_path in list_images(input_root / split_name):
            output_path = output_root / split_name / f"{image_path.stem}{ANNOTATION_SUFFIX}"
            if not output_path.exists():
                return False
    return True


def list_images(image_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def process_split(
    split_name: str,
    input_root: Path,
    output_root: Path,
    overwrite: bool,
) -> dict[str, int]:
    input_dir = input_root / split_name
    output_dir = output_root / split_name
    image_paths = list_images(input_dir)

    counts = {"saved": 0, "skipped": 0}

    for image_path in tqdm(image_paths, desc=split_name, unit="image", ascii=True, ncols=100):
        output_path = output_dir / f"{image_path.stem}{ANNOTATION_SUFFIX}"

        if output_path.exists() and not overwrite:
            counts["skipped"] += 1
            continue

        mask = load_binary_mask(image_path)
        write_annotation(output_path, build_auto_payload(image_path, mask))
        counts["saved"] += 1

    return counts


def main() -> int:
    args = parse_args()
    args.input = resolve_path(args.input, args.dataset, segmentation_dir, "--input")
    args.output = resolve_path(args.output, args.dataset, annotation_monai_dir, "--output")
    validate_args(args)
    ensure_output_dirs(args.output)

    if not args.overwrite and _all_outputs_up_to_date(args.input, args.output):
        print("All annotation files already exist. Nothing to do.")
        return 0

    totals = {split_name: {} for split_name in SPLIT_NAMES}

    for split_name in SPLIT_NAMES:
        totals[split_name] = process_split(
            split_name=split_name,
            input_root=args.input,
            output_root=args.output,
            overwrite=args.overwrite,
        )

    print("Annotation generation complete.")
    for split_name in SPLIT_NAMES:
        counts = totals[split_name]
        print(f"{split_name}: saved={counts['saved']}, skipped={counts['skipped']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Files saved so far are kept; run the same command again to continue.")
        raise SystemExit(130)
