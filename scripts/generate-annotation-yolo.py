"""Annotate surgical-tool boxes and tips with the yolov8stooltip detector.

The detector is the repository's standalone YOLOv8s pose model
(``standalone/yolov8stooltip``, one ``tool`` class whose keypoint is the tip).
It is loaded with that project's own ``common.inference.Detector`` and the
checkpoint ``standalone/yolov8stooltip/data/model/<dataset>/model.pt`` by
default, so this script needs the parent tooltip-detector repository next to
tooltip-annotator.

Output follows the annotation JSON format of this project (see
``tooltip/annotation.py``) and is written to
``data/dataset/<dataset>/annotation-yolo/{train,val,test}``. ``source`` is the
checkpoint path relative to the repository root, e.g.
``"standalone/yolov8stooltip/data/model/cholec80/model.pt"``, the same value
the repository's ``scripts/relabel-annotation.py`` wrote into annotation/.

Each detection becomes one annotation exactly as relabel-annotation.py makes
it: the tip is rounded and clipped to the frame, and the box is grown to hold
the tip pixel. ``Detector`` folds BatchNorm into the convolutions, which
relabel-annotation.py does not, so a coordinate can differ from its labels by
1px on a few frames.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from tqdm import tqdm

from tooltip.annotation import ANNOTATION_SUFFIX, build_payload, write_annotation
from tooltip.dataset_paths import DATA_ROOT, images_dir, resolve_path

try:
    import cv2
except ImportError as exc:  # pragma: no cover - depends on runtime environment
    cv2 = None
    CV2_IMPORT_ERROR = exc
else:
    CV2_IMPORT_ERROR = None


SPLIT_NAMES = ("train", "val", "test")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
# tooltip-annotator lives inside the tooltip-detector repository.
REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_ROOT = REPO_ROOT / "standalone" / "yolov8stooltip"
# Same thresholds as the detector project and relabel-annotation.py.
DEFAULT_CONF = 0.25
DEFAULT_IOU = 0.45


def annotation_yolo_dir(name: str) -> Path:
    return DATA_ROOT / "dataset" / name / "annotation-yolo"


def default_model(name: str) -> Path:
    return DETECTOR_ROOT / "data" / "model" / name / "model.pt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Annotate tool boxes and tips with the yolov8stooltip detector."
    )
    parser.add_argument("--dataset", default=None, help="Dataset name under data/dataset/.")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Root directory with train/val/test images. Defaults to data/dataset/<dataset>/images.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Root directory for annotation JSON files. Defaults to data/dataset/<dataset>/annotation-yolo.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help="yolov8stooltip checkpoint. Defaults to standalone/yolov8stooltip/data/model/<dataset>/model.pt.",
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=SPLIT_NAMES,
        default=list(SPLIT_NAMES),
        help="Splits to annotate. Default: train val test.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Annotate at most this many new images per split (for a quick trial).",
    )
    parser.add_argument("--device", default=None, help="Torch device. Default: cuda:0 if available.")
    parser.add_argument("--conf", type=float, default=DEFAULT_CONF, help="Confidence threshold. Default: 0.25.")
    parser.add_argument("--iou", type=float, default=DEFAULT_IOU, help="NMS IoU threshold. Default: 0.45.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Annotate again images whose JSON already exists instead of skipping them.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if CV2_IMPORT_ERROR is not None:
        raise RuntimeError("opencv-python is required to read images.") from CV2_IMPORT_ERROR
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be at least 1.")
    if not args.input.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {args.input}")
    if not args.model.is_file():
        raise FileNotFoundError(f"Checkpoint does not exist: {args.model}")


def load_detector(model_path: Path, device: str | None):
    """The detector project's own inference class, imported from its directory."""
    if not (DETECTOR_ROOT / "common" / "inference.py").is_file():
        raise FileNotFoundError(f"yolov8stooltip project not found: {DETECTOR_ROOT}")
    sys.path.insert(0, str(DETECTOR_ROOT))
    from common.inference import Detector

    return Detector(str(model_path), device=device)


def model_source(model_path: Path) -> str:
    """The checkpoint path relative to the repository root, or as given if outside it."""
    resolved = model_path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def tool_annotation(row, width: int, height: int) -> dict[str, dict[str, int]]:
    """One detection row [x1, y1, x2, y2, score, class, kx, ky] as an annotation.

    Same rule as the repository's interactive-trainer: the tip is rounded and
    clipped to the frame, and the box is grown to hold the tip pixel.
    """
    x1, y1, x2, y2 = (float(value) for value in row[:4])
    tip_x = min(max(int(round(float(row[6]))), 0), width - 1)
    tip_y = min(max(int(round(float(row[7]))), 0), height - 1)
    left = max(min(int(math.floor(x1)), tip_x), 0)
    top = max(min(int(math.floor(y1)), tip_y), 0)
    right = min(max(int(math.ceil(x2)), tip_x + 1), width)
    bottom = min(max(int(math.ceil(y2)), tip_y + 1), height)
    return {
        "bbox": {"x": left, "y": top, "width": max(right - left, 1), "height": max(bottom - top, 1)},
        "tip": {"x": tip_x, "y": tip_y},
    }


def list_images(image_dir: Path) -> list[Path]:
    if not image_dir.is_dir():
        return []
    return sorted(
        path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def process_split(split_name: str, args: argparse.Namespace, detector, source: str) -> dict[str, int]:
    output_dir = args.output / split_name
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {"saved": 0, "skipped": 0, "unreadable": 0}

    pending = []
    for image_path in list_images(args.input / split_name):
        if (output_dir / f"{image_path.stem}{ANNOTATION_SUFFIX}").exists() and not args.overwrite:
            counts["skipped"] += 1
            continue
        pending.append(image_path)
    if args.limit is not None:
        pending = pending[: args.limit]

    for image_path in tqdm(pending, desc=split_name, unit="image", ascii=True, ncols=100):
        image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            tqdm.write(f"unreadable image, skipped: {image_path}")
            counts["unreadable"] += 1
            continue
        height, width = image_bgr.shape[:2]
        detections, _elapsed_ms = detector.detect(
            cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB), conf=args.conf, iou=args.iou
        )
        annotations = [tool_annotation(row, width, height) for row in detections]
        annotations.sort(key=lambda item: (item["bbox"]["x"], item["bbox"]["y"]))
        payload = build_payload(image_path.name, width, height, annotations, source)
        write_annotation(output_dir / f"{image_path.stem}{ANNOTATION_SUFFIX}", payload)
        counts["saved"] += 1
    return counts


def main() -> int:
    args = parse_args()
    args.input = resolve_path(args.input, args.dataset, images_dir, "--input")
    args.output = resolve_path(args.output, args.dataset, annotation_yolo_dir, "--output")
    args.model = resolve_path(args.model, args.dataset, default_model, "--model")
    validate_args(args)

    source = model_source(args.model)
    detector = load_detector(args.model, args.device)
    print(f"Loaded {source} on {detector.device}.")

    totals = {split_name: process_split(split_name, args, detector, source) for split_name in args.splits}

    print("YOLO annotation complete.")
    for split_name, counts in totals.items():
        print(f"{split_name}: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Files saved so far are kept; run the same command again to continue.")
        raise SystemExit(130)
