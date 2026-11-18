"""Annotate surgical tools and their tips with Claude Opus through the Anthropic API.

Each frame is sent to Claude Opus with instructions to find every visible
instrument, draw a tight box around it and mark its distal working end (the
tip), and the answer is constrained to a JSON schema (structured outputs).
Results are written in this project's annotation JSON format (see
``tooltip/annotation.py``) with ``"source": "opus"`` to
``data/dataset/<dataset>/annotation-opus/{train,val,test}``.

An instrument may show two distal ends, e.g. clearly open jaws. Its annotation
then carries the second end under an optional ``"tip2"`` next to the required
``"tip"``, the same schema extension `generate-annotation-qwen.py` uses.

Two ways to call the API:

- ``--mode sync`` (default): one request per frame, a few in parallel. Good
  for trials; full price.
- ``--mode batch``: Message Batches API at half price. Requests are submitted
  in chunks and their ids are kept in
  ``data/dataset/<dataset>/annotation-opus-batches.json``. Results usually
  arrive within an hour (at most 24 hours); run the script again, or pass
  ``--wait``, to collect them. Frames already in a submitted batch are not
  submitted twice.

The API key is read from the ``ANTHROPIC_API_KEY`` environment variable.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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
    import anthropic
except ImportError as exc:  # pragma: no cover - depends on runtime environment
    anthropic = None
    ANTHROPIC_IMPORT_ERROR = exc
else:
    ANTHROPIC_IMPORT_ERROR = None

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - depends on runtime environment
    Image = None
    PIL_IMPORT_ERROR = exc
else:
    PIL_IMPORT_ERROR = None


SPLIT_NAMES = ("train", "val", "test")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
SOURCE_OPUS = "opus"
DEFAULT_MODEL = "claude-opus-5-5"

# Frames are downscaled on our side so their long edge is at most this, so the
# API never resizes them and the model's pixel coordinates map back to the
# frame by a plain scale factor. 736x480 cholec80/erop frames are sent as is.
DEFAULT_MAX_EDGE = 1568

# Message Batches limits are 100,000 requests or 256 MB per batch; stay well
# under the size limit since every request carries a base64 image.
BATCH_MAX_BYTES = 200 * 1024 * 1024
BATCH_POLL_SECONDS = 60

# An instrument has at most this many tips ("tip" and "tip2").
MAX_TIPS = 2
# Two tips closer than this many pixels are one tip reported twice.
SAME_TIP_DISTANCE = 6

# USD per million tokens: input, output. Used only to report the cost of a
# run from the usage the API returns; the Batch API halves both.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.0, 20.0),
}
CACHE_READ_FACTOR = 0.05

LABELS = [
    "grasper",
    "bipolar",
    "hook",
    "scissors",
    "clipper",
    "irrigator",
    "specimen bag",
    "other",
]

SYSTEM_PROMPT = """\
You annotate surgical instruments in frames of laparoscopic surgery videos \
(mostly cholecystectomy) for a tool and tool-tip detection dataset.

For each image:
1. Find every surgical instrument that is visible, even partly. Instruments \
enter the circular endoscope view from its edges; look for dark instruments \
against dark tissue and for instruments partly hidden by tissue or by another \
instrument. Frames typically show one to three instruments. Check the whole \
field of view before answering, and report each instrument once.
2. For each instrument give:
- label: one of grasper, bipolar, hook, scissors, clipper, irrigator, \
specimen bag, other.
- bbox: a tight axis-aligned box around the visible part of the instrument, \
shaft and working end together, in pixel coordinates of the image (origin at \
the top-left corner, x to the right, y down; x2 > x1 and y2 > y1).
- tips: the distal working end of the instrument, i.e. the end of the jaws, \
of the hook or of the blades, which is the end opposite to where the shaft \
enters the image. Give exactly one point, except when the instrument clearly \
shows two separate distal ends such as widely open jaws; then give the end of \
each jaw as two points. For a hook, the tip is the end of the metal hook, not \
the end of its white insulating sheath. If the working end is hidden behind \
tissue, give the most distal visible point of the instrument.

Do not report clips already left in tissue, gauze, light reflections or the \
black border. If no instrument is visible, return an empty list."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "instruments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "enum": LABELS},
                    "bbox": {
                        "type": "object",
                        "properties": {
                            "x1": {"type": "integer"},
                            "y1": {"type": "integer"},
                            "x2": {"type": "integer"},
                            "y2": {"type": "integer"},
                        },
                        "required": ["x1", "y1", "x2", "y2"],
                        "additionalProperties": False,
                    },
                    "tips": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "integer"},
                                "y": {"type": "integer"},
                            },
                            "required": ["x", "y"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["label", "bbox", "tips"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["instruments"],
    "additionalProperties": False,
}


def annotation_opus_dir(name: str) -> Path:
    return DATA_ROOT / "dataset" / name / "annotation-opus"


def annotation_opus_raw_dir(name: str) -> Path:
    return DATA_ROOT / "dataset" / name / "annotation-opus-raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Annotate surgical-tool boxes and tips with Claude Opus through the Anthropic API."
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Dataset name, e.g. 'erop' or 'cholec80'. Used to resolve default --input/--output.",
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
        help="Root directory where train/val/test annotation JSON files will be saved. Defaults to data/dataset/<dataset>/annotation-opus.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model id. Default: {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--effort",
        default="low",
        choices=("low", "medium", "high", "xhigh", "max"),
        help=(
            "Thinking effort. Thinking tokens are billed as output tokens, so "
            "this is the main cost knob. Default: low."
        ),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16000,
        help="Output limit per frame, thinking included. Default: 16000.",
    )
    parser.add_argument(
        "--max-edge",
        type=int,
        default=DEFAULT_MAX_EDGE,
        help=f"Downscale frames whose long edge exceeds this before sending. Default: {DEFAULT_MAX_EDGE}.",
    )
    parser.add_argument(
        "--mode",
        default="sync",
        choices=("sync", "batch"),
        help="sync: one request per frame (full price). batch: Message Batches API (half price, asynchronous).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel requests in sync mode. Default: 4.",
    )
    parser.add_argument(
        "--batch-requests",
        type=int,
        default=2000,
        help="Maximum requests per submitted batch in batch mode. Default: 2000.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="In batch mode, keep polling until every submitted batch has ended and its results are written.",
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
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Annotate again images whose JSON already exists instead of skipping them.",
    )
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help="Also save the raw API answer and token usage of every processed image, for debugging.",
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        default=None,
        help="Root directory for --save-raw files. Defaults to data/dataset/<dataset>/annotation-opus-raw.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if ANTHROPIC_IMPORT_ERROR is not None:
        raise RuntimeError(
            "The anthropic package is required. Run `uv sync` and try again."
        ) from ANTHROPIC_IMPORT_ERROR
    if PIL_IMPORT_ERROR is not None:
        raise RuntimeError(
            "pillow is required to read images. Install it and run the script again."
        ) from PIL_IMPORT_ERROR
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Set the ANTHROPIC_API_KEY environment variable to your Anthropic API key.")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be at least 1.")
    if args.workers < 1 or args.batch_requests < 1:
        raise ValueError("--workers and --batch-requests must be at least 1.")

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


def annotation_path(args: argparse.Namespace, split_name: str, image_path: Path) -> Path:
    return args.output / split_name / f"{image_path.stem}{ANNOTATION_SUFFIX}"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


def sent_size(width: int, height: int, max_edge: int) -> tuple[int, int]:
    """Size the frame is sent at: unchanged unless its long edge exceeds max_edge."""
    long_edge = max(width, height)
    if long_edge <= max_edge:
        return width, height
    scale = max_edge / long_edge
    return max(1, round(width * scale)), max(1, round(height * scale))


def encode_image(image_path: Path, max_edge: int) -> tuple[str, str, int, int, int, int]:
    """Return (media_type, base64 data, width, height, sent_width, sent_height)."""
    with Image.open(image_path) as image:
        width, height = image.size
        send_w, send_h = sent_size(width, height, max_edge)
        suffix = image_path.suffix.lower()
        if (send_w, send_h) == (width, height) and suffix in (".png", ".jpg", ".jpeg"):
            data = image_path.read_bytes()
            media_type = "image/png" if suffix == ".png" else "image/jpeg"
        else:
            buffer = io.BytesIO()
            image.convert("RGB").resize((send_w, send_h), Image.LANCZOS).save(buffer, format="PNG")
            data = buffer.getvalue()
            media_type = "image/png"
    return media_type, base64.standard_b64encode(data).decode("ascii"), width, height, send_w, send_h


def build_params(args: argparse.Namespace, image_path: Path) -> tuple[dict, tuple[int, int, int, int]]:
    media_type, data, width, height, send_w, send_h = encode_image(image_path, args.max_edge)
    params = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {
                        "type": "text",
                        "text": f"This image is {send_w}x{send_h} pixels. Annotate every surgical instrument in it.",
                    },
                ],
            }
        ],
        "output_config": {
            "effort": args.effort,
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
    }
    return params, (width, height, send_w, send_h)


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


def _clamp(value: float, low: int, high: int) -> int:
    return int(round(min(max(value, low), high)))


def to_annotations(
    data: dict,
    size: tuple[int, int, int, int],
) -> list[dict[str, object]]:
    """Turn the schema-shaped answer into this project's bbox/tip annotations.

    Coordinates are scaled back to the frame and clamped into it, every tip is
    clamped into its box, tiny boxes are dropped, and an instrument keeps at
    most two tips: "tip", the one nearer the frame centre, and "tip2".
    """
    width, height, send_w, send_h = size
    sx, sy = width / send_w, height / send_h
    cx, cy = width / 2.0, height / 2.0

    entries = []
    for item in data.get("instruments", []):
        box = item["bbox"]
        x1, x2 = sorted((box["x1"] * sx, box["x2"] * sx))
        y1, y2 = sorted((box["y1"] * sy, box["y2"] * sy))
        x1, x2 = _clamp(x1, 0, width - 1), _clamp(x2, 0, width - 1)
        y1, y2 = _clamp(y1, 0, height - 1), _clamp(y2, 0, height - 1)
        if is_too_small_box(x2 - x1, y2 - y1):
            continue

        tips: list[tuple[int, int]] = []
        for point in item.get("tips", []):
            tip = (_clamp(point["x"] * sx, x1, x2), _clamp(point["y"] * sy, y1, y2))
            if len(tips) < MAX_TIPS and all(
                (t[0] - tip[0]) ** 2 + (t[1] - tip[1]) ** 2 >= SAME_TIP_DISTANCE**2 for t in tips
            ):
                tips.append(tip)
        if not tips:
            # Same "tip is toward the centre" fallback as the mask pipeline.
            tips.append((x1 if abs(x1 - cx) < abs(x2 - cx) else x2, y1 if abs(y1 - cy) < abs(y2 - cy) else y2))
        tips.sort(key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t))

        annotation: dict[str, object] = {
            "bbox": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
            "label": item["label"],
            "tip": {"x": tips[0][0], "y": tips[0][1]},
        }
        if len(tips) > 1:
            annotation["tip2"] = {"x": tips[1][0], "y": tips[1][1]}
        entries.append(((x1, y1, x2, y2), annotation))

    entries.sort(key=lambda entry: entry[0])
    return [annotation for _, annotation in entries]


def usage_dict(message) -> dict[str, int]:
    usage = getattr(message, "usage", None)
    if usage is None:
        return {}
    return {
        key: int(getattr(usage, key, 0) or 0)
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    }


class Run:
    """Writes results and keeps the counts and token usage of one run."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.counts = {"saved": 0, "failed": 0}
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        self.failures: list[str] = []

    def handle(
        self,
        split_name: str,
        image_path: Path,
        size: tuple[int, int, int, int],
        message=None,
        error: str | None = None,
    ) -> None:
        """Turn one API outcome into an annotation file (or a failure)."""
        text = None
        usage = usage_dict(message) if message is not None else {}
        for key, value in usage.items():
            self.usage[key] += value

        annotations = None
        if error is None:
            stop_reason = getattr(message, "stop_reason", None)
            text = next((block.text for block in message.content if block.type == "text"), None)
            if stop_reason == "refusal":
                error = "refused by the model"
            elif stop_reason == "max_tokens":
                error = "hit --max-tokens before finishing; raise it"
            elif text is None:
                error = "no text block in the answer"
            else:
                try:
                    annotations = to_annotations(json.loads(text), size)
                except (ValueError, KeyError, TypeError) as exc:
                    error = f"unreadable answer: {exc}"

        if self.args.save_raw:
            raw_path = self.args.raw_output / split_name / f"{image_path.stem}{ANNOTATION_SUFFIX}"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            width, height, send_w, send_h = size
            record = {
                "image": image_path.name,
                "model": self.args.model,
                "effort": self.args.effort,
                "mode": self.args.mode,
                "width": width,
                "height": height,
                "sent_width": send_w,
                "sent_height": send_h,
                "stop_reason": getattr(message, "stop_reason", None),
                "answer": text,
                "usage": usage,
                "error": error,
                "annotations": annotations,
            }
            raw_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")

        if error is not None:
            # Leave no annotation behind so the next run retries this frame.
            self.counts["failed"] += 1
            self.failures.append(f"{split_name}/{image_path.name}: {error}")
            return

        width, height = size[0], size[1]
        payload = build_payload(
            image_name=image_path.name,
            width=width,
            height=height,
            annotations=annotations,
            source=SOURCE_OPUS,
        )
        payload["model"] = self.args.model
        output_path = annotation_path(self.args, split_name, image_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_annotation(output_path, payload)
        self.counts["saved"] += 1

    def report(self) -> None:
        print(f"saved={self.counts['saved']}, failed={self.counts['failed']}")
        u = self.usage
        print(
            "tokens: "
            f"input={u['input_tokens']:,}, output (incl. thinking)={u['output_tokens']:,}, "
            f"cache write={u['cache_creation_input_tokens']:,}, cache read={u['cache_read_input_tokens']:,}"
        )
        prices = PRICES_PER_MTOK.get(self.args.model)
        if prices and (u["input_tokens"] or u["output_tokens"]):
            factor = 0.5 if self.args.mode == "batch" else 1.0
            cost = factor * (
                u["input_tokens"] * prices[0]
                + u["cache_creation_input_tokens"] * prices[0] * 1.25
                + u["cache_read_input_tokens"] * prices[0] * CACHE_READ_FACTOR
                + u["output_tokens"] * prices[1]
            ) / 1_000_000
            done = max(1, self.counts["saved"] + self.counts["failed"])
            print(f"estimated cost: ${cost:,.2f} (${cost / done:.4f} per frame)")
        if self.failures:
            print(f"{len(self.failures)} frame(s) failed and will be retried on the next run:")
            for line in self.failures[:20]:
                print(f"  {line}")
            if len(self.failures) > 20:
                print(f"  ... and {len(self.failures) - 20} more")


def pending_images(args: argparse.Namespace, exclude: set[str] | None = None) -> list[tuple[str, Path]]:
    """Frames still to annotate, as (split, image path), honouring --overwrite and --limit."""
    exclude = exclude or set()
    pending: list[tuple[str, Path]] = []
    for split_name in args.splits:
        chosen = []
        for image_path in list_images(args.input / split_name):
            if f"{split_name}/{image_path.name}" in exclude:
                continue
            if annotation_path(args, split_name, image_path).exists() and not args.overwrite:
                continue
            chosen.append((split_name, image_path))
        if args.limit is not None:
            chosen = chosen[: args.limit]
        pending.extend(chosen)
    return pending


# ---------------------------------------------------------------------------
# Sync mode
# ---------------------------------------------------------------------------


def run_sync(args: argparse.Namespace, client, run: Run) -> None:
    pending = pending_images(args)

    def call(item: tuple[str, Path]):
        split_name, image_path = item
        params, size = build_params(args, image_path)
        try:
            return item, size, client.messages.create(**params), None
        except anthropic.APIError as exc:
            return item, size, None, f"API error: {exc}"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(call, item) for item in pending]
        for future in tqdm(as_completed(futures), total=len(futures), unit="image", ascii=True, ncols=100):
            (split_name, image_path), size, message, error = future.result()
            run.handle(split_name, image_path, size, message, error)


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"batches": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n")
    tmp.replace(path)


def collect_batches(args: argparse.Namespace, client, run: Run, state: dict, state_path: Path) -> int:
    """Write the results of every ended, not yet collected batch. Return how many are still running."""
    running = 0
    for batch in state["batches"]:
        if batch["collected"]:
            continue
        status = client.messages.batches.retrieve(batch["id"]).processing_status
        if status != "ended":
            running += 1
            continue

        items = batch["items"]
        for result in client.messages.batches.results(batch["id"]):
            key = items.get(result.custom_id)
            if key is None:
                continue
            split_name, name = key.split("/", 1)
            image_path = args.input / split_name / name
            with Image.open(image_path) as image:
                width, height = image.size
            size = (width, height, *sent_size(width, height, batch["max_edge"]))
            outcome = result.result
            if outcome.type == "succeeded":
                run.handle(split_name, image_path, size, outcome.message)
            elif outcome.type == "errored":
                run.handle(split_name, image_path, size, error=f"batch request errored: {outcome.error}")
            else:
                run.handle(split_name, image_path, size, error=f"batch request {outcome.type}")
        batch["collected"] = True
        save_state(state_path, state)
        print(f"Collected batch {batch['id']} ({len(items)} requests).")
    return running


def submit_batches(args: argparse.Namespace, client, state: dict, state_path: Path) -> int:
    in_flight = {
        key for batch in state["batches"] if not batch["collected"] for key in batch["items"].values()
    }
    pending = pending_images(args, exclude=in_flight)
    submitted = 0

    def flush(requests: list, items: dict) -> None:
        nonlocal submitted
        if not requests:
            return
        batch = client.messages.batches.create(requests=requests)
        state["batches"].append(
            {
                "id": batch.id,
                "submitted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "model": args.model,
                "effort": args.effort,
                "max_edge": args.max_edge,
                "items": items,
                "collected": False,
            }
        )
        save_state(state_path, state)
        submitted += len(requests)
        print(f"Submitted batch {batch.id} ({len(requests)} requests).")

    requests: list = []
    items: dict[str, str] = {}
    size_bytes = 0
    for split_name, image_path in tqdm(pending, desc="encode", unit="image", ascii=True, ncols=100):
        params, _ = build_params(args, image_path)
        request_bytes = len(json.dumps(params))
        if requests and (len(requests) >= args.batch_requests or size_bytes + request_bytes > BATCH_MAX_BYTES):
            flush(requests, items)
            requests, items, size_bytes = [], {}, 0
        custom_id = f"r{len(requests)}"
        requests.append({"custom_id": custom_id, "params": params})
        items[custom_id] = f"{split_name}/{image_path.name}"
        size_bytes += request_bytes
    flush(requests, items)
    return submitted


def run_batch(args: argparse.Namespace, client, run: Run) -> None:
    state_path = args.output.parent / f"{args.output.name}-batches.json"
    state = load_state(state_path)

    collect_batches(args, client, run, state, state_path)
    submitted = submit_batches(args, client, state, state_path)
    print(f"Submitted {submitted} new request(s). Batch ids are kept in {state_path}.")

    while args.wait:
        running = collect_batches(args, client, run, state, state_path)
        if running == 0:
            break
        print(f"{running} batch(es) still running; checking again in {BATCH_POLL_SECONDS}s ...")
        time.sleep(BATCH_POLL_SECONDS)
    if not args.wait:
        print("Run the same command again later (or add --wait) to collect the results.")


def main() -> int:
    args = parse_args()
    args.input = resolve_path(args.input, args.dataset, images_dir, "--input")
    args.output = resolve_path(args.output, args.dataset, annotation_opus_dir, "--output")
    if args.save_raw:
        args.raw_output = resolve_path(args.raw_output, args.dataset, annotation_opus_raw_dir, "--raw-output")
    validate_args(args)

    client = anthropic.Anthropic(max_retries=5)
    run = Run(args)
    if args.mode == "sync":
        run_sync(args, client, run)
    else:
        run_batch(args, client, run)

    print("Opus annotation run complete.")
    run.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
