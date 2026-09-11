"""Cooperative cancellation shared by a run and its owned media tools."""

import threading


class Cancelled(Exception):
    """Internal control flow; persisted as CANCELLED by the manager."""


class CancellationToken:
    def __init__(self) -> None:
        self.event = threading.Event()

    def check(self) -> None:
        if self.event.is_set():
            raise Cancelled()

    def cancel(self) -> None:
        self.event.set()
