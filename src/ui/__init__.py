"""The window: the control panel on the left, the graph and the data preview beside it.

The package is split so that the parts can be read one at a time:

- :mod:`src.ui.fields` turns what a field holds into what a setting holds, and back. It
  holds no tkinter code at all, so those rules can be tested without opening a window.
- :mod:`src.ui.widgets` builds the rows and blocks the panel is assembled from.
- :mod:`src.ui.shell` holds the panel, the file bar and the scrollable area around them.
- :mod:`src.ui.sample_list` holds the list of samples and the per sample style block.
- :mod:`src.ui.general_tab`, :mod:`src.ui.axis_tab` and :mod:`src.ui.style_tab` each build
  one tab of the notebook.
- :mod:`src.ui.data_pane` draws the graph, reads the file, and shows the sheet preview.

:mod:`src.app` composes those into the one window and is the module the command line uses.

The two environment variables below are set here, rather than in the one module that used
to hold everything, because a module that reaches for matplotlib before they are set picks
a backend that cannot show a window. Doing it on import of the package means whichever of
these modules is imported first, the other is safe to import after it.
"""

import os

# The conda-forge numpy build shipped in this environment aborts inside the MKL threading
# layer as soon as a matrix product runs, which matplotlib triggers on every draw. The
# single threaded layer avoids the abort and is fast enough for graphs.
os.environ.setdefault('MKL_THREADING_LAYER', 'SEQUENTIAL')
# The window embeds the figure, so the interactive backend has to be chosen before
# pyplot or any canvas is created.
os.environ.setdefault('MPLBACKEND', 'TkAgg')
