"""Pygame presentation. All story-specific content lives in the story package."""
from pathlib import Path
from functools import lru_cache
import math
import re
import warnings
import pygame as pg
from .story import Session, StoryError
from .display import Display
from .layout import Layout
from .text import paginate
from .catalog import STORIES
from .library import Library

INK = (237, 238, 244)
MUTED = (161, 174, 195)
ACCENT = (137, 220, 206)
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
        self.running = True
        self.buttons = []
        self.font_path = pg.font.match_font("segoeui,dejavusans,arial")
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
        pg.display.set_caption(story.title)
        settings = story.data.get("settings", {})
        self.font_path = str(story.asset(settings["font"])) if "font" in settings else pg.font.match_font("segoeui,dejavusans,arial")
        self.speed = settings.get("text_speed", 36)
        self.sound = None
        if pg.mixer.get_init():
            try:
                path = story.asset(settings["typing_sound"]) if "typing_sound" in settings else Path(__file__).parent / "assets/typing.wav"
                self.sound = pg.mixer.Sound(str(path))
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
        self.layout = Layout(self.window.get_size())
        self.canvas = pg.Surface(self.window.get_size())
        self.viewport = self.canvas.get_rect()
        self.font = pg.font.Font(self.font_path, self.layout.body_size)
        self.small = pg.font.Font(self.font_path, self.layout.small_size)
        self.label = pg.font.Font(self.font_path, self.layout.label_size)
        self.line_height = self.font.get_linesize()
        self.history_step = self.small.get_linesize() * 2 + self.layout.pad * 2 + self.layout.gap

    def fit_background(self):
        source = self.art(self.session.node["art"])
        w, h = self.canvas.get_size()
        sw, sh = source.get_size()
        ratio = max(w / sw, h / sh)
        scaled = pg.transform.smoothscale(source, (math.ceil(sw * ratio), math.ceil(sh * ratio)))
        self.background = scaled.subsurface(((scaled.get_width() - w) // 2, (scaled.get_height() - h) // 2, w, h)).copy()

    def reflow_text(self):
        text = self.session.node["text"]
        self.pages = paginate(text, self.font, self.layout.body.width,
                              self.layout.body.height // self.line_height, self.session.current.offset)
        self.page = self.pages[0]
        self.lines = [text[line.start:line.end] for line in self.page.lines]
        self.page_text = text[self.page.start:self.page.end]

    def ensure_layout(self):
        if self.canvas.get_size() == self.window.get_size():
            return False
        visible = getattr(self, "visible", 0)
        self.configure_layout()
        if self.story is None:
            return True
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
                self.sound.stop()  # Keep fast typing from stacking loud clicks.
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

    def panel(self, rect, alpha=220, color=(14, 21, 34), radius=20):
        rect = pg.Rect(rect)
        layer = pg.Surface(rect.size, pg.SRCALPHA)
        pg.draw.rect(layer, (*color, alpha), layer.get_rect(), border_radius=radius)
        pg.draw.rect(layer, (190, 214, 240, 36), layer.get_rect(), 1, border_radius=radius)
        self.canvas.blit(layer, rect)

    def button(self, rect, label, action, enabled=True, active=False):
        rect = pg.Rect(rect)
        hover = rect.collidepoint(self.mouse()) and enabled
        self.panel(rect, 245 if hover else 210, (38, 66, 75) if hover or active else (20, 30, 46), 10)
        text = self.small.render(self.elide(label, self.small, rect.width - self.layout.gap), True, ACCENT if enabled else (91, 104, 122))
        self.canvas.blit(text, text.get_rect(center=rect.center))
        if enabled:
            self.buttons.append((rect, action))

    def mouse(self, pos=None):
        return pos if pos is not None else pg.mouse.get_pos()

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
            self.panel(l.header, 185, radius=p)
            self.text(self.elide(self.story.title, self.label, l.title.width), l.title.topleft, self.label)
            labels = ["Окно · F11" if self.display.fullscreen else "Экран · F11",
                      "Назад · ←", "Журнал · Tab", "Скрыть · H",
                      "Звук: выкл · M" if self.muted else "Звук: вкл · M", "Истории", "Выход"]
            for rect, label, action in zip(l.toolbar, labels, ("fullscreen", "back", "history", "hide", "mute", "library", "quit")):
                self.button(rect, label, (action,), action != "back" or len(self.session.frames) > 1)
            self.panel(l.dialogue, 218, radius=p)
            speaker = self.session.node.get("speaker", "") or "Повествование"
            self.text(self.elide(speaker, self.label, l.body.width), l.speaker, self.label, ACCENT)
            self.canvas.set_clip(l.body)
            for i, (line, span) in enumerate(zip(self.lines, self.page.lines)):
                count = max(0, self.visible - (span.start - self.page.start))
                self.text(line[:count], (l.body.x, l.body.y + i * self.line_height))
            self.canvas.set_clip(None)
            hint = "ЛКМ / пробел — показать текст"
            if self.complete:
                hint = "Выберите продолжение" if self.choosing else "ЛКМ / пробел — продолжить"
                if self.last_page and "ending" in self.session.node:
                    hint = "Конец истории · можно вернуться к выбору"
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
        return layout, y

    def draw_choices(self):
        area = self.layout.choices
        l, p = self.layout, self.layout.pad
        heading = f"ВАШ ВЫБОР · {self.focus + 1} / {len(self.session.node['choices'])}"
        self.text(heading, (area.x, l.choice_heading_y), self.small, ACCENT)
        hint = "Колесо / ↑ ↓ — выделить · Enter / ЛКМ — выбрать"
        hint_x = area.x if l.compact else area.x + area.width // 2
        hint_y = l.choice_heading_y + self.small.get_linesize() if l.compact else l.choice_heading_y
        self.text(self.elide(hint, self.small, area.right - hint_x), (hint_x, hint_y), self.small, MUTED)
        layout, total = self.choice_layout()
        self.choice_scroll = max(0, min(self.choice_scroll, max(0, total - area.height)))
        self.canvas.set_clip(area)
        for i, y, height, lines in layout:
            rect = pg.Rect(area.x, area.y + y - self.choice_scroll, area.width, height)
            self.panel(rect, 239, (31, 57, 65) if i == self.focus else (18, 28, 44), 12)
            if i == self.focus:
                pg.draw.rect(self.canvas, ACCENT, rect, 2, border_radius=12)
            self.text(f"{i + 1:02}", (rect.x + p, rect.y + p), self.small, ACCENT)
            for j, line in enumerate(lines):
                self.text(line, (rect.x + p * 3, rect.y + p + j * self.label.get_linesize()), self.label)
            clipped = rect.clip(area)
            if clipped.height:
                self.buttons.append((clipped, ("choose", i)))
        self.canvas.set_clip(None)
        if total > area.height:
            track = pg.Rect(area.right + self.layout.gap, area.y, max(3, p // 4), area.height)
            pg.draw.rect(self.canvas, (45, 61, 77), track, border_radius=2)
            thumb_height = max(18, round(area.height * area.height / total))
            thumb_y = area.y + round((area.height - thumb_height) * self.choice_scroll / (total - area.height))
            pg.draw.rect(self.canvas, ACCENT, (track.x, thumb_y, track.width, thumb_height), border_radius=2)

    def move_choice(self, delta, wrap_around=False):
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
        self.panel(rect, 236, radius=p)
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
        self.panel(rect, 250, radius=p)
        title_width = l.history_close.x - rect.x - p * 2
        self.text(self.elide("История прохождения", self.font, title_width), (rect.x + p, rect.y + p), self.font)
        self.text(self.elide("Нажмите запись для возврата. Следующие шаги будут отменены.", self.small, area.width),
                  (area.x, area.y - p - self.small.get_linesize()), self.small, MUTED)
        self.button(l.history_close, "Закрыть · Tab", ("history",))
        self.scroll = max(0, min(self.scroll, max(0, len(self.session.frames) * self.history_step - area.height)))
        self.canvas.set_clip(area)
        for index, frame in enumerate(self.session.frames):
            row = pg.Rect(area.x, area.y + index * self.history_step - self.scroll, area.width, self.history_step - l.gap)
            if not row.colliderect(area):
                continue
            self.panel(row, 255, (26, 44, 58), p // 2)
            node = self.story.nodes[frame.node]
            head = f"{index + 1:02} · {node.get('speaker') or 'Повествование'} · стр. {frame.page + 1}"
            if frame.choice:
                head = f"{index + 1:02} · Выбор: {frame.choice}"
            self.text(self.elide(head, self.small, row.width - p * 2), (row.x + p, row.y + p), self.small, ACCENT)
            self.text(self.elide(node["text"][frame.offset:], self.small, row.width - p * 2),
                      (row.x + p, row.y + p + self.small.get_linesize()), self.small, INK)
            self.buttons.append((row.clip(area), ("rewind", index)))
        self.canvas.set_clip(None)

    def dispatch(self, action):
        kind = action[0]
        if kind == "quit":
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
