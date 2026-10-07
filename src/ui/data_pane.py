"""The graph, the file it is drawn from, and the sheet preview underneath it.

Everything that turns a workbook into a picture lives here: reading the file, deciding
which rows and columns are the measurements, drawing the figure into the window, and
working out which bar or point a click landed on. The data preview is here too, because
it is the same table the graph is read from, and a change in one is a change in the other.
"""

from __future__ import annotations

import tkinter as tk
import warnings
import zipfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd
from matplotlib.backend_bases import PickEvent
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from src.app_state import AppState
from src.excel_reader import (
    ExcelLayoutError,
    SheetLayout,
    detect_layout,
    detect_scatter_layout,
    parse_columns,
    read_dataset,
    read_table,
    read_xy,
)
from src.models import (
    DEFAULT_X_DIRECTION,
    MAX_DECIMALS,
    MIN_DECIMALS,
    X_DIRECTION_LABELS,
    X_DIRECTIONS,
    Dataset,
    XDirection,
)
from src.plotting import plot_dataset
from src.sheet_view import Role, SheetView
from src.ui.base import (
    _SYNTHETIC_EVENT,
    NO_FILE,
    PANEL_WIDTH,
    _AppBase,
)
from src.ui.fields import (
    INDEX_X,
    first_of,
    label_to,
    optional_number,
    where_word,
    x_position,
    x_text,
)
from src.ui.widgets import number_row

# The modifiers that make a click add to the selection rather than replace it, matching the
# Ctrl and Shift that the sample list itself uses. The names are matplotlib's own, taken
# from the modifiers carried on the mouse event.
MODIFIER_KEYS = frozenset({'ctrl', 'control', 'shift'})
# A window opened before a file is chosen still needs a dataset, so there is something to
# draw and the panel can be built and tested without a workbook.
EMPTY_DATASET = Dataset(samples=())
# Height reserved for the data preview under the graph. It is fixed rather than a share of
# the window, so a tall sheet cannot push the graph out of sight, and a short sheet cannot
# leave a band of empty grid between the two. The grid scrolls inside it.
SHEET_PANE_HEIGHT = 190


class DataPaneMixin(_AppBase):
    """Reading the workbook, drawing the graph, and the sheet preview it is read from."""

    def _build_canvas(self) -> None:
        """Create the embedded figure canvas and the data preview beneath it.

        The canvas sits in a resize-aware area. Its figure keeps its natural size where it
        fits, shrinks uniformly when the area is smaller, and stays centred as the window
        changes size.

        There is no navigation toolbar. Its home, pan, zoom and save buttons duplicate the
        save buttons in the panel, and panning or zooming a graph that is deliberately held
        at one size fights the rule that fixes the size in the first place.
        """
        body = ttk.Frame(self.root)
        body.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self._canvas_area = ttk.Frame(body)
        self._canvas_area.pack(fill=tk.BOTH, expand=True)
        self.canvas = FigureCanvasTkAgg(Figure(), master=self._canvas_area)
        natural_width, natural_height = (float(value) for value in self.canvas.figure.get_size_inches())
        self._natural_figure_size = natural_width, natural_height
        # The pick handler is connected by redraw, because every new figure replaces the
        # canvas callback registry and takes the connection with it.
        self.canvas.get_tk_widget().place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self._canvas_area.bind('<Configure>', self._on_canvas_resize)
        self._build_sheet_pane(body)
    def _size_to_canvas(self, figure: Figure, width: int, height: int) -> None:
        """Centre the figure and shrink it uniformly only when the canvas is too small.

        The natural dimensions are saved separately because a fitted figure's own dimensions
        are smaller. Reusing those reduced dimensions on the next resize would make the
        graph shrink again even when more room became available.

        Args:
            figure: The figure to size.
            width: Available width in pixels.
            height: Available height in pixels.

        """
        if width <= 1 or height <= 1:
            return
        dpi = figure.dpi
        natural_w, natural_h = self._natural_figure_size
        fit = min(width / dpi / natural_w, height / dpi / natural_h, 1.0)
        canvas_width = max(1, round(natural_w * dpi * fit))
        canvas_height = max(1, round(natural_h * dpi * fit))
        self.canvas.get_tk_widget().configure(width=canvas_width, height=canvas_height)
        figure.set_size_inches(canvas_width / dpi, canvas_height / dpi, forward=False)

    def _on_canvas_resize(self, event: tk.Event[tk.Misc]) -> None:
        """Fit and centre the figure when the space around it changes size.

        Args:
            event: The resize event for the area holding the embedded canvas.

        """
        self._size_to_canvas(self.canvas.figure, event.width, event.height)

    def redraw(self, mark_dirty: bool = True) -> None:
        """Rebuild the figure from the current state and show it.

        The figure returns to its natural dimensions before being fitted to the available
        area, so a control change or a later larger window cannot leave it accidentally
        shrunken from an earlier resize.

        ``draw_idle`` coalesces rapid changes, such as dragging the spread slider, into a
        single repaint instead of redrawing on every intermediate value.

        Args:
            mark_dirty: Whether this redraw represents a user adjustment. Redraws that only
                put existing state on screen, such as after loading a file or resetting,
                pass ``False``.

        """
        figure = plot_dataset(self.state.dataset, self.state.config)
        natural_width, natural_height = (float(value) for value in figure.get_size_inches())
        self._natural_figure_size = natural_width, natural_height
        self._size_to_canvas(figure, self._canvas_area.winfo_width(), self._canvas_area.winfo_height())
        # The canvas has to be told about the new figure, not just the other way round.
        # Assigning ``canvas.figure`` alone leaves ``figure.canvas`` pointing at the figure
        # the canvas was built with, and every artist then looks like it belongs to a
        # different canvas, so matplotlib discards all picking and a click on a bar reaches
        # nothing. ``set_canvas`` is what the canvas constructor itself calls.
        figure.set_canvas(self.canvas)
        self.canvas.figure = figure
        # ``set_canvas`` gives the canvas a fresh callback registry, so the pick handler
        # connected once at build time is gone by now and has to be connected again. Without
        # this the graph would look right and still ignore every click.
        self.canvas.mpl_connect('pick_event', self._on_pick)
        self.canvas.draw_idle()
        if mark_dirty:
            self._mark_dirty()
    def _on_pick(self, event: PickEvent) -> None:
        """Select the sample whose bar was clicked.

        A plain click replaces the selection and Ctrl or Shift adds to it, mirroring what
        clicking a row in the sample list does, so the graph and the list behave as one
        control. Selecting a bar also reveals the style panel, which is the quickest way to
        reach the fill, outline and hatch controls for it.

        Nothing is recoloured as a side effect: the colour chooser stays on the swatch and
        the outline button, so a click only ever chooses a sample.

        Clicks are ignored while the navigation toolbar is panning or zooming, because there
        the same press is part of dragging the axes rather than a request to select.

        Args:
            event: The matplotlib pick event.

        """
        if self._toolbar_is_active():
            return
        name = getattr(self.canvas.figure, 'sample_by_bar', {}).get(id(event.artist))
        if not name:
            return
        index = self.state.index_of(name)
        if index < 0:
            return
        self._select_bar(index, extend=self._has_selection_modifier(event))

    @staticmethod
    def _has_selection_modifier(event: PickEvent) -> bool:
        """Return whether Ctrl or Shift was held during a click.

        The modifiers arrive as a list, so they are intersected rather than combined with
        ``&``, which only works between two sets.

        Args:
            event: The matplotlib pick event.

        Returns:
            ``True`` when the click should extend the selection.

        """
        modifiers = getattr(getattr(event, 'mouseevent', None), 'modifiers', ())
        return bool(MODIFIER_KEYS.intersection(modifiers or ()))
    def _toolbar_is_active(self) -> bool:
        """Return whether the navigation toolbar is panning or zooming.

        The toolbar keeps its state in an enum whose inactive member is still truthy, and that
        enum is private to matplotlib. The underlying text is read instead: it is empty when
        the toolbar is idle and names the mode otherwise, which also covers a plain string.
        """
        toolbar = getattr(self.canvas, 'toolbar', None)
        mode = getattr(toolbar, 'mode', None)
        return bool(getattr(mode, 'value', mode))
    def _select_bar(self, index: int, extend: bool) -> None:
        """Highlight the row for a clicked bar, adding to the selection when asked to.

        Args:
            index: Position of the clicked sample in the current order.
            extend: Whether Ctrl or Shift was held, which keeps the rows already highlighted
                and toggles this one, matching the list's own multi selection.

        """
        if not extend:
            self._select_row(index)
            return
        rows = set(self._selected_indices()) ^ {index}
        self._apply_indices(sorted(rows))
        self.listbox.focus(self._row_id(index))
        self.listbox.see(self._row_id(index))
        self._show_selected_color()
        self._show_selected_style()
    def _build_sheet_pane(self, body: ttk.Frame) -> None:
        """Create the sheet-like preview of the imported data, below the graph.

        Args:
            body: The frame holding the graph and everything under it.

        """
        box = ttk.Frame(body)
        box.pack(side=tk.BOTTOM, fill=tk.X)
        # The block is given a fixed height so a long sheet cannot push the graph out of
        # the window. The grid scrolls inside it, so the block never changes size.
        box.pack_propagate(False)
        box.configure(height=SHEET_PANE_HEIGHT)
        ttk.Separator(box, orient=tk.HORIZONTAL).pack(fill=tk.X)
        self.sheet_caption = ttk.Label(
            box,
            text='No file loaded',
            font=('Segoe UI', 8),
            foreground='#666666',
        )
        self.sheet_caption.pack(anchor=tk.W, padx=4, pady=(3, 0))
        self.sheet = SheetView(box, self._on_sheet_changed)
        self.sheet.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 4))
    def _sync_sheet_pane(self) -> None:
        """Show the loaded worksheet in the preview and mark what is being plotted.

        Called after the file is read and whenever the chart type changes, so the grid
        always shows the sheet that produced the graph above it. A freshly opened file has
        every column selected, which is exactly what the reader read on its own.
        """
        table = self._current_table()
        self.sheet.set_table(table)
        if table is None:
            self.sheet_caption.configure(text=NO_FILE)
            return
        self.sheet.set_mode('x_and_y' if self.state.config.chart == 'scatter' else 'columns')
        # A sheet that carries the usual markers is read correctly without any attention, so
        # the preview is seeded with the rows the reader found. A sheet without them starts
        # empty, and stays empty until the user points at the rows.
        self._seed_roles(table)
        if self.state.config.chart == 'scatter':
            x_row = self.sheet.role_row(Role.X_VALUES)
            self.sheet.set_selection(self.sheet.columns, x_row)
            self._describe_scatter_selection()
        else:
            self.sheet.select_all_columns()
            self._describe_column_selection()
    def _describe_column_selection(self) -> None:
        """Say how many columns of the sheet the bar graph is drawn from."""
        chosen = self.sheet.columns
        total = len(self.sheet.measured_columns())
        self.sheet_caption.configure(
            text=f'{len(chosen)} of {total} columns plotted — click a column number to add or remove it'
        )
    def _describe_scatter_selection(self) -> None:
        """Say which row and columns the scatter plot is taking its values from.

        The numbers are one based because that is how the sheet numbers them, so the caption
        and the preview the user clicks always agree.
        """
        columns = ', '.join(str(column) for column in self.sheet.columns)
        direction = label_to(X_DIRECTIONS, X_DIRECTION_LABELS, self.x_direction_var.get(), DEFAULT_X_DIRECTION)
        # The caption is written in the field's own terms, so a tidy sheet reads as
        # "index" and a GraphPad XY table reads as a row number, which is what was typed.
        position = x_position(self.x_var.get()) if direction == 'column' else None
        x = x_text(position) if position is not None else self.x_var.get().strip()
        if not x or not self.sheet.columns:
            self.sheet_caption.configure(
                text='No x values chosen \u2014 tick the columns to plot and set the x values on the left'
            )
            return
        where = 'index' if direction == 'column' and x == INDEX_X else f'{where_word(direction)} {x}'
        self.sheet_caption.configure(text=f'x values: {where}    y series: columns {columns}')
    def _on_sheet_changed(self) -> None:
        """Re-read the sheet for the columns and x row the user just picked in the preview."""
        if self.syncing or self.input_path is None:
            return
        if self.state.config.chart == 'scatter':
            self._apply_scatter_selection()
        else:
            self._apply_column_selection()
    def _update_xy(self, _event: object = None) -> None:
        """Re-read the sheet as a scatter plot using the rows and columns that were named.

        A choice that cannot be read is reported and the previous graph is kept, rather than
        replacing a working graph with a broken one.
        """
        if self.syncing or self.state.config.chart != 'scatter':
            return
        table = self._current_table()
        if table is None:
            return
        direction = label_to(X_DIRECTIONS, X_DIRECTION_LABELS, self.x_direction_var.get(), DEFAULT_X_DIRECTION)
        # A row is addressed by its number and a column by its heading, so the field is
        # read the way the chosen direction means it rather than as a number either way.
        # The local is named apart from the helper of the same name, so that reading the
        # field here is not read as calling the local.
        x_at: int | None
        if direction == 'row':
            rows = parse_columns(self.x_var.get())
            x_at = rows[0] - 1 if len(rows) == 1 else None
        else:
            x_at = x_position(self.x_var.get())
        # The y values are the columns ticked in the preview rather than a list typed on the
        # panel, so there is only ever one answer to which series are plotted. An empty grid
        # selection means nothing is ticked, which the reader already reports on.
        y = list(self.sheet.columns)
        if x_at is None:
            self._report_no_x_values()
            return
        series_row = first_of(parse_columns(self.series_var.get()))
        try:
            series, x_label = read_xy(
                table,
                x_row=x_at if direction == 'row' else None,
                x_column=x_at if direction == 'column' else None,
                y_columns=tuple(y),
                series_row=None if series_row is None else series_row - 1,
                first_data_row=self._first_xy_row(table, direction, x_at, series_row),
                path=self.input_path,
            )
        except (OSError, zipfile.BadZipFile, ExcelLayoutError, ValueError) as error:
            messagebox.showerror('Cannot read the sheet', str(error), parent=self.root)
            return
        if not series:
            messagebox.showerror(
                'Cannot read the sheet', 'None of the named columns held any points.', parent=self.root
            )
            return
        self.state.dataset = replace(self.state.dataset, series=series, x_label=x_label)
        self.state.config.x_row = x_at if direction == 'row' else None
        self.state.config.x_column = x_at if direction == 'column' else None
        self.state.config.x_direction = direction
        self.state.config.x_columns = tuple(y)
        self.state.config.series_row = None if series_row is None else series_row - 1
        self.state.config.connect_points = self.connect_var.get()
        # The preview is brought into step whether the choice came from its grid or from
        # the fields, so the two controls can never show different rows and columns.
        self.sheet.set_selection(self.state.config.x_columns, self.state.config.x_row)
        self._describe_scatter_selection()
        self.redraw()
    def _report_no_x_values(self) -> None:
        """Say that the sheet has no x values to plot against, and how to name them.

        A sheet with no ``Group`` or ``Condition`` markers cannot be read as a bar graph,
        so a scatter plot of it draws nothing at all. An empty graph with no explanation
        reads as a broken program, so the gap is named and the way out is given.
        """
        name = self.input_path.name if self.input_path is not None else 'This sheet'
        messagebox.showinfo(
            'No x values detected',
            f'{name} has no x values the program can work out, so a scatter plot cannot be '
            f'drawn yet.\n\nName them by hand in the Scatter plot controls:\n'
            f'\u2022 X values \u2014 the number of the row, the number of a column, '
            f'or \u201cindex\u201d for the left index column.\n'
            f'\u2022 Series name row number \u2014 the number of the row naming each series.\n\n'
            f'Say whether the x values run down a Column or across a Row, then tick the '
            f'columns to plot in the sheet below the graph.',
            parent=self.root,
        )

    @staticmethod
    def _first_xy_row(
        table: pd.DataFrame,
        direction: XDirection,
        x_index: int,
        series_row: int | None,
    ) -> int:
        """Return the first sheet row a scatter point may come from.

        The first row is a heading, and whichever of the x row and the series names row
        comes further down is also read as names rather than as data, so points start
        below both of them.

        Args:
            table: The trimmed worksheet table.
            direction: Whether the x values run down a column or across a row.
            x_index: Worksheet position of the x values, zero based.
            series_row: Worksheet row naming each series, one based, or ``None``.

        Returns:
            The first row a point may be read from.

        """
        named = [row - 1 for row in (series_row,) if row is not None]
        if direction == 'row':
            named.append(x_index)
        return max(named, default=0) + 1
    def _apply_column_selection(self) -> None:
        """Rebuild the bar graph from only the columns left selected in the preview.

        The sheet is re-read rather than the parsed samples being filtered, because a
        column that was left out must not influence the names, groups or counts of the ones
        that stayed. A read that fails leaves the previous graph and the previous selection
        in place, so a column can always be ticked back in.
        """
        table = self._current_table()
        if table is None or self.input_path is None:
            return
        columns = self.sheet.columns
        layout = self._layout_from_roles(table)
        if layout is None:
            return
        try:
            dataset = read_dataset(self.input_path, layout, columns=columns)
        except (OSError, zipfile.BadZipFile, ExcelLayoutError, ValueError) as error:
            messagebox.showerror('Cannot read the sheet', f'{self.input_path.name}\n\n{error}', parent=self.root)
            self.sheet.select_all_columns()
            return
        if not dataset.samples:
            messagebox.showerror(
                'Cannot read the sheet',
                'None of the selected columns held any measurements.',
                parent=self.root,
            )
            self.sheet.select_all_columns()
            return
        self.state.replace_dataset(dataset)
        self.state.set_columns(columns)
        self._refresh_list()
        self._refresh_groups()
        self._on_row_selected(_SYNTHETIC_EVENT)
        self._describe_column_selection()
        self.redraw()
    def _apply_scatter_selection(self) -> None:
        """Rebuild the scatter plot from the columns and the x row picked in the preview.

        The x field in the panel is filled from the grid rather than the other way round, so
        the two controls always show the same choice, and the existing read path is reused
        rather than a second implementation of it.

        The x values are not always a grid choice: a tidy sheet is detected with its x
        values already in the left index, and there is no row to pick. So the columns are
        applied whatever the x is, and only a row picked in the grid replaces the x.
        Bailing out because no row carries the role would leave a detected scatter plot
        unable to lose a series, which is the one thing the grid click is for.
        """
        row = self.sheet.role_row(Role.X_VALUES)
        if not self.sheet.columns:
            # Nothing is chosen yet, so there is no graph to draw. The caption already says
            # what to click, and the graph is left as it is rather than being emptied.
            self._describe_scatter_selection()
            return
        if row is not None:
            # A row chosen in the grid is the x values running across the sheet, so
            # the direction follows the pick rather than contradicting it.
            self.syncing = True
            try:
                self.x_direction_var.set(X_DIRECTION_LABELS['row'])
                self.x_var.set(str(row + 1))
            finally:
                self.syncing = False
        self._update_xy()
        self._describe_scatter_selection()
    def _layout_from_roles(self, table: pd.DataFrame) -> SheetLayout | None:
        """Build the rows to read the sheet by from the roles given in the preview.

        The first measurement row is not a role of its own: it is everything below the last
        row that carries a name, so a sheet with no group row can still be read once the user
        has said where the sample names are.

        Args:
            table: The trimmed worksheet table, used to check the rows fall inside the sheet.

        Returns:
            The rows to read, or ``None`` when the sheet is too short for what was chosen.

        """
        named = [self.sheet.role_row(Role.GROUP), self.sheet.role_row(Role.CONDITIONS)]
        first = max((row for row in named if row is not None), default=-1) + 1
        if not 0 <= first < len(table.index):
            return None
        return SheetLayout(
            group_row=self.sheet.role_row(Role.GROUP),
            condition_row=self.sheet.role_row(Role.CONDITIONS),
            first_data_row=first,
        )
    def _seed_roles(self, table: pd.DataFrame) -> None:
        """Show the roles the reader worked out for itself, so the preview starts correct.

        A sheet with the usual markers needs no attention, so the roles it implies are shown
        as given. A sheet without them starts empty, and the graph stays empty until the user
        points at the rows.

        Args:
            table: The trimmed worksheet table.

        """
        if self.input_path is None:
            self.sheet.set_assignment({})
            self.sheet.select_all_columns()
            return
        try:
            layout = detect_layout(table, self.input_path)
        except ExcelLayoutError:
            self.sheet.set_assignment({})
            self.sheet.select_all_columns()
            return
        assignment: dict[Role, tuple[int, ...]] = {}
        if layout.group_row is not None:
            assignment[Role.GROUP] = (layout.group_row,)
        if layout.condition_row is not None:
            assignment[Role.CONDITIONS] = (layout.condition_row,)
        assignment[Role.Y_VALUES] = self.sheet.measured_columns()
        self.sheet.set_assignment(assignment)
        self.sheet.set_selection(self.sheet.measured_columns(), None)
    def _seed_scatter_fields(self) -> None:
        """Fill the scatter fields from the sheet, or ask when the sheet gives nothing.

        A sheet carrying the usual markers has nothing to offer a scatter plot, so its x
        values and series names are worked out here, and the columns to plot are ticked in
        the preview. When none of them can be, the fields are left empty and the user is
        told, because an empty graph with no explanation is indistinguishable from a broken
        one.
        """
        table = self._current_table()
        found = None if table is None else detect_scatter_layout(table)
        if found is None:
            self.syncing = True
            try:
                self.x_var.set('')
                self.series_var.set('')
            finally:
                self.syncing = False
            self.sheet.set_selection((), None)
            self._describe_scatter_selection()
            self._report_no_x_values()
            return
        self.syncing = True
        try:
            self.x_direction_var.set(X_DIRECTION_LABELS[found.x_direction])
            self.x_var.set(str(found.x_index + 1) if found.x_direction == 'row' else x_text(found.x_index))
            self.series_var.set('' if found.series_row is None else str(found.series_row + 1))
            # The y values are read from the preview rather than from a field, so the
            # detected columns are ticked in the grid instead of being written anywhere.
            self.sheet.set_selection(found.y_columns, None)
        finally:
            self.syncing = False
        self._update_xy()
    def _current_table(self) -> pd.DataFrame | None:
        """Return the trimmed worksheet table, or ``None`` when it cannot be read."""
        if self.input_path is None:
            return None
        try:
            return read_table(self.input_path)
        except (OSError, zipfile.BadZipFile, ValueError):
            return None
    def load_file(self, path: Path) -> bool:
        """Read a workbook and show it, keeping the current data if the read fails.

        The state is only replaced once the file has been read successfully, so a broken
        file never leaves the window showing a graph that no longer matches the sheet. A
        sheet whose rows the reader cannot work out is still opened, because the preview
        below the graph is where those rows are chosen by hand.

        Args:
            path: Workbook to load.

        Returns:
            ``True`` when the file was loaded, ``False`` when it could not be read at all.

        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            try:
                table = read_table(path)
            except (OSError, zipfile.BadZipFile, ValueError) as error:
                messagebox.showerror('Cannot open file', f'{path.name}\n\n{error}', parent=self.root)
                return False

        layout = self._remembered_layout.get(path.name)
        if layout is None:
            try:
                layout = detect_layout(table, path)
            except ExcelLayoutError:
                # The usual markers are missing, so nothing can be plotted until the rows are
                # chosen in the preview. The sheet is still opened, empty, so the preview can
                # be filled from it.
                layout = None
        try:
            dataset = read_dataset(path, layout) if layout is not None else EMPTY_DATASET
        except (OSError, zipfile.BadZipFile, ExcelLayoutError, ValueError) as error:
            messagebox.showerror('Cannot open file', f'{path.name}\n\n{error}', parent=self.root)
            return False

        self.state = AppState(dataset)
        self.state.set_columns(None)
        self.input_path = path
        self.last_dir = str(path.parent)
        self.dirty = False
        self.file_var.set(self._file_label())
        self._sync_from_state()
        self.redraw(mark_dirty=False)
        self._select_row(0) if self.state.dataset.samples else None
        self.root.title(f'{path.name} — GraphPad Prism style graph')
        # The preview reads the file again, so it is filled last and only once the sheet is
        # known to be readable.
        self._sync_sheet_pane()
        self._warn_about(caught)
        return True
    def _open_file(self) -> None:
        """Ask for a workbook and load it, confirming first if there are unsaved changes."""
        if self.dirty and not messagebox.askyesno(
            'Discard changes?',
            'The graph has unsaved adjustments. Open another file anyway?',
            parent=self.root,
        ):
            return
        chosen = filedialog.askopenfilename(
            parent=self.root,
            title='Open Excel file',
            initialdir=self.last_dir,
            filetypes=[('Excel workbooks', '*.xlsx *.xlsm'), ('All files', '*.*')],
        )
        if chosen:
            self.load_file(Path(chosen))
    def _warn_about(self, caught: Sequence[warnings.WarningMessage]) -> None:
        """Show any repair notices the reader produced while loading a file.

        Args:
            caught: The warnings recorded during the read.

        """
        notes = [f'• {entry.message}' for entry in caught]
        if notes:
            messagebox.showwarning('File loaded with warnings', '\n'.join(notes), parent=self.root)
    def _sync_data(self) -> None:
        """Put the data preview's field back, and tell the grid how to round its values."""
        chosen = self.state.config.preview_decimals
        self.decimals_var.set('' if chosen is None else str(chosen))
        self.sheet.set_decimals(chosen)

    def _build_preview_tab(self, tab: ttk.Frame) -> None:
        """Create the tab holding how the data preview under the graph reads.

        The setting lives in a tab of its own rather than beside the graph controls because
        it changes nothing that is drawn: it decides how many digits the preview prints, so
        putting it with the options that alter the graph would imply it alters one.

        Args:
            tab: The Data preview tab frame.

        """
        ttk.Label(
            tab,
            text='How the data preview under the graph shows the values it reads.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 40,
        ).pack(anchor=tk.W, pady=(0, 4))
        self.decimals_var = tk.StringVar()
        number_row(tab, 'Decimal places', self.decimals_var, self._update_preview_decimals)
        ttk.Label(
            tab,
            text='Leave the field empty to show every value exactly as the sheet holds it.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 40,
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            tab,
            text='This changes the preview only. The graph is always drawn from the values '
            'as they are.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 40,
        ).pack(anchor=tk.W, pady=(10, 0))
    def _update_preview_decimals(self, _event: object = None) -> None:
        """Round what the data preview prints, or show the sheet exactly when empty.

        The field is corrected to the number actually applied, so a value outside the
        allowed range cannot leave the preview rounding to something the field does not
        say. Only the grid is redrawn: no value the reader produced has changed.

        Args:
            _event: Unused; the field applies the rounding itself.

        """
        if self.syncing:
            return
        text = self.decimals_var.get().strip()
        if not text:
            chosen: int | None = None
        else:
            number = optional_number(text)
            if number is None or number != int(number):
                return
            chosen = max(MIN_DECIMALS, min(int(number), MAX_DECIMALS))
            self.decimals_var.set(str(chosen))
        self.state.config.preview_decimals = chosen
        self.sheet.set_decimals(chosen)
