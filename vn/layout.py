"""Responsive geometry in actual window pixels; no fixed-resolution canvas."""
import pygame as pg


class Layout:
    def __init__(self, size):
        self.width, self.height = size
        w, h = size
        # A typographic unit derived from the device's shorter side.
        self.unit = max(7, min(w, h) / 45)
        u = self.unit
        self.pad = max(6, round(u * 1.25))
        p = self.pad
        self.body_size = max(12, round(u * 1.62))
        self.label_size = max(11, round(u * 1.25))
        self.small_size = max(10, round(u * 1.12))
        self.button_height = round(u * 2.7)
        self.gap = max(4, round(u * .6))
        self.compact = w / u < 108
        self.columns = 3 if w / u < 48 else 4 if self.compact else 7
        rows = (7 + self.columns - 1) // self.columns
        header_height = self.button_height + p
        if self.compact:
            header_height = self.label_size + p * 2 + rows * (self.button_height + self.gap)
        self.header = pg.Rect(p, p, w - 2 * p, header_height)
        self.title = pg.Rect(self.header.x + p, self.header.y + p // 2,
                             self.header.width - 2 * p, self.label_size * 2)
        if self.compact:
            button_y = self.title.bottom + self.gap
            button_x = self.header.x + p // 2
            button_width = (self.header.width - p - (self.columns - 1) * self.gap) // self.columns
        else:
            button_width = round(u * 8.4)
            button_y = self.header.y + p // 2
            button_x = self.header.right - p // 2 - 7 * button_width - 6 * self.gap
            self.title.width = button_x - self.title.x - p
        self.toolbar = [pg.Rect(button_x + (i % self.columns) * (button_width + self.gap),
                               button_y + (i // self.columns) * (self.button_height + self.gap),
                               button_width, self.button_height) for i in range(7)]
        self.dialogue = pg.Rect(2 * p, h - p - round(h * .36), w - 4 * p, round(h * .36))
        self.speaker = (self.dialogue.x + p, self.dialogue.y + p)
        self.body = pg.Rect(self.dialogue.x + p, self.dialogue.y + p + self.label_size * 2,
                            self.dialogue.width - 2 * p,
                            self.dialogue.height - 2 * p - self.label_size * 2 - self.small_size * 2)
        self.footer_y = self.dialogue.bottom - p - self.small_size
        self.choice_heading_y = self.header.bottom + p
        top = self.choice_heading_y + self.small_size * (3 if self.compact else 2)
        self.choices = pg.Rect(3 * p, top, w - 6 * p, max(1, self.dialogue.top - p - top))
        end_width = min(self.choices.width, round(u * 50))
        self.ending = pg.Rect((w - end_width) // 2, self.choices.y, end_width, self.choices.height)
        self.history = pg.Rect(2 * p, 2 * p, w - 4 * p, h - 4 * p)
        self.history_close = pg.Rect(self.history.right - round(u * 10) - p, self.history.y + p,
                                     round(u * 10), self.button_height)
        self.history_area = pg.Rect(self.history.x + p, self.history.y + 3 * p + self.button_height + self.small_size * 2,
                                    self.history.width - 2 * p,
                                    self.history.height - 4 * p - self.button_height - self.small_size * 2)
