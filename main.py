"""Convenience entrypoint: `python main.py <command>` is the same as `aika <command>`."""

from aika.aika_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
