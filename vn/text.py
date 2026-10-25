"""Line wrapping with source offsets so resizing never invalidates rollback."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Line:
    start: int
    end: int


@dataclass(frozen=True)
class Page:
    start: int
    end: int
    lines: tuple[Line, ...]


def paginate(text, font, width, capacity, start=0):
    lines = []
    position = start
    width = max(1, width)
    while position < len(text):
        begin = position
        last_space = None
        while position < len(text) and text[position] != "\n":
            if font.size(text[begin:position + 1])[0] > width and position > begin:
                if last_space is not None:
                    position = last_space + 1
                break
            if text[position].isspace():
                last_space = position
            position += 1
        end = position
        if position < len(text) and text[position] == "\n":
            position += 1
        lines.append(Line(begin, end))
    if not lines:
        lines = [Line(start, start)]
    capacity = max(1, capacity)
    pages = []
    for i in range(0, len(lines), capacity):
        chunk = lines[i:i + capacity]
        end = lines[i + capacity].start if i + capacity < len(lines) else len(text)
        pages.append(Page(chunk[0].start, end, tuple(chunk)))
    return pages
