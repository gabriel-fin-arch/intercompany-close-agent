"""Run something with the model switched off, whatever the environment says.

Triage calls Claude whenever ANTHROPIC_API_KEY is set (triage/node.py), with
ANTHROPIC_MODEL naming another model than the default. The demo and the
README's sample results are meant to show the offline run, so they clear both
for the duration and put them back after.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

_MODEL_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL")


@contextmanager
def offline() -> Iterator[None]:
    saved = {name: os.environ.pop(name) for name in _MODEL_ENV if name in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)
