"""Shared native-pixel materials and interruptible, critically damped feedback."""
from collections import OrderedDict
from functools import lru_cache
import math
from pathlib import Path

import pygame as pg

INK = (245, 246, 250)
MUTED = (182, 189, 204)
ACCENT = (143, 190, 255)
SURFACE = (24, 28, 38)
RAISED = (38, 43, 56)
SELECTED = (39, 64, 99)


def system_font(bold=False):
    path = pg.font.match_font("segoeui,dejavusans,arial", bold=bold)
    # SDL can resolve the family to Segoe UI Light on Windows. Prefer the
    # actual regular/semibold face so small labels retain their contrast.
    if path and Path(path).name.lower().startswith("segoeui"):
        face = Path(path).with_name("seguisb.ttf" if bold else "segoeui.ttf")
        if face.is_file():
            return str(face)
    return path


def mix(first, second, amount):
    return tuple(round(a + (b - a) * max(0, min(1, amount))) for a, b in zip(first, second))


class Feedback:
    """Retarget from the current value AND velocity; never delay input."""
    def __init__(self):
        self.states = OrderedDict()
        self.reduced = False

    def value(self, key, target):
        if key not in self.states:
            self.states[key] = [float(target), 0.0, float(target)]
        state = self.states[key]
        state[2] = float(target)
        if self.reduced:
            state[:] = [float(target), 0.0, float(target)]
        self.states.move_to_end(key)
        if len(self.states) > 160:
            self.states.popitem(last=False)
        return state[0]

    def step(self, dt):
        dt = max(0, min(dt, .1))
        omega = 24.0
        decay = math.exp(-omega * dt)
        for state in self.states.values():
            value, velocity, target = state
            if self.reduced:
                state[:] = [target, 0.0, target]
                continue
            offset = value - target
            slope = velocity + omega * offset
            state[0] = target + (offset + slope * dt) * decay
            state[1] = (velocity - omega * slope * dt) * decay


@lru_cache(maxsize=96)
def material(size, color, alpha, radius, solid=False):
    layer = pg.Surface(size, pg.SRCALPHA)
    pg.draw.rect(layer, (*color, 255 if solid else alpha), layer.get_rect(), border_radius=radius)
    pg.draw.rect(layer, (211, 224, 255, 85 if solid else 30), layer.get_rect(), 1, border_radius=radius)
    return layer


@lru_cache(maxsize=24)
def shadow(size, radius):
    layer = pg.Surface((size[0] + 20, size[1] + 24), pg.SRCALPHA)
    for spread in range(10, 0, -2):
        rect = pg.Rect(10 - spread, 12 - spread, size[0] + spread * 2, size[1] + spread * 2)
        pg.draw.rect(layer, (0, 0, 0, 4 + (10 - spread) * 2), rect, border_radius=radius + spread)
    return layer


def frost(surface):
    """Prepared once per background/resize, never blurred in the frame loop."""
    w, h = surface.get_size()
    small = pg.transform.smoothscale(surface, (max(1, w // 32), max(1, h // 32)))
    return pg.transform.smoothscale(small, (w, h))


def rounded_cover(source, size, radius):
    w, h = size
    ratio = max(w / source.get_width(), h / source.get_height())
    scaled = pg.transform.smoothscale(source, (math.ceil(source.get_width() * ratio), math.ceil(source.get_height() * ratio)))
    result = pg.Surface(size, pg.SRCALPHA)
    result.blit(scaled, ((w - scaled.get_width()) // 2, (h - scaled.get_height()) // 2))
    mask = pg.Surface(size, pg.SRCALPHA)
    pg.draw.rect(mask, (255, 255, 255), mask.get_rect(), border_radius=radius)
    result.blit(mask, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    return result
