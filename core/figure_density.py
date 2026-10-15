"""Measuring how much of a figure is flat face.

**Read this before using it as a gate. It does not measure what it was built
to measure. It was wrong three separate ways in half an hour, each of which
would have shipped looking reasonable — docs/findings/2026-10-15-density-probe.md.**

The intent was to automate the one judgement in anatomy's acceptance bar — "a
bare face or an empty corner is unfinished work, not calm" — on the theory that
"is this region empty" is a question about ink, and ink is countable.

It is countable. It is also the wrong question. Run against anatomy's own
reference figures, the densest and most finished of them (arcade-cabinet, about
240 solids) scores WORST, and marking its flagged cells shows every one of them
sitting on the cabinet's interior wall and side panel: correctly drawn flat
faces that are supposed to be empty, because they are the backdrop the
mechanism stands against.

And once the fill stopped leaking through hairline outlines, a third answer:
the card's own frame seals it, so "enclosed by the drawing" means "inside the
card", and what this reports is the share of the frame carrying no ink. That
ordering is at least sensible — dense figures leave less of the card empty —
but it is not a measure of whether anything is unfinished.

Kept as a descriptive statistic, and because the negative result is worth
keeping.

For a gate, use the checks that measure real things: `kit/audit.mjs` ray-casts
the geometry and `scripts/lines.mjs` counts floating line ends. Both are facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class Cell:
    row: int
    col: int
    box: Tuple[int, int, int, int]      # x, y, w, h in page pixels
    density: float                      # share of the cell that is marked
    inside: bool                        # does the figure reach this cell
    bare: bool

    def crop(self) -> str:
        """Where to look, in the form a close-up would take."""
        x, y, w, h = self.box
        return f"{w}x{h}+{x}+{y}"


@dataclass
class Survey:
    cells: List[Cell] = field(default_factory=list)
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)
    page: float = 0.0
    coverage: float = 0.0               # share of the whole image that is inked

    @property
    def inside(self) -> List[Cell]:
        return [c for c in self.cells if c.inside]

    @property
    def bare(self) -> List[Cell]:
        return [c for c in self.cells if c.bare]

    def summary(self) -> str:
        if not self.inside:
            return "nothing drawn"
        head = (f"flat faces: {len(self.bare)} of {len(self.inside)} enclosed "
                f"cells carry almost no ink")
        if not self.bare:
            return head
        worst = sorted(self.bare, key=lambda c: c.density)[:4]
        return head + "\n" + "\n".join(
            f"  ({c.row},{c.col}) {c.density:.2%} ink  crop {c.crop()}"
            for c in worst)


def read(path: str) -> np.ndarray:
    """A page as greyscale in 0..1. Alpha is composited onto the page colour."""
    from PIL import Image
    image = Image.open(path)
    if image.mode in ("RGBA", "LA"):
        flat = Image.new("RGB", image.size, (0, 0, 0))
        flat.paste(image, mask=image.split()[-1])
        image = flat
    return np.asarray(image.convert("L"), dtype=np.float32) / 255.0


def page_colour(grey: np.ndarray) -> float:
    """The page itself, taken from its border rather than assumed.

    Light theme and dark theme are the same measurement with the sign flipped,
    so nothing here needs to know which one it is looking at.
    """
    border = np.concatenate([grey[0], grey[-1], grey[:, 0], grey[:, -1]])
    return float(np.median(border))


def ink(grey: np.ndarray, page: Optional[float] = None,
        floor: float = 0.04) -> np.ndarray:
    """Marked pixels: far enough from the page colour to be deliberate."""
    base = page_colour(grey) if page is None else page
    return (np.abs(grey - base) > floor)


def silhouette(marked: np.ndarray, grow: int = 2, step: int = 4) -> np.ndarray:
    """The object's filled outline: ink, plus everything the ink encloses.

    "Inside the figure" cannot mean "near the ink". Measured that way, every
    one of anatomy's own reference figures reports the same half-dozen bare
    cells as a half-finished one, because the dark card around a machine is
    adjacent to it on two sides. The question is whether a region is *enclosed*
    by the drawing, which is a flood fill from the outside: whatever the fill
    cannot reach is interior, and an empty interior cell is a bare face.

    Run at `step` resolution because cell-level accuracy is all that is needed,
    and dilated by `grow` first so a dotted or hairline outline still seals.

    The downsample MAX-POOLS rather than strides. Striding drops a one-pixel
    outline unless it happens to land on a multiple of `step`, which in a
    drawing made almost entirely of hairlines means the fill leaks out through
    the gaps and nothing reads as enclosed.
    """
    from collections import deque

    height_in, width_in = marked.shape
    rows, cols = height_in // step, width_in // step
    if rows < 1 or cols < 1:
        return marked.copy()
    small = (marked[:rows * step, :cols * step]
             .reshape(rows, step, cols, step).any(axis=(1, 3)))
    grown = small.copy()
    for _ in range(grow):
        out = grown.copy()
        out[1:, :] |= grown[:-1, :]
        out[:-1, :] |= grown[1:, :]
        out[:, 1:] |= grown[:, :-1]
        out[:, :-1] |= grown[:, 1:]
        grown = out

    height, width = grown.shape
    outside = np.zeros_like(grown)
    queue: deque = deque()
    edges = [(y, x) for x in range(width) for y in (0, height - 1)]
    edges += [(y, x) for y in range(height) for x in (0, width - 1)]
    for y, x in edges:
        if not grown[y, x] and not outside[y, x]:
            outside[y, x] = True
            queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width \
                    and not grown[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                queue.append((ny, nx))
    return small | (~grown & ~outside)


def survey(path: str, cells: int = 8, floor: float = 0.04,
           bare_at: float = 0.01, fills: float = 0.5,
           step: int = 4) -> Survey:
    """Grid the drawing and report the cells it encloses but does not fill.

    `bare_at` is the share of a cell that has to be marked for it to count as
    worked. `fills` is how much of a cell has to fall inside the object's
    silhouette before the cell is judged at all, which is what keeps the quiet
    space around a machine from being reported as unfinished work.
    """
    grey = read(path)
    base = page_colour(grey)
    marked = ink(grey, base, floor)
    found = Survey(page=base, coverage=float(marked.mean()))
    if not marked.any():
        return found

    rows, cols = np.where(marked)
    y0, y1 = int(rows.min()), int(rows.max()) + 1
    x0, x1 = int(cols.min()), int(cols.max()) + 1
    found.bounds = (x0, y0, x1 - x0, y1 - y0)
    body = silhouette(marked, step=step)

    height = max(1, (y1 - y0) // cells)
    width = max(1, (x1 - x0) // cells)
    density = np.zeros((cells, cells), dtype=np.float32)
    enclosed = np.zeros((cells, cells), dtype=np.float32)
    boxes = {}
    for r in range(cells):
        for c in range(cells):
            top = y0 + r * height
            left = x0 + c * width
            bottom = y1 if r == cells - 1 else top + height
            right = x1 if c == cells - 1 else left + width
            patch = marked[top:bottom, left:right]
            density[r, c] = float(patch.mean()) if patch.size else 0.0
            inner = body[top // step:max(top // step + 1, bottom // step),
                         left // step:max(left // step + 1, right // step)]
            enclosed[r, c] = float(inner.mean()) if inner.size else 0.0
            boxes[(r, c)] = (left, top, right - left, bottom - top)

    for r in range(cells):
        for c in range(cells):
            inside = enclosed[r, c] >= fills
            found.cells.append(Cell(
                row=r, col=c, box=boxes[(r, c)], density=float(density[r, c]),
                inside=bool(inside),
                bare=bool(inside and density[r, c] < bare_at)))
    return found


def compare(paths: Sequence[str], **kw) -> List[Tuple[str, Survey]]:
    """Several pages at once — a figure against the reference examples.

    Calibrating a threshold against figures that are known to meet the bar is
    the only honest way to pick one.
    """
    return [(path, survey(path, **kw)) for path in paths]
