"""The contract the parts of the window are written against.

The window is one window, not several, so the pieces that build it are written as mixins
rather than as separate objects talking to one another. That keeps every control reachable
as ``self.<name>`` and keeps the events wired straight to the handler that applies them,
which is what the panel is made of.

The cost of that choice is that the pieces refer to attributes and to one another without
either being able to see the other. This module is where that is written down: every
attribute a mixin is allowed to use, and every method it is allowed to call, is declared
here once. A mixin that reaches for something not declared fails the type check rather
than working until the day something moves.

Nothing here is implemented. :class:`src.app.GraphPadApp` is the class that satisfies it.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    from src.app_state import AppState
    from src.excel_reader import SheetLayout
    from src.sheet_view import SheetView

# The measurements of the window itself, which every part has to agree on and no part owns.
# They live here rather than in one of the parts because more than one of them is built from
# a part: the panel is sized from them and the data pane is drawn into what is left, so
# importing them from either would make the two parts import each other.
PANEL_WIDTH = 300
MIN_CANVAS_WIDTH = 520
MIN_WINDOW_HEIGHT = 560
NO_FILE = 'No file loaded — use Open… to choose an Excel sheet'
# Passed to a handler in place of a real event, so that calling one directly from a test or
# from another part is the same as the widget calling it. It is held here because the reset
# and the file loading both reach for it and neither is built from the other.
_SYNTHETIC_EVENT = cast('tk.Event[tk.Misc]', object())

# The window every part of the panel is written against. The attributes are the state and
# the widgets the parts share; the methods below them are the ones a part may call on
# another, each declared with what it is given and what it returns.
#
# The tkinter variables are declared rather than created here, because they belong to
# whichever tab builds them. Declaring them means a tab can be read on its own and a
# handler can be checked against the field it reads, without either being able to invent
# a variable that no tab ever makes.
class _AppBase:
    """The state, the widgets and the calls the parts of the window share."""

    # The state being edited, and the files it came from and is suggested to be saved as.
    state: AppState
    input_path: Path | None
    output_hint: Path | None
    # Set when the graph no longer matches the settings, and cleared by a reset.
    dirty: bool
    # The directory the file chooser opens in, so it opens where the user last was.
    last_dir: str
    # Suppresses the callbacks while the state is being pushed onto the widgets.
    syncing: bool
    # The rows chosen for each sheet, so one is only asked about once. Keyed by file name
    # rather than path, because the choice belongs to the sheet, not to where it sits.
    _remembered_layout: dict[str, SheetLayout]

    root: tk.Tk
    panel: ttk.Frame
    # The canvas holding the scrollable column of options, which the wheel is bound to.
    _body_canvas: tk.Canvas
    tabs: ttk.Notebook
    _canvas_area: ttk.Frame
    figure: Figure
    canvas: FigureCanvasTkAgg
    _natural_figure_size: tuple[float, float]
    # The grid of the worksheet below the graph, and the caption saying what is read from it.
    sheet: SheetView
    sheet_caption: ttk.Label
    # The list of samples, and the sample name and group shown on each row.
    listbox: ttk.Treeview
    # The palette menu, while it is open.
    palette_popup: tk.Toplevel | None
    # The picker itself is a plain frame, not a ttk widget, because the vista theme gives a
    # ttk widget an element layout of its own that a packed canvas inside it fights.
    palette_button: tk.Frame

    # The colour of the highlighted sample, typed as a hex code and previewed on a button.
    hex_var: tk.StringVar
    hex_entry: ttk.Entry
    swatch: tk.Button
    # The colour palette in use, its name, and the parts of the picker showing it.
    palette_key_var: tk.StringVar
    palette_var: tk.StringVar
    palette_name: ttk.Label
    palette_swatch: tk.Canvas

    # The title of the graph, and the font, size and position it is drawn with.
    title_var: tk.StringVar
    title_size_var: tk.StringVar
    title_font_type_var: tk.StringVar
    title_position_var: tk.StringVar
    # The legend, its own block on the tab, and the font and position it is offered with.
    legend_frame: ttk.Labelframe
    legend_var: tk.BooleanVar
    legend_font_var: tk.StringVar
    legend_font_type_var: tk.StringVar
    legend_position_var: tk.StringVar
    # The kind of graph, and the block of fields that only a scatter plot needs.
    chart_var: tk.StringVar
    xy_frame: ttk.Labelframe
    x_direction_var: tk.StringVar
    x_var: tk.StringVar
    x_entry: ttk.Entry
    series_var: tk.StringVar
    series_entry: ttk.Entry

    # The two axes, the settings they share, and the block of fields for each.
    axis_width_var: tk.StringVar
    axis_font_type_var: tk.StringVar
    x_title_var: tk.StringVar
    x_title_entry: ttk.Entry
    x_max_var: tk.StringVar
    x_step_var: tk.StringVar
    x_axis_length_var: tk.StringVar
    x_max_entry: ttk.Entry
    x_step_entry: ttk.Entry
    x_tick_font_var: tk.StringVar
    x_axis_type_var: tk.StringVar
    x_axis_type_combo: ttk.Combobox
    rotation_var: tk.StringVar
    rotation_entry: ttk.Spinbox
    y_title_var: tk.StringVar
    y_axis_length_var: tk.StringVar
    y_max_var: tk.StringVar
    y_step_var: tk.StringVar
    y_label_size_var: tk.StringVar
    y_tick_font_var: tk.StringVar
    log_var: tk.StringVar

    # How the marks are drawn, and the frame around them.
    connect_var: tk.BooleanVar
    point_labels_var: tk.BooleanVar
    points_var: tk.BooleanVar
    jitter_var: tk.DoubleVar
    orientation_var: tk.StringVar
    error_var: tk.StringVar
    bar_width_var: tk.StringVar
    bar_hatch_var: tk.StringVar
    point_type_var: tk.StringVar
    point_type_combo: ttk.Combobox
    color_by_var: tk.StringVar
    grouped_var: tk.BooleanVar
    # The style of the sample highlighted in the list, and its per series choices.
    style_frame: ttk.Labelframe
    style_name: ttk.Label
    edge_var: tk.StringVar
    hatch_var: tk.StringVar
    series_style_frame: ttk.Frame
    connect_series_var: tk.BooleanVar
    label_series_var: tk.BooleanVar
    # The groups, and the field naming a new one.
    group_vars: dict[str, tk.BooleanVar]
    group_list: ttk.Frame
    merge_name_var: tk.StringVar
    # How the preview rounds what it prints.
    decimals_var: tk.StringVar
    # The name of the file that is loaded, or a note that none is.
    file_var: tk.StringVar

    def redraw(self, mark_dirty: bool = True) -> None:
        """Draw the graph again, by default recording that it no longer matches the settings.

        Args:
            mark_dirty: Whether the drawing counts as an edit.

        """

    def _mark_dirty(self) -> None:
        """Record that the graph no longer matches the settings."""

    def _sync_from_state(self) -> None:
        """Push the state onto every widget without the widgets reading as a user edit."""

    def _refresh_list(self) -> None:
        """Rebuild the sample list from the state."""

    def _refresh_groups(self) -> None:
        """Rebuild the list of groups from the state."""

    def _show_selected_style(self) -> None:
        """Show the style block for the sample highlighted in the list."""

    def _show_selected_color(self) -> None:
        """Copy the colour of the highlighted sample into the hex field and the swatch."""

    def _on_row_selected(self, _event: object = None) -> None:
        """React to the highlight in the sample list moving to another sample.

        Args:
            _event: Unused; the selection is read from the list.

        """

    def _describe_column_selection(self) -> None:
        """Say how many columns of the sheet the bar graph is drawn from."""

    def _describe_scatter_selection(self) -> None:
        """Say which row and columns the scatter plot is taking its values from."""

    def _sync_sheet_pane(self) -> None:
        """Give the sheet preview the table, the mode and the rounding the graph is using."""

    def _apply_column_selection(self) -> None:
        """Rebuild the bar graph from only the columns left selected in the preview."""

    def _apply_scatter_selection(self) -> None:
        """Rebuild the scatter plot from the columns and the x row picked in the preview."""

    def _update_color_by(self, _event: object = None) -> None:
        """Apply whether colours follow samples or whole groups.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _update_point_type(self, _event: object = None) -> None:
        """Choose the shape every point is drawn as.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _update_palette(self) -> None:
        """Apply the palette in use to every sample that has not been coloured by hand."""

    def _update_chart(self, _event: object = None) -> None:
        """Switch between a bar graph and a scatter plot.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _update_legend_position(self, _event: object = None) -> None:
        """Move the legend above the plot, beside it, or onto the plot.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _update_title_position(self, _event: object = None) -> None:
        """Say where the plot title is written.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _update_title_font(self, _event: object = None) -> None:
        """Draw the plot title in the family chosen for it.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _update_legend_font(self, _event: object = None) -> None:
        """Draw the legend names in the family chosen for them.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _sync_scatter_panels(self) -> None:
        """Show, hide or grey out the controls that depend on the kind of graph."""

    def _build_color_row(self, panel: tk.Widget) -> None:
        """Create the row that types a colour as a hex code.

        Args:
            panel: The control panel the row is added to.

        """

    def _build_general_tab(self, tab: ttk.Frame) -> None:
        """Create the tab holding what the graph as a whole looks like.

        Args:
            tab: The General tab frame.

        """

    def _build_axis_tab(self, tab: ttk.Frame) -> None:
        """Create the tab holding the name, scale, range and fonts of each axis.

        Args:
            tab: The Axis tab frame.

        """

    def _build_style_panel(self, panel: ttk.Frame) -> None:
        """Create the tab holding how the drawing itself is dressed.

        Args:
            panel: The Plot style tab frame.

        """

    def _build_preview_tab(self, tab: ttk.Frame) -> None:
        """Create the tab holding how the data preview reads.

        Args:
            tab: The Data preview tab frame.

        """

    # The list and the panel reach for one another: the panel puts the list in, and reading
    # a file has to choose a sample so that the list and the style block are not left showing
    # whatever was there before.
    def _build_sample_list(self, panel: ttk.Frame) -> None:
        """Create the list of samples, above the scrolling options.

        Args:
            panel: The control panel the list is added to.

        """

    def _open_file(self) -> None:
        """Ask for a workbook and load it."""

    def _file_label(self) -> str:  # pragma: no cover - declared, not implemented here
        """Return the name of the loaded workbook, or a note that none is."""
        raise NotImplementedError


    def _select_row(self, index: int) -> None:
        """Highlight one row of the sample list and show its style.

        Args:
            index: Position in the current order, or ``-1`` for none.

        """

    def _selected_indices(self) -> tuple[int, ...]:  # pragma: no cover - declared, not implemented here
        """Return the positions of the highlighted rows, in the order they are shown."""
        raise NotImplementedError


    def _apply_indices(self, indices: Sequence[int]) -> None:
        """Put the samples back in the order these positions name.

        Args:
            indices: The positions, in the order they should appear.

        """

    def _row_id(self, index: int) -> str:  # pragma: no cover - declared, not implemented here
        """Return the id the list uses for one row, which is its name.

        Args:
            index: Position in the current order.

        """
        raise NotImplementedError

    def _selected_samples(self) -> tuple[str, ...]:  # pragma: no cover - declared, not implemented
        """Return the names of the highlighted samples, in the order they are shown."""
        raise NotImplementedError

    # The General tab offers the sizes of the text it shows, but the handler that applies
    # them is shared with the two axis blocks, so both reach for it and neither owns it.
    def _update_fonts(self, _event: object = None) -> None:
        """Apply the requested tick, legend, axis title and figure title font sizes.

        Args:
            _event: Unused; the fields apply the sizes themselves.

        """

    def _update_xy(self, _event: object = None) -> None:
        """Re-read the sheet as a scatter plot using the rows and columns that were named.

        Args:
            _event: Unused; the fields apply the choice themselves.

        """

    def _seed_scatter_fields(self) -> None:
        """Fill the scatter fields from the sheet, or ask when the sheet gives nothing."""

    # The Plot style tab offers the boxes that join and name points, but the handlers behind
    # them sit with the General tab, which is where those settings are stored.
    def _update_connect(self, _event: object = None) -> None:
        """Join the points of a scatter plot with a line, or draw them on their own.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _update_point_labels(self, _event: object = None) -> None:
        """Name every series beside its rightmost point, or name none of them.

        Args:
            _event: Unused; the field applies the choice itself.

        """

    def _update_line_width(self, _event: object = None) -> None:
        """Apply the axis and bar line thicknesses typed into the two fields.

        Args:
            _event: Unused; the fields apply the values themselves.

        """
