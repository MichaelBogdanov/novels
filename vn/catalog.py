"""Discover playable packages without depending on the local demo or drafts."""
from pathlib import Path
from .story import Story, StoryError

STORIES = Path(__file__).resolve().parents[1] / "stories"


def discover_stories(directory=STORIES):
    stories, errors = [], []
    for path in sorted(Path(directory).glob("*/story.json")):
        if path.parent.name == "demo" or path.parent.name.startswith("."):
            continue
        try:
            stories.append(Story(path))
        except StoryError as exc:
            errors.append(f"{path.parent.name}: {exc}")
    stories.sort(key=lambda story: story.title.casefold())
    return stories, errors
