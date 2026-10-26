"""Render the actual Pygame UI at several sizes, without changing story files."""
import os
from dataclasses import replace
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame as pg
from vn.app import App


def main():
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "preview/interface")
    destination.mkdir(parents=True, exist_ok=True)
    app = App()
    app.muted = True
    screenshots = 0

    def capture(name):
        nonlocal screenshots
        app.render()
        for _ in range(30):
            app.feedback.step(1 / 60)
        app.render()
        assert all(app.viewport.contains(rect) for rect, _ in app.buttons), name
        pg.image.save(app.canvas, str(destination / f"{name}.png"))
        screenshots += 1

    try:
        for size in ((640, 480), (1280, 720), (1920, 1080), (1080, 1920)):
            tag = f"{size[0]}x{size[1]}"
            app.window = pg.display.set_mode(size, pg.RESIZABLE)
            app.show_library()
            capture(f"library-{tag}")
            if not app.catalog:
                continue
            app.start_story(app.catalog[0])
            app.visible = len(app.page_text)
            capture(f"reading-{tag}")
            app.dispatch(("toolbar",))
            capture(f"toolbar-{tag}")
            app.dispatch(("toolbar",))
            # Use real story nodes for choices and endings; rendering only.
            for state, key in (("choices", "choices"), ("ending", "ending")):
                node_id = next(name for name, node in app.story.nodes.items() if key in node)
                app.session.frames[-1] = replace(app.session.current, node=node_id, offset=0, page=0)
                app.load_frame(revealed=True)
                while not app.last_page:
                    app.advance()
                    app.visible = len(app.page_text)
                capture(f"{state}-{tag}")
            app.dispatch(("history",))
            capture(f"history-{tag}")
        app.window = pg.display.set_mode((1280, 720), pg.RESIZABLE)
        for story in app.catalog:
            app.start_story(story)
            app.visible = len(app.page_text)
            capture(f"story-{story.path.parent.name}")
        print(f"Rendered {screenshots} screens to {destination.resolve()}")
    finally:
        pg.quit()


if __name__ == "__main__":
    main()
