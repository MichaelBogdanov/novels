"""Library screen, sharing the application's native-size drawing helpers."""
from functools import lru_cache
import pygame as pg
from .catalog import discover_stories
from .story import Story, StoryError
from .ui import ACCENT, MUTED, SURFACE, SELECTED, mix, rounded_cover


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
        pg.display.set_caption("Визуальные новеллы - Библиотека")

    @lru_cache(maxsize=12)
    def cover(self, path):
        try:
            return pg.image.load(str(path)).convert()
        except (OSError, ValueError, pg.error):
            return None

    def menu_geometry(self):
        w, h = self.canvas.get_size()
        p = self.layout.pad
        width = min(w - p * 4, round(self.layout.unit * 88))
        x = (w - width) // 2
        top = p * 4 + self.heading.get_linesize() + self.small.get_linesize()
        bottom = self.menu_footer_y() - p
        self.menu_outer = pg.Rect(x, top, width, max(1, bottom - top))
        self.menu_hero = None
        if w >= 1000 and w / h >= 1.35 and self.catalog:
            hero_width = round(width * .44)
            self.menu_hero = pg.Rect(x, top, hero_width, bottom - top)
            x += hero_width + p * 2
            width -= hero_width + p * 2
        elif h >= 1000 and h / w >= 1.35 and self.catalog:
            hero_height = round(self.layout.unit * 28)
            self.menu_hero = pg.Rect(x, top, width, hero_height)
            top += hero_height + p * 2
        row_height = max(68, self.label.get_linesize() + self.small.get_linesize() + p * 2 + self.layout.gap)
        area = pg.Rect(x, top, width, max(row_height, bottom - top))
        capacity = max(1, area.height // (row_height + self.layout.gap))
        self.menu_offset = max(0, min(self.menu_offset, self.menu_focus))
        if self.menu_focus >= self.menu_offset + capacity:
            self.menu_offset = self.menu_focus - capacity + 1
        self.menu_offset = min(self.menu_offset, max(0, len(self.catalog) - capacity))
        return area, row_height, capacity

    def menu_footer_y(self):
        return self.canvas.get_height() - self.layout.pad * 2 - self.layout.button_height * 2 - self.small.get_linesize() * 2

    @lru_cache(maxsize=20)
    def cover_thumbnail(self, path, size, radius):
        source = self.cover(path)
        return rounded_cover(source, size, radius) if source else None

    @lru_cache(maxsize=3)
    def library_background(self, size):
        surface = pg.Surface(size)
        w, h = size
        # Quiet, static light: no distracting moving background behind the reader.
        for y in range(h):
            pg.draw.line(surface, mix((29, 36, 52), (12, 15, 22), y / max(1, h - 1)), (0, y), (w, y))
        return surface

    def draw_library_hero(self):
        rect = self.menu_hero
        if rect is None:
            return
        p = self.layout.pad
        story = self.catalog[self.menu_focus]
        self.panel(rect, 255, SURFACE, p * 2, glass=True)
        image_fraction = .58 if self.canvas.get_height() / self.canvas.get_width() >= 1.35 else .48
        image_rect = pg.Rect(rect.x + p, rect.y + p, rect.width - p * 2, round(rect.height * image_fraction))
        cover = self.cover_thumbnail(story.asset(story.nodes[story.start]["art"]), image_rect.size, p)
        if cover:
            self.canvas.blit(cover, image_rect)
        title, _, author = story.title.partition(" · ")
        y = image_rect.bottom + p
        self.text("ВЫБРАННАЯ ИСТОРИЯ", (image_rect.x, y), self.small, ACCENT)
        y += self.small.get_linesize() + self.layout.gap
        # At most two title lines; metadata and the action keep a stable position.
        words, lines, line = title.split(), [], ""
        for word in words:
            candidate = (line + " " + word).strip()
            if line and self.ui_title.size(candidate)[0] > image_rect.width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
        if len(lines) > 2:
            lines = [lines[0], " ".join(lines[1:])]
        for line in lines:
            self.text(self.elide(line, self.ui_title, image_rect.width), (image_rect.x, y), self.ui_title)
            y += self.ui_title.get_linesize()
        button_y = rect.bottom - p - self.layout.button_height
        if y + self.small.get_linesize() + self.layout.gap <= button_y - p:
            self.text(self.elide(author or "Визуальная история", self.small, image_rect.width),
                      (image_rect.x, y + self.layout.gap), self.small, MUTED)
        self.button((image_rect.x, button_y, image_rect.width, self.layout.button_height),
                    "Открыть историю   →", ("open_story", self.menu_focus), active=True)

    def render_library(self):
        self.canvas.blit(self.library_background(self.canvas.get_size()), (0, 0))
        area, height, capacity = self.menu_geometry()
        p, gap = self.layout.pad, self.layout.gap
        outer = self.menu_outer
        self.text("ВИЗУАЛЬНЫЕ НОВЕЛЛЫ", (outer.x, p * 2), self.small, ACCENT)
        self.text("Библиотека", (outer.x, p * 2 + self.small.get_linesize() + gap), self.heading)
        count = f"{len(self.catalog):02}"
        self.text(count, (outer.right - self.heading.size(count)[0], p * 2 + self.small.get_linesize() + gap), self.heading, MUTED)
        self.draw_library_hero()
        self.canvas.set_clip(area)
        if not self.catalog:
            self.panel(area, 240)
            message = "Пока нет доступных историй"
            self.text(self.elide(message, self.font, area.width - p * 2),
                      (area.x + p, area.centery - self.font.get_linesize()), self.font)
            self.text("Загляните сюда позже", (area.x + p, area.centery + gap), self.small, MUTED)
        for index in range(self.menu_offset, min(len(self.catalog), self.menu_offset + capacity)):
            story = self.catalog[index]
            rect = pg.Rect(area.x, area.y + (index - self.menu_offset) * (height + gap), area.width, height)
            selected = index == self.menu_focus
            amount = self.feedback.value(("story", index), selected or rect.collidepoint(self.mouse()))
            self.panel(rect, 255, mix(SURFACE, SELECTED, amount), p)
            if selected:
                pg.draw.rect(self.canvas, ACCENT, rect, 2, border_radius=p)
            thumb = pg.Rect(rect.x + gap, rect.y + gap, round(height * 1.35), height - gap * 2)
            source = self.cover_thumbnail(story.asset(story.nodes[story.start]["art"]), thumb.size, max(6, p // 2))
            if source:
                self.canvas.blit(source, thumb)
            text_x = thumb.right + p
            title, _, author = story.title.partition(" · ")
            available = rect.right - text_x - p * 3
            self.text(self.elide(title, self.label, available), (text_x, rect.y + p), self.label)
            self.text(self.elide(author or "Визуальная история", self.small, available),
                      (text_x, rect.y + p + self.label.get_linesize() + gap), self.small, MUTED)
            self.text("›", (rect.right - p * 2, rect.centery - self.label.get_height() // 2), self.label, ACCENT if selected else MUTED)
            self.buttons.append((rect.clip(area), ("open_story", index)))
        self.canvas.set_clip(None)
        if len(self.catalog) > capacity:
            scroll_area = pg.Rect(area.x, area.y, area.width, capacity * (height + gap) - gap)
            self.scrollbar(scroll_area, len(self.catalog) * (height + gap) - gap, self.menu_offset * (height + gap))
        y = self.menu_footer_y()
        status = self.menu_error or (f"{self.menu_focus + 1} / {len(self.catalog)}: ↑ ↓ / колесо - выбор, Enter - открыть" if self.catalog else "")
        self.text(self.elide(status, self.small, outer.width), (outer.x, y), self.small, MUTED)
        y += self.small.get_linesize() + gap
        width = (outer.width - gap * 2) // 3
        for index, (label, action, enabled) in enumerate([
            ("Продолжить", "resume", self.story is not None),
            ("Обновить", "refresh", True), ("Выйти из игры", "quit", True)
        ]):
            self.button((outer.x + index * (width + gap), y, width, self.layout.button_height), label, (action,), enabled)
        y += self.layout.button_height + gap
        for index, (label, action, active, shortcut) in enumerate([
            ("Окно" if self.display.fullscreen else "Полный экран", "fullscreen", self.display.fullscreen, "F11"),
            ("Без анимации" if self.feedback.reduced else "Анимация", "motion", self.feedback.reduced, "F6"),
            ("Без прозрачности" if self.solid_ui else "Прозрачность", "transparency", self.solid_ui, "F7"),
        ]):
            self.button((outer.x + index * (width + gap), y, width, self.layout.button_height), label, (action,), active=active, shortcut=shortcut)

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
            pg.display.set_caption(self.story.title.replace(" · ", " - "))
        elif kind == "refresh":
            self.cover.cache_clear()
            self.cover_thumbnail.cache_clear()
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
