"""Regressions for appearance preferences and responsive library composition."""
import os
from pathlib import Path
import tempfile
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame as pg
from vn.app import App
from vn.ui import Feedback
from fixtures import make_story


class FeedbackTests(unittest.TestCase):
    def test_reversal_keeps_current_value_and_settles_without_overshoot(self):
        feedback = Feedback()
        feedback.value("hover", False)
        feedback.value("hover", True)
        for _ in range(5):
            feedback.step(1 / 60)
        current = feedback.value("hover", True)
        self.assertGreater(current, 0)
        self.assertLess(current, 1)
        self.assertEqual(feedback.value("hover", False), current)
        for _ in range(60):
            feedback.step(1 / 60)
            self.assertGreaterEqual(feedback.value("hover", False), 0)
            self.assertLessEqual(feedback.value("hover", False), 1)
        self.assertAlmostEqual(feedback.value("hover", False), 0, places=6)

    def test_reduced_motion_snaps_an_inflight_transition(self):
        feedback = Feedback()
        feedback.value("focus", False)
        feedback.value("focus", True)
        feedback.step(.03)
        feedback.reduced = True
        feedback.step(0)
        self.assertEqual(feedback.value("focus", True), 1)
        self.assertEqual(feedback.value("focus", False), 0)


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(pg.quit)
        self.root = Path(self.directory.name)
        self.story = make_story(self.root / "story")

    def test_preferences_preserve_reading_modal_and_choice_input(self):
        app = App(self.story, stories_dir=self.root)
        app.visible = 7
        frames = app.session.frames.copy()
        for hidden, history in ((False, False), (True, False), (False, True)):
            app.hidden, app.history = hidden, history
            for key in (pg.K_F6, pg.K_F7):
                app.event(pg.event.Event(pg.KEYDOWN, key=key))
                app.render()
                self.assertEqual(app.session.frames, frames)
                self.assertEqual(app.visible, 7)
                self.assertEqual((app.hidden, app.history), (hidden, history))
        app.hidden = app.history = False
        app.session.advance()
        app.load_frame(revealed=True)
        app.move_choice(1)
        app.render()
        app.event(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(1, app.viewport.centery)))
        self.assertEqual(app.session.current.node, "path")

    def test_library_sections_and_controls_fit_wide_small_and_portrait(self):
        app = App(stories_dir=self.root)
        for size in ((640, 480), (1000, 480), (1280, 720), (1920, 1080), (1080, 1920)):
            app.window = pg.display.set_mode(size, pg.RESIZABLE)
            app.render()
            area, _, _ = app.menu_geometry()
            self.assertTrue(app.viewport.contains(area), size)
            if app.menu_hero:
                self.assertTrue(app.viewport.contains(app.menu_hero), size)
                self.assertFalse(app.menu_hero.colliderect(area), size)
            for action in ("motion", "transparency"):
                rect = next(rect for rect, value in app.buttons if value == (action,))
                self.assertTrue(app.viewport.contains(rect), size)
                app.event(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=rect.center))
                self.assertTrue(app.in_menu)
                self.assertIsNone(app.session)

    def test_solid_material_is_independent_of_background(self):
        app = App(self.story, stories_dir=self.root)
        app.solid_ui = True
        rect = pg.Rect(20, 20, 200, 100)
        colors = []
        for background in ((255, 255, 255), (0, 0, 0)):
            app.canvas.fill(background)
            app.panel(rect, glass=True)
            colors.append(app.canvas.get_at(rect.center))
        self.assertEqual(colors[0], colors[1])


if __name__ == "__main__":
    unittest.main()
