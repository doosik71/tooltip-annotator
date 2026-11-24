from __future__ import annotations

import argparse
import json
import math
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont, messagebox, ttk

from tooltip.annotation import (
    ANNOTATION_SUFFIX,
    SOURCE_MANUAL,
    build_payload,
    write_annotation,
)
from tooltip.dataset_paths import (
    annotation_dir,
    annotation_manual_dir,
    images_dir,
    list_datasets,
    resolve_path,
    screenshot_dir,
)

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


SPLIT_NAMES = ("train", "val", "test")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
HANDLE_SIZE = 7.5
TIP_RADIUS = 6
# Annotation keys holding a tip. "tip2" is optional: annotation-qwen records the
# second end of an opened jaw there.
TIP_KEYS = ("tip", "tip2")
# Add mode dims the image to this brightness, except inside the box being drawn.
ADD_MODE_BRIGHTNESS = 0.5
MIN_BOX_SIZE = 4
# Pointer shape and fill colour for the tip or resize handle under the pointer.
HANDLE_CURSOR = "crosshair"
HANDLE_HOVER_FILL = "#ffffff"

# Image list rows are coloured by their Source column: the n-th tab after
# Default (Manual, then each annotation-* tab) takes the n-th background. Tabs
# beyond the palette and rows matching no tab keep the default colours. The
# selected row always takes the theme's selection colours, which override tag
# colours.
SOURCE_ROW_BACKGROUNDS = (
    "#ffe9a8",  # Manual: yellow
    "#cfe6ff",  # sky
    "#d3f2d3",  # green
    "#f5d3f5",  # pink
    "#ffd9c2",  # peach
    "#e0d9ff",  # lavender
    "#cff2ec",  # mint
    "#f9d2d2",  # rose
    "#e6f2b8",  # lime
    "#eee3cf",  # sand
)
SOURCE_ROW_FOREGROUND = "#1a1a1a"
# Deeper shades of the row backgrounds, in the same order, for the marker strip
# beside the list scrollbar, where the pale row colours would vanish against
# its grey background.
SOURCE_MARKER_COLORS = (
    "#e8a33d",  # Manual: yellow
    "#4a9fe8",  # sky
    "#3fae4f",  # green
    "#c95ac9",  # pink
    "#f07f3c",  # peach
    "#7e6ad6",  # lavender
    "#2eb8a0",  # mint
    "#d9534f",  # rose
    "#9cbf2b",  # lime
    "#b39563",  # sand
)

# Image list columns, in pixels. The Source column names the tab whose labels
# annotation/ holds for the frame (see default_source()).
LIST_NUMBER_COLUMN_WIDTH = 80
LIST_IMAGE_COLUMN_WIDTH = 230
LIST_SOURCE_COLUMN_WIDTH = 80
# Source cells are filled only for rows on screen, in a worker thread, shortly
# after the list stops scrolling; finished work is picked up by polling.
SOURCE_UPDATE_DELAY_MS = 50
SOURCE_POLL_MS = 30
# The marker strip samples one frame per pixel row, evenly spaced over the
# split (every frame when the split is shorter than the strip), and the worker
# fills the Source of those samples this many at a time. Visible rows requested
# meanwhile wait for at most one chunk.
SOURCE_SCAN_CHUNK = 100

# The Every selector lists only every N-th frame of the split (list numbers
# N, 2N, 3N, ...; numbers start at 1), so a pass over the list spreads over
# all of it. N runs from 1 (every frame) to this value.
MAX_LIST_STRIDE = 20

# A thin strip beside the list scrollbar shows the Source (in
# SOURCE_MARKER_COLORS) of sampled frames and where the current frame sits in
# the whole list, like the overview ruler in VS Code.
LIST_MARKER_WIDTH = 8
LIST_MARKER_BACKGROUND = "#e6e6e6"
# The visible-range box is shaded with this colour at this opacity.
LIST_MARKER_VISIBLE_COLOR = "#000000"
LIST_MARKER_VISIBLE_ALPHA = 0.3
# A large split shows well under one pixel's worth of rows, so the visible-range
# box is drawn at least this tall to stay findable.
LIST_MARKER_VISIBLE_MIN_HEIGHT = 8
LIST_MARKER_CURRENT_COLOR = "#1565c0"

# The tool number drawn on each bbox, as a multiple of the canvas default font.
ANNOTATION_LABEL_FONT_SCALE = 2

# The tool count in the status bar stands out from the rest of the readout.
TOOL_COUNT_FONT_SCALE = 1.5
TOOL_COUNT_FOREGROUND = "#1565c0"

# Toolbar buttons are colour-coded by what they do: creating, destroying,
# writing to disk, and discarding in-memory edits.
BUTTON_STYLES = {
    "Add.TButton": "#1565c0",     # blue
    "Delete.TButton": "#c62828",  # red
    "Save.TButton": "#e65100",    # orange
    "Reload.TButton": "#6a1b9a",  # purple
    "Screenshot.TButton": "#00838f",  # teal
}
ADD_ACTIVE_STYLE = "AddActive.TButton"
ADD_ACTIVE_BACKGROUND = "#ffe680"
ADD_ACTIVE_HOVER_BACKGROUND = "#ffd84d"
BUTTON_DISABLED_FOREGROUND = "#9e9e9e"

# Button labels carry their shortcut so the toolbar documents itself.
ADD_BUTTON_LABEL = "Add Tool [INS/Wheel]"
ADD_BUTTON_ACTIVE_LABEL = "Adding... (Esc/Wheel to cancel)"
DELETE_BUTTON_LABEL = "Delete Tool [DEL]"
SAVE_BUTTON_LABEL = "Save [F2]"
RELOAD_BUTTON_LABEL = "Reload [F3]"
SCREENSHOT_BUTTON_LABEL = "Screenshot [F5]"
AUTO_SAVE_LABEL = "Auto Save [F9]"
SHOW_ANNOTATION_LABEL = "Show Annotation [F10]"
KEEP_TAB_LABEL = "Keep Tab [F11]"

# The view tabs above the image. Default shows annotation/, the final labels
# training and evaluation read; Manual shows annotation-manual/. Every other
# annotation-* directory next to annotation/ is an automatic labeller's output
# (annotation-monai, annotation-qwen, ...) and gets a read-only tab of its own.
# Number keys 1-9 select the tabs in order.
DEFAULT_TAB = 0
MANUAL_TAB = 1
AUTO_DIR_PREFIX = "annotation-"
MAX_TAB_SHORTCUTS = 9
# Horizontal and vertical padding inside each tab, in pixels. The theme default
# leaves the tabs too narrow to hit comfortably.
TAB_STYLE = "Source.TNotebook"
TAB_PADDING = (20, 6)
# The selected tab is drawn in bold on this background so the shown source
# stands out; the colour matches the current-frame mark in the list strip.
TAB_SELECTED_BACKGROUND = "#1565c0"
TAB_SELECTED_FOREGROUND = "#ffffff"
# A tab without a file for the frame is greyed out on a darker background than
# the other tabs (#c3c3c3 in the default theme).
TAB_DISABLED_BACKGROUND = "#a6a6a6"
TAB_DISABLED_FOREGROUND = "#7a7a7a"

# Screenshots are drawn with OpenCV at the image's own resolution, so these
# mirror the canvas colours (as RGB) and sizes in image pixels.
SCREENSHOT_BOX_COLOR = (59, 215, 255)       # #3bd7ff
SCREENSHOT_TIP_LINE_COLOR = (255, 128, 128)  # #ff8080
SCREENSHOT_TIP_FILL_COLOR = (255, 77, 77)    # #ff4d4d
SCREENSHOT_TIP_OUTLINE_COLOR = (122, 0, 0)   # #7a0000
SCREENSHOT_LINE_WIDTH = 2
SCREENSHOT_LABEL_FONT_SCALE = 0.8
SCREENSHOT_LABEL_THICKNESS = 2


def read_annotations(path: Path) -> list | None:
    """The ``annotations`` list of one label file, or None if it is missing or unreadable."""
    try:
        return json.loads(path.read_text()).get("annotations")
    except (OSError, ValueError, AttributeError):
        return None


def default_source(
    file_name: str,
    default_dir: Path,
    candidates: list[tuple[str, Path]],
) -> str:
    """Name the first candidate whose labels equal annotation/'s for one frame.

    Only the ``annotations`` lists are compared, so metadata such as
    ``source``, ``model`` or ``edited_at`` does not matter. Returns "" when
    annotation/ has no file or no candidate matches.
    """
    default = read_annotations(default_dir / file_name)
    if default is None:
        return ""
    for label, directory in candidates:
        if read_annotations(directory / file_name) == default:
            return label
    return ""


class AnnotationEditor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.images_root = args.images
        self.annotation_root = args.annotation
        self.manual_root = args.manual
        self.current_dataset = args.dataset or ""
        self.dataset_locked = args.dataset_locked

        self.root = tk.Tk()
        self.root.title("Tooltip Annotation Editor")
        self.root.geometry("1600x960")
        self.root.minsize(1100, 700)

        # Canvas text items default to TkDefaultFont; scale a copy of it for the
        # per-tool number so the label stays readable over the video frame.
        # Tk encodes a size in pixels as a negative number, and multiplying
        # keeps that convention intact.
        canvas_font = tkfont.nametofont("TkDefaultFont")
        self.annotation_label_font = tkfont.Font(
            family=canvas_font.cget("family"),
            size=canvas_font.cget("size") * ANNOTATION_LABEL_FONT_SCALE,
            weight=canvas_font.cget("weight"),
        )
        self.tool_count_font = tkfont.Font(
            family=canvas_font.cget("family"),
            size=round(canvas_font.cget("size") * TOOL_COUNT_FONT_SCALE),
            weight="bold",
        )

        self.dataset_var = tk.StringVar(value=self.current_dataset)
        self.split_var = tk.StringVar(value=SPLIT_NAMES[0])
        self.auto_save_var = tk.BooleanVar(value=args.auto_save)
        self.show_annotation_var = tk.BooleanVar(value=True)
        self.keep_tab_var = tk.BooleanVar(value=False)
        self.list_stride_var = tk.StringVar(value="1")
        # Only frames whose list number (index + 1) is divisible by list_stride
        # are rows of the image list.
        self.list_stride = 1
        self.status_var = tk.StringVar(value="Ready")
        self.tool_count_var = tk.StringVar(value="0")
        self.images_label_var = tk.StringVar(value="Images (0 / 0)")

        self.current_split = SPLIT_NAMES[0]
        self.image_paths: list[Path] = []
        self.current_index: int | None = None
        self.current_image_path: Path | None = None
        self.current_image_rgb: np.ndarray | None = None
        self.current_annotations: list[dict[str, dict[str, int]]] = []
        # (label, root, kind) per view tab, kind being "default", "manual" or
        # "auto". current_tab is the tab shown; preferred_tab is the one the
        # user picked last. A newly opened frame starts on Default, or with
        # Keep Tab on, on preferred_tab when the frame has it.
        self.tabs: list[tuple[str, Path, str]] = []
        self.tab_frames: list[ttk.Frame] = []
        self.current_tab = DEFAULT_TAB
        self.preferred_tab = DEFAULT_TAB
        self.manual_stems: set[str] = set()
        self.manual_indices: set[int] = set()
        self.list_index_width = 1
        # Source column cache by list index. source_generation is bumped on
        # every split load so answers for the previous list are dropped.
        self.default_sources: dict[int, str] = {}
        self.source_pending: set[int] = set()
        self.source_generation = 0
        self.source_update_job: str | None = None
        # Row tag per Source label, rebuilt with the tabs.
        self.source_tags: dict[str, str] = {}
        # Marker strip (priority, colour) per Source label, rebuilt with the
        # tabs; the earlier tab wins when frames share a pixel row.
        self.source_marker_colors: dict[str, tuple[int, str]] = {}
        # Sampled list indices still waiting for the background Source scan,
        # and whether a scan chunk is in the worker.
        self.source_scan_queue: list[int] = []
        self.source_scan_running = False
        self.source_executor = ThreadPoolExecutor(max_workers=1)
        self.image_width = 0
        self.image_height = 0

        self.selected_annotation_index: int | None = None
        self.mode = "select"
        self.drag_state: dict[str, object] | None = None
        self.pointer_position: tuple[float, float] | None = None
        self.hovered_handle: tuple[str, int, str | None] | None = None
        self.preview_box: tuple[float, float, float, float] | None = None
        self.dirty = False
        self.photo_image: tk.PhotoImage | None = None
        self.canvas_scale = 1.0
        self.canvas_offset_x = 0.0
        self.canvas_offset_y = 0.0
        self.canvas_image_width = 0
        self.canvas_image_height = 0

        self._build_ui()
        self._bind_events()
        self._ensure_output_dirs()
        self._rebuild_tabs()
        self._load_split(self.current_split)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_button_styles(self) -> None:
        """Colour-code the toolbar buttons.

        Each colour gets its own ttk style because ttk buttons take no direct
        foreground option. The disabled state is mapped back to grey so a
        coloured button still reads as unavailable.
        """
        style = ttk.Style()
        for style_name, foreground in BUTTON_STYLES.items():
            style.configure(style_name, foreground=foreground)
            style.map(style_name, foreground=[("disabled", BUTTON_DISABLED_FOREGROUND)])

        style.configure(
            ADD_ACTIVE_STYLE,
            foreground=BUTTON_STYLES["Add.TButton"],
            background=ADD_ACTIVE_BACKGROUND,
        )
        style.map(
            ADD_ACTIVE_STYLE,
            foreground=[("disabled", BUTTON_DISABLED_FOREGROUND)],
            background=[("active", ADD_ACTIVE_HOVER_BACKGROUND)],
        )

    def _build_ui(self) -> None:
        self._configure_button_styles()

        top_bar = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        top_bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top_bar, text="Dataset").pack(side=tk.LEFT)
        self.dataset_combobox = ttk.Combobox(
            top_bar,
            textvariable=self.dataset_var,
            values=list_datasets(),
            state=tk.DISABLED if self.dataset_locked else "readonly",
            width=14,
        )
        self.dataset_combobox.pack(side=tk.LEFT, padx=(8, 18))

        ttk.Label(top_bar, text="Split").pack(side=tk.LEFT)
        self.split_combobox = ttk.Combobox(
            top_bar,
            textvariable=self.split_var,
            values=SPLIT_NAMES,
            state="readonly",
            width=8,
        )
        self.split_combobox.pack(side=tk.LEFT, padx=(8, 18))

        self.add_button = ttk.Button(
            top_bar, text=ADD_BUTTON_LABEL, style="Add.TButton", command=self._on_add_button
        )
        self.add_button.pack(side=tk.LEFT)

        self.delete_button = ttk.Button(
            top_bar, text=DELETE_BUTTON_LABEL, style="Delete.TButton", command=self._delete_selected
        )
        self.delete_button.pack(side=tk.LEFT, padx=(8, 0))

        self.save_button = ttk.Button(
            top_bar, text=SAVE_BUTTON_LABEL, style="Save.TButton", command=self._save_current_annotation
        )
        self.save_button.pack(side=tk.LEFT, padx=(8, 0))

        self.reload_button = ttk.Button(
            top_bar, text=RELOAD_BUTTON_LABEL, style="Reload.TButton",
            command=self._reload_current_annotation
        )
        self.reload_button.pack(side=tk.LEFT, padx=(8, 0))

        self.screenshot_button = ttk.Button(
            top_bar, text=SCREENSHOT_BUTTON_LABEL, style="Screenshot.TButton",
            command=self._save_screenshot
        )
        self.screenshot_button.pack(side=tk.LEFT, padx=(8, 0))

        self.auto_save_checkbutton = ttk.Checkbutton(
            top_bar,
            text=AUTO_SAVE_LABEL,
            variable=self.auto_save_var,
            command=self._on_auto_save_toggled,
        )
        self.auto_save_checkbutton.pack(side=tk.LEFT, padx=(12, 0))

        self.show_annotation_checkbutton = ttk.Checkbutton(
            top_bar,
            text=SHOW_ANNOTATION_LABEL,
            variable=self.show_annotation_var,
            command=self._render_scene,
        )
        self.show_annotation_checkbutton.pack(side=tk.LEFT, padx=(18, 0))

        self.keep_tab_checkbutton = ttk.Checkbutton(
            top_bar,
            text=KEEP_TAB_LABEL,
            variable=self.keep_tab_var,
        )
        self.keep_tab_checkbutton.pack(side=tk.LEFT, padx=(18, 0))

        ttk.Label(top_bar, text="Every").pack(side=tk.LEFT, padx=(18, 0))
        self.list_stride_combobox = ttk.Combobox(
            top_bar,
            textvariable=self.list_stride_var,
            values=[str(n) for n in range(1, MAX_LIST_STRIDE + 1)],
            state="readonly",
            width=4,
        )
        self.list_stride_combobox.pack(side=tk.LEFT, padx=(8, 0))

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left_panel = ttk.Frame(body, padding=(0, 0, 10, 0))
        body.add(left_panel, weight=0)

        ttk.Label(left_panel, textvariable=self.images_label_var).pack(anchor=tk.W, pady=(0, 6))

        list_frame = ttk.Frame(left_panel)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.image_list = ttk.Treeview(
            list_frame,
            columns=("number", "image", "source"),
            show="headings",
            selectmode="browse",
        )
        self.image_list.heading("number", text="#", anchor=tk.W)
        self.image_list.heading("image", text="Image", anchor=tk.W)
        self.image_list.heading("source", text="Source", anchor=tk.W)
        self.image_list.column("number", width=LIST_NUMBER_COLUMN_WIDTH, stretch=False)
        self.image_list.column("image", width=LIST_IMAGE_COLUMN_WIDTH, stretch=True)
        self.image_list.column("source", width=LIST_SOURCE_COLUMN_WIDTH, stretch=False)
        self.image_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.image_list.yview)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_scrollbar = list_scrollbar
        self.image_list.configure(yscrollcommand=self._on_list_scrolled)

        self.list_marker = tk.Canvas(
            list_frame,
            width=LIST_MARKER_WIDTH,
            background=LIST_MARKER_BACKGROUND,
            highlightthickness=0,
        )
        self.list_marker.pack(side=tk.RIGHT, fill=tk.Y)

        right_panel = ttk.Frame(body)
        body.add(right_panel, weight=1)

        # Only the tab strip is used: every tab holds an empty frame and the
        # single canvas below shows whichever annotation source is selected.
        tab_style = ttk.Style()
        tab_style.configure(f"{TAB_STYLE}.Tab", padding=TAB_PADDING)
        self.tab_selected_font = tkfont.nametofont("TkDefaultFont").copy()
        self.tab_selected_font.configure(weight="bold")
        # A style's state map replaces the inherited one per option, so the
        # theme's grey "disabled" foreground has to be restated here.
        tab_style.map(
            f"{TAB_STYLE}.Tab",
            background=[("disabled", TAB_DISABLED_BACKGROUND), ("selected", TAB_SELECTED_BACKGROUND)],
            foreground=[("disabled", TAB_DISABLED_FOREGROUND), ("selected", TAB_SELECTED_FOREGROUND)],
            font=[("selected", self.tab_selected_font)],
        )
        self.tab_notebook = ttk.Notebook(right_panel, style=TAB_STYLE)
        self.tab_notebook.pack(side=tk.TOP, fill=tk.X)

        self.canvas = tk.Canvas(right_panel, background="#101417", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # The toolbar carries every shortcut in its button labels now, so the
        # hint line only covers the mouse gestures, leaving the bottom bar wide
        # enough for the status readout that used to crowd the toolbar.
        instruction = (
            "Drag bbox interior to move. Drag corner/edge handles to resize. "
            "Drag red tip handle to move the tip. Right-click for tool actions. "
            "Arrow keys or mouse wheel move between images."
        )
        bottom_bar = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bottom_bar, text=instruction).pack(side=tk.LEFT)
        # The tool count gets labels of its own so it can be coloured and stay
        # visible while a status message replaces the rest of the readout.
        status_frame = ttk.Frame(bottom_bar)
        status_frame.pack(side=tk.RIGHT)
        ttk.Label(status_frame, text="tools").pack(side=tk.LEFT)
        ttk.Label(
            status_frame,
            textvariable=self.tool_count_var,
            font=self.tool_count_font,
            foreground=TOOL_COUNT_FOREGROUND,
        ).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(status_frame, text="|").pack(side=tk.LEFT, padx=6)
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)

        self._update_buttons()

    def _bind_events(self) -> None:
        self.dataset_combobox.bind("<<ComboboxSelected>>", self._on_dataset_changed)
        self.split_combobox.bind("<<ComboboxSelected>>", self._on_split_changed)
        self.list_stride_combobox.bind("<<ComboboxSelected>>", self._on_list_stride_changed)
        self.image_list.bind("<<TreeviewSelect>>", self._on_image_selected)

        # The Treeview class binds Up/Down to move the selection itself, which
        # fires <<TreeviewSelect>>, and the toplevel binding below would then
        # move it a second time. Widget bindings run before class and toplevel
        # ones, so handling Up/Down here and returning "break" keeps it to one
        # step. Left/Right need no such guard: on a flat list their class
        # bindings only open or close tree items, which do not exist here.
        self.image_list.bind("<Up>", self._on_previous_image_shortcut)
        self.image_list.bind("<Down>", self._on_next_image_shortcut)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        # While the button is held the more specific <B1-Motion> wins, so the
        # cursor chosen before the press stays put for the whole drag.
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<Configure>", self._on_canvas_resized)
        self.list_marker.bind("<Configure>", self._on_list_marker_resized)
        # identify() still answers for the old layout while <Configure> is
        # being handled, so measure once Tk is idle again.
        self.list_scrollbar.bind(
            "<Configure>", lambda _event: self.root.after_idle(self._fit_list_marker_to_trough)
        )
        # Wheel click on the image toggles add mode: it enters it like Insert
        # and cancels it like Escape, so a new box can be started or abandoned
        # without leaving the mouse. Button-2 is the wheel on Windows and X11.
        self.canvas.bind("<ButtonPress-2>", self._on_canvas_wheel_click)
        # Right click opens a context menu for the tool under the pointer, or
        # for the selected one when the click lands on empty image.
        self.canvas.bind("<ButtonPress-3>", self._on_canvas_context_menu)
        # Wheel scroll over the image steps through images: up is previous,
        # down is next. Windows (and Tk 9 on X11) report <MouseWheel>; older
        # Tk on X11 reports Button-4/5 instead.
        self.canvas.bind("<MouseWheel>", self._on_canvas_wheel)
        self.canvas.bind("<Button-4>", self._on_previous_image_shortcut)
        self.canvas.bind("<Button-5>", self._on_next_image_shortcut)
        # One shortcut per action, each printed on its button. Bare letter keys
        # are deliberately not bound: a stray "d" must not delete a tool.
        self.root.bind("<Insert>", self._on_add_shortcut)
        self.root.bind("<Delete>", self._on_delete_shortcut)
        self.root.bind("<Control-s>", self._on_save_shortcut)
        self.root.bind("<Control-S>", self._on_save_shortcut)
        self.root.bind("<Up>", self._on_previous_image_shortcut)
        self.root.bind("<Left>", self._on_previous_image_shortcut)
        self.root.bind("<Down>", self._on_next_image_shortcut)
        self.root.bind("<Right>", self._on_next_image_shortcut)
        self.root.bind("<F2>", self._on_save_shortcut)
        self.root.bind("<F3>", self._on_reload_shortcut)
        self.root.bind("<F5>", self._on_screenshot_shortcut)
        self.root.bind("<F9>", lambda _event: self._on_toggle_shortcut(self.auto_save_checkbutton))
        self.root.bind("<F10>", lambda _event: self._on_toggle_shortcut(self.show_annotation_checkbutton))
        self.root.bind("<F11>", lambda _event: self._on_toggle_shortcut(self.keep_tab_checkbutton))
        self.root.bind("<Escape>", self._on_escape)
        for number in range(1, MAX_TAB_SHORTCUTS + 1):
            self.root.bind(
                f"<Key-{number}>",
                lambda _event, index=number - 1: self._on_tab_shortcut(index),
            )
        self.tab_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        # Clicking a tab focuses the notebook, whose class bindings would then
        # cycle tabs on Left/Right. Keep the arrows stepping through images.
        for key, handler in (
            ("<Left>", self._on_previous_image_shortcut),
            ("<Up>", self._on_previous_image_shortcut),
            ("<Right>", self._on_next_image_shortcut),
            ("<Down>", self._on_next_image_shortcut),
        ):
            self.tab_notebook.bind(key, handler)

    def _ensure_output_dirs(self) -> None:
        """Create the generated-annotation directories only.

        annotation-manual/ is left untouched: it is created on the first save
        instead. Pre-creating it would leave empty directories behind for
        datasets nobody has corrected, and would block `git clone` for anyone
        keeping their hand labels in a repository of their own at that path.
        """
        for split_name in SPLIT_NAMES:
            (self.annotation_root / split_name).mkdir(parents=True, exist_ok=True)

    def _on_close(self) -> None:
        if not self._confirm_leave_current_image():
            return
        self.source_executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    def _on_dataset_changed(self, _event: tk.Event[tk.Misc]) -> None:
        requested_dataset = self.dataset_var.get()
        if requested_dataset == self.current_dataset:
            return
        if not self._confirm_leave_current_image():
            self.dataset_var.set(self.current_dataset)
            return
        self._switch_dataset(requested_dataset)

    def _switch_dataset(self, dataset_name: str) -> None:
        """Repoint every root at another dataset and reload the current split."""
        self.current_dataset = dataset_name
        self.dataset_var.set(dataset_name)
        self.images_root = images_dir(dataset_name)
        self.annotation_root = annotation_dir(dataset_name)
        self.manual_root = annotation_manual_dir(dataset_name)
        # Only materialise output directories for a dataset that actually has
        # frames, so selecting a source-only entry does not litter data/.
        if self.images_root.is_dir():
            self._ensure_output_dirs()
        self._rebuild_tabs()
        self._load_split(self.current_split)

    def _on_split_changed(self, _event: tk.Event[tk.Misc]) -> None:
        requested_split = self.split_var.get()
        if requested_split == self.current_split:
            return
        if not self._confirm_leave_current_image():
            self.split_var.set(self.current_split)
            return
        self._load_split(requested_split)

    def _on_image_selected(self, _event: tk.Event[tk.Misc]) -> None:
        # <<TreeviewSelect>> is queued, so it also arrives after the code
        # selects a row itself; by then current_index already names that row
        # and the check below ignores it.
        selection = self.image_list.selection()
        if not selection:
            return
        new_index = int(selection[0])
        if new_index == self.current_index:
            return
        if not self._confirm_leave_current_image():
            self._restore_list_selection()
            return
        self._open_image_at_index(new_index)

    def _on_canvas_resized(self, _event: tk.Event[tk.Misc]) -> None:
        self._render_scene()

    def _on_auto_save_toggled(self) -> None:
        """Flush the pending edit as soon as auto save is switched on."""
        if self.auto_save_var.get() and self.dirty:
            self._save_current_annotation()
            return
        self._update_status()

    def _on_add_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._enter_add_mode()
        return "break"

    def _on_save_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._save_current_annotation()
        return "break"

    def _on_delete_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._delete_selected()
        return "break"

    def _on_reload_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._reload_current_annotation()
        return "break"

    def _on_tab_shortcut(self, index: int) -> str:
        self._request_tab(index)
        return "break"

    def _on_tab_changed(self, _event: tk.Event[tk.Misc]) -> None:
        # The event is queued, so it also arrives after every programmatic
        # select(); by then current_tab already matches and it is ignored.
        selected = self.tab_notebook.index("current")
        if selected != self.current_tab:
            self._request_tab(selected)

    def _on_screenshot_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._save_screenshot()
        return "break"

    def _on_toggle_shortcut(self, checkbutton: ttk.Checkbutton) -> str:
        # invoke() toggles the box and runs its command, exactly like a click.
        # "break" also keeps F10 from Tk's default menu-bar binding.
        checkbutton.invoke()
        return "break"

    def _on_previous_image_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._navigate_images(-1)
        return "break"

    def _on_next_image_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._navigate_images(1)
        return "break"

    def _on_add_button(self) -> None:
        # Clicking the button again while adding cancels, like a wheel click.
        if self.mode == "add":
            self._on_escape(None)
        else:
            self._enter_add_mode()

    def _on_canvas_wheel_click(self, event: tk.Event[tk.Misc]) -> str:
        if self.mode == "add":
            return self._on_escape(event)
        return self._on_add_shortcut(event)

    def _on_canvas_wheel(self, event: tk.Event[tk.Misc]) -> str:
        if event.delta > 0:
            self._navigate_images(-1)
        elif event.delta < 0:
            self._navigate_images(1)
        return "break"

    def _on_escape(self, _event: tk.Event[tk.Misc]) -> str:
        if self.mode == "add":
            self.mode = "select"
            self.preview_box = None
            self.drag_state = None
            self._update_status()
            self._update_buttons()
            self._render_scene()
        return "break"

    def _load_split(self, split_name: str) -> None:
        self.current_split = split_name
        self.split_var.set(split_name)
        split_dir = self.images_root / split_name
        self.image_paths = self._list_images(split_dir)
        self.current_index = None
        self.current_image_path = None
        self.current_image_rgb = None
        self.current_annotations = []
        self.current_tab = DEFAULT_TAB
        self.selected_annotation_index = None
        self.preview_box = None
        self.drag_state = None
        self.mode = "select"
        self.dirty = False
        self.manual_stems = self._list_manual_stems(split_name)
        self.manual_indices = set()
        # Pad the running number to the digit count of the split's frame total,
        # so [00001] in a 71,032-frame split and [1] in a 3-frame one.
        self.list_index_width = len(str(len(self.image_paths))) or 1

        self.source_generation += 1
        self.default_sources = {}
        self.source_pending = set()
        self.source_scan_queue = []
        self.source_scan_running = False

        for index, image_path in enumerate(self.image_paths):
            if image_path.stem in self.manual_stems:
                self.manual_indices.add(index)
        self._fill_image_list()

        first_listed = self.list_stride - 1
        if first_listed < len(self.image_paths):
            self._select_list_row(first_listed)
            self._open_image_at_index(first_listed)
        else:
            self._update_images_label()
            self._refresh_tab_states()
            self._render_scene()
            self._update_status("No images found in the selected split.")
        self._update_buttons()
        self._render_list_markers()
        self._schedule_source_update()
        self._scan_marker_samples()

    def _open_image_at_index(self, index: int) -> None:
        self.current_index = index
        self.current_image_path = self.image_paths[index]
        self.current_image_rgb = self._load_rgb_image(self.current_image_path)
        self.image_height, self.image_width = self.current_image_rgb.shape[:2]
        self.current_tab = (
            self.preferred_tab
            if self.keep_tab_var.get() and self._tab_available(self.preferred_tab)
            else DEFAULT_TAB
        )
        self._update_images_label()
        self._render_list_markers()
        self._load_current_tab()

    def _discover_tabs(self) -> list[tuple[str, Path, str]]:
        """Return Default, Manual, then one tab per annotation-* sibling directory.

        The automatic sources are found on disk rather than listed in code, so
        a new labeller only has to write annotation-<name>/ to get a tab.
        """
        tabs = [
            ("Default", self.annotation_root, "default"),
            ("Manual", self.manual_root, "manual"),
        ]
        parent = self.annotation_root.parent
        if parent.is_dir():
            for path in sorted(parent.glob(f"{AUTO_DIR_PREFIX}*")):
                if not path.is_dir() or path.resolve() == self.manual_root.resolve():
                    continue
                if path.name == self.manual_root.name:
                    continue
                label = path.name.removeprefix(AUTO_DIR_PREFIX).capitalize()
                tabs.append((label, path, "auto"))
        return tabs

    def _rebuild_tabs(self) -> None:
        for frame in self.tab_frames:
            self.tab_notebook.forget(frame)
            frame.destroy()
        self.tabs = self._discover_tabs()
        self.tab_frames = []
        for index, (label, _root, _kind) in enumerate(self.tabs):
            text = f"[{index + 1}] {label}" if index < MAX_TAB_SHORTCUTS else label
            frame = ttk.Frame(self.tab_notebook, height=0)
            self.tab_notebook.add(frame, text=text)
            self.tab_frames.append(frame)
        self.source_tags = {}
        self.source_marker_colors = {}
        for index, (label, _root, _kind) in enumerate(self.tabs[DEFAULT_TAB + 1 :]):
            if index < len(SOURCE_MARKER_COLORS):
                self.source_marker_colors[label] = (index, SOURCE_MARKER_COLORS[index])
            if index < len(SOURCE_ROW_BACKGROUNDS):
                tag = f"source-{index}"
                self.image_list.tag_configure(
                    tag, background=SOURCE_ROW_BACKGROUNDS[index], foreground=SOURCE_ROW_FOREGROUND
                )
                self.source_tags[label] = tag
        self.current_tab = DEFAULT_TAB
        self.preferred_tab = DEFAULT_TAB
        self.tab_notebook.select(DEFAULT_TAB)

    def _tab_annotation_path(self, tab_index: int, image_path: Path) -> Path:
        root = self.tabs[tab_index][1]
        return root / self.current_split / f"{image_path.stem}{ANNOTATION_SUFFIX}"

    def _tab_available(self, tab_index: int) -> bool:
        """Default is always open; every other tab needs a file for this frame."""
        if tab_index == DEFAULT_TAB:
            return True
        if self.current_image_path is None or tab_index >= len(self.tabs):
            return False
        return self._tab_annotation_path(tab_index, self.current_image_path).exists()

    def _refresh_tab_states(self) -> None:
        # Enable the shown tab before selecting it: a disabled tab cannot be
        # selected.
        for index in range(len(self.tabs)):
            available = self._tab_available(index)
            self.tab_notebook.tab(index, state=tk.NORMAL if available else tk.DISABLED)
        self.tab_notebook.select(self.current_tab)

    def _request_tab(self, index: int) -> None:
        """Switch the view to another annotation source, asking about unsaved edits."""
        if (
            index == self.current_tab
            or index >= len(self.tabs)
            or self.current_image_path is None
            or not self._tab_available(index)
            or not self._confirm_leave_current_image(always_ask=True)
        ):
            self.tab_notebook.select(self.current_tab)
            return
        self.current_tab = index
        self.preferred_tab = index
        self._load_current_tab()

    def _load_current_tab(self) -> None:
        """Show the current frame's annotations from the source of the current tab."""
        self._refresh_tab_states()
        self.current_annotations = self._load_annotation(
            self._tab_annotation_path(self.current_tab, self.current_image_path)
        )
        self.selected_annotation_index = 0 if self.current_annotations else None
        self.preview_box = None
        self.drag_state = None
        self.mode = "select"
        self.dirty = False
        self._update_buttons()
        self._update_status()
        self._render_scene()

    def _load_rgb_image(self, image_path: Path) -> np.ndarray:
        image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise RuntimeError(f"Failed to read image: {image_path}")
        return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    def _load_annotation(self, annotation_path: Path) -> list[dict[str, dict[str, int]]]:
        if not annotation_path.exists():
            return []

        try:
            payload = json.loads(annotation_path.read_text())
        except json.JSONDecodeError:
            messagebox.showwarning("Annotation", f"Invalid JSON: {annotation_path}")
            return []

        annotations = payload.get("annotations", [])
        normalized: list[dict[str, dict[str, int]]] = []
        for item in annotations:
            bbox = item.get("bbox", {})
            tip = item.get("tip", {})
            try:
                annotation = {
                    "bbox": self._normalize_bbox(
                        {
                            "x": int(bbox.get("x", 0)),
                            "y": int(bbox.get("y", 0)),
                            "width": int(bbox.get("width", 1)),
                            "height": int(bbox.get("height", 1)),
                        }
                    ),
                    "tip": self._normalize_tip(
                        {
                            "x": int(tip.get("x", 0)),
                            "y": int(tip.get("y", 0)),
                        }
                    ),
                }
                tip2 = item.get("tip2")
                if isinstance(tip2, dict):
                    annotation["tip2"] = self._normalize_tip(
                        {"x": int(tip2.get("x", 0)), "y": int(tip2.get("y", 0))}
                    )
            except (TypeError, ValueError):
                continue
            # Carried through untouched so a save keeps the instrument name.
            label = item.get("label")
            if isinstance(label, str):
                annotation["label"] = label
            normalized.append(annotation)
        return normalized

    def _save_current_annotation(self) -> None:
        """Write the shown annotation into annotation/, the final labels.

        An edit is stored in annotation-manual/ first and then mirrored into
        annotation/, whichever tab it was made on. An unedited automatic result
        (Monai, Qwen, ...) is adopted by copying its file into annotation/ as
        it is, keeping its own source. The automatic directories are never
        written to.
        """
        if self.current_image_path is None:
            return

        label, _root, kind = self.tabs[self.current_tab]
        annotation_path = self._tab_annotation_path(DEFAULT_TAB, self.current_image_path)
        annotation_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.dirty:
            if kind != "auto":
                return
            shutil.copyfile(
                self._tab_annotation_path(self.current_tab, self.current_image_path),
                annotation_path,
            )
            self._refresh_current_source()
            self._update_status(f"Adopted the {label} annotation into annotation/.")
            return

        payload = build_payload(
            image_name=self.current_image_path.name,
            width=self.image_width,
            height=self.image_height,
            annotations=[
                {key: annotation[key] for key in ("bbox", *TIP_KEYS, "label") if key in annotation}
                for annotation in self.current_annotations
            ],
            source=SOURCE_MANUAL,
        )

        manual_path = self._tab_annotation_path(MANUAL_TAB, self.current_image_path)
        manual_path.parent.mkdir(parents=True, exist_ok=True)
        write_annotation(manual_path, payload)
        shutil.copyfile(manual_path, annotation_path)

        self._set_current_manual_flag(True)
        self._refresh_current_source()
        self.dirty = False
        # An edit made on an automatic tab is a manual annotation now, so show
        # it under Manual rather than under the source it no longer matches.
        if kind == "auto":
            self.current_tab = MANUAL_TAB
        self._refresh_tab_states()
        self._update_buttons()
        self._update_status("Saved manual annotation.")

    def _save_screenshot(self) -> None:
        """Write the current frame with its visible overlays for slides.

        The annotation overlay follows the Show Annotation toggle. The image keeps its native resolution, and editing aids (selection
        highlight, resize handles, the add-mode preview box) are left out.
        """
        if self.current_image_path is None or self.current_image_rgb is None:
            return

        composed = self.current_image_rgb.copy()
        if self.show_annotation_var.get():
            self._draw_screenshot_annotations(composed)

        # With explicit path options there may be no dataset name; the images
        # root sits in the dataset directory, so its sibling is the fallback.
        screenshot_root = (
            screenshot_dir(self.current_dataset)
            if self.current_dataset
            else self.images_root.parent / "screenshot"
        )
        screenshot_root.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_root / self.current_image_path.name
        if not cv2.imwrite(str(screenshot_path), cv2.cvtColor(composed, cv2.COLOR_RGB2BGR)):
            messagebox.showerror("Screenshot", f"Failed to write screenshot: {screenshot_path}")
            return
        self._update_status(f"Saved screenshot: {screenshot_path}")

    def _draw_screenshot_annotations(self, image: np.ndarray) -> None:
        """Draw boxes, numbers and tips onto an RGB image, as on the canvas."""
        for index, annotation in enumerate(self.current_annotations):
            bbox = annotation["bbox"]
            x1, y1 = bbox["x"], bbox["y"]
            x2, y2 = x1 + bbox["width"], y1 + bbox["height"]
            cv2.rectangle(image, (x1, y1), (x2, y2), SCREENSHOT_BOX_COLOR,
                          SCREENSHOT_LINE_WIDTH, cv2.LINE_AA)
            label = str(index + 1)
            (_, text_height), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, SCREENSHOT_LABEL_FONT_SCALE, SCREENSHOT_LABEL_THICKNESS
            )
            cv2.putText(image, label, (x1 + 6, y1 + 6 + text_height), cv2.FONT_HERSHEY_SIMPLEX,
                        SCREENSHOT_LABEL_FONT_SCALE, SCREENSHOT_BOX_COLOR,
                        SCREENSHOT_LABEL_THICKNESS, cv2.LINE_AA)

        for annotation in self.current_annotations:
            bbox = annotation["bbox"]
            center = (bbox["x"] + bbox["width"] // 2, bbox["y"] + bbox["height"] // 2)
            for key in TIP_KEYS:
                if key not in annotation:
                    continue
                tip = (annotation[key]["x"], annotation[key]["y"])
                cv2.line(image, center, tip, SCREENSHOT_TIP_LINE_COLOR, SCREENSHOT_LINE_WIDTH, cv2.LINE_AA)
                cv2.circle(image, tip, TIP_RADIUS, SCREENSHOT_TIP_FILL_COLOR, -1, cv2.LINE_AA)
                cv2.circle(image, tip, TIP_RADIUS, SCREENSHOT_TIP_OUTLINE_COLOR,
                           SCREENSHOT_LINE_WIDTH, cv2.LINE_AA)

    def _list_manual_stems(self, split_name: str) -> set[str]:
        manual_dir = self.manual_root / split_name
        if not manual_dir.is_dir():
            return set()
        return {path.stem for path in manual_dir.glob(f"*{ANNOTATION_SUFFIX}")}

    def _fill_image_list(self) -> None:
        """Rebuild the list rows: list numbers N, 2N, ... (N = list_stride),
        each row keyed by its list index (number - 1)."""
        self.image_list.delete(*self.image_list.get_children())
        for index in range(self.list_stride - 1, len(self.image_paths), self.list_stride):
            label = self.default_sources.get(index, "")
            tag = self.source_tags.get(label)
            self.image_list.insert(
                "",
                tk.END,
                iid=str(index),
                values=(self._list_number(index), self.image_paths[index].name, label),
                tags=(tag,) if tag else (),
            )

    def _on_list_stride_changed(self, _event: tk.Event[tk.Misc]) -> None:
        """List only every N-th frame; a current frame left out moves to the
        listed frame just before it (or the first listed one)."""
        stride = int(self.list_stride_var.get())
        if stride == self.list_stride:
            return
        if stride > len(self.image_paths):
            # The split is shorter than N: the list would be empty.
            self.list_stride_var.set(str(self.list_stride))
            self._update_status(f"The split has fewer than {stride} images.")
            return
        target = None
        if self.current_index is not None and (self.current_index + 1) % stride:
            if not self._confirm_leave_current_image():
                self.list_stride_var.set(str(self.list_stride))
                return
            target = max(self.current_index - (self.current_index + 1) % stride, stride - 1)
        self.list_stride = stride
        self._fill_image_list()
        if target is not None:
            self._select_list_row(target)
            self._open_image_at_index(target)
        elif self.current_index is not None:
            self._select_list_row(self.current_index)
        self._render_list_markers()
        self._schedule_source_update()

    def _list_number(self, index: int) -> str:
        """The # column: running number, zero-padded to the split's digit count."""
        return f"{index + 1:0{self.list_index_width}d}"

    def _select_list_row(self, index: int) -> None:
        """Select, focus and scroll to one image-list row."""
        iid = str(index)
        self.image_list.selection_set(iid)
        self.image_list.focus(iid)
        self.image_list.see(iid)

    def _schedule_source_update(self) -> None:
        """Fill the Source cells of the rows on screen once scrolling settles."""
        if self.source_update_job is None:
            self.source_update_job = self.root.after(
                SOURCE_UPDATE_DELAY_MS, self._request_visible_sources
            )

    def _source_candidates(self) -> list[tuple[str, Path]]:
        """(tab label, split directory) of every tab except Default, in tab order."""
        return [(label, root / self.current_split) for label, root, _kind in self.tabs[DEFAULT_TAB + 1 :]]

    def _request_visible_sources(self) -> None:
        """Hand the visible rows without a Source value to the worker thread."""
        self.source_update_job = None
        total = len(self.image_paths)
        if total == 0 or not self.tabs:
            return
        # The list holds list numbers N, 2N, ... (N = list_stride), so row r
        # is list index (r + 1) * N - 1.
        stride = self.list_stride
        rows = total // stride
        first, last = (float(value) for value in self.image_list.yview())
        start = max(int(first * rows), 0)
        end = min(math.ceil(last * rows) + 1, rows)
        indices = [
            index
            for index in ((row + 1) * stride - 1 for row in range(start, end))
            if index not in self.default_sources and index not in self.source_pending
        ]
        if indices:
            self._submit_sources(indices)

    def _scan_marker_samples(self) -> None:
        """Queue the marker strip's sampled frames for the background Source scan."""
        self.source_scan_queue = [index for _top, _bottom, index in self._marker_samples()]
        if not self.source_scan_running:
            self._scan_source_chunk()

    def _scan_source_chunk(self) -> None:
        """Hand the next queued frames without a Source value to the worker.

        The following chunk is submitted only once this one is written back,
        so visible-row requests queue between chunks instead of behind the
        whole scan.
        """
        self.source_scan_running = False
        if not self.tabs:
            return
        while self.source_scan_queue:
            chunk = self.source_scan_queue[:SOURCE_SCAN_CHUNK]
            del self.source_scan_queue[:SOURCE_SCAN_CHUNK]
            indices = [
                index
                for index in chunk
                if index not in self.default_sources and index not in self.source_pending
            ]
            if indices:
                self.source_scan_running = True
                self._submit_sources(indices, on_done=self._scan_source_chunk)
                return

    def _submit_sources(self, indices: list[int], on_done=None) -> None:
        """Compute the Source of `indices` in the worker thread."""
        self.source_pending.update(indices)

        default_dir = self.tabs[DEFAULT_TAB][1] / self.current_split
        candidates = self._source_candidates()
        jobs = [(index, f"{self.image_paths[index].stem}{ANNOTATION_SUFFIX}") for index in indices]

        def work() -> list[tuple[int, str]]:
            return [(index, default_source(name, default_dir, candidates)) for index, name in jobs]

        self._poll_sources(self.source_executor.submit(work), self.source_generation, on_done)

    def _poll_sources(self, future: Future, generation: int, on_done=None) -> None:
        """Write a finished worker answer into the list (Tk is not thread-safe)."""
        if not future.done():
            self.root.after(SOURCE_POLL_MS, self._poll_sources, future, generation, on_done)
            return
        if generation != self.source_generation or future.cancelled():
            return
        for index, label in future.result():
            self.source_pending.discard(index)
            self._set_list_source(index, label, render=False)
        self._render_list_markers()
        if on_done is not None:
            on_done()

    def _set_list_source(self, index: int, label: str, render: bool = True) -> None:
        self.default_sources[index] = label
        # Marker-strip samples need not be rows of a strided list.
        if self.image_list.exists(str(index)):
            tag = self.source_tags.get(label)
            self.image_list.item(str(index), tags=(tag,) if tag else ())
            self.image_list.set(str(index), "source", label)
        if render:
            self._render_list_markers()

    def _refresh_current_source(self) -> None:
        """Recompute the current frame's Source after annotation/ was written."""
        if self.current_index is None or self.current_image_path is None:
            return
        name = f"{self.current_image_path.stem}{ANNOTATION_SUFFIX}"
        default_dir = self.tabs[DEFAULT_TAB][1] / self.current_split
        self._set_list_source(
            self.current_index, default_source(name, default_dir, self._source_candidates())
        )

    def _set_current_manual_flag(self, is_manual: bool) -> None:
        """Record whether the current frame has a manual file, for the list strip."""
        if self.current_image_path is None or self.current_index is None:
            return

        if is_manual:
            self.manual_stems.add(self.current_image_path.stem)
            self.manual_indices.add(self.current_index)
        else:
            self.manual_stems.discard(self.current_image_path.stem)
            self.manual_indices.discard(self.current_index)
        self._render_list_markers()

    def _on_list_scrolled(self, first: str, last: str) -> None:
        """Forward the list's visible range to the scrollbar, the marker strip
        and the Source column."""
        self.list_scrollbar.set(first, last)
        self._render_list_markers()
        self._schedule_source_update()

    def _on_list_marker_resized(self, _event: tk.Event) -> None:
        """Resample the strip for its new height and redraw it."""
        self._scan_marker_samples()
        self._render_list_markers()

    def _fit_list_marker_to_trough(self) -> None:
        """Pad the marker strip so it spans only the scrollbar's scroll area.

        The arrow buttons are measured with `identify()` instead of assuming a
        size, since it differs between ttk themes (and a theme may have none).
        """
        scrollbar = self.list_scrollbar
        height = scrollbar.winfo_height()
        x = scrollbar.winfo_width() // 2
        if height < 2:
            return

        top = 0
        for y in range(height // 2):
            if "uparrow" in scrollbar.identify(x, y):
                top = y + 1
            elif top:
                break
        bottom = height
        for y in range(height - 1, height // 2, -1):
            if "downarrow" in scrollbar.identify(x, y):
                bottom = y
            elif bottom != height:
                break
        self.list_marker.pack_configure(pady=(top, height - bottom))

    def _render_list_markers(self) -> None:
        """Redraw the strip beside the list scrollbar.

        Each pixel row takes the Source colour of the frame sampled for it
        (see _marker_samples()), so the cost follows the strip height rather
        than the split size. Rows whose sample has no known Source stay blank.
        """
        self.list_marker.delete("all")
        total = len(self.image_paths)
        if total == 0:
            return
        width = max(self.list_marker.winfo_width(), 1)
        height = max(self.list_marker.winfo_height(), 1)

        def row_of(index: int) -> int:
            return min(int(index * height / total), height - 2)

        # 1. Sampled frames by Source colour, runs of one colour merged into
        # one band.
        bands: list[tuple[int, int, str]] = []
        for band_top, band_bottom, index in self._marker_samples():
            mark = self.source_marker_colors.get(self.default_sources.get(index))
            if mark is None:
                continue
            color = mark[1]
            if bands and bands[-1][1] == band_top and bands[-1][2] == color:
                bands[-1] = (bands[-1][0], band_bottom, color)
            else:
                bands.append((band_top, band_bottom, color))
        for band_top, band_bottom, color in bands:
            self.list_marker.create_rectangle(0, band_top, width, band_bottom, fill=color, width=0)

        # 2. The rows currently shown in the list, as a translucent box. It
        # uses the same scale as the marks, so a mark inside the box is a row
        # on screen, which the scrollbar thumb cannot show exactly.
        first, last = (float(value) for value in self.image_list.yview())
        top = first * height
        bottom = last * height
        if bottom - top < LIST_MARKER_VISIBLE_MIN_HEIGHT:
            center = (top + bottom) / 2
            top = center - LIST_MARKER_VISIBLE_MIN_HEIGHT / 2
            bottom = center + LIST_MARKER_VISIBLE_MIN_HEIGHT / 2
        top = min(max(top, 0), height - LIST_MARKER_VISIBLE_MIN_HEIGHT)
        bottom = max(min(bottom, height), top + LIST_MARKER_VISIBLE_MIN_HEIGHT)
        # Canvas items have no alpha, so the box is painted with what lies
        # beneath it (background and Source marks) pre-blended with the shade.
        self.list_marker.create_rectangle(
            0, top, width, bottom,
            fill=self._shade_visible_range(LIST_MARKER_BACKGROUND), width=0,
        )
        for band_top, band_bottom, color in bands:
            if band_bottom > top and band_top < bottom:
                self.list_marker.create_rectangle(
                    0, max(band_top, top), width, min(band_bottom, bottom),
                    fill=self._shade_visible_range(color), width=0,
                )

        # 3. The current frame, on top of everything.
        if self.current_index is not None:
            y = row_of(self.current_index)
            self.list_marker.create_rectangle(
                0, y - 1, width, y + 1, fill=LIST_MARKER_CURRENT_COLOR, width=0
            )

    def _marker_samples(self) -> list[tuple[int, int, int]]:
        """(top, bottom, list index) of the frame shown on each strip band.

        A split longer than the strip gets one evenly spaced frame per pixel
        row; a shorter one shows every frame on its proportional band.
        """
        total = len(self.image_paths)
        height = max(self.list_marker.winfo_height(), 1)
        if total == 0:
            return []
        if total > height:
            return [(y, y + 1, y * total // height) for y in range(height)]
        return [(index * height // total, (index + 1) * height // total, index) for index in range(total)]

    def _shade_visible_range(self, color: str) -> str:
        """Return `color` as seen through the translucent visible-range box."""
        base = self.list_marker.winfo_rgb(color)
        shade = self.list_marker.winfo_rgb(LIST_MARKER_VISIBLE_COLOR)
        channels = (
            round((b * (1 - LIST_MARKER_VISIBLE_ALPHA) + s * LIST_MARKER_VISIBLE_ALPHA) / 257)
            for b, s in zip(base, shade)
        )
        return "#{:02x}{:02x}{:02x}".format(*channels)

    def _render_scene(self) -> None:
        self.canvas.delete("all")
        if self.current_image_rgb is None:
            self.hovered_handle = None
            self.canvas.create_text(
                self.canvas.winfo_width() / 2,
                self.canvas.winfo_height() / 2,
                text="No image loaded",
                fill="#c7d0d9",
                font=("TkDefaultFont", 16),
            )
            return

        composed = self.current_image_rgb
        canvas_width = max(self.canvas.winfo_width(), 1)
        canvas_height = max(self.canvas.winfo_height(), 1)
        scale = min(canvas_width / self.image_width, canvas_height / self.image_height)
        scale = max(scale, 0.01)

        display_width = max(1, int(round(self.image_width * scale)))
        display_height = max(1, int(round(self.image_height * scale)))
        offset_x = (canvas_width - display_width) / 2.0
        offset_y = (canvas_height - display_height) / 2.0

        self.canvas_scale = scale
        self.canvas_offset_x = offset_x
        self.canvas_offset_y = offset_y
        self.canvas_image_width = display_width
        self.canvas_image_height = display_height

        resized = cv2.resize(composed, (display_width, display_height), interpolation=cv2.INTER_AREA)
        if self.mode == "add":
            resized = self._dim_for_add_mode(resized)
        self.photo_image = self._rgb_to_photoimage(resized)
        self.canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self.photo_image)

        self.hovered_handle = self._handle_under_pointer()
        if self.show_annotation_var.get():
            for index, annotation in enumerate(self.current_annotations):
                self._draw_annotation_box(index, annotation)

            for index, annotation in enumerate(self.current_annotations):
                self._draw_annotation_tip(index, annotation)

        if self.preview_box is not None:
            x1, y1, x2, y2 = self.preview_box
            cx1, cy1 = self._image_to_canvas(x1, y1)
            cx2, cy2 = self._image_to_canvas(x2, y2)
            self.canvas.create_rectangle(
                cx1,
                cy1,
                cx2,
                cy2,
                outline="#f8e45c",
                width=2,
                dash=(6, 3),
            )

    def _dim_for_add_mode(self, display_rgb: np.ndarray) -> np.ndarray:
        """Darken the displayed image, keeping the box being drawn at full brightness.

        Applied to the display-sized image after compositing, so screenshots
        never pick it up.
        """
        dimmed = cv2.convertScaleAbs(display_rgb, alpha=ADD_MODE_BRIGHTNESS)
        if self.preview_box is not None:
            x1, y1, x2, y2 = self.preview_box
            left = int(min(x1, x2) * self.canvas_scale)
            top = int(min(y1, y2) * self.canvas_scale)
            right = int(math.ceil(max(x1, x2) * self.canvas_scale))
            bottom = int(math.ceil(max(y1, y2) * self.canvas_scale))
            dimmed[top:bottom, left:right] = display_rgb[top:bottom, left:right]
        return dimmed

    def _draw_annotation_box(self, index: int, annotation: dict[str, dict[str, int]]) -> None:
        bbox = annotation["bbox"]
        x1 = bbox["x"]
        y1 = bbox["y"]
        x2 = bbox["x"] + bbox["width"]
        y2 = bbox["y"] + bbox["height"]
        cx1, cy1 = self._image_to_canvas(x1, y1)
        cx2, cy2 = self._image_to_canvas(x2, y2)

        is_selected = index == self.selected_annotation_index
        outline = "#ffd34d" if is_selected else "#3bd7ff"
        width = 3 if is_selected else 2

        self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=outline, width=width)
        self.canvas.create_text(
            cx1 + 6,
            cy1 + 6,
            text=str(index + 1),
            fill=outline,
            anchor=tk.NW,
            font=self.annotation_label_font,
        )

        if is_selected:
            mid_x = (cx1 + cx2) / 2
            mid_y = (cy1 + cy2) / 2
            handle_points = {
                "nw": (cx1, cy1), "ne": (cx2, cy1), "sw": (cx1, cy2), "se": (cx2, cy2),
                "n": (mid_x, cy1), "s": (mid_x, cy2), "w": (cx1, mid_y), "e": (cx2, mid_y),
            }
            for handle_name, (handle_x, handle_y) in handle_points.items():
                hovered = self.hovered_handle == ("resize", index, handle_name)
                self.canvas.create_rectangle(
                    handle_x - HANDLE_SIZE,
                    handle_y - HANDLE_SIZE,
                    handle_x + HANDLE_SIZE,
                    handle_y + HANDLE_SIZE,
                    outline="#111111",
                    fill=HANDLE_HOVER_FILL if hovered else "#ffd34d",
                    width=1,
                )

    def _draw_annotation_tip(self, index: int, annotation: dict[str, dict[str, int]]) -> None:
        bbox = annotation["bbox"]
        x1 = bbox["x"]
        y1 = bbox["y"]
        x2 = bbox["x"] + bbox["width"]
        y2 = bbox["y"] + bbox["height"]
        cx1, cy1 = self._image_to_canvas(x1, y1)
        cx2, cy2 = self._image_to_canvas(x2, y2)

        for key in TIP_KEYS:
            if key not in annotation:
                continue
            tip_x, tip_y = self._image_to_canvas(annotation[key]["x"], annotation[key]["y"])
            self.canvas.create_line(
                (cx1 + cx2) / 2.0,
                (cy1 + cy2) / 2.0,
                tip_x,
                tip_y,
                fill="#ff8080",
                width=2,
                dash=(3, 2),
            )
            self.canvas.create_oval(
                tip_x - TIP_RADIUS,
                tip_y - TIP_RADIUS,
                tip_x + TIP_RADIUS,
                tip_y + TIP_RADIUS,
                outline="#7a0000",
                fill=HANDLE_HOVER_FILL if self.hovered_handle == ("tip", index, key) else "#ff4d4d",
                width=2,
            )

    def _rgb_to_photoimage(self, rgb: np.ndarray) -> tk.PhotoImage:
        height, width = rgb.shape[:2]
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        return tk.PhotoImage(data=header + rgb.tobytes(), format="PPM")

    def _image_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.canvas_offset_x + x * self.canvas_scale,
            self.canvas_offset_y + y * self.canvas_scale,
        )

    def _canvas_to_image(self, x: float, y: float) -> tuple[float, float]:
        return (
            (x - self.canvas_offset_x) / self.canvas_scale,
            (y - self.canvas_offset_y) / self.canvas_scale,
        )

    def _point_inside_image(self, x: float, y: float) -> bool:
        return 0 <= x <= self.image_width and 0 <= y <= self.image_height

    def _enter_add_mode(self) -> None:
        if self.current_image_path is None:
            return
        self.mode = "add"
        self.preview_box = None
        self.drag_state = None
        self._update_buttons()
        self._update_status("Add mode: drag on the image to create a new bbox.")
        self._render_scene()

    def _on_canvas_context_menu(self, event: tk.Event[tk.Misc]) -> str:
        """Pop up the tool actions for the right-clicked or selected tool.

        A right click on a tool selects it first, like a left click. With a tool
        selected the menu offers Add or Remove Second Tip, whichever applies,
        then Delete Tool; with none it offers Add Tool. Cancel, Esc or a click
        outside closes it.
        """
        if self.current_image_rgb is None or self.mode == "add":
            return "break"

        image_x, image_y = self._canvas_to_image(event.x, event.y)
        if self.show_annotation_var.get():
            hit = self._hit_test(image_x, image_y)
            if hit is not None and hit["index"] != self.selected_annotation_index:
                self.selected_annotation_index = hit["index"]
                self._update_buttons()
                self._render_scene()
        else:
            # Hidden tools cannot be targeted, matching the left click.
            self.selected_annotation_index = None
            self._update_buttons()
            self._render_scene()

        # Only the actions that apply are listed: the second-tip action, then
        # the tool action, then Cancel.
        menu = tk.Menu(self.root, tearoff=False)
        if self.selected_annotation_index is None:
            menu.add_command(label="Add Tool", command=self._enter_add_mode)
        else:
            if "tip2" in self.current_annotations[self.selected_annotation_index]:
                menu.add_command(label="Remove Second Tip", command=self._remove_second_tip)
            else:
                menu.add_command(
                    label="Add Second Tip", command=lambda: self._add_second_tip(image_x, image_y)
                )
            delete_color = BUTTON_STYLES["Delete.TButton"]
            menu.add_command(
                label="Delete Tool",
                command=self._delete_selected,
                foreground=delete_color,
                activeforeground=delete_color,
            )
        # Choosing Cancel just closes the menu.
        menu.add_separator()
        menu.add_command(label="Cancel")
        # tk_popup returns at once on X11 and the menu keeps its grab until it
        # closes, so a click anywhere outside the menu closes it. Releasing the
        # grab here would leave the menu open until an entry is chosen.
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _add_second_tip(self, image_x: float, image_y: float) -> None:
        """Give the selected tool a second tip at the right-clicked point.

        The point is pulled onto the nearest pixel inside the box, so a menu
        opened from outside the box still lands the tip on the tool.
        """
        if self.selected_annotation_index is None:
            return
        annotation = self.current_annotations[self.selected_annotation_index]
        if "tip2" in annotation:
            return
        bbox = annotation["bbox"]
        annotation["tip2"] = {
            "x": self._clamp_int(int(round(image_x)), bbox["x"], bbox["x"] + bbox["width"] - 1),
            "y": self._clamp_int(int(round(image_y)), bbox["y"], bbox["y"] + bbox["height"] - 1),
        }
        self._mark_dirty()

    def _remove_second_tip(self) -> None:
        if self.selected_annotation_index is None:
            return
        annotation = self.current_annotations[self.selected_annotation_index]
        if annotation.pop("tip2", None) is not None:
            self._mark_dirty()

    def _delete_selected(self) -> None:
        if self.selected_annotation_index is None:
            return
        del self.current_annotations[self.selected_annotation_index]
        if self.current_annotations:
            self.selected_annotation_index = min(self.selected_annotation_index, len(self.current_annotations) - 1)
        else:
            self.selected_annotation_index = None
        self._mark_dirty()
        self._render_scene()

    def _reload_current_annotation(self) -> None:
        """Discard edits and show the frame's final labels from annotation/ again."""
        if self.current_image_path is None:
            return
        self.current_tab = DEFAULT_TAB
        self.preferred_tab = DEFAULT_TAB
        self._load_current_tab()
        self._update_status("Reloaded annotation from annotation/.")

    def _navigate_images(self, step: int) -> None:
        if self.current_index is None or not self.image_paths:
            return

        new_index = self.current_index + step * self.list_stride
        if new_index < 0 or new_index >= len(self.image_paths):
            return
        if not self._confirm_leave_current_image():
            self._restore_list_selection()
            return

        self._select_list_row(new_index)
        self._open_image_at_index(new_index)

    def _on_canvas_press(self, event: tk.Event[tk.Misc]) -> None:
        if self.current_image_rgb is None:
            return

        image_x, image_y = self._canvas_to_image(event.x, event.y)
        if self.mode == "add":
            if not self._point_inside_image(image_x, image_y):
                return
            self.drag_state = {
                "kind": "add",
                "start": (self._clamp_x(image_x), self._clamp_y(image_y)),
            }
            self.preview_box = (image_x, image_y, image_x, image_y)
            self._render_scene()
            return

        if not self.show_annotation_var.get():
            self.selected_annotation_index = None
            self.drag_state = None
            self._update_buttons()
            self._render_scene()
            return

        hit = self._hit_test(image_x, image_y)
        if hit is None:
            self.selected_annotation_index = None
            self.drag_state = None
            self._update_buttons()
            self._render_scene()
            return

        self.selected_annotation_index = hit["index"]
        annotation = self.current_annotations[self.selected_annotation_index]
        self.drag_state = {
            "kind": hit["kind"],
            "index": hit["index"],
            "start_point": (image_x, image_y),
            "start_bbox": annotation["bbox"].copy(),
            # For a tip drag "handle" names the tip being dragged.
            "start_tips": {key: annotation[key].copy() for key in TIP_KEYS if key in annotation},
            "handle": hit.get("handle"),
        }
        self._update_buttons()
        self._render_scene()

    def _on_canvas_motion(self, event: tk.Event[tk.Misc]) -> None:
        """Show a crosshair and highlight the tip or resize handle under the pointer.

        The crosshair marks the exact hit point, which an arrow does not over
        remote displays such as TurboVNC, where the arrow tip can sit a few
        pixels off the real pointer position.
        """
        self.pointer_position = (event.x, event.y)
        handle = self._handle_under_pointer()
        cursor = HANDLE_CURSOR if handle is not None else ""
        if self.canvas.cget("cursor") != cursor:
            self.canvas.configure(cursor=cursor)
        if handle != self.hovered_handle:
            self._render_scene()

    def _on_canvas_leave(self, _event: tk.Event[tk.Misc]) -> None:
        self.pointer_position = None
        if self.hovered_handle is not None:
            self._render_scene()

    def _handle_under_pointer(self) -> tuple[str, int, str | None] | None:
        """Return the (kind, index, handle) of the tip or resize handle to highlight.

        Recomputed on every render rather than cached from the last motion, so
        switching images or deleting a tool never leaves a stale highlight. A
        handle being dragged stays highlighted even when the pointer is
        clamped away from it.
        """
        if self.drag_state is not None and self.drag_state["kind"] in ("tip", "resize"):
            return (
                str(self.drag_state["kind"]),
                int(self.drag_state["index"]),
                self.drag_state["handle"],
            )
        if (
            self.pointer_position is None
            or self.current_image_rgb is None
            or self.mode != "select"
            or not self.show_annotation_var.get()
        ):
            return None
        hit = self._hit_test(*self._canvas_to_image(*self.pointer_position))
        if hit is None or hit["kind"] not in ("tip", "resize"):
            return None
        return (hit["kind"], hit["index"], hit.get("handle"))

    def _on_canvas_drag(self, event: tk.Event[tk.Misc]) -> None:
        if self.current_image_rgb is None or self.drag_state is None:
            return

        image_x, image_y = self._canvas_to_image(event.x, event.y)
        image_x = self._clamp_x(image_x)
        image_y = self._clamp_y(image_y)
        kind = self.drag_state["kind"]

        if kind == "add":
            start_x, start_y = self.drag_state["start"]
            self.preview_box = (start_x, start_y, image_x, image_y)
            self._render_scene()
            return

        annotation = self.current_annotations[int(self.drag_state["index"])]
        if kind == "tip":
            tip = {
                "x": int(round(image_x)),
                "y": int(round(image_y)),
            }
            annotation[self.drag_state["handle"]] = tip
            # Grow the box from its drag-start extent so it always contains the
            # tip pixel; dragging the tip back inside restores the original box.
            start_bbox = self.drag_state["start_bbox"]
            annotation["bbox"] = self._normalize_box_from_points(
                min(start_bbox["x"], tip["x"]),
                min(start_bbox["y"], tip["y"]),
                max(start_bbox["x"] + start_bbox["width"], tip["x"] + 1),
                max(start_bbox["y"] + start_bbox["height"], tip["y"] + 1),
            )
            self._mark_dirty(render=False)
            self._render_scene()
            return

        if kind == "move":
            start_x, start_y = self.drag_state["start_point"]
            start_bbox = self.drag_state["start_bbox"]
            delta_x = int(round(image_x - start_x))
            delta_y = int(round(image_y - start_y))

            new_x = self._clamp_int(start_bbox["x"] + delta_x, 0, self.image_width - start_bbox["width"])
            new_y = self._clamp_int(start_bbox["y"] + delta_y, 0, self.image_height - start_bbox["height"])
            applied_delta_x = new_x - start_bbox["x"]
            applied_delta_y = new_y - start_bbox["y"]

            annotation["bbox"] = {
                "x": new_x,
                "y": new_y,
                "width": start_bbox["width"],
                "height": start_bbox["height"],
            }
            for key, start_tip in self.drag_state["start_tips"].items():
                annotation[key] = self._normalize_tip(
                    {
                        "x": start_tip["x"] + applied_delta_x,
                        "y": start_tip["y"] + applied_delta_y,
                    }
                )
            self._mark_dirty(render=False)
            self._render_scene()
            return

        if kind == "resize":
            start_bbox = self.drag_state["start_bbox"]
            x1 = start_bbox["x"]
            y1 = start_bbox["y"]
            x2 = start_bbox["x"] + start_bbox["width"]
            y2 = start_bbox["y"] + start_bbox["height"]
            handle = self.drag_state["handle"]

            # Corner handles move both coordinates; edge handles ("n", "s",
            # "w", "e") move only their own side.
            if "n" in handle:
                y1 = image_y
            if "s" in handle:
                y2 = image_y
            if "w" in handle:
                x1 = image_x
            if "e" in handle:
                x2 = image_x

            normalized = self._normalize_box_from_points(x1, y1, x2, y2)
            annotation["bbox"] = normalized
            # Pull each tip from its drag-start position onto the nearest pixel
            # inside the box, so shrinking never leaves it outside; growing
            # the box back restores the original tip.
            for key, start_tip in self.drag_state["start_tips"].items():
                annotation[key] = {
                    "x": self._clamp_int(
                        start_tip["x"], normalized["x"], normalized["x"] + normalized["width"] - 1
                    ),
                    "y": self._clamp_int(
                        start_tip["y"], normalized["y"], normalized["y"] + normalized["height"] - 1
                    ),
                }
            self._mark_dirty(render=False)
            self._render_scene()

    def _on_canvas_release(self, event: tk.Event[tk.Misc]) -> None:
        if self.drag_state is None:
            return

        kind = self.drag_state["kind"]
        if kind == "add":
            image_x, image_y = self._canvas_to_image(event.x, event.y)
            image_x = self._clamp_x(image_x)
            image_y = self._clamp_y(image_y)
            start_x, start_y = self.drag_state["start"]
            bbox = self._normalize_box_from_points(start_x, start_y, image_x, image_y)
            self.preview_box = None
            if bbox["width"] >= MIN_BOX_SIZE and bbox["height"] >= MIN_BOX_SIZE:
                tip_x = bbox["x"] + bbox["width"] // 2
                tip_y = bbox["y"] + bbox["height"] // 2
                self.current_annotations.append(
                    {
                        "bbox": bbox,
                        "tip": self._normalize_tip({"x": tip_x, "y": tip_y}),
                    }
                )
                self.selected_annotation_index = len(self.current_annotations) - 1
                self._mark_dirty(render=False)
            self.mode = "select"
            self._update_buttons()
            self._update_status()
            self._render_scene()

        self.drag_state = None

    def _hit_test(self, image_x: float, image_y: float) -> dict[str, object] | None:
        """Resolve a click to a tip handle, a resize handle, or a bbox.

        Handles are tested before box interiors, and the smallest box wins among
        the ones under the cursor, so a tool nested inside a larger one stays
        reachable instead of being swallowed by it.
        """
        threshold = max(8.0 / self.canvas_scale, 3.0)
        # Resize handles are drawn 1.5x larger than the original 8px reach.
        handle_threshold = max(12.0 / self.canvas_scale, 3.0)
        tip_threshold_sq = (threshold * 1.5) ** 2

        # Tips first: a tip may sit inside any number of boxes and must not be
        # shadowed by them. Nearest tip wins, the selected one breaking ties.
        tip_hit: tuple[tuple[float, bool], int, str] | None = None
        for index, annotation in enumerate(self.current_annotations):
            for tip_key in TIP_KEYS:
                if tip_key not in annotation:
                    continue
                tip = annotation[tip_key]
                distance_sq = (tip["x"] - image_x) ** 2 + (tip["y"] - image_y) ** 2
                if distance_sq > tip_threshold_sq:
                    continue
                key = (distance_sq, index != self.selected_annotation_index)
                if tip_hit is None or key < tip_hit[0]:
                    tip_hit = (key, index, tip_key)
        if tip_hit is not None:
            return {"index": tip_hit[1], "kind": "tip", "handle": tip_hit[2]}

        # Resize handles exist only on the selected box.
        if self.selected_annotation_index is not None:
            bbox = self.current_annotations[self.selected_annotation_index]["bbox"]
            x1 = bbox["x"]
            y1 = bbox["y"]
            x2 = bbox["x"] + bbox["width"]
            y2 = bbox["y"] + bbox["height"]
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            # Corners come first so they win where a small box crowds the
            # edge handles against them.
            handles = {
                "nw": (x1, y1),
                "ne": (x2, y1),
                "sw": (x1, y2),
                "se": (x2, y2),
                "n": (mid_x, y1),
                "s": (mid_x, y2),
                "w": (x1, mid_y),
                "e": (x2, mid_y),
            }
            for handle_name, (handle_x, handle_y) in handles.items():
                if abs(handle_x - image_x) <= handle_threshold and abs(handle_y - image_y) <= handle_threshold:
                    return {
                        "index": self.selected_annotation_index,
                        "kind": "resize",
                        "handle": handle_name,
                    }

        # Interiors last, smallest area first. Equal areas keep the current
        # selection so repeated clicks on the same spot do not toggle.
        box_hit: tuple[tuple[int, bool], int] | None = None
        for index, annotation in enumerate(self.current_annotations):
            bbox = annotation["bbox"]
            x1 = bbox["x"]
            y1 = bbox["y"]
            x2 = bbox["x"] + bbox["width"]
            y2 = bbox["y"] + bbox["height"]
            if not (x1 <= image_x <= x2 and y1 <= image_y <= y2):
                continue
            key = (
                bbox["width"] * bbox["height"],
                index != self.selected_annotation_index,
            )
            if box_hit is None or key < box_hit[0]:
                box_hit = (key, index)
        if box_hit is not None:
            return {"index": box_hit[1], "kind": "move"}

        return None

    def _mark_dirty(self, render: bool = True) -> None:
        self.dirty = True
        self._update_buttons()
        self._update_status()
        if render:
            self._render_scene()

    def _update_buttons(self) -> None:
        # An unedited automatic result can still be saved: that adopts it.
        adoptable = (
            self.current_image_path is not None
            and bool(self.tabs)
            and self.tabs[self.current_tab][2] == "auto"
        )
        self.save_button.configure(state=tk.NORMAL if self.dirty or adoptable else tk.DISABLED)
        self.delete_button.configure(state=tk.NORMAL if self.selected_annotation_index is not None else tk.DISABLED)
        adding = self.mode == "add"
        self.add_button.configure(
            text=ADD_BUTTON_ACTIVE_LABEL if adding else ADD_BUTTON_LABEL,
            style=ADD_ACTIVE_STYLE if adding else "Add.TButton",
        )
        self.screenshot_button.configure(
            state=tk.NORMAL if self.current_image_path is not None else tk.DISABLED
        )

    def _update_images_label(self) -> None:
        total_count = len(self.image_paths)
        current_position = self.current_index + 1 if self.current_index is not None and total_count else 0
        self.images_label_var.set(f"Images ({current_position:,} / {total_count:,})")

    def _update_status(self, message: str | None = None) -> None:
        self.tool_count_var.set(str(len(self.current_annotations)))
        if message is not None:
            self.status_var.set(message)
            return

        mode_text = "add" if self.mode == "add" else "select"
        self.status_var.set(f"mode={mode_text}")

    def _confirm_leave_current_image(self, always_ask: bool = False) -> bool:
        if not self.dirty:
            return True

        # Auto save turns the prompt into a save, which is the whole point of
        # the option: moving between frames must not stop to ask. Switching
        # tabs passes always_ask, since it may be a deliberate look elsewhere.
        if self.auto_save_var.get() and not always_ask:
            self._save_current_annotation()
            return not self.dirty

        response = messagebox.askyesnocancel(
            "Unsaved changes",
            "Save changes before switching images or tabs, or closing the editor?",
            default=messagebox.YES,
        )
        if response is None:
            return False
        if response:
            self._save_current_annotation()
            return not self.dirty
        return True

    def _restore_list_selection(self) -> None:
        if self.current_index is None:
            return
        self._select_list_row(self.current_index)

    def _list_images(self, image_dir: Path) -> list[Path]:
        if not image_dir.exists():
            return []
        return sorted(
            path
            for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )

    def _normalize_bbox(self, bbox: dict[str, int]) -> dict[str, int]:
        x = self._clamp_int(int(bbox["x"]), 0, max(self.image_width - 1, 0))
        y = self._clamp_int(int(bbox["y"]), 0, max(self.image_height - 1, 0))
        width = max(int(bbox["width"]), 1)
        height = max(int(bbox["height"]), 1)
        width = min(width, max(self.image_width - x, 1))
        height = min(height, max(self.image_height - y, 1))
        return {"x": x, "y": y, "width": width, "height": height}

    def _normalize_box_from_points(self, x1: float, y1: float, x2: float, y2: float) -> dict[str, int]:
        left = self._clamp_int(int(round(min(x1, x2))), 0, max(self.image_width - 1, 0))
        top = self._clamp_int(int(round(min(y1, y2))), 0, max(self.image_height - 1, 0))
        right = self._clamp_int(int(round(max(x1, x2))), 0, max(self.image_width, 1))
        bottom = self._clamp_int(int(round(max(y1, y2))), 0, max(self.image_height, 1))
        width = max(right - left, 1)
        height = max(bottom - top, 1)
        return self._normalize_bbox({"x": left, "y": top, "width": width, "height": height})

    def _normalize_tip(self, tip: dict[str, int]) -> dict[str, int]:
        return {
            "x": self._clamp_int(int(tip["x"]), 0, max(self.image_width - 1, 0)),
            "y": self._clamp_int(int(tip["y"]), 0, max(self.image_height - 1, 0)),
        }

    def _clamp_int(self, value: int, low: int, high: int) -> int:
        if high < low:
            return low
        return max(low, min(value, high))

    def _clamp_x(self, value: float) -> float:
        return max(0.0, min(float(value), max(float(self.image_width - 1), 0.0)))

    def _clamp_y(self, value: float) -> float:
        return max(0.0, min(float(value), max(float(self.image_height - 1), 0.0)))

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "GUI editor for bbox/tip annotations. Shows annotation/, "
            "annotation-manual/ and every automatic annotation-* source side by "
            "side in tabs, and writes only annotation/ and annotation-manual/."
        )
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help=(
            "Dataset name, e.g. 'erop' or 'cholec80'. Used to resolve default "
            "--images/--annotation/--manual when not given "
            "explicitly. Defaults to the first dataset found under "
            "data/dataset-src or data/dataset; the Dataset selector in the "
            "toolbar switches at runtime."
        ),
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=None,
        help="Root directory containing train/val/test source images. Defaults to data/dataset/<dataset>/images.",
    )
    parser.add_argument(
        "--annotation",
        type=Path,
        default=None,
        help=(
            "Root directory of the final train/val/test annotation JSON files. "
            "Its annotation-* siblings are shown as automatic sources. Defaults "
            "to data/dataset/<dataset>/annotation."
        ),
    )
    parser.add_argument(
        "--manual",
        type=Path,
        default=None,
        help=(
            "Root directory where hand-corrected annotation JSON files are "
            "kept. Defaults to data/dataset/<dataset>/annotation-manual."
        ),
    )
    parser.add_argument(
        "--auto-save",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Save pending changes when moving to another image instead of "
            "asking. On by default; pass --no-auto-save to be asked every time. "
            "Can be toggled in the toolbar either way."
        ),
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if CV2_IMPORT_ERROR is not None:
        raise RuntimeError(
            "opencv-python is required to display images and overlays. "
            "Install it and run the script again."
        ) from CV2_IMPORT_ERROR
    if NUMPY_IMPORT_ERROR is not None:
        raise RuntimeError(
            "numpy is required to compose overlays and edit annotations. "
            "Install it and run the script again."
        ) from NUMPY_IMPORT_ERROR

    if not args.images.exists():
        raise FileNotFoundError(f"images directory does not exist: {args.images}")
    if not args.images.is_dir():
        raise NotADirectoryError(f"images path is not a directory: {args.images}")

    args.annotation.mkdir(parents=True, exist_ok=True)

    for split_name in SPLIT_NAMES:
        images_split = args.images / split_name
        if not images_split.exists():
            raise FileNotFoundError(f"Image split directory does not exist: {images_split}")


def main() -> int:
    args = parse_args()

    # Switching datasets in the GUI recomputes every root from the dataset name,
    # which would silently drop explicitly given paths. Pin the selector in that
    # case instead.
    args.dataset_locked = any(
        path is not None
        for path in (args.images, args.annotation, args.manual)
    )

    if args.dataset is None and not args.dataset_locked:
        datasets = list_datasets()
        if not datasets:
            raise SystemExit(
                "No datasets found under data/dataset-src or data/dataset. "
                "Pass --dataset or the explicit path options."
            )
        args.dataset = datasets[0]

    args.images = resolve_path(args.images, args.dataset, images_dir, "--images")
    args.annotation = resolve_path(args.annotation, args.dataset, annotation_dir, "--annotation")
    args.manual = resolve_path(args.manual, args.dataset, annotation_manual_dir, "--manual")
    validate_args(args)
    editor = AnnotationEditor(args)
    editor.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
