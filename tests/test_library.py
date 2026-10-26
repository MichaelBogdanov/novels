import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame as pg
from vn.app import App
from vn.catalog import discover_stories
from fixtures import make_story


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(pg.quit)
        self.root = Path(self.directory.name)

    def click(self, app, action):
        app.render()
        rect = next(rect for rect, value in app.buttons if value == action)
        app.event(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=rect.center))

    def test_empty_library_resize_fullscreen_and_exit(self):
        app = App(stories_dir=self.root)
        self.assertIsNone(app.session)
        for size in ((640, 480), (1280, 720), (1080, 1920)):
            app.window = pg.display.set_mode(size, pg.RESIZABLE)
            app.render()
            app.update(0.1)
            self.assertTrue(all(app.viewport.contains(rect) for rect, _ in app.buttons))
            self.assertNotIn(("resume",), [action for _, action in app.buttons])
        app.dispatch(("fullscreen",))
        app.render()
        app.dispatch(("fullscreen",))
        self.click(app, ("quit",))
        self.assertFalse(app.running)

    def test_discovery_skips_demo_and_reports_broken_package(self):
        make_story(self.root / "ready")
        make_story(self.root / "demo")
        (self.root / "bad").mkdir()
        (self.root / "bad/story.json").write_text("{}", encoding="utf-8")
        stories, errors = discover_stories(self.root)
        self.assertEqual(len(stories), 1)
        self.assertEqual(len(errors), 1)
        app = App(stories_dir=self.root)
        app.render()
        self.assertTrue(app.menu_error)

    def test_scroll_open_resume_switch_and_quit(self):
        for i in range(12):
            make_story(self.root / str(i))
        app = App(stories_dir=self.root)
        app.window = pg.display.set_mode((640, 480), pg.RESIZABLE)
        app.event(pg.event.Event(pg.MOUSEWHEEL, x=0, y=-100))
        app.render()
        self.assertEqual(app.menu_focus, 11)
        self.assertGreater(app.menu_offset, 0)
        self.click(app, ("open_story", 11))
        self.assertFalse(app.in_menu)
        app.visible = 7
        session = app.session
        self.click(app, ("toolbar",))
        self.click(app, ("library",))
        app.update(0.1)
        self.assertEqual(app.visible, 7)
        self.click(app, ("resume",))
        self.assertIs(app.session, session)
        self.assertEqual(app.visible, 7)
        self.click(app, ("library",))
        app.menu_focus = 0
        app.event(pg.event.Event(pg.KEYDOWN, key=pg.K_RETURN))
        self.assertIsNot(app.session, session)
        self.assertEqual(app.visible, 0)
        self.click(app, ("quit",))
        self.assertFalse(app.running)

    def test_unreadable_art_does_not_replace_session(self):
        good = make_story(self.root / "good")
        app = App(good, stories_dir=self.root)
        session = app.session
        app.show_library()
        (self.root / "good/pixel.png").write_bytes(b"broken")
        self.click(app, ("open_story", 0))
        self.assertTrue(app.in_menu)
        self.assertIs(app.session, session)
        self.assertTrue(app.menu_error)

    def test_bundled_sound_mute_and_no_audio_device(self):
        story = make_story(self.root / "ready")
        app = App(story, stories_dir=self.root)
        self.assertIsNotNone(app.sound)
        self.assertGreater(app.sound.get_length(), 0)
        self.assertLess(app.sound.get_length(), 0.15)
        app.sound = Mock()
        app.dispatch(("mute",))
        app.update(0.1)
        app.sound.play.assert_not_called()
        app.sound = None
        pg.mixer.quit()
        with self.assertWarns(UserWarning):
            app.start_story(story)
        app.render()
        self.assertIsNone(app.sound)


if __name__ == "__main__":
    unittest.main()
