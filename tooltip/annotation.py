"""Shared bbox/tip annotation computation and JSON payload helpers.

`scripts/generate-annotation-monai.py` builds the automatic annotations from
segmentation masks. `scripts/annotation-editor.py` shares the payload and
writing helpers when it saves a manual edit.

Payload provenance
------------------

Every payload carries a ``source`` field naming what produced it:

- ``"tooltip-annotator/scripts/generate-annotation-monai.py"`` (`SOURCE_MASK`)
  written by `generate-annotation-monai` into ``annotation-monai/``, freely
  regenerated from masks.
- ``"manual"`` written by `annotation-editor` into ``annotation-manual/`` and
  mirrored into ``annotation/``.
- any other string: an automatic labeller outside this project, e.g. the
  path of the detector checkpoint the parent repository relabelled with.

Files written before this field existed have no ``source`` key, and files
written before the sources were spelled out say ``"auto"``; both came from
the mask pipeline. `annotation_source()` returns the value as it is, with
``"auto"`` for a missing key.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

try:
    import cv2
except ImportError as exc:  # pragma: no cover - depends on runtime environment
    cv2 = None
    CV2_IMPORT_ERROR = exc
else:
    CV2_IMPORT_ERROR = None

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - depends on runtime environment
    np = None
    NUMPY_IMPORT_ERROR = exc
else:
    NUMPY_IMPORT_ERROR = None


ANNOTATION_SUFFIX = ".json"
# The path, from the parent repository root, of the script that writes these.
SOURCE_MASK = "tooltip-annotator/scripts/generate-annotation-monai.py"
SOURCE_LEGACY_AUTO = "auto"
SOURCE_MANUAL = "manual"

# Two tips of one tool at most this many pixels apart are one tip: the 20 px
# tolerance of the tip F1 @ 20 px metric. merge_close_tips() replaces them
# with their mean.
TIP_MERGE_RADIUS = 20

# Contours this small are almost always noise rather than a tool: drop a box
# when both sides are under SMALL_BOX_MIN_SIZE or either side is under
# THIN_BOX_MIN_SIZE.
SMALL_BOX_MIN_SIZE = 16
THIN_BOX_MIN_SIZE = 10


def load_binary_mask(mask_path: Path) -> np.ndarray:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise RuntimeError(f"Failed to read segmentation mask: {mask_path}")

    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

    _, binary_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return binary_mask


def contour_centroid(points: np.ndarray) -> np.ndarray:
    contour = points.reshape(-1, 1, 2).astype(np.int32)
    moments = cv2.moments(contour)
    if moments["m00"] != 0:
        return np.array(
            [
                moments["m10"] / moments["m00"],
                moments["m01"] / moments["m00"],
            ],
            dtype=np.float32,
        )

    return points.mean(axis=0, dtype=np.float32)


def farthest_point(reference: np.ndarray, points: np.ndarray) -> np.ndarray:
    distances = np.sum((points - reference) ** 2, axis=1)
    return points[int(np.argmax(distances))]


def compute_tip(points: np.ndarray, image_center: np.ndarray) -> np.ndarray:
    center = contour_centroid(points)
    point_a = farthest_point(center, points)
    point_b = farthest_point(point_a.astype(np.float32), points)

    distance_a = np.sum((point_a.astype(np.float32) - image_center) ** 2)
    distance_b = np.sum((point_b.astype(np.float32) - image_center) ** 2)
    return point_a if distance_a <= distance_b else point_b


def is_too_small_box(width: int, height: int) -> bool:
    if width < SMALL_BOX_MIN_SIZE and height < SMALL_BOX_MIN_SIZE:
        return True
    return width < THIN_BOX_MIN_SIZE or height < THIN_BOX_MIN_SIZE


def extract_annotations(mask: np.ndarray) -> list[dict[str, object]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    image_height, image_width = mask.shape[:2]
    image_center = np.array([image_width / 2.0, image_height / 2.0], dtype=np.float32)

    contour_entries: list[tuple[tuple[int, int, int, int], dict[str, object]]] = []

    for contour in contours:
        if contour.size == 0:
            continue

        x, y, width, height = cv2.boundingRect(contour.astype(np.int32))
        if is_too_small_box(width, height):
            continue

        points = contour.reshape(-1, 2).astype(np.float32)
        tip = compute_tip(points, image_center)

        annotation = {
            "bbox": {
                "x": int(x),
                "y": int(y),
                "width": int(width),
                "height": int(height),
            },
            "tip": {
                "x": int(round(float(tip[0]))),
                "y": int(round(float(tip[1]))),
            },
        }
        contour_entries.append(((x, y, width, height), annotation))

    contour_entries.sort(key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3]))
    return [entry[1] for entry in contour_entries]


def merge_close_tips(annotation: dict) -> bool:
    """Fold ``tip2`` into ``tip`` when they are within TIP_MERGE_RADIUS.

    The merged tip is the mean of the two, rounded to whole pixels (halves
    up). Returns whether the annotation changed.
    """
    tip, tip2 = annotation.get("tip"), annotation.get("tip2")
    if not isinstance(tip, dict) or not isinstance(tip2, dict):
        return False
    if math.dist((tip["x"], tip["y"]), (tip2["x"], tip2["y"])) > TIP_MERGE_RADIUS:
        return False
    annotation["tip"] = {
        key: int(math.floor((tip[key] + tip2[key]) / 2 + 0.5)) for key in ("x", "y")
    }
    del annotation["tip2"]
    return True


def build_payload(
    image_name: str,
    width: int,
    height: int,
    annotations: list[dict[str, object]],
    source: str,
) -> dict[str, object]:
    """Assemble one frame's annotation payload.

    Manual payloads additionally record ``edited_at`` so an edit can be dated
    without consulting the filesystem.
    """
    payload: dict[str, object] = {
        "image": image_name,
        "width": int(width),
        "height": int(height),
        "source": source,
        "annotations": annotations,
    }
    if source == SOURCE_MANUAL:
        payload["edited_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return payload


def build_auto_payload(mask_path: Path, mask: np.ndarray) -> dict[str, object]:
    height, width = mask.shape[:2]
    return build_payload(
        image_name=mask_path.name,
        width=width,
        height=height,
        annotations=extract_annotations(mask),
        source=SOURCE_MASK,
    )


def write_annotation(output_path: Path, payload: dict[str, object]) -> None:
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def annotation_source(payload: dict[str, object]) -> str:
    """Return the payload's provenance, ``"auto"`` for files without one."""
    return str(payload.get("source", SOURCE_LEGACY_AUTO))
