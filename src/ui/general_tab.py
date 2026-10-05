"""The General tab: what the graph as a whole is, and what kind of graph it is.

This is the tab a reader starts on, and its order is the order the choices are made in: the
graph is given a title, that title is given a font, a legend is asked for and styled, and
the kind of graph is chosen last because that decides whether the scatter fields below mean
anything at all.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.graphpad_style import DEFAULT_LEGEND_FONT
from src.models import (
    CHART_KINDS,
    CHART_LABELS,
    DEFAULT_CHART,
    DEFAULT_FONT_TYPE,
    DEFAULT_LEGEND_POSITION,
    DEFAULT_TITLE_POSITION,
    DEFAULT_X_DIRECTION,
    LEGEND_LABELS,
    LEGEND_POSITIONS,
    TITLE_LABELS,
    TITLE_POSITIONS,
    X_DIRECTION_LABELS,
    X_DIRECTIONS,
)
from src.ui.base import _SYNTHETIC_EVENT, PANEL_WIDTH, _AppBase
from src.ui.fields import label_to
from src.ui.widgets import option_row, pair_row, section

# The font families offered wherever a font type can be picked. They are the faces that
# ship with Windows and are therefore already installed, plus the two matplotlib fallbacks
# that resolve on the machines this is run on. The list is a fixed set of real family names
# rather than a scan of the installed ones, so a name in it is one worth offering.
FONT_CHOICES: tuple[str, ...] = (
    'Arial',
    'Calibri',
    'Cambria',
    'Consolas',
    'Courier New',
    'Segoe UI',
    'Tahoma',
    'Times New Roman',
    'Trebuchet MS',
    'Verdana',
)
# The direction choices offered in the dropdown, in the order they are shown.
X_DIRECTION_CHOICES: tuple[str, ...] = tuple(X_DIRECTION_LABELS[one] for one in X_DIRECTIONS)
# The legend positions offered, in the order they are shown.
LEGEND_POSITION_CHOICES: tuple[str, ...] = tuple(LEGEND_LABELS[one] for one in LEGEND_POSITIONS)
# The title placements offered. There is one, and it is the Prism default, but it is a
# choice like any other so that a graph centred above its plot is a decision rather than
# the only thing the renderer can do.
TITLE_POSITION_CHOICES: tuple[str, ...] = tuple(TITLE_LABELS[one] for one in TITLE_POSITIONS)


class GeneralTabMixin(_AppBase):
    """What the graph is as a whole: its title, its legend and its kind."""

    def _sync_general(self) -> None:
        """Put the General tab's fields back, showing the settings that are really in use."""
        config = self.state.config
        self._refresh_list()
        self.title_var.set(config.title or '')
        self.title_font_type_var.set(config.title_font or DEFAULT_FONT_TYPE)
        self.title_position_var.set(TITLE_LABELS[config.title_position])
        self.legend_var.set(config.show_legend)
        self.legend_font_var.set(str(config.legend_size or DEFAULT_LEGEND_FONT))
        self.legend_font_type_var.set(config.legend_font or DEFAULT_FONT_TYPE)
        self.legend_position_var.set(LEGEND_LABELS[config.legend_position])
        self.chart_var.set(CHART_LABELS[config.chart])
        self.connect_var.set(config.connect_points)
        self.point_labels_var.set(config.point_labels)
        # The scatter block is shown, hidden or greyed according to the kind of graph, so it
        # has to be brought into step with the chart field that was just set.
        self._sync_scatter_panels()

    def _build_general_tab(self, tab: ttk.Frame) -> None:
        """Create the tab holding what the graph as a whole looks like.

        The order is the order the choices are made in when the graph is first put together:
        it is given a title, that title is given a font and a place, a legend is asked for
        and styled, and the sort of graph is chosen last because it decides which of the
        fields below are needed at all.

        Args:
            tab: The General tab frame.

        """
        self.title_var = tk.StringVar()
        ttk.Label(tab, text='Plot title', font=('Segoe UI', 8)).pack(anchor=tk.W)
        ttk.Entry(tab, textvariable=self.title_var).pack(fill=tk.X)
        self.title_var.trace_add('write', lambda *_: self._update_title())

        self._build_title_controls(tab)

        # The legend and the series names are separate choices: either, both or neither may
        # be shown, so neither is quietly switched off by turning the other on. They sit in
        # their own block because the legend has three settings of its own, which left in
        # the open they read as belonging to the title above them.
        self.legend_frame = section(tab, 'Legend')
        self._build_legend_controls(self.legend_frame)

        # The sort of graph decides which of the fields below mean anything: a bar graph
        # reads whole columns, while a scatter plot has to be told where its x values are.
        self.chart_var = tk.StringVar(value=CHART_LABELS[DEFAULT_CHART])
        option_row(
            tab,
            ('Graph type', self.chart_var, tuple(CHART_LABELS[kind] for kind in CHART_KINDS), self._update_chart),
            (None, None, (), None),
        )

        # A scatter plot needs to be told where its x values are and which row names the
        # series, which a bar graph never does, so this block only appears for one.
        self.xy_frame = section(tab, 'Scatter plot only')
        self._build_xy_controls(self.xy_frame)

    def _build_title_controls(self, panel: tk.Widget) -> None:
        """Create the controls that say how the plot title is drawn.

        The family and the size are both applied to the title itself, so the two halves of
        this row are two settings rather than one size beside a family nothing reads.

        Args:
            panel: The frame the controls are added to.

        """
        self.title_font_type_var = tk.StringVar(value=DEFAULT_FONT_TYPE)
        self.title_size_var = tk.StringVar()
        pair_row(
            panel,
            ('Title font type', self.title_font_type_var, FONT_CHOICES, self._update_title_font),
            ('Title text size', self.title_size_var, (), self._update_fonts),
        )
        # Centred above the plot is the Prism default, and the one place a title can be read
        # without covering a bar, so it is offered as the choice rather than assumed.
        self.title_position_var = tk.StringVar(value=TITLE_LABELS[DEFAULT_TITLE_POSITION])
        option_row(
            panel,
            ('Title position', self.title_position_var, TITLE_POSITION_CHOICES, self._update_title_position),
            (None, None, (), None),
        )

    def _build_legend_controls(self, panel: tk.Widget) -> None:
        """Create the controls that decide whether the legend is drawn, and how.

        Every setting of the legend is in this one block, so the tab reads as three things
        rather than as a run of unrelated rows: what the graph is called, what the legend
        says, and what sort of graph it is.

        Args:
            panel: The frame the controls are added to.

        """
        self.legend_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            panel,
            text='Show legend',
            variable=self.legend_var,
            command=self._update_legend,
        ).pack(anchor=tk.W)

        # ``legend_font_var`` keeps its name because it is the legend text size, which is
        # what it has always held and what the font handlers read.
        self.legend_font_var = tk.StringVar()
        self.legend_font_type_var = tk.StringVar(value=DEFAULT_FONT_TYPE)
        pair_row(
            panel,
            ('Legend font type', self.legend_font_type_var, FONT_CHOICES, self._update_legend_font),
            ('Legend text size', self.legend_font_var, (), self._update_fonts),
        )
        # Where the legend sits is a real choice: above the plot and beside it both keep
        # the names clear of the bars, and the third is offered for a graph that is short
        # on room and would rather have the space back.
        self.legend_position_var = tk.StringVar(value=LEGEND_LABELS[DEFAULT_LEGEND_POSITION])
        option_row(
            panel,
            ('Legend position', self.legend_position_var, LEGEND_POSITION_CHOICES, self._update_legend_position),
            (None, None, (), None),
        )
    def _build_xy_controls(self, panel: tk.Widget) -> None:
        """Create the controls that say where a scatter plot takes its x values from.

        The y values are not named here. They are the columns ticked in the preview under
        the graph, which is where the series are chosen from, and a second copy of that
        choice on the panel could disagree with the grid about what is plotted.

        Args:
            panel: The frame the controls are added to.

        """
        # Which way round the sheet keeps its x values is the one thing the reader cannot
        # infer from a row or a column alone, because both are just a line of numbers. It
        # is offered as a choice rather than guessed at, because a scatter plot drawn
        # against the wrong axis is a plausible looking wrong answer.
        self.x_direction_var = tk.StringVar(value=X_DIRECTION_LABELS[DEFAULT_X_DIRECTION])
        option_row(
            panel,
            ('X values run down a', self.x_direction_var, X_DIRECTION_CHOICES, self._update_xy),
            (None, None, (), None),
        )
        self.x_var = tk.StringVar()
        ttk.Label(panel, text='X values: index', font=('Segoe UI', 8)).pack(anchor=tk.W)
        self.x_entry = ttk.Entry(panel, textvariable=self.x_var)
        self.x_entry.pack(fill=tk.X)
        self.x_entry.bind('<Return>', lambda _e: self._update_xy())
        self.x_entry.bind('<FocusOut>', lambda _e: self._update_xy())
        ttk.Label(
            panel,
            text='Type "index" for the left index column, or the number of a row or column.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 60,
        ).pack(anchor=tk.W, pady=(2, 0))
        # A sheet written as a GraphPad XY table names its series in a row of text above
        # the measurements. Without being told which row that is, every series is named
        # after the header row above it, which repeats a group name once per column.
        self.series_var = tk.StringVar()
        ttk.Label(panel, text='Series name row number', font=('Segoe UI', 8)).pack(anchor=tk.W, pady=(8, 0))
        self.series_entry = ttk.Entry(panel, textvariable=self.series_var)
        self.series_entry.pack(fill=tk.X)
        self.series_entry.bind('<Return>', lambda _e: self._update_xy())
        self.series_entry.bind('<FocusOut>', lambda _e: self._update_xy())
        ttk.Label(
            panel,
            text='Leave empty to name each series after the top row of the sheet.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 60,
        ).pack(anchor=tk.W, pady=(2, 0))
    def _update_title(self) -> None:
        """Copy the title field into the settings."""
        text = self.title_var.get().strip()
        self.state.config.title = text or None
        self.redraw()
    def _update_chart(self, _event: object = None) -> None:
        """Switch between a bar graph and a scatter plot.

        Error bars, replicate spread and grouping describe a summary of several replicates,
        which a scatter plot of single points has no meaning for, so those controls are hidden
        rather than left on screen doing nothing.
        """
        if self.syncing:
            return
        chosen = label_to(CHART_KINDS, CHART_LABELS, self.chart_var.get(), DEFAULT_CHART)
        self.state.config.chart = chosen
        self._sync_scatter_panels()
        self.sheet.set_mode('x_and_y' if chosen == 'scatter' else 'columns')
        if chosen == 'bar':
            self.sheet.select_all_columns()
            self._describe_column_selection()
        else:
            self._seed_scatter_fields()
        # The list shows series for a scatter plot and samples for a bar graph, so it is
        # rebuilt here rather than only when a file is read. Without this the rows still
        # named after samples, or still empty, and a click on the graph has nothing to
        # highlight.
        self._refresh_list()
        self._refresh_groups()
        self._on_row_selected(_SYNTHETIC_EVENT)
        self.redraw()
    def _update_legend(self) -> None:
        """Show or hide the sample legend."""
        self.state.config.show_legend = bool(self.legend_var.get())
        self.redraw()
    def _update_legend_position(self, _event: object = None) -> None:
        """Move the legend above the plot, beside it, or onto the plot.

        A caption the window does not know falls back to the default rather than being
        stored, so a stale field cannot leave the legend somewhere the renderer has no
        placement for.
        """
        if self.syncing:
            return
        self.state.config.legend_position = label_to(
            LEGEND_POSITIONS, LEGEND_LABELS, self.legend_position_var.get(), DEFAULT_LEGEND_POSITION
        )
        self.redraw()
    def _update_title_position(self, _event: object = None) -> None:
        """Say where the plot title is written, which is centred above the graph."""
        if self.syncing:
            return
        self.state.config.title_position = label_to(
            TITLE_POSITIONS, TITLE_LABELS, self.title_position_var.get(), DEFAULT_TITLE_POSITION
        )
        self.redraw()
    def _update_title_font(self, _event: object = None) -> None:
        """Draw the plot title in the family chosen for it.

        Storing ``None`` while the field shows the default keeps the title following the
        font the whole figure uses, so a panel left untouched is not a request to fix the
        title at one family forever.
        """
        if self.syncing:
            return
        chosen = self.title_font_type_var.get()
        self.state.config.title_font = None if chosen == DEFAULT_FONT_TYPE else chosen
        self.redraw()
    def _update_legend_font(self, _event: object = None) -> None:
        """Draw the legend names in the family chosen for them.

        As with the title, the default family stores nothing, so the names keep following
        the font the rest of the figure uses.
        """
        if self.syncing:
            return
        chosen = self.legend_font_type_var.get()
        self.state.config.legend_font = None if chosen == DEFAULT_FONT_TYPE else chosen
        self.redraw()
    def _update_point_labels(self, _event: object = None) -> None:
        """Name every series beside its rightmost point, or name none of them.

        This is separate from the legend, which stays on the General tab. Either may be
        shown on its own, and both together, so a graph with a legend above and names at
        the right is a choice rather than an accident.

        The switch is an all or nothing one, so it fills the named set with every series
        rather than leaving the user to label them one at a time from the style panel.
        The per series boxes then take names back out of it, which is the way to drop the
        few that would otherwise sit on top of one another.
        """
        if self.syncing:
            return
        config = self.state.config
        config.point_labels = self.point_labels_var.get()
        config.label_series = self.state.series_names if config.point_labels else ()
        # The style panel shows the named set through the box of the highlighted series, so
        # it is refreshed here or it can be left showing a tick the graph has stopped obeying.
        self._show_selected_style()
        self.redraw()
    def _update_connect(self, _event: object = None) -> None:
        """Join the points of a scatter plot with a line, or draw them on their own."""
        if self.syncing:
            return
        self.state.config.connect_points = self.connect_var.get()
        self.redraw()


