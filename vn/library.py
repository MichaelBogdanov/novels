"""Library screen, sharing the application's native-size drawing helpers."""
from functools import lru_cache
import math
import pygame as pg
from .catalog import discover_stories
from .story import Story, StoryError


class Library:
    def refresh_catalog(self):
        self.catalog, errors = discover_stories(self.stories_dir)
        self.catalog_errors = errors
        self.menu_error = "Некоторые истории недоступны. Подробности в терминале." if errors else ""
        for error in errors:
            print(error)
        self.menu_focus = min(self.menu_focus, max(0, len(self.catalog) - 1))

    def show_library(self):
        self.stop_sound()
        self.in_menu = True
        self.hidden = self.history = False
        self.refresh_catalog()
        pg.display.set_caption("Визуальные новеллы · Библиотека")

    @lru_cache(maxsize=12)
    def cover(self, path):
        try:
            return pg.image.load(str(path)).convert()
        except (OSError, ValueError, pg.error):
            return None

    def menu_geometry(self):
        w, h = self.canvas.get_size()
        p = self.layout.pad
        width = min(w - p * 4, round(self.layout.unit * 66))
        x = (w - width) // 2
        top = p * 3 + self.font.get_linesize() + self.small.get_linesize() * 2
        bottom = h - p * 3 - self.layout.button_height * 2 - self.small.get_linesize() * 2
        row_height = max(70, self.small.get_linesize() * 3 + p * 2)
        area = pg.Rect(x, top, width, max(row_height, bottom - top))
        capacity = max(1, area.height // (row_height + self.layout.gap))
        self.menu_offset = max(0, min(self.menu_offset, self.menu_focus))
        if self.menu_focus >= self.menu_offset + capacity:
            self.menu_offset = self.menu_focus - capacity + 1
        self.menu_offset = min(self.menu_offset, max(0, len(self.catalog) - capacity))
        return area, row_height, capacity

    def render_library(self):
        self.canvas.fill((10, 17, 29))
        area, height, capacity = self.menu_geometry()
        p, gap = self.layout.pad, self.layout.gap
        self.text("Визуальные новеллы", (area.x, p * 2), self.font)
        subtitle = "Истории, в которых вы выбираете продолжение"
        self.text(self.elide(subtitle, self.small, area.width),
                  (area.x, p * 2 + self.font.get_linesize() + gap), self.small, (161, 174, 195))
        self.canvas.set_clip(area)
        if not self.catalog:
            self.panel(area, 240)
            message = "Пока нет доступных историй"
            self.text(self.elide(message, self.font, area.width - p * 2),
                      (area.x + p, area.centery - self.font.get_linesize()), self.font)
            self.text("Загляните сюда позже", (area.x + p, area.centery + gap), self.small, (161, 174, 195))
        for index in range(self.menu_offset, min(len(self.catalog), self.menu_offset + capacity)):
            story = self.catalog[index]
            rect = pg.Rect(area.x, area.y + (index - self.menu_offset) * (height + gap), area.width, height)
            selected = index == self.menu_focus
            self.panel(rect, 255, (27, 51, 60) if selected else (19, 29, 45), 12)
            if selected:
                pg.draw.rect(self.canvas, (137, 220, 206), rect, 2, border_radius=12)
            thumb = pg.Rect(rect.x + gap, rect.y + gap, round(height * 1.35), height - gap * 2)
            source = self.cover(story.asset(story.nodes[story.start]["art"]))
            if source:
                scale = max(thumb.width / source.get_width(), thumb.height / source.get_height())
                scaled = pg.transform.smoothscale(source, (math.ceil(source.get_width() * scale), math.ceil(source.get_height() * scale)))
                self.canvas.blit(scaled, thumb, ((scaled.get_width() - thumb.width) // 2,
                                               (scaled.get_height() - thumb.height) // 2, thumb.width, thumb.height))
            text_x = thumb.right + p
            title, _, author = story.title.partition(" · ")
            available = rect.right - text_x - p
            self.text(self.elide(title, self.label, available), (text_x, rect.y + p), self.label)
            self.text(self.elide(author or "Визуальная история", self.small, available),
                      (text_x, rect.y + p + self.label.get_linesize() + gap), self.small, (161, 174, 195))
            self.buttons.append((rect.clip(area), ("open_story", index)))
        self.canvas.set_clip(None)
        y = self.canvas.get_height() - p * 2 - self.layout.button_height * 2 - self.small.get_linesize() * 2
        status = self.menu_error or (f"{self.menu_focus + 1} / {len(self.catalog)} · ↑ ↓ / колесо — выбор · Enter — открыть" if self.catalog else "")
        self.text(self.elide(status, self.small, area.width), (area.x, y), self.small, (161, 174, 195))
        y += self.small.get_linesize() + gap
        width = (area.width - gap * 2) // 3
        for index, (label, action, enabled) in enumerate([
            ("Продолжить", "resume", self.story is not None),
            ("Обновить", "refresh", True), ("Выйти из игры", "quit", True)
        ]):
            self.button((area.x + index * (width + gap), y, width, self.layout.button_height), label, (action,), enabled)
        self.button((area.x, y + self.layout.button_height + gap, area.width, self.layout.button_height),
                    "Окно · F11" if self.display.fullscreen else "На весь экран · F11", ("fullscreen",))

    def library_action(self, action):
        kind = action[0]
        if kind == "open_story":
            try:
                story = Story(self.catalog[action[1]].path)
                # Decode resources before replacing the current session.
                for path in {node["art"] for node in story.nodes.values()}:
                    pg.image.load(str(story.asset(path)))
                settings = story.data.get("settings", {})
                if "font" in settings:
                    pg.font.Font(str(story.asset(settings["font"])), 16)
                self.start_story(story)
            except (StoryError, OSError, ValueError, pg.error) as exc:
                self.menu_error = "Не удалось открыть историю. Выберите другую."
                print(f"Ошибка истории: {exc}")
        elif kind == "resume" and self.story:
            self.in_menu = False
            pg.display.set_caption(self.story.title)
        elif kind == "refresh":
            self.cover.cache_clear()
            self.refresh_catalog()

    def library_event(self, event):
        if event.type == pg.KEYDOWN:
            if event.key in (pg.K_UP, pg.K_DOWN) and self.catalog:
                self.menu_focus = (self.menu_focus + (-1 if event.key == pg.K_UP else 1)) % len(self.catalog)
            elif event.key == pg.K_RETURN and self.catalog:
                self.library_action(("open_story", self.menu_focus))
            elif event.key == pg.K_ESCAPE:
                self.library_action(("resume",))
        elif event.type == pg.MOUSEWHEEL and self.catalog:
            amount = event.y * (-1 if getattr(event, "flipped", False) else 1)
            self.menu_focus = max(0, min(len(self.catalog) - 1, self.menu_focus - amount))
        elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            for rect, action in reversed(self.buttons):
                if rect.collidepoint(event.pos):
                    self.dispatch(action)
                    break
