import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
from vn.story import Story, StoryError, Session
from fixtures import make_story

ROOT = Path(__file__).resolve().parents[1]


class StoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.story = make_story(directory.name)
        self.session = Session(self.story)

    def test_converging_choices_keep_actual_path(self):
        s = self.session
        s.advance()
        s.advance(0)
        self.assertEqual(s.current.node, "harbor")
        original = s.current.choice
        s.back()
        s.advance(2)
        self.assertEqual(s.current.node, "harbor")
        self.assertNotEqual(s.current.choice, original)
        self.assertEqual(len(s.frames), 3)

    def test_all_endings_and_rechoose(self):
        s = self.session
        s.advance()
        s.advance(1)
        s.advance()
        for index, expected in enumerate(("good", "neutral", "bad")):
            s.advance(index)
            self.assertEqual(s.node["ending"]["type"], expected)
            self.assertFalse(s.advance())
            s.back()
            self.assertEqual(s.current.node, "lantern")

    def test_pages_rewind_restart_and_cycles(self):
        s = self.session
        s.next_page()
        s.advance()
        s.back()
        self.assertEqual(s.current.page, 1)
        s.rewind(0)
        self.assertEqual(len(s.frames), 1)
        self.assertFalse(s.back())
        self.story.nodes["arrival"]["next"] = "arrival"
        s.advance()
        s.advance()
        self.assertEqual(len(s.frames), 3)
        s.restart()
        self.assertEqual(len(s.frames), 1)

    def test_rejects_bad_content(self):
        mutations = [
            lambda d: d.update(start="missing"),
            lambda d: d["nodes"]["arrival"].update(next="missing"),
            lambda d: d["nodes"]["arrival"].update(choices=[]),
            lambda d: d["nodes"]["letter"]["choices"][0].update(target="missing"),
            lambda d: d["nodes"]["home"]["ending"].update(type="unknown"),
            lambda d: d["settings"].update(text_speed=0),
            lambda d: d["nodes"]["arrival"].update(art="absent.png"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story.json"
            for mutate in mutations:
                d = copy.deepcopy(self.story.data)
                for node in d["nodes"].values():
                    node["art"] = str(self.story.asset(node["art"]))
                mutate(d)
                path.write_text(json.dumps(d), encoding="utf-8")
                with self.assertRaises(StoryError):
                    Story(path)


class UITests(unittest.TestCase):
    def setUp(self):
        import pygame as pg
        from vn.app import App
        self.pg = pg
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = App(make_story(directory.name))
        self.app.render()

    def tearDown(self):
        self.pg.quit()

    def key(self, key):
        self.app.event(self.pg.event.Event(self.pg.KEYDOWN, key=key))
        self.app.render()

    def wheel(self, amount, **extra):
        self.app.event(self.pg.event.Event(self.pg.MOUSEWHEEL, y=amount, x=0, **extra))
        self.app.render()

    def show_choices(self, count=None):
        self.app.session.advance()
        if count:
            self.app.session.node["choices"] = [
                {"text": f"Вариант {i + 1}", "target": "path" if i == count - 1 else "harbor"}
                for i in range(count)
            ]
        self.app.load_frame(revealed=True)
        self.finish_node()
        self.app.render()

    def finish_node(self):
        while not self.app.last_page:
            self.app.visible = len(self.app.page_text)
            self.app.advance()
        self.app.visible = len(self.app.page_text)

    def test_wheel_selects_even_when_all_choices_fit(self):
        self.show_choices()
        self.wheel(-1)
        self.assertEqual(self.app.focus, 1)
        self.assertEqual(self.app.choice_scroll, 0)
        self.assertEqual(self.app.session.current.node, "letter")
        self.key(self.pg.K_RETURN)
        self.assertEqual(self.app.session.current.node, "path")

    def test_wheel_scrolls_and_scaled_click_selects_last_option(self):
        self.show_choices(15)
        app, pg = self.app, self.pg
        for size in ((800, 600), (1920, 1080), (2560, 1080), (720, 1280)):
            app.window = pg.display.set_mode(size, pg.RESIZABLE)
            app.render()
            self.finish_node()
            app.render()
            self.wheel(-100)
            self.assertEqual(app.focus, 14)
            self.assertGreater(app.choice_scroll, 0)
            rect = next(rect for rect, action in app.buttons if action == ("choose", 14))
            self.assertEqual(rect.height, app.choice_layout()[0][-1][2])
            # Verify actual inverse mapping through the input dispatcher.
            point = rect.center
            app.event(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=point))
            self.assertEqual(app.session.current.node, "path")
            app.back()
            app.render()

    def test_precise_wheel_direction_and_no_double_legacy_events(self):
        self.show_choices()
        for _ in range(3):
            self.wheel(0, precise_y=-0.25)
        self.assertEqual(self.app.focus, 0)
        self.wheel(0, precise_y=-0.25)
        self.assertEqual(self.app.focus, 1)
        # SDL can emit legacy wheel buttons alongside MOUSEWHEEL: don't count twice.
        self.app.event(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=5, pos=(300, 200)))
        self.assertEqual(self.app.focus, 1)
        self.wheel(-1, flipped=True)
        self.assertEqual(self.app.focus, 0)
        self.wheel(10)
        self.assertEqual(self.app.focus, 0)
        self.key(self.pg.K_RETURN)
        self.assertEqual(self.app.session.current.node, "harbor")

    def test_wheel_respects_hidden_ui_and_history_modal(self):
        self.show_choices()
        self.key(self.pg.K_h)
        self.wheel(-1)
        self.assertEqual(self.app.focus, 0)
        self.key(self.pg.K_h)
        self.key(self.pg.K_TAB)
        self.wheel(-1)
        self.assertEqual(self.app.focus, 0)
        self.assertEqual(self.app.session.current.node, "letter")

    def test_shift_wheel_can_read_an_extra_tall_option(self):
        self.show_choices()
        self.app.session.node["choices"][0]["text"] = "Очень длинный вариант. " * 200
        self.app.render()
        self.pg.key.set_mods(self.pg.KMOD_SHIFT)
        try:
            self.wheel(-4)
        finally:
            self.pg.key.set_mods(0)
        self.assertGreater(self.app.choice_scroll, 0)
        self.assertEqual(self.app.focus, 0)

    def test_fullscreen_roundtrip_preserves_story_and_window(self):
        from unittest.mock import patch
        app, pg = self.app, self.pg
        initial_size = app.window.get_size()
        app.visible = 7
        before = app.session.frames.copy()
        self.key(pg.K_F11)
        self.assertTrue(app.display.fullscreen)
        self.assertEqual(app.window.get_size(), pg.display.get_desktop_sizes()[0])
        self.assertEqual(app.session.frames, before)
        self.assertEqual(app.visible, 7)
        with patch.object(pg.display, "set_mode", wraps=pg.display.set_mode) as set_mode:
            self.key(pg.K_ESCAPE)
            set_mode.assert_called_once_with(initial_size, pg.RESIZABLE)
        self.assertFalse(app.display.fullscreen)
        self.assertFalse(app.hidden)
        # SDL dummy retains the desktop-sized surface after leaving fullscreen;
        # the requested restoration is asserted above, real Windows checked separately.
        if pg.display.get_driver() != "dummy":
            self.assertEqual(app.window.get_size(), initial_size)
        app.event(pg.event.Event(pg.KEYDOWN, key=pg.K_RETURN, mod=pg.KMOD_ALT))
        self.assertTrue(app.display.fullscreen)
        self.assertEqual(app.session.frames, before)
        self.key(pg.K_F11)

    def test_fullscreen_shortcut_works_when_ui_hidden_or_modal(self):
        self.key(self.pg.K_h)
        self.key(self.pg.K_F11)
        self.assertTrue(self.app.hidden)
        self.assertTrue(self.app.display.fullscreen)
        self.key(self.pg.K_F11)
        self.key(self.pg.K_h)
        self.key(self.pg.K_TAB)
        self.key(self.pg.K_F11)
        self.assertTrue(self.app.history)
        self.key(self.pg.K_ESCAPE)
        self.assertFalse(self.app.history)
        self.assertTrue(self.app.display.fullscreen)
        self.key(self.pg.K_ESCAPE)
        self.assertFalse(self.app.display.fullscreen)

    def test_typewriter_skip_hide_and_modal(self):
        app, pg = self.app, self.pg
        app.update(0.1)
        self.assertGreater(app.visible, 0)
        count = app.visible
        self.key(pg.K_h)
        app.update(0.1)
        self.assertEqual(app.visible, count)
        self.assertFalse(app.buttons)
        self.key(pg.K_SPACE)
        self.assertFalse(app.hidden)
        self.assertEqual(app.visible, count)
        self.key(pg.K_SPACE)
        self.assertTrue(app.complete)
        self.key(pg.K_TAB)
        self.key(pg.K_SPACE)
        self.assertEqual(app.session.current.node, "arrival")
        self.key(pg.K_TAB)
        self.key(pg.K_SPACE)
        self.assertEqual(app.session.current.node, "letter")

    def test_choice_keyboard_endings_and_rollback(self):
        app, pg = self.app, self.pg
        for _ in range(2):
            self.key(pg.K_SPACE)
        self.key(pg.K_SPACE)
        self.assertTrue(app.choosing)
        self.key(pg.K_DOWN)
        self.key(pg.K_RETURN)
        self.assertEqual(app.session.current.node, "path")
        for _ in range(3):
            self.key(pg.K_SPACE)
        self.assertTrue(app.choosing)
        self.key(pg.K_RETURN)
        self.key(pg.K_SPACE)
        self.assertEqual(app.session.node["ending"]["type"], "good")
        app.render()
        app.dispatch(("choice_back",))
        self.assertTrue(app.choosing)
        self.assertEqual(app.session.current.node, "lantern")

    def test_long_text_choices_and_window_scaling(self):
        from vn.app import wrap
        app, pg = self.app, self.pg
        app.session.node["text"] = ("Оченьдлинноеслово" * 40 + "\n") * 4
        app.load_frame()
        self.assertGreater(len(app.pages), 1)
        self.assertTrue(all(app.font.size(app.session.node["text"][line.start:line.end])[0] <= app.layout.body.width for page in app.pages for line in page.lines))
        self.key(pg.K_SPACE)
        self.key(pg.K_SPACE)
        self.assertEqual(app.session.current.page, 1)
        self.key(pg.K_LEFT)
        self.assertEqual(app.session.current.page, 0)
        self.assertTrue(app.complete)
        app.session.advance()
        app.session.node["choices"] = [{"text": "Выбор " * 100, "target": "home"} for _ in range(12)]
        app.load_frame(revealed=True)
        app.window = pg.display.set_mode((800, 600), pg.RESIZABLE)
        app.render()
        self.assertEqual(app.canvas.get_size(), (800, 600))
        self.finish_node()
        self.key(pg.K_UP)
        self.assertEqual(app.focus, 11)
        self.key(pg.K_RETURN)
        self.assertEqual(app.session.current.node, "home")

    def test_each_printed_glyph_triggers_sound(self):
        from unittest.mock import Mock
        app = self.app
        app.page_text = "А б!"
        app.visible = 0
        app.sound = Mock()
        for _ in range(10):
            app.update(0.1)
        self.assertEqual(app.sound.play.call_count, 3)

    def test_native_layout_and_hitboxes_at_different_aspect_ratios(self):
        app, pg = self.app, self.pg
        font_sizes = {}
        for size in ((640, 480), (1280, 720), (1920, 1080), (2560, 1440), (3440, 1440), (1080, 1920)):
            app.window = pg.display.set_mode(size, pg.RESIZABLE)
            app.render()
            self.assertEqual(app.canvas.get_size(), size)
            self.assertEqual(app.background.get_size(), size)
            self.assertEqual(app.viewport, pg.Rect((0, 0), size))
            font_sizes[size] = app.font.get_height()
            self.assertLessEqual(len(app.lines) * app.line_height, app.layout.body.height)
            for rect, _ in app.buttons:
                self.assertTrue(app.viewport.contains(rect))
            journal = next(rect for rect, action in app.buttons if action == ("history",))
            app.event(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=journal.center))
            app.render()
            self.assertTrue(app.history)
            close = next(rect for rect, action in app.buttons if action == ("history",))
            app.event(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=close.center))
            app.render()
            self.assertFalse(app.history)
        self.assertGreater(font_sizes[(2560, 1440)], font_sizes[(1280, 720)])
        self.assertTrue(app.layout.compact)
        self.assertEqual(app.layout.columns, 3)

    def test_resize_preserves_text_anchors_and_no_content_is_skipped(self):
        app, pg = self.app, self.pg
        source = ("Первая строка с пробелами.  \n" + "Длинноеслово" * 40 + "\n\n") * 5
        app.session.node["text"] = source
        app.load_frame()
        app.visible = 7
        app.window = pg.display.set_mode((1080, 1920), pg.RESIZABLE)
        app.render()
        self.assertEqual(app.visible, 7)
        self.assertEqual(app.page.start, 0)
        app.visible = len(app.page_text)
        end = app.page.end
        app.advance()
        self.assertEqual(app.session.current.offset, end)
        self.assertEqual(app.page.start, end)
        frames = app.session.frames.copy()
        app.window = pg.display.set_mode((2560, 1440), pg.RESIZABLE)
        app.render()
        self.assertEqual(app.session.frames, frames)
        self.assertEqual(app.page.start, end)
        self.assertEqual("".join(source[page.start:page.end] for page in app.pages), source[end:])
        app.back()
        self.assertEqual(app.page.start, 0)
        # Walk all pages using the current layout and reconstruct the exact source.
        pieces = []
        while True:
            pieces.append(app.page_text)
            if app.last_page:
                break
            app.visible = len(app.page_text)
            app.advance()
        self.assertEqual("".join(pieces), source)


class DisplayTests(unittest.TestCase):
    def test_sizes_fit_small_large_wide_and_portrait_displays(self):
        from vn.display import fit_size
        from vn.layout import Layout
        for size in ((640, 480), (1366, 768), (1920, 1080), (3840, 2160), (3440, 1440), (1080, 1920)):
            initial = fit_size(size, fraction=0.9)
            self.assertLess(initial[0], size[0])
            self.assertLess(initial[1], size[1])
            layout = Layout(size)
            import pygame as pg
            bounds = pg.Rect((0, 0), size)
            for rect in (layout.header, layout.dialogue, layout.body, layout.choices,
                         layout.ending, layout.history, layout.history_area, *layout.toolbar):
                self.assertTrue(bounds.contains(rect), (size, rect))
                self.assertGreater(rect.width, 0)
                self.assertGreater(rect.height, 0)
            self.assertLessEqual(layout.header.bottom, layout.choices.top)
            self.assertLess(layout.choices.bottom, layout.dialogue.top)



if __name__ == "__main__":
    unittest.main()
