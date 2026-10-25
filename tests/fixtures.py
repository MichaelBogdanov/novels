"""Small generated test graph; no dependency on a published or demo story."""
import json
from pathlib import Path
import struct
import zlib
from vn.story import Story


def make_story(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"\x00\x20\x30\x40")) + chunk(b"IEND", b"")
    (root / "pixel.png").write_bytes(png)
    nodes = {
        "arrival": {"next": "letter"},
        "letter": {"choices": [{"text": str(i), "target": target} for i, target in enumerate(("harbor", "path", "harbor"))]},
        "harbor": {"next": "lantern"},
        "path": {"next": "lantern"},
        "lantern": {"choices": [{"text": str(i), "target": target} for i, target in enumerate(("home", "wait", "end"))]},
        "home": {"ending": {"type": "good", "title": "A"}},
        "wait": {"ending": {"type": "neutral", "title": "B"}},
        "end": {"ending": {"type": "bad", "title": "C"}},
    }
    for node in nodes.values():
        node.update(text="Текст для проверки движка.", art="pixel.png")
    data = dict(version=1, title="Тест", start="arrival", settings={}, nodes=nodes)
    path = root / "story.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return Story(path)
