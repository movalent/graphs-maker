"""Pytest bootstrap.

The variables below are set before any test imports numpy. ``MKL_THREADING_LAYER`` is
required because the free-threaded numpy build in this environment aborts inside MKL as
soon as a matrix product runs, and matplotlib triggers that on every draw.
"""

import os

import pytest

os.environ.setdefault('MKL_THREADING_LAYER', 'SEQUENTIAL')
os.environ.setdefault('MPLBACKEND', 'Agg')


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register opt-in execution for the slower GUI undo/redo tests."""
    parser.addoption(
        '--run-undo-redo',
        action='store_true',
        help='run GUI undo/redo tests (omitted by default)',
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Omit GUI undo/redo tests unless explicitly enabled."""
    if config.getoption('--run-undo-redo'):
        return

    selected = [item for item in items if 'undo_redo' not in item.keywords]
    deselected = [item for item in items if 'undo_redo' in item.keywords]
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
