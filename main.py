import argparse
from pathlib import Path
import sys
from vn.story import Story, StoryError
from vn.catalog import discover_stories


def main():
    parser = argparse.ArgumentParser(description="Универсальный движок визуальных новелл")
    parser.add_argument("story", nargs="?", type=Path, help="Путь к истории; без аргумента открывается библиотека")
    parser.add_argument("--validate", action="store_true", help="Проверить JSON и существование ресурсов без запуска окна")
    parser.add_argument("--fullscreen", action="store_true", help="Запустить на весь экран в разрешении рабочего стола")
    args = parser.parse_args()
    try:
        story = Story(args.story) if args.story else None
        if args.validate:
            stories, errors = ([story], []) if story else discover_stories()
            for item in stories:
                print(f"OK: {item.title}, узлов: {len(item.nodes)}")
            for error in errors:
                print(error, file=sys.stderr)
            if not stories and not errors:
                print("Пока нет доступных историй")
            return 1 if errors else 0
        from vn.app import App
        App(story, fullscreen=args.fullscreen).run()
    except StoryError as exc:
        print(f"Ошибка новеллы: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
