"""Create GraphPad Prism style graphs from Excel data sheets.

The package is split into three layers so that the user interface can be replaced
without touching the data handling or the rendering:

- :mod:`src.excel_reader` turns an ``.xlsx`` worksheet into a :class:`~src.models.Dataset`.
- :mod:`src.plotting` renders a :class:`~src.models.Dataset` as a Prism style figure.
- :mod:`src.ui` holds the window that puts those two together, one module per part of it.
- :mod:`src.app` and :mod:`src.cli` are thin front ends on top of those layers.
"""

import os

# The conda-forge numpy build shipped in this environment aborts inside the MKL threading
# layer as soon as a matrix product runs, which matplotlib triggers on every draw. The
# single threaded layer avoids the abort and is fast enough for graphs.
os.environ.setdefault('MKL_THREADING_LAYER', 'SEQUENTIAL')

from src.excel_reader import ExcelLayoutError, ExcelLayoutWarning, read_dataset, read_table
from src.models import Dataset, ErrorKind, PlotConfig, Sample
from src.plotting import plot_dataset

__all__ = [
    'Dataset',
    'ErrorKind',
    'ExcelLayoutError',
    'ExcelLayoutWarning',
    'PlotConfig',
    'Sample',
    'plot_dataset',
    'read_dataset',
    'read_table',
]
