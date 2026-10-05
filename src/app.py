"""The interactive window: assembling it, and the two ways into it.

The window itself is in :mod:`src.ui`, one module per part of it, and this module is the
small part that has to know about all of them: it composes the parts into
:class:`GraphPadApp`, and it holds the two entry points, the command line parser and
:func:`main`, that the outside world uses to reach the window.

Because the parts are composed rather than nested, almost nothing here is a method. What is
left is the constructor, the few calls that cross between parts, and the running of the
thing.

This file also runs when executed directly, as ``python src/app.py``, not just as
``python -m src.app``, so the imports below are deliberately placed after the start up
block and are marked accordingly.
"""

from __future__ import annotations

import argparse
import os
import sys
import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from tkinter import ttk

# Running this file directly, as ``python src/app.py``, puts src/ on sys.path instead of
# the project root, so the ``src`` package would not be importable. Adding the parent
# directory makes both that form and ``python -m src.app`` work. This has to happen before
# the package is imported below.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# The window embeds the figure, so the interactive backend has to be selected before
# pyplot or any canvas is created.
os.environ.setdefault('MPLBACKEND', 'TkAgg')
os.environ.setdefault('MKL_THREADING_LAYER', 'SEQUENTIAL')

# ruff: noqa: E402 - the environment and path must be prepared before these imports.
from src.app_state import AppState
from src.excel_reader import SheetLayout, read_dataset
from src.ui.axis_tab import AxisTabMixin
from src.ui.base import (
    MIN_CANVAS_WIDTH,
    MIN_WINDOW_HEIGHT,
    PANEL_WIDTH,
)
from src.ui.data_pane import EMPTY_DATASET, DataPaneMixin
from src.ui.general_tab import GeneralTabMixin
from src.ui.sample_list import SampleListMixin
from src.ui.shell import ShellMixin
from src.ui.style_tab import StyleTabMixin


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the interactive window.

    Returns:
        The configured parser.

    """
    parser = argparse.ArgumentParser(
        prog='graphpad-app',
        description='Adjust a GraphPad Prism style graph in an interactive window.',
    )
    parser.add_argument(
        '--input',
        type=Path,
        default=None,
        help='Optional file to open straight away; choose one in the window if omitted.',
    )
    parser.add_argument('--output', type=Path, help='Path suggested by default when saving.')
    return parser


class GraphPadApp(ShellMixin, SampleListMixin, DataPaneMixin, GeneralTabMixin, AxisTabMixin, StyleTabMixin):
    """The main window, holding the controls on the left and the graph on the right.

    The window is one window, so it is written as a class assembled from the parts it is
    made of rather than as several objects passing messages about. Each part is in
    :mod:`src.ui` and is named for what it holds, not for where it sits: the shell the
    controls are put in, the list of samples, the graph and the sheet, and one module per
    tab of the notebook. The shape each part may take is written down once in
    :mod:`src.ui.base`.

    What is left here is the window itself: the constructor that starts the parts off, the
    few calls that cross between them, and the entry points the command line uses. A part
    owns the fields it builds and puts them back itself, so nothing here has to know that
    the Plot style tab has a ``bar_width_var``.

    Attributes:
        state: The dataset and settings being edited.
        root: The Tk root window.
        listbox: Reorderable list of sample names.
        sheet: The worksheet preview below the graph, used to pick the columns to plot.
        input_path: The workbook currently loaded, if any.
        output_hint: Path suggested by default when saving.

    """

    def __init__(
        self,
        state: AppState | None = None,
        input_path: Path | None = None,
        output_hint: Path | None = None,
    ) -> None:
        """Build the window and draw the graph once.

        Args:
            state: The dataset and settings to edit; an empty one is used when omitted so
                the window can be opened before a file is chosen.
            input_path: Source workbook, used to suggest a name when saving.
            output_hint: Path suggested by default when saving.

        """
        self.state = state or AppState(EMPTY_DATASET)
        self.input_path = input_path
        self.output_hint = output_hint
        self.dirty = False
        self.last_dir = '.'
        self.syncing = False
        # The rows chosen for each workbook, so a sheet is only asked about once. Keyed by
        # file name rather than path because the choice belongs to the sheet, not to where
        # the file happens to sit.
        self._remembered_layout: dict[str, SheetLayout] = {}
        self.palette_popup: tk.Toplevel | None = None

        self.root = tk.Tk()
        self.root.title('GraphPad Prism style graph')
        self.root.geometry('1100x720')
        self.root.minsize(PANEL_WIDTH + MIN_CANVAS_WIDTH, MIN_WINDOW_HEIGHT)

        style = ttk.Style(self.root)
        if 'vista' in style.theme_names():
            style.theme_use('vista')

        self._build_controls()
        self._build_canvas()
        self._sync_from_state()
        self.redraw()
        if self.state.dataset.samples:
            self._select_row(0)


    def _sync_scatter_panels(self) -> None:
        """Show, hide or grey out the controls that depend on the kind of graph.

        The General tab has to be told where the x values are and which row names the
        series, and a bar graph decides both for itself, so that block is hidden entirely
        for a bar graph. The x range on the Axis tab is the other way round: the field is
        still shown, because a block that changes shape as the graph type changes is harder
        to follow than one that is simply greyed out and ignored.

        """
        scatter = self.state.config.chart == 'scatter'
        if scatter and not self.xy_frame.winfo_manager():
            self.xy_frame.pack(fill=tk.X)
        elif not scatter and self.xy_frame.winfo_manager():
            self.xy_frame.pack_forget()
        # A bar graph has no x values to scale, so neither the range nor the scale can mean
        # anything: its x axis is a row of categories, which has no logarithmic form. The
        # title is greyed out for the same reason, because a bar graph names its samples
        # along that axis instead of labelling it. The fields keep whatever was typed into
        # them and are simply not editable, so a switch back to a scatter plot does not
        # silently lose a title that was already worked out.
        for field in (self.x_max_entry, self.x_step_entry, self.x_axis_type_combo, self.x_title_entry):
            field.configure(state='normal' if scatter else 'disabled')


    def _sync_from_state(self) -> None:
        """Push the state onto every widget, without the widgets reading as a user edit.

        Setting a widget runs its own callback, which would look like a user adjustment and
        mark the freshly loaded graph as edited. The guard suppresses that for the duration.

        Each part of the window puts its own fields back, rather than this method reaching
        into every variable it owns. That way a new field is filled in by the tab that builds
        it, and no field is filled in from two places, which is how a control and the setting
        it shows quietly drift apart.
        """
        self.syncing = True
        try:
            self._sync_general()
            self._sync_axis()
            self._sync_style()
            self._sync_data()
        finally:
            self.syncing = False

    def run(self) -> None:
        """Show the window and block until it is closed."""
        self.root.mainloop()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the interactive window.

    Args:
        argv: Command line arguments, or ``None`` to read them from the process.

    Returns:
        A process exit code, ``0`` on success.

    """
    args = build_parser().parse_args(argv)
    if args.input is None:
        GraphPadApp(output_hint=args.output).run()
        return 0
    state = AppState(read_dataset(args.input))
    GraphPadApp(state, args.input, args.output).run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())



