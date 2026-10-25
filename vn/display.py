"""Window sizing and coordinate mapping, independent of story layout."""
import pygame as pg


def fit_size(bounds, fraction=1.0):
    return tuple(max(1, int(value * fraction)) for value in bounds)


class Display:
    def __init__(self, fullscreen=False):
        self.fullscreen = fullscreen
        self.windowed_size = fit_size(self.desktop_size(), fraction=0.9)
        self.surface = self.open(fullscreen)

    @staticmethod
    def desktop_size():
        return pg.display.get_desktop_sizes()[0]

    def open(self, fullscreen):
        size = self.desktop_size() if fullscreen else self.windowed_size
        return pg.display.set_mode(size, pg.FULLSCREEN if fullscreen else pg.RESIZABLE)

    def toggle(self):
        if not self.fullscreen:
            self.windowed_size = self.surface.get_size()
        else:
            # The desktop resolution may have changed while fullscreen was active.
            desktop = self.desktop_size()
            if any(value > bound for value, bound in zip(self.windowed_size, desktop)):
                self.windowed_size = fit_size(desktop, 0.9)
        self.surface = self.open(not self.fullscreen)
        self.fullscreen = not self.fullscreen
        return self.surface
