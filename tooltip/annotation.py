"""Shared bbox/tip annotation computation and JSON payload helpers.

`scripts/generate_annotation.py` builds the automatic annotations from
segmentation masks. `scripts/annotation_editor.py` reuses the very same code to
recompute a frame when the user reverts a manual edit back to the automatic
result, so the two paths cannot drift apart.

Payload provenance
------------------

Every payload carries a ``source`` field:

- ``"auto"``   written by `generate_annotation`, freely regenerated from masks.
- ``"manual"`` written by `annotation_editor`, stored in the separate
  ``annotation-manual/`` tree and never overwritten by `generate_annotation`.

Files written before this field existed have no ``source`` key;
`annotation_source()` reads those as ``"auto"``.
"""
from __future__ import annotations

import json
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
SOURCE_AUTO = "auto"
SOURCE_MANUAL = "manual"

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
        source=SOURCE_AUTO,
    )


def write_annotation(output_path: Path, payload: dict[str, object]) -> None:
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def annotation_source(payload: dict[str, object]) -> str:
    """Return the payload's provenance, defaulting to auto for legacy files."""
    source = payload.get("source", SOURCE_AUTO)
    return SOURCE_MANUAL if source == SOURCE_MANUAL else SOURCE_AUTO
