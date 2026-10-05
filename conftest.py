"""Pytest bootstrap.

The variables below are set before any test imports numpy. ``MKL_THREADING_LAYER`` is
required because the free-threaded numpy build in this environment aborts inside MKL as
soon as a matrix product runs, and matplotlib triggers that on every draw.
"""

import os

os.environ.setdefault('MKL_THREADING_LAYER', 'SEQUENTIAL')
os.environ.setdefault('MPLBACKEND', 'Agg')
