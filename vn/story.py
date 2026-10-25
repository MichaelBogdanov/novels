"""Validated story graph and reversible navigation; no Pygame dependency."""
from dataclasses import dataclass
import json
from pathlib import Path


class StoryError(ValueError):
    pass


class Story:
    def __init__(self, path):
        self.path = Path(path).resolve()
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise StoryError(f"Не удалось прочитать {self.path}: {exc}") from exc
        self.validate()
        self.nodes = self.data["nodes"]
        self.start = self.data["start"]
        self.title = self.data["title"]

    def asset(self, name):
        return self.path.parent / name

    def validate(self):
        def require(ok, message):
            if not ok:
                raise StoryError(message)

        d = self.data
        require(isinstance(d, dict), "Корень JSON должен быть объектом")
        require(d.get("version") == 1, "Поддерживается version: 1")
        require(isinstance(d.get("title"), str) and d["title"].strip(), "Нужен title")
        nodes = d.get("nodes")
        require(isinstance(nodes, dict) and bool(nodes), "nodes должен быть непустым объектом")
        require(isinstance(d.get("start"), str) and d["start"] in nodes, "start: неизвестный узел")
        settings = d.get("settings", {})
        require(isinstance(settings, dict), "settings должен быть объектом")
        for key, low, high in [("text_speed", 1, 150), ("volume", 0, 1)]:
            value = settings.get(key, 36 if key == "text_speed" else 0.25)
            require(type(value) in (int, float) and low <= value <= high, f"settings.{key}: допустимо {low}–{high}")
        for key in ("font", "typing_sound"):
            if key in settings:
                require(isinstance(settings[key], str), f"settings.{key}: нужен путь")
                require(self.asset(settings[key]).is_file(), f"Не найден ресурс: {settings[key]}")
        for name, node in nodes.items():
            require(isinstance(node, dict), f"{name}: узел должен быть объектом")
            require(isinstance(node.get("text"), str) and node["text"].strip(), f"{name}: нужен text")
            require(isinstance(node.get("speaker", ""), str), f"{name}: speaker должен быть строкой")
            require(isinstance(node.get("art"), str), f"{name}: нужен путь art")
            require(self.asset(node["art"]).is_file(), f"{name}: не найден арт {node['art']}")
            modes = [key for key in ("next", "choices", "ending") if key in node]
            require(len(modes) == 1, f"{name}: нужен ровно один из next, choices, ending")
            if "next" in node:
                require(isinstance(node["next"], str) and node["next"] in nodes, f"{name}: неизвестный next")
            if "choices" in node:
                choices = node["choices"]
                require(isinstance(choices, list) and bool(choices), f"{name}: choices должен быть непустым списком")
                for i, choice in enumerate(choices):
                    require(isinstance(choice, dict), f"{name}.choices[{i}]: нужен объект")
                    require(isinstance(choice.get("text"), str) and choice["text"].strip(), f"{name}.choices[{i}]: нужен text")
                    require(isinstance(choice.get("target"), str) and choice["target"] in nodes, f"{name}.choices[{i}]: неизвестный target")
            if "ending" in node:
                end = node["ending"]
                require(isinstance(end, dict), f"{name}: ending должен быть объектом")
                require(end.get("type") in ("good", "bad", "neutral"), f"{name}: тип концовки good, bad или neutral")
                require(isinstance(end.get("title"), str) and end["title"].strip(), f"{name}: нужен ending.title")


@dataclass(frozen=True)
class Frame:
    node: str
    page: int = 0
    choice: str | None = None  # Choice taken to reach this frame.
    offset: int = 0  # Source-text anchor, independent of window size and wrapping.


class Session:
    """History follows actual visits, including repeated nodes and converging branches."""
    def __init__(self, story):
        self.story = story
        self.frames = [Frame(story.start)]

    @property
    def current(self):
        return self.frames[-1]

    @property
    def node(self):
        return self.story.nodes[self.current.node]

    def next_page(self, offset=0):
        self.frames.append(Frame(self.current.node, self.current.page + 1, offset=offset))

    def advance(self, choice=None):
        node = self.node
        if "choices" in node:
            if type(choice) is not int or not 0 <= choice < len(node["choices"]):
                raise ValueError("Необходимо выбрать допустимый вариант")
            selected = node["choices"][choice]
            self.frames.append(Frame(selected["target"], choice=selected["text"]))
        elif "next" in node:
            self.frames.append(Frame(node["next"]))
        else:
            return False
        return True

    def rewind(self, index):
        if not 0 <= index < len(self.frames):
            raise IndexError(index)
        del self.frames[index + 1:]

    def back(self):
        if len(self.frames) > 1:
            self.frames.pop()
            return True
        return False

    def restart(self):
        self.frames[:] = [Frame(self.story.start)]
