"""Responsive geometry in actual window pixels; no fixed-resolution canvas."""
import pygame as pg


class Layout:
    def __init__(self, size, toolbar_open=True):
        self.toolbar_open = toolbar_open
        self.width, self.height = size
        w, h = size
        # A typographic unit derived from the device's shorter side.
        self.unit = max(8, min(24, min(w, h) / 54))
        u = self.unit
        self.pad = max(8, round(u * 1.25))
        p = self.pad
        self.body_size = max(16, round(u * 1.55))
        self.label_size = max(13, round(u * 1.25))
        self.small_size = max(12, round(u * 1.12))
        self.button_height = max(30, round(u * 2.65))
        self.gap = max(4, round(u * .6))
        self.compact = w / u < 92
        self.columns = 3 if w / u < 60 else 4 if self.compact else 7
        rows = (7 + self.columns - 1) // self.columns
        header_height = self.button_height + 2 * p
        if self.compact:
            header_height += rows * (self.button_height + self.gap)
        self.toolbar_toggle = pg.Rect(w - p - max(104, round(u * 10.4)), p,
                                      max(104, round(u * 10.4)), self.button_height)
        self.header = pg.Rect(p, self.toolbar_toggle.bottom + self.gap, w - 2 * p, header_height)
        self.story_title = pg.Rect(self.header.x, p, self.toolbar_toggle.x - self.header.x - self.gap,
                                   self.button_height)
        self.title = pg.Rect(self.header.x + p, self.header.y + p,
                             self.header.width - 2 * p, self.button_height)
        if self.compact:
            button_y = self.title.bottom + self.gap
            button_x = self.header.x + p
            button_width = (self.header.width - 2 * p - (self.columns - 1) * self.gap) // self.columns
        else:
            button_width = max(100, round(u * 8.8))
            button_y = self.header.y + p
            button_x = self.header.right - p - 7 * button_width - 6 * self.gap
            self.title.width = button_x - self.title.x - p
        self.toolbar = [pg.Rect(button_x + (i % self.columns) * (button_width + self.gap),
                               button_y + (i // self.columns) * (self.button_height + self.gap),
                               button_width, self.button_height) for i in range(7)]
        dialogue_height = max(116, min(round(h * .24), round(u * 13)))
        self.dialogue = pg.Rect(self.header.x, h - p - dialogue_height,
                                self.header.width, dialogue_height)
        self.speaker = (self.dialogue.x + p, self.dialogue.y + p)
        self.body = pg.Rect(self.dialogue.x + p, self.dialogue.y + p + self.label_size * 2,
                            self.dialogue.width - 2 * p,
                            self.dialogue.height - 2 * p - self.label_size * 2 - self.small_size * 2)
        self.footer_y = self.dialogue.bottom - p - self.small_size
        self.choice_heading_y = (self.header.bottom if toolbar_open else self.toolbar_toggle.bottom) + p
        self.choice_heading_height = self.small_size * (3 if self.compact else 2) + self.gap * 2
        top = self.choice_heading_y + self.choice_heading_height + self.gap
        choice_width = min(self.dialogue.width, round(u * 60))
        self.choices = pg.Rect((w - choice_width) // 2, top, choice_width, max(1, self.dialogue.top - p - top))
        self.choice_bounds = self.choices.copy()
        end_width = self.choices.width
        end_height = min(self.choices.height, round(u * 16))
        self.ending = pg.Rect((w - end_width) // 2, self.choices.bottom - end_height, end_width, end_height)
        history_width = min(w - 4 * p, round(u * 76))
        self.history = pg.Rect((w - history_width) // 2, 2 * p, history_width, h - 4 * p)
        self.history_close = pg.Rect(self.history.right - round(u * 10) - p, self.history.y + p,
                                     round(u * 10), self.button_height)
        self.history_area = pg.Rect(self.history.x + p, self.history.y + 3 * p + self.button_height + self.small_size * 2,
                                    self.history.width - 2 * p,
                                    self.history.height - 4 * p - self.button_height - self.small_size * 2)
