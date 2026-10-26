"""Pygame presentation. All story-specific content lives in the story package."""
from array import array
from functools import lru_cache
import math
import re
import warnings
import os
import pygame as pg
from .story import Session, StoryError
from .display import Display
from .layout import Layout
from .text import paginate
from .catalog import STORIES
from .library import Library
from .ui import ACCENT, INK, MUTED, SURFACE, RAISED, SELECTED, Feedback, mix, material, shadow, frost, system_font

ENDING = {"good": (137, 220, 186), "bad": (240, 145, 155), "neutral": (195, 187, 241)}
ENDING_LABEL = {"good": "СВЕТЛЫЙ ФИНАЛ", "bad": "ТРАГИЧЕСКИЙ ФИНАЛ", "neutral": "НЕЙТРАЛЬНЫЙ ФИНАЛ"}


def wrap(text, font, width):
    """Wrap before typewriting, preserving paragraphs and splitting long tokens."""
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for token in re.findall(r"\S+\s*", paragraph):
            if line and font.size(line + token.rstrip())[0] > width:
                lines.append(line.rstrip())
                line = ""
            for char in token:
                if font.size(line + char)[0] > width and line:
                    lines.append(line.rstrip())
                    line = ""
                line += char
        lines.append(line.rstrip())
    return lines


class App(Library):
    def __init__(self, story=None, fullscreen=False, stories_dir=STORIES):
        pg.mixer.pre_init(44100, -16, 1, 512)
        pg.init()
        self.display = Display(fullscreen)
        self.window = self.display.surface
        self.story = self.session = None
        self.stories_dir = stories_dir
        self.in_menu = True
        self.menu_focus = self.menu_offset = 0
        self.muted = False
        self.sound = None
        self.hidden = self.history = False
        self.toolbar_open = False
        self.running = True
        self.buttons = []
        self.feedback = Feedback()
        self.feedback.reduced = os.environ.get("VN_REDUCED_MOTION") == "1"
        self.solid_ui = os.environ.get("VN_REDUCED_TRANSPARENCY") == "1"
        self.font_path = system_font()
        self.configure_layout()
        self.show_library()
        if story is not None:
            self.start_story(story)

    def stop_sound(self):
        if self.sound:
            self.sound.stop()

    def start_story(self, story):
        self.stop_sound()
        self.art.cache_clear()
        self.story = story
        self.session = Session(story)
        self.in_menu = False
        pg.display.set_caption(story.title.replace(" · ", " - "))
        settings = story.data.get("settings", {})
        self.font_path = str(story.asset(settings["font"])) if "font" in settings else system_font()
        self.speed = settings.get("text_speed", 36)
        self.sound = None
        if pg.mixer.get_init():
            try:
                if "typing_sound" in settings:
                    self.sound = pg.mixer.Sound(str(story.asset(settings["typing_sound"])))
                else:
                    samples = array("h", (int(2800 * math.sin(2 * math.pi * 740 * i / 44100)
                                              * (1 - i / 1323) ** 2) for i in range(1323)))
                    self.sound = pg.mixer.Sound(buffer=samples)
                self.sound.set_volume(settings.get("volume", 0.25))
            except (OSError, pg.error) as exc:
                warnings.warn(f"Звук недоступен: {exc}")
        else:
            warnings.warn("Аудиоустройство недоступно; новелла запущена без звука")
        self.hidden = self.history = False
        self.scroll = self.choice_scroll = self.focus = 0
        self.configure_layout()
        self.load_frame()

    @lru_cache(maxsize=8)
    def art(self, path):
        try:
            return pg.image.load(str(self.story.asset(path))).convert()
        except (OSError, pg.error, ValueError) as exc:
            raise StoryError(f"Не удалось загрузить арт {path}: {exc}") from exc

    def configure_layout(self):
        self.layout = Layout(self.window.get_size(), toolbar_open=self.toolbar_open)
        self.canvas = pg.Surface(self.window.get_size())
        self.viewport = self.canvas.get_rect()
        self.font = pg.font.Font(self.font_path, self.layout.body_size)
        self.small = pg.font.Font(self.font_path, self.layout.small_size)
        self.key_font = pg.font.Font(system_font(bold=True), self.layout.small_size)
        self.key_font.set_bold(True)
        self.label = pg.font.Font(self.font_path, self.layout.label_size)
        self.label.set_bold(True)
        self.heading = pg.font.Font(system_font(bold=True), round(self.layout.body_size * 2.0))
        self.ui_title = pg.font.Font(system_font(bold=True), round(self.layout.body_size * 1.3))
        self.line_height = self.font.get_linesize()
        self.history_step = self.small.get_linesize() * 2 + self.layout.pad * 2 + self.layout.gap

    def fit_background(self):
        source = self.art(self.session.node["art"])
        w, h = self.canvas.get_size()
        sw, sh = source.get_size()
        ratio = max(w / sw, h / sh)
        scaled = pg.transform.smoothscale(source, (math.ceil(sw * ratio), math.ceil(sh * ratio)))
        self.background = scaled.subsurface(((scaled.get_width() - w) // 2, (scaled.get_height() - h) // 2, w, h)).copy()
        self.frosted_background = frost(self.background)

    def reflow_text(self):
        text = self.session.node["text"]
        self.pages = paginate(text, self.font, self.layout.body.width,
                              self.layout.body.height // self.line_height, self.session.current.offset)
        self.page = self.pages[0]
        self.lines = [text[line.start:line.end] for line in self.page.lines]
        self.page_text = text[self.page.start:self.page.end]

    def ensure_layout(self):
        if self.canvas.get_size() == self.window.get_size() and self.layout.toolbar_open == self.toolbar_open:
            return False
        visible = getattr(self, "visible", 0)
        resized = self.canvas.get_size() != self.window.get_size()
        self.configure_layout()
        if self.story is None:
            return True
        if resized:
            self.fit_background()
        self.reflow_text()
        self.visible = min(visible, len(self.page_text))
        if self.choosing:
            self.move_choice(0)
        return True

    def load_frame(self, revealed=False):
        self.stop_sound()
        self.fit_background()
        self.reflow_text()
        self.visible = len(self.page_text) if revealed else 0
        self.timer = 0
        self.choice_scroll = 0
        self.focus = 0
        self.wheel_remainder = 0.0

    @property
    def complete(self):
        return self.visible >= len(self.page_text)

    @property
    def last_page(self):
        return len(self.pages) == 1

    @property
    def choosing(self):
        return self.complete and self.last_page and "choices" in self.session.node

    def update(self, dt):
        self.feedback.step(dt)
        if self.in_menu or self.hidden or self.history or self.complete:
            return
        self.timer += min(dt, 0.1)
        # Per-character scheduling; punctuation receives a small natural pause.
        while not self.complete:
            previous = self.page_text[self.visible - 1] if self.visible else ""
            delay = (3 if previous in ".!?…" and previous else 1.5 if previous in ",;:" and previous else 1) / self.speed
            if self.timer < delay:
                break
            self.timer -= delay
            char = self.page_text[self.visible]
            self.visible += 1
            if not char.isspace() and self.sound and not self.muted:
                self.sound.play()

    def advance(self):
        self.stop_sound()
        if not self.complete:
            self.visible = len(self.page_text)
        elif not self.last_page:
            self.session.next_page(self.page.end)
            self.load_frame()
        elif "next" in self.session.node:
            self.session.advance()
            self.load_frame()

    def back(self):
        if self.session.back():
            self.load_frame(revealed=True)

    def text(self, text, pos, font=None, color=INK):
        self.canvas.blit((font or self.font).render(text, True, color), pos)

    def panel(self, rect, alpha=225, color=SURFACE, radius=20, glass=False):
        rect = pg.Rect(rect)
        if rect.width <= 0 or rect.height <= 0:
            return
        if glass:
            self.canvas.blit(shadow(rect.size, radius), (rect.x - 10, rect.y - 8))
            if not self.solid_ui and not self.in_menu and self.viewport.contains(rect):
                layer = self.frosted_background.subsurface(rect).copy().convert_alpha()
                mask = material(rect.size, (255, 255, 255), 255, radius)
                layer.blit(mask, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
                self.canvas.blit(layer, rect)
        self.canvas.blit(material(rect.size, color, alpha, radius, self.solid_ui), rect)

    def button(self, rect, label, action, enabled=True, active=False, shortcut=None):
        rect = pg.Rect(rect)
        hover = rect.collidepoint(self.mouse()) and enabled
        amount = self.feedback.value(("button", action), hover or active)
        self.panel(rect, 245, mix(RAISED, SELECTED, amount), max(8, self.layout.pad))
        if active:
            pg.draw.rect(self.canvas, ACCENT, rect, 1, border_radius=max(8, self.layout.pad))
        color = INK if enabled else (123, 130, 146)
        key = self.key_font.render(shortcut, True, color) if shortcut else None
        gap = self.layout.gap if key else 0
        available = rect.width - self.layout.pad - (key.get_width() + gap if key else 0)
        text = self.small.render(self.elide(label, self.small, available), True, color)
        width = text.get_width() + (key.get_width() + gap if key else 0)
        x = rect.centerx - width // 2
        self.canvas.blit(text, (x, rect.centery - text.get_height() // 2))
        if key:
            self.canvas.blit(key, (x + text.get_width() + gap, rect.centery - key.get_height() // 2))
        if enabled:
            self.buttons.append((rect, action))

    def mouse(self, pos=None):
        return pos if pos is not None else pg.mouse.get_pos()

    def scrollbar(self, area, total, offset):
        if total <= area.height:
            return
        track = pg.Rect(area.right + self.layout.gap, area.y, max(3, self.layout.pad // 4), area.height)
        pg.draw.rect(self.canvas, RAISED, track, border_radius=2)
        height = min(area.height, max(18, round(area.height * area.height / total)))
        position = max(0, min(1, offset / (total - area.height)))
        thumb = pg.Rect(track.x, area.y + round((area.height - height) * position), track.width, height)
        pg.draw.rect(self.canvas, MUTED, thumb, border_radius=2)

    @staticmethod
    def elide(value, font, width):
        value = value.replace("\n", " ")
        if font.size(value)[0] <= width:
            return value
        while value and font.size(value + "…")[0] > width:
            value = value[:-1]
        return value + "…" if value else ""

    def render(self):
        self.ensure_layout()
        self.buttons = []
        if self.in_menu:
            self.render_library()
            self.window.blit(self.canvas, (0, 0))
            pg.display.flip()
            return
        self.canvas.blit(self.background, (0, 0))
        if not self.hidden:
            l, p = self.layout, self.layout.pad
            title = self.elide(self.story.title.partition(" · ")[0], self.small, l.story_title.width - p * 2)
            title_rect = l.story_title.copy()
            title_rect.width = self.small.size(title)[0] + p * 2
            self.panel(title_rect, 215, radius=l.button_height // 2, glass=True)
            self.text(title, (title_rect.x + p, title_rect.centery - self.small.get_height() // 2), self.small)
            self.button(l.toolbar_toggle, "Свернуть" if self.toolbar_open else "Меню",
                        ("toolbar",), active=self.toolbar_open, shortcut="F2")
            if self.toolbar_open:
                self.panel(l.header, 235, radius=p * 2, glass=True)
                self.text(self.elide(self.story.title.replace(" · ", " - "), self.label, l.title.width),
                          (l.title.x, l.title.centery - self.label.get_height() // 2), self.label)
                labels = ["Окно" if self.display.fullscreen else "Экран",
                          "Назад", "Журнал", "Скрыть",
                          "Звук: выкл" if self.muted else "Звук: вкл", "Истории", "Выход"]
                shortcuts = ("F11", "←", "Tab", "H", "M", None, None)
                for rect, label, action, shortcut in zip(l.toolbar, labels, ("fullscreen", "back", "history", "hide", "mute", "library", "quit"), shortcuts):
                    self.button(rect, label, (action,), action != "back" or len(self.session.frames) > 1, shortcut=shortcut)
            self.panel(l.dialogue, 225, radius=p * 2, glass=True)
            speaker = self.session.node.get("speaker", "") or "Повествование"
            self.text(self.elide(speaker, self.label, l.body.width), l.speaker, self.label, ACCENT)
            self.canvas.set_clip(l.body)
            for i, (line, span) in enumerate(zip(self.lines, self.page.lines)):
                count = max(0, self.visible - (span.start - self.page.start))
                self.text(line[:count], (l.body.x, l.body.y + i * self.line_height))
            self.canvas.set_clip(None)
            hint = "ЛКМ / пробел - показать текст"
            if self.complete:
                hint = "Выберите продолжение" if self.choosing else "ЛКМ / пробел - продолжить"
                if self.last_page and "ending" in self.session.node:
                    hint = "Конец истории - можно вернуться к выбору"
            counter = f"{self.session.current.page + 1} / {self.session.current.page + len(self.pages)}"
            counter_width = self.small.size(counter)[0]
            self.text(self.elide(hint, self.small, l.body.width - counter_width - p),
                      (l.body.x, l.footer_y), self.small, MUTED)
            self.text(counter, (l.body.right - counter_width, l.footer_y), self.small, MUTED)
            if self.choosing:
                self.draw_choices()
            if self.complete and self.last_page and "ending" in self.session.node:
                self.draw_ending()
            if self.history:
                self.draw_history()
        # Fonts, panels and hitboxes are already rendered at native window resolution.
        self.window.blit(self.canvas, (0, 0))
        pg.display.flip()

    def choice_layout(self):
        layout, y = [], 0
        for i, choice in enumerate(self.session.node["choices"]):
            lines = wrap(choice["text"], self.label, self.layout.choices.width - self.layout.pad * 4)
            height = max(self.layout.button_height, len(lines) * self.label.get_linesize() + self.layout.pad * 2)
            layout.append((i, y, height, lines))
            y += height + self.layout.gap
        return layout, max(0, y - self.layout.gap)

    def fit_choices(self):
        # Short lists stay close to the dialogue; long lists retain a scroll viewport.
        _, total = self.choice_layout()
        bounds = self.layout.choice_bounds
        height = min(bounds.height, max(1, total))
        self.layout.choices = pg.Rect(bounds.x, bounds.bottom - height, bounds.width, height)
        self.layout.choice_heading_y = self.layout.choices.top - self.layout.choice_heading_height - self.layout.gap
        self.layout.choice_header = pg.Rect(bounds.x, self.layout.choice_heading_y,
                                            bounds.width, self.layout.choice_heading_height)

    def draw_choices(self):
        self.fit_choices()
        area = self.layout.choices
        l, p = self.layout, self.layout.pad
        self.panel(l.choice_header, 245, radius=12)
        heading = f"Ваш выбор   {self.focus + 1} / {len(self.session.node['choices'])}"
        heading_y = l.choice_header.y + l.gap if l.compact else l.choice_header.centery - self.small.get_height() // 2
        self.text(heading, (area.x + p, heading_y), self.small, ACCENT)
        hint = "Колесо / ↑ ↓ - выделить, Enter / ЛКМ - выбрать"
        hint_x = area.x + p if l.compact else area.x + area.width // 2
        hint_y = heading_y + self.small.get_linesize() if l.compact else heading_y
        self.text(self.elide(hint, self.small, area.right - p - hint_x), (hint_x, hint_y), self.small, MUTED)
        layout, total = self.choice_layout()
        self.choice_scroll = max(0, min(self.choice_scroll, max(0, total - area.height)))
        self.canvas.set_clip(area)
        for i, y, height, lines in layout:
            rect = pg.Rect(area.x, area.y + y - self.choice_scroll, area.width, height)
            amount = self.feedback.value(("choice", i), i == self.focus)
            self.panel(rect, 245, mix(SURFACE, SELECTED, amount), 12)
            if i == self.focus:
                pg.draw.rect(self.canvas, ACCENT, rect, 2, border_radius=12)
            self.text(f"{i + 1:02}", (rect.x + p, rect.y + p), self.small, ACCENT)
            for j, line in enumerate(lines):
                self.text(line, (rect.x + p * 3, rect.y + p + j * self.label.get_linesize()), self.label)
            clipped = rect.clip(area)
            if clipped.height:
                self.buttons.append((clipped, ("choose", i)))
        self.canvas.set_clip(None)
        self.scrollbar(area, total, self.choice_scroll)

    def move_choice(self, delta, wrap_around=False):
        self.fit_choices()
        count = len(self.session.node["choices"])
        target = self.focus + delta
        self.focus = target % count if wrap_around else max(0, min(target, count - 1))
        layout, total = self.choice_layout()
        _, top, height, _ = layout[self.focus]
        if top < self.choice_scroll or height > self.layout.choices.height:
            self.choice_scroll = top
        elif top + height > self.choice_scroll + self.layout.choices.height:
            self.choice_scroll = top + height - self.layout.choices.height
        self.choice_scroll = max(0, min(self.choice_scroll, max(0, total - self.layout.choices.height)))

    def wheel(self, event):
        if self.hidden:
            return
        amount = getattr(event, "precise_y", event.y)
        if getattr(event, "flipped", False):
            amount = -amount
        if self.history:
            self.scroll -= amount * self.history_step
        elif self.choosing:
            if pg.key.get_mods() & pg.KMOD_SHIFT:
                # Free scrolling also allows reading a single extra-tall option.
                self.choice_scroll -= amount * self.label.get_linesize() * 2
                self.wheel_remainder = 0.0
                return
            if amount * self.wheel_remainder < 0:
                self.wheel_remainder = 0.0
            self.wheel_remainder += amount
            steps = math.trunc(self.wheel_remainder)
            self.wheel_remainder -= steps
            if steps:
                self.move_choice(-steps)
        elif amount > 0:
            self.back()

    def draw_ending(self):
        ending = self.session.node["ending"]
        l, p = self.layout, self.layout.pad
        rect = l.ending
        self.panel(rect, 240, radius=p * 2, glass=True)
        self.text(ENDING_LABEL[ending["type"]], (rect.x + p, rect.y + p), self.label, ENDING[ending["type"]])
        button_y = rect.bottom - p - l.button_height
        width = (rect.width - p * 3) // 2
        self.button((rect.x + p, button_y, width, l.button_height), "Начать заново", ("restart",))
        self.button((rect.x + p * 2 + width, button_y, width, l.button_height), "Вернуться к выбору", ("choice_back",),
                    any("choices" in self.story.nodes[f.node] for f in self.session.frames[:-1]))
        title_area = pg.Rect(rect.x + p, rect.y + p * 2 + self.label.get_linesize(),
                             rect.width - 2 * p, max(1, button_y - rect.y - p * 3 - self.label.get_linesize()))
        size = round(l.body_size * 1.35)
        while True:
            font = pg.font.Font(self.font_path, size)
            lines = wrap(ending["title"], font, title_area.width)
            if len(lines) * font.get_linesize() <= title_area.height or size <= 8:
                break
            size -= 1
        self.canvas.set_clip(title_area)
        for i, line in enumerate(lines):
            self.text(line, (title_area.x, title_area.y + i * font.get_linesize()), font)
        self.canvas.set_clip(None)

    def draw_history(self):
        self.buttons = []  # Modal: never dispatch a click to the scene underneath.
        l, p = self.layout, self.layout.pad
        rect, area = l.history, l.history_area
        self.panel(self.canvas.get_rect(), 210, (4, 8, 15), 0)
        self.panel(rect, 250, radius=p * 2)
        title_width = l.history_close.x - rect.x - p * 2
        self.text(self.elide("История прохождения", self.font, title_width), (rect.x + p, rect.y + p), self.font)
        self.text(self.elide("Нажмите запись для возврата. Следующие шаги будут отменены.", self.small, area.width),
                  (area.x, area.y - p - self.small.get_linesize()), self.small, MUTED)
        self.button(l.history_close, "Закрыть", ("history",), shortcut="Tab")
        self.scroll = max(0, min(self.scroll, max(0, len(self.session.frames) * self.history_step - area.height)))
        self.canvas.set_clip(area)
        for index, frame in enumerate(self.session.frames):
            row = pg.Rect(area.x, area.y + index * self.history_step - self.scroll, area.width, self.history_step - l.gap)
            if not row.colliderect(area):
                continue
            current = index == len(self.session.frames) - 1
            amount = self.feedback.value(("history", index), current or row.collidepoint(self.mouse()))
            self.panel(row, 255, mix(RAISED, SELECTED, amount), p)
            node = self.story.nodes[frame.node]
            head = f"{index + 1:02} - {node.get('speaker') or 'Повествование'}, страница {frame.page + 1}"
            if frame.choice:
                head = f"{index + 1:02} - Выбор: {frame.choice}"
            self.text(self.elide(head, self.small, row.width - p * 2), (row.x + p, row.y + p), self.small, ACCENT)
            self.text(self.elide(node["text"][frame.offset:], self.small, row.width - p * 2),
                      (row.x + p, row.y + p + self.small.get_linesize()), self.small, INK)
            self.buttons.append((row.clip(area), ("rewind", index)))
        self.canvas.set_clip(None)
        self.scrollbar(area, len(self.session.frames) * self.history_step, self.scroll)

    def dispatch(self, action):
        kind = action[0]
        if kind == "toolbar":
            self.toolbar_open = not self.toolbar_open
            self.ensure_layout()
        elif kind == "quit":
            self.stop_sound()
            self.running = False
        elif kind == "library":
            self.show_library()
        elif kind in ("open_story", "resume", "refresh"):
            self.library_action(action)
        elif kind == "back":
            self.back()
        elif kind == "history":
            self.history = not self.history
            self.scroll = len(self.session.frames) * self.history_step
        elif kind == "hide":
            self.hidden = not self.hidden
        elif kind == "mute":
            self.stop_sound()
            self.muted = not self.muted
        elif kind == "fullscreen":
            self.window = self.display.toggle()
            self.ensure_layout()
        elif kind == "motion":
            self.feedback.reduced = not self.feedback.reduced
            self.feedback.step(0)
        elif kind == "transparency":
            self.solid_ui = not self.solid_ui
        elif kind == "choose":
            self.session.advance(action[1])
            self.load_frame()
        elif kind == "rewind":
            self.session.rewind(action[1])
            self.history = False
            self.load_frame(revealed=True)
        elif kind == "restart":
            self.session.restart()
            self.load_frame()
        elif kind == "choice_back":
            for i in range(len(self.session.frames) - 2, -1, -1):
                if "choices" in self.story.nodes[self.session.frames[i].node]:
                    self.session.rewind(i)
                    self.load_frame(revealed=True)
                    break

    def event(self, event):
        if self.ensure_layout():
            self.render()  # Rebuild hitboxes before processing a click after resize.
        if event.type == pg.QUIT:
            self.running = False
        elif event.type == pg.KEYDOWN and event.key in (pg.K_F6, pg.K_F7):
            self.dispatch(("motion" if event.key == pg.K_F6 else "transparency",))
        elif event.type == pg.KEYDOWN and (event.key == pg.K_F11 or (event.key == pg.K_RETURN and getattr(event, "mod", 0) & pg.KMOD_ALT)):
            self.dispatch(("fullscreen",))
        elif self.in_menu:
            self.library_event(event)
        elif event.type == pg.KEYDOWN:
            key = event.key
            if key == pg.K_F11 or (key == pg.K_RETURN and getattr(event, "mod", 0) & pg.KMOD_ALT):
                self.dispatch(("fullscreen",))
            elif key == pg.K_ESCAPE:
                if self.history:
                    self.history = False
                elif self.display.fullscreen:
                    self.dispatch(("fullscreen",))
                else:
                    self.hidden = not self.hidden
            elif self.hidden:
                if key in (pg.K_h, pg.K_SPACE):
                    self.hidden = False
            elif self.history:
                if key == pg.K_TAB:
                    self.history = False
                elif key in (pg.K_UP, pg.K_DOWN):
                    self.scroll += -self.history_step if key == pg.K_UP else self.history_step
            elif key == pg.K_F2:
                self.dispatch(("toolbar",))
            elif key == pg.K_h:
                self.hidden = True
            elif key == pg.K_TAB:
                self.dispatch(("history",))
            elif key == pg.K_m:
                self.dispatch(("mute",))
            elif key in (pg.K_LEFT, pg.K_BACKSPACE):
                self.back()
            elif self.choosing and key in (pg.K_UP, pg.K_DOWN):
                self.wheel_remainder = 0.0
                self.move_choice(-1 if key == pg.K_UP else 1, wrap_around=True)
            elif self.choosing and key == pg.K_RETURN:
                self.dispatch(("choose", self.focus))
            elif key == pg.K_SPACE:
                self.advance()
        elif event.type == pg.MOUSEWHEEL:
            self.wheel(event)
        elif event.type == pg.MOUSEMOTION and not self.hidden and not self.history and self.choosing:
            # Stationary mouse hover must not override selection by wheel/keyboard.
            if getattr(event, "rel", (0, 0)) != (0, 0):
                pos = self.mouse(event.pos)
                for rect, action in self.buttons:
                    if action[0] == "choose" and rect.collidepoint(pos):
                        self.focus = action[1]
                        self.wheel_remainder = 0.0
                        break
        elif event.type == pg.MOUSEBUTTONDOWN:
            if event.button == 3:
                if not self.history:
                    self.hidden = not self.hidden
            elif event.button == 1:
                if self.hidden:
                    self.hidden = False
                    return
                pos = self.mouse(event.pos)
                if not self.viewport.collidepoint(event.pos):
                    return
                for rect, action in reversed(self.buttons):
                    if rect.collidepoint(pos):
                        self.dispatch(action)
                        return
                if self.toolbar_open and self.layout.header.collidepoint(pos):
                    return
                if not self.history:
                    if self.choosing:
                        self.dispatch(("choose", self.focus))
                    else:
                        self.advance()

    def run(self):
        clock = pg.time.Clock()
        self.render()
        try:
            while self.running:
                dt = clock.tick(60) / 1000
                for event in pg.event.get():
                    self.event(event)
                    # Refresh hitboxes between queued inputs after transitions.
                    self.render()
                self.update(dt)
                self.render()
        finally:
            pg.quit()
