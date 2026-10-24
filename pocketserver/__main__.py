from __future__ import annotations

import argparse
import os
from pathlib import Path

from .server import PocketServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PocketServer media and download server")
    parser.add_argument("--host", default="0.0.0.0", help="address to listen on")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("POCKETSERVER_HOME", Path.home() / "PocketServer")),
        help="configuration, download, and media directory",
    )
    parser.add_argument("--no-open", action="store_true", help="do not open a local browser")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = PocketServer(args.data_dir, args.host, args.port)
    app.run(open_browser=not args.no_open)


if __name__ == "__main__":
    main()
