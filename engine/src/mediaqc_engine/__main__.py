"""Executable entry point. Stdout is exclusively the binary UTF-8 protocol."""

import logging
import sys

from mediaqc_engine.ipc.server import serve


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    try:
        serve(sys.stdin.buffer, sys.stdout.buffer)
    except (BrokenPipeError, OSError):
        logging.getLogger(__name__).error("Desktop pipe closed; engine exiting")


if __name__ == "__main__":
    main()
