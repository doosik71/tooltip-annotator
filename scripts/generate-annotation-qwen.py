"""Annotate surgical tools and their tips with a local vision-language model.

This reproduces, with a model that runs on the local GPU, the way Claude
labelled a frame by looking at it: name each visible instrument, draw a tight
box around it and point at its distal working end (the tip). No remote API is
called. The default model is Qwen3-VL-8B-Instruct, downloaded once into
``data/models/`` and loaded from there afterwards.

Output follows the annotation JSON format of this project (see
``tooltip/annotation.py``) with ``"source": "qwen"`` and is written to
``data/dataset/<dataset>/annotation-qwen/{train,val,test}``. Each payload
also records the local model that produced it under ``"model"``, and each
annotation carries the instrument name the model gave under ``"label"``.

An instrument may show two distal ends, e.g. the open jaws of a grasper,
scissors or bipolar forceps. Its annotation then carries the second end under
an optional ``"tip2"`` next to the required ``"tip"``; readers that only know
``"tip"`` keep working unchanged.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from tqdm import tqdm

from tooltip.annotation import (
    ANNOTATION_SUFFIX,
    build_payload,
    is_too_small_box,
    write_annotation,
)
from tooltip.dataset_paths import DATA_ROOT, images_dir, resolve_path

try:
    import torch
except ImportError as exc:  # pragma: no cover - depends on runtime environment
    torch = None
    TORCH_IMPORT_ERROR = exc
else:
    TORCH_IMPORT_ERROR = None

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - depends on runtime environment
    Image = None
    PIL_IMPORT_ERROR = exc
else:
    PIL_IMPORT_ERROR = None


SPLIT_NAMES = ("train", "val", "test")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
SOURCE_QWEN = "qwen"
DEFAULT_MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
MODELS_ROOT = DATA_ROOT / "models"
# Qwen3-VL answers boxes and points in coordinates normalised to 0-1000 on
# both axes, whatever the image size (it does so even when asked for pixels).
# Frames are therefore passed at their own size and mapped back by
# frame size / COORD_RANGE.
COORD_RANGE = 1000
# Two boxes overlapping this much are the model repeating one instrument.
DUPLICATE_IOU = 0.9
# An instrument has at most this many tips ("tip" and "tip2").
MAX_TIPS = 2
# Two tips closer than this many pixels are one tip reported twice.
SAME_TIP_DISTANCE = 6

# The answer format is shown with placeholders only: concrete example values
# were copied into answers by the model (same coordinates, same labels).
PROMPT = """\
This is a frame from a laparoscopic surgery video. \
The circular endoscope view may be surrounded by black borders.

Find every surgical instrument visible in the image (for example grasper, \
hook/electrocautery, clipper, scissors, bipolar forceps, irrigator, specimen bag).
For each instrument give:
- "label": the instrument type,
- "bbox_2d": [x1, y1, x2, y2], a tight box around the visible part of the \
instrument, shaft and tip together,
- "point_2d": the tool tip, the distal working end of the instrument (end of \
the jaws, hook or blade), which is the end opposite to where the shaft enters \
the image. Give one point [x, y]. Only when the instrument shows two separate \
distal ends, such as the two open jaws of a grasper, scissors or bipolar \
forceps, give both ends as [[x1, y1], [x2, y2]].
Report each instrument only once, even when its jaws are open.

Use coordinates normalized to 0-1000 on both axes, where [0, 0] is the \
top-left and [1000, 1000] the bottom-right corner of the image. Do not report \
tissue, clips already left in tissue, gauze or light reflections as \
instruments. If no instrument is visible, answer [].
Answer only with a JSON list with one object per instrument, in the form
[{"label": "<instrument type>", "bbox_2d": [x1, y1, x2, y2], "point_2d": [x, y]}, ...]"""


def annotation_qwen_dir(name: str) -> Path:
    return DATA_ROOT / "dataset" / name / "annotation-qwen"



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Annotate surgical-tool boxes and tips with a local "
            "vision-language model, the way Claude labels a frame."
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
        help="Root directory containing train/val/test image folders. Defaults to data/dataset/<dataset>/images.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Root directory where train/val/test annotation JSON files will be saved. Defaults to data/dataset/<dataset>/annotation-qwen.",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help=f"Hugging Face repository of the Qwen3-VL model. Default: {DEFAULT_MODEL_ID}.",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=None,
        help="Local model directory. Defaults to data/models/<model name>; downloaded there when missing.",
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
        help="Annotate at most this many images per split (for a quick trial).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Torch device to use, for example cuda or cuda:0. Defaults to cuda:0 when available, else cpu.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Number of images per generation batch. Default: 8.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=512,
        help="Generation length limit per image. Default: 512.",
    )
    parser.add_argument(
        "--attn",
        default="sdpa",
        choices=("sdpa", "flash_attention_2", "eager"),
        help="Attention implementation. flash_attention_2 needs the flash-attn package. Default: sdpa.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Annotate again images whose JSON already exists instead of skipping them.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if TORCH_IMPORT_ERROR is not None:
        raise RuntimeError(
            "torch is required to run the model. Install it and run the script again."
        ) from TORCH_IMPORT_ERROR
    if PIL_IMPORT_ERROR is not None:
        raise RuntimeError(
            "pillow is required to read images. Install it and run the script again."
        ) from PIL_IMPORT_ERROR
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1.")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be at least 1.")

    if not args.input.is_dir():
        raise NotADirectoryError(f"Input directory does not exist: {args.input}")
    for split_name in args.splits:
        split_dir = args.input / split_name
        if not split_dir.is_dir():
            raise NotADirectoryError(f"Split directory does not exist: {split_dir}")


def list_images(image_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def resolve_device(device_arg: str | None) -> "torch.device":
    if device_arg:
        return torch.device(device_arg)
    return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def ensure_model(model_id: str, model_dir: Path) -> Path:
    """Download the model into data/models once, then always load it from there."""
    if (model_dir / "config.json").exists():
        return model_dir

    from huggingface_hub import snapshot_download

    print(f"Downloading {model_id} to {model_dir} ...")
    model_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=model_id, local_dir=str(model_dir))
    return model_dir


def load_model(model_dir: Path, device: "torch.device", attn: str):
    try:
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    except ImportError as exc:
        raise RuntimeError(
            "transformers>=4.57 is required for Qwen3-VL. Run `uv sync` and try again."
        ) from exc

    dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        str(model_dir),
        torch_dtype=dtype,
        attn_implementation=attn,
    ).to(device)
    model.eval()

    processor = AutoProcessor.from_pretrained(str(model_dir))
    # Batched generation needs left padding so every prompt ends at the same position.
    processor.tokenizer.padding_side = "left"
    return model, processor


# ---------------------------------------------------------------------------
# Parsing the model answer
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> object:
    """Return the JSON value in a model answer, tolerating code fences and chatter."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    # Last resort: collect every complete {...} object, e.g. from a truncated list.
    objects = []
    for match in re.finditer(r"\{[^{}]*\}", text):
        try:
            objects.append(json.loads(match.group(0)))
        except json.JSONDecodeError:
            continue
    if objects:
        return objects
    raise ValueError(f"No JSON found in model answer: {text[:200]!r}")


def _numbers(value: object, count: int) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != count:
        return None
    try:
        return [float(v) for v in value]
    except (TypeError, ValueError):
        return None


def _points(value: object) -> list[list[float]]:
    """Read a tip answer: [x, y], [[x, y]] or [[x1, y1], [x2, y2], ...]."""
    single = _numbers(value, 2)
    if single is not None:
        return [single]
    if not isinstance(value, (list, tuple)):
        return []
    return [point for point in (_numbers(entry, 2) for entry in value) if point is not None]


def _add_tip(
    tips: list[tuple[int, int]],
    point: tuple[float, float],
    rect: tuple[int, int, int, int],
) -> None:
    """Clamp a tip into its box and keep it unless it repeats one already kept."""
    x1, y1, x2, y2 = rect
    tip = (int(round(min(max(point[0], x1), x2))), int(round(min(max(point[1], y1), y2))))
    if len(tips) >= MAX_TIPS:
        return
    for kept in tips:
        if (kept[0] - tip[0]) ** 2 + (kept[1] - tip[1]) ** 2 < SAME_TIP_DISTANCE**2:
            return
    tips.append(tip)


def _store_tips(
    annotation: dict[str, object],
    tips: list[tuple[int, int]],
    width: int,
    height: int,
) -> None:
    """Write "tip" (and "tip2"), the tip nearer the frame centre first."""
    cx, cy = width / 2.0, height / 2.0
    tips = sorted(tips, key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t))
    annotation["tip"] = {"x": tips[0][0], "y": tips[0][1]}
    annotation.pop("tip2", None)
    if len(tips) > 1:
        annotation["tip2"] = {"x": tips[1][0], "y": tips[1][1]}


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def parse_answer(
    text: str,
    scale_x: float,
    scale_y: float,
    width: int,
    height: int,
) -> list[dict[str, object]]:
    """Turn the model answer into this project's bbox/tip annotations.

    Coordinates are scaled from the model's 0-1000 range back to the frame,
    clamped to the frame, and every tip is clamped into its box. An
    instrument keeps at most two tips: "tip", the one nearer the frame centre,
    and "tip2". A missing tip falls back to the box corner nearest the frame
    centre, the same "tip is toward the centre" rule the mask pipeline uses.
    Tiny boxes are dropped. A box repeating an earlier one is dropped too, but
    its tip is kept as that instrument's second tip, since the model sometimes
    reports open jaws as two instruments.
    """
    data = _extract_json(text)
    if isinstance(data, dict):
        data = data.get("tools") or data.get("instruments") or [data]
    if not isinstance(data, list):
        raise ValueError(f"Unexpected model answer: {text[:200]!r}")

    # Each entry: box, tips, annotation without tips yet.
    kept: list[tuple[tuple[int, int, int, int], list[tuple[int, int]], dict[str, object]]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        box = _numbers(item.get("bbox_2d", item.get("bbox")), 4)
        if box is None:
            continue

        x1, x2 = sorted((box[0] * scale_x, box[2] * scale_x))
        y1, y2 = sorted((box[1] * scale_y, box[3] * scale_y))
        x1 = int(round(min(max(x1, 0), width - 1)))
        x2 = int(round(min(max(x2, 0), width - 1)))
        y1 = int(round(min(max(y1, 0), height - 1)))
        y2 = int(round(min(max(y2, 0), height - 1)))
        box_width, box_height = x2 - x1, y2 - y1
        if is_too_small_box(box_width, box_height):
            continue
        rect = (x1, y1, x2, y2)

        points = [
            (x * scale_x, y * scale_y)
            for x, y in _points(item.get("point_2d", item.get("tip")))
        ]

        duplicate = next(
            (entry for entry in kept if _iou(rect, entry[0]) >= DUPLICATE_IOU), None
        )
        if duplicate is not None:
            for point in points:
                _add_tip(duplicate[1], point, duplicate[0])
            continue

        tips: list[tuple[int, int]] = []
        for point in points:
            _add_tip(tips, point, rect)
        if not tips:
            cx, cy = width / 2.0, height / 2.0
            _add_tip(
                tips,
                (x1 if abs(x1 - cx) < abs(x2 - cx) else x2, y1 if abs(y1 - cy) < abs(y2 - cy) else y2),
                rect,
            )

        annotation: dict[str, object] = {
            "bbox": {"x": x1, "y": y1, "width": box_width, "height": box_height},
        }
        label = item.get("label")
        if isinstance(label, str) and label.strip():
            annotation["label"] = label.strip()
        kept.append((rect, tips, annotation))

    kept.sort(key=lambda entry: entry[0])
    for _, tips, annotation in kept:
        _store_tips(annotation, tips, width, height)
    return [annotation for _, _, annotation in kept]


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def annotate_batch(
    image_paths: list[Path],
    model,
    processor,
    device: "torch.device",
    max_new_tokens: int,
) -> list[tuple[str, int, int]]:
    """Run one batch and return (answer, width, height) per image."""
    images, texts, sizes = [], [], []
    for image_path in image_paths:
        with Image.open(image_path) as image:
            image = image.convert("RGB")
        width, height = image.size

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ]
        texts.append(
            processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        )
        images.append(image)
        sizes.append((width, height))

    inputs = processor(text=texts, images=images, padding=True, return_tensors="pt").to(device)
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    new_tokens = generated[:, inputs["input_ids"].shape[1] :]
    answers = processor.batch_decode(new_tokens, skip_special_tokens=True)
    return [(answer, *size) for answer, size in zip(answers, sizes)]


def process_split(
    split_name: str,
    args: argparse.Namespace,
    model,
    processor,
    device: "torch.device",
    failures: list[str],
) -> dict[str, int]:
    input_dir = args.input / split_name
    output_dir = args.output / split_name
    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths = list_images(input_dir)
    counts = {"saved": 0, "skipped": 0, "failed": 0}

    pending = []
    for image_path in image_paths:
        if (output_dir / f"{image_path.stem}{ANNOTATION_SUFFIX}").exists() and not args.overwrite:
            counts["skipped"] += 1
            continue
        pending.append(image_path)
    if args.limit is not None:
        pending = pending[: args.limit]

    progress = tqdm(total=len(pending), desc=split_name, unit="image", ascii=True, ncols=100)
    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        results = annotate_batch(batch, model, processor, device, args.max_new_tokens)

        for image_path, (answer, width, height) in zip(batch, results):
            error = None
            try:
                annotations = parse_answer(
                    answer, width / COORD_RANGE, height / COORD_RANGE, width, height
                )
            except ValueError as exc:
                error = str(exc)

            if error is not None:
                # Leave no annotation behind so the next run retries this frame.
                counts["failed"] += 1
                failures.append(f"{split_name}/{image_path.name}: {error}")
                continue

            payload = build_payload(
                image_name=image_path.name,
                width=width,
                height=height,
                annotations=annotations,
                source=SOURCE_QWEN,
            )
            payload["model"] = args.model_id
            write_annotation(output_dir / f"{image_path.stem}{ANNOTATION_SUFFIX}", payload)
            counts["saved"] += 1
        progress.update(len(batch))
    progress.close()
    return counts


def main() -> int:
    args = parse_args()
    args.input = resolve_path(args.input, args.dataset, images_dir, "--input")
    args.output = resolve_path(args.output, args.dataset, annotation_qwen_dir, "--output")
    if args.model_dir is None:
        args.model_dir = MODELS_ROOT / args.model_id.split("/")[-1]
    validate_args(args)

    device = resolve_device(args.device)
    model_dir = ensure_model(args.model_id, args.model_dir)
    print(f"Loading {model_dir} on {device} ...")
    model, processor = load_model(model_dir, device, args.attn)

    totals: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    for split_name in args.splits:
        totals[split_name] = process_split(split_name, args, model, processor, device, failures)

    print("Claude-style annotation complete.")
    for split_name, counts in totals.items():
        print(
            f"{split_name}: saved={counts['saved']}, "
            f"skipped={counts['skipped']}, failed={counts['failed']}"
        )
    if failures:
        print(f"{len(failures)} frame(s) could not be parsed and will be retried on the next run:")
        for line in failures[:20]:
            print(f"  {line}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Files saved so far are kept; run the same command again to continue.")
        raise SystemExit(130)
