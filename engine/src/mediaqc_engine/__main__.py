"""Executable entry point. Stdout is exclusively the binary UTF-8 protocol."""

import argparse
import logging
import sys
from pathlib import Path

from mediaqc_engine.ipc.server import serve


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path)
    args = parser.parse_args()
    try:
        serve(sys.stdin.buffer, sys.stdout.buffer, args.state_directory)
    except (BrokenPipeError, OSError):
        logging.getLogger(__name__).error("Desktop pipe closed; engine exiting")


if __name__ == "__main__":
    main()
