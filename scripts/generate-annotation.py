from __future__ import annotations

import argparse
import shutil
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
    annotation_dir,
    annotation_manual_dir,
    resolve_path,
    segmentation_dir,
)


SPLIT_NAMES = ("train", "val", "test")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


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
            "--input/--output/--manual when not given explicitly."
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
        help="Root directory where train/val/test annotation JSON files will be saved. Defaults to data/dataset/<dataset>/annotation.",
    )
    parser.add_argument(
        "--manual",
        type=Path,
        default=None,
        help=(
            "Root directory holding hand-corrected annotation JSON files, which "
            "always win over generated ones. Read-only to this script. Defaults "
            "to data/dataset/<dataset>/annotation-manual."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Regenerate existing JSON files instead of skipping them. Manual "
            "annotations are preserved either way."
        ),
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

    if args.manual.exists() and not args.manual.is_dir():
        raise NotADirectoryError(f"Manual path is not a directory: {args.manual}")


def ensure_output_dirs(output_root: Path) -> None:
    for split_name in SPLIT_NAMES:
        (output_root / split_name).mkdir(parents=True, exist_ok=True)


def _needs_materialize(manual_path: Path, output_path: Path) -> bool:
    """Report whether the generated copy still differs from the manual original."""
    if not output_path.exists():
        return True
    if manual_path.stat().st_size != output_path.stat().st_size:
        return True
    return manual_path.read_bytes() != output_path.read_bytes()


def _all_outputs_up_to_date(
    input_root: Path,
    output_root: Path,
    manual_root: Path,
) -> bool:
    for split_name in SPLIT_NAMES:
        manual_dir = manual_root / split_name
        manual_exists = manual_dir.is_dir()
        for image_path in list_images(input_root / split_name):
            output_path = output_root / split_name / f"{image_path.stem}{ANNOTATION_SUFFIX}"
            if not output_path.exists():
                return False
            if manual_exists:
                manual_path = manual_dir / f"{image_path.stem}{ANNOTATION_SUFFIX}"
                if manual_path.exists() and _needs_materialize(manual_path, output_path):
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
    manual_root: Path,
    overwrite: bool,
) -> dict[str, int]:
    input_dir = input_root / split_name
    output_dir = output_root / split_name
    manual_dir = manual_root / split_name
    manual_exists = manual_dir.is_dir()
    image_paths = list_images(input_dir)

    counts = {"saved": 0, "skipped": 0, "manual": 0, "restored": 0}

    for image_path in tqdm(image_paths, desc=split_name, unit="image", ascii=True, ncols=100):
        output_path = output_dir / f"{image_path.stem}{ANNOTATION_SUFFIX}"

        # A hand-corrected annotation always wins: it is copied over the
        # generated file and the mask is never re-analyzed for this frame.
        if manual_exists:
            manual_path = manual_dir / f"{image_path.stem}{ANNOTATION_SUFFIX}"
            if manual_path.exists():
                counts["manual"] += 1
                if _needs_materialize(manual_path, output_path):
                    shutil.copyfile(manual_path, output_path)
                    counts["restored"] += 1
                continue

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
    args.output = resolve_path(args.output, args.dataset, annotation_dir, "--output")
    args.manual = resolve_path(args.manual, args.dataset, annotation_manual_dir, "--manual")
    validate_args(args)
    ensure_output_dirs(args.output)

    if not args.overwrite and _all_outputs_up_to_date(args.input, args.output, args.manual):
        print("All annotation files already exist. Nothing to do.")
        return 0

    totals = {split_name: {} for split_name in SPLIT_NAMES}

    for split_name in SPLIT_NAMES:
        totals[split_name] = process_split(
            split_name=split_name,
            input_root=args.input,
            output_root=args.output,
            manual_root=args.manual,
            overwrite=args.overwrite,
        )

    print("Annotation generation complete.")
    for split_name in SPLIT_NAMES:
        counts = totals[split_name]
        print(
            f"{split_name}: "
            f"saved={counts['saved']}, "
            f"skipped={counts['skipped']}, "
            f"manual={counts['manual']} (restored={counts['restored']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
