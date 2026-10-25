"""Check playable packages and image decoding without local source work."""
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame as pg
from vn.catalog import discover_stories


def main():
    stories, errors = discover_stories()
    for story in stories:
        seen, pending = set(), [story.start]
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            node = story.nodes[name]
            pending.extend([node["next"]] if "next" in node else [choice["target"] for choice in node.get("choices", [])])
        missing = set(story.nodes) - seen
        if missing:
            errors.append(f"{story.title}: недостижимые сцены: {sorted(missing)}")
        for path in {node["art"] for node in story.nodes.values()}:
            try:
                pg.image.load(str(story.asset(path)))
            except (OSError, ValueError, pg.error) as exc:
                errors.append(f"{story.title}: {path}: {exc}")
        print(f"{story.title}: {len(seen)} достижимых сцен, {sum('ending' in n for n in story.nodes.values())} финалов")
    for error in errors:
        print(error, file=sys.stderr)
    if not stories and not errors:
        print("Пока нет доступных историй")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
