"""GPU viewport progress bar for STEP import operations.

Draws a compact branded card in the bottom-left corner of every open 3D
viewport using Blender's GPU/blf APIs.  Zero idle overhead — the draw handler
is registered only while an import is active.

Usage::

    with ViewportProgressBar() as bar:
        bar.start(context, filename="model.step")
        bar.update(0.1, "Reading file")
        bar.update(0.5, "Converting STEP → GLB")
        bar.update(0.9, "Importing to scene")
    # finish() called automatically on __exit__
"""

from __future__ import annotations

import math
import time
import traceback
from typing import Literal, Optional

import bpy

# Module-level state read directly by the draw callback — no file I/O on
# the hot path.  Updated by ViewportProgressBar.update().
_STATE: dict = {"active": False}
_draw_handle: Optional[object] = None


def _draw_callback() -> None:
    """SpaceView3D POST_PIXEL draw callback — renders the progress card."""
    import gpu
    import blf
    from gpu_extras.batch import batch_for_shader

    state = _STATE
    if not state.get("active"):
        return

    try:
        region = bpy.context.region
        if region is None:
            return
    except Exception:
        traceback.print_exc()
        return

    percent = float(state.get("percent", 0.0))
    phase = str(state.get("phase", ""))
    elapsed = float(state.get("elapsed", 0.0))

    _FONT = 0
    _BLUE = (0.231, 0.494, 0.965, 1.0)

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    def _rrect_verts(x, y, w, h, r, segs=8):
        cx_, cy_ = x + w / 2, y + h / 2
        verts = [(cx_, cy_)]
        corners = [
            (x + r, y + r, math.pi, 1.5 * math.pi),
            (x + w - r, y + r, 1.5 * math.pi, 2.0 * math.pi),
            (x + w - r, y + h - r, 0.0, 0.5 * math.pi),
            (x + r, y + h - r, 0.5 * math.pi, math.pi),
        ]
        for ox, oy, a0, a1 in corners:
            for i in range(segs + 1):
                a = a0 + (a1 - a0) * i / segs
                verts.append((ox + math.cos(a) * r, oy + math.sin(a) * r))
        verts.append(verts[1])
        return verts

    def _fan_tris(fan):
        c = fan[0]
        out = []
        for i in range(1, len(fan) - 1):
            out.extend([c, fan[i], fan[i + 1]])
        return out

    def _rrect(x, y, w, h, r, color):
        if w <= 0 or h <= 0:
            return
        tris = _fan_tris(_rrect_verts(x, y, w, h, max(r, 0.01)))
        b = batch_for_shader(shader, "TRIS", {"pos": tris})
        shader.bind()
        shader.uniform_float("color", color)
        b.draw(shader)

    MARGIN = 20
    CARD_W = 280
    PAD = 12
    ROW_GAP = 6
    BAR_H = 8
    CORNER_R = 6
    TITLE_SZ = 12
    SMALL_SZ = 10
    BADGE_PX = 6
    BADGE_PY = 3

    blf.size(_FONT, TITLE_SZ)
    _, title_h = blf.dimensions(_FONT, "Ag")

    blf.size(_FONT, SMALL_SZ)
    _, small_h = blf.dimensions(_FONT, "Ag")

    badge_label = "STEP"
    blf.size(_FONT, SMALL_SZ)
    badge_tw, badge_th = blf.dimensions(_FONT, badge_label)
    badge_w = badge_tw + BADGE_PX * 2
    badge_h = badge_th + BADGE_PY * 2

    CARD_H = PAD + max(title_h, badge_h) + ROW_GAP + BAR_H + ROW_GAP + small_h + PAD

    cx = MARGIN + 10
    cy = MARGIN + 20

    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")

    # Card background
    _rrect(cx, cy, CARD_W, CARD_H, CORNER_R, (0.08, 0.08, 0.10, 0.90))

    # Row 1: badge + phase text + elapsed/pct
    row1_y = cy + CARD_H - PAD - max(title_h, badge_h)

    badge_x = cx + PAD
    badge_y = row1_y + (max(title_h, badge_h) - badge_h) / 2
    _rrect(badge_x, badge_y, badge_w, badge_h, 3, _BLUE)
    blf.size(_FONT, SMALL_SZ)
    blf.color(_FONT, 0.05, 0.05, 0.05, 1.0)
    blf.position(_FONT, badge_x + BADGE_PX, badge_y + BADGE_PY, 0)
    blf.draw(_FONT, badge_label)

    pct_text = f"{elapsed:.1f}s  {int(percent * 100)}%"
    blf.size(_FONT, SMALL_SZ)
    pct_tw, _ = blf.dimensions(_FONT, pct_text)
    title_clip_r = cx + CARD_W - PAD - pct_tw - 8

    blf.size(_FONT, TITLE_SZ)
    title_x = badge_x + badge_w + 8
    blf.enable(_FONT, blf.CLIPPING)
    blf.clipping(_FONT, title_x, row1_y, title_clip_r, row1_y + title_h + 2)
    blf.color(_FONT, 1.0, 1.0, 1.0, 0.95)
    blf.position(_FONT, title_x, row1_y, 0)
    blf.draw(_FONT, phase)
    blf.disable(_FONT, blf.CLIPPING)

    blf.size(_FONT, SMALL_SZ)
    blf.color(_FONT, *_BLUE)
    blf.position(_FONT, cx + CARD_W - PAD - pct_tw, row1_y, 0)
    blf.draw(_FONT, pct_text)

    # Row 2: progress bar
    row2_y = row1_y - ROW_GAP - BAR_H
    bar_x = cx + PAD
    bar_w = CARD_W - PAD * 2
    _rrect(bar_x, row2_y, bar_w, BAR_H, BAR_H / 2, (0.15, 0.15, 0.18, 1.0))
    fill_w = max(bar_w * max(0.0, min(1.0, percent)), BAR_H)
    _rrect(bar_x, row2_y, fill_w, BAR_H, BAR_H / 2, _BLUE)

    # Row 3: filename
    row3_y = row2_y - ROW_GAP - small_h
    filename = str(state.get("filename", ""))
    if filename:
        blf.size(_FONT, SMALL_SZ)
        blf.enable(_FONT, blf.CLIPPING)
        blf.clipping(_FONT, cx + PAD, row3_y, cx + CARD_W - PAD, row3_y + small_h + 2)
        blf.color(_FONT, 0.55, 0.55, 0.60, 0.85)
        blf.position(_FONT, cx + PAD, row3_y, 0)
        blf.draw(_FONT, filename)
        blf.disable(_FONT, blf.CLIPPING)

    gpu.state.blend_set("NONE")


def _force_redraw() -> None:
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        traceback.print_exc()


class ViewportProgressBar:
    """GPU-drawn progress card in the 3D viewport.

    Use as a context manager::

        with ViewportProgressBar(context, "model.step") as bar:
            bar.update(0.1, "Reading file")
            bar.update(0.5, "Converting")
            bar.update(0.9, "Importing")
    """

    def __init__(self, context, filename: str) -> None:
        self._context = context
        self._filename = filename
        self._start = time.time()
        self._active = False

    def __enter__(self) -> "ViewportProgressBar":
        global _draw_handle, _STATE

        prefs = self._context.preferences.addons.get(__package__)
        if prefs and not prefs.preferences.show_progress:
            return self
        if bpy.app.background:
            return self

        self._active = True
        _STATE = {
            "active": True,
            "filename": self._filename,
            "percent": 0.0,
            "phase": "Starting",
            "elapsed": 0.0,
        }
        if _draw_handle is None:
            try:
                _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                    _draw_callback, (), "WINDOW", "POST_PIXEL"
                )
            except Exception:
                traceback.print_exc()
        _force_redraw()
        return self

    def update(self, percent: float, phase: str) -> None:
        global _STATE
        if not self._active:
            return
        _STATE.update(
            {
                "percent": max(0.0, min(1.0, percent)),
                "phase": phase,
                "elapsed": time.time() - self._start,
            }
        )
        _force_redraw()

    def __exit__(self, *_) -> Literal[False]:
        global _draw_handle, _STATE
        if not self._active:
            return False
        self._active = False
        _STATE = {"active": False}
        if _draw_handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
            except Exception:
                traceback.print_exc()
            _draw_handle = None
        _force_redraw()
        return False
