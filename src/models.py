"""Typed data structures shared by the reader, the plotting layer and the user interface."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import fmean, stdev
from typing import Literal

from src.graphpad_style import DEFAULT_PALETTE, FALLBACK_FONTS

ErrorKind = Literal['sd', 'sem', 'none']
ColorBy = Literal['sample', 'group']
# Which way round the graph is drawn. ``vertical`` is the Prism default, where the
# measurements run up the value axis and the sample names run along the bottom. The other two
# put the measurements on a horizontal axis instead, so a long list of sample names has room
# to be read rather than being squeezed under a narrow graph.
Orientation = Literal['vertical', 'horizontal', 'inverted']
ORIENTATIONS: tuple[Orientation, ...] = ('vertical', 'horizontal', 'inverted')
ORIENTATION_LABELS: dict[Orientation, str] = {
    'vertical': 'Vertical bars',
    'horizontal': 'Horizontal bars',
    'inverted': 'Inverted (values across)',
}
# Which sort of graph is drawn. A bar graph summarises a column of replicates; a scatter
# graph plots paired x and y values, one point per row of the sheet.
ChartKind = Literal['bar', 'scatter']
CHART_KINDS: tuple[ChartKind, ...] = ('bar', 'scatter')
CHART_LABELS: dict[ChartKind, str] = {'bar': 'Bar graph', 'scatter': 'Scatter plot'}
# The graph a sheet is drawn as until the user says otherwise. A bar graph is the Prism
# default, and the only one that can be drawn without the user naming any rows or columns.
DEFAULT_CHART: ChartKind = 'bar'
# Which way round a scatter sheet keeps its x values. A tidy dataset runs them down a
# column, one per data row, while a GraphPad XY table runs them across a row, one above
# each plotted column. Both are common, so the user says which they have.
XDirection = Literal['column', 'row']
X_DIRECTIONS: tuple[XDirection, ...] = ('column', 'row')
X_DIRECTION_LABELS: dict[XDirection, str] = {'column': 'Column', 'row': 'Row'}
# The starting point for the x direction of a sheet that has to be read by hand. A tidy
# dataset, which is the more common of the two shapes, keeps its x values down a column. The
# field is seeded from the sheet where it can be worked out, so this only applies to a sheet
# the user has to point at.
DEFAULT_X_DIRECTION: XDirection = 'column'
# Where the legend sits relative to the plot. ``above`` is the Prism default and the one place
# it can never cover a bar; ``right`` keeps it clear of the bars too but narrows the plot;
# ``inside`` sits on the plot itself, which is compact but can cover a tall bar.
LegendPosition = Literal['above', 'right', 'inside']
LEGEND_POSITIONS: tuple[LegendPosition, ...] = ('above', 'right', 'inside')
LEGEND_LABELS: dict[LegendPosition, str] = {
    'above': 'Above graph',
    'right': 'Right of graph',
    'inside': 'Top right (inside graph)',
}
DEFAULT_LEGEND_POSITION: LegendPosition = 'above'
# Where the plot title is written. It is held as data rather than hard coded in the renderer so
# that the caption a user reads in the window and the placement the figure uses cannot drift.
TitlePosition = Literal['center']
TITLE_POSITIONS: tuple[TitlePosition, ...] = ('center',)
TITLE_LABELS: dict[TitlePosition, str] = {'center': 'Centered above the graph'}
DEFAULT_TITLE_POSITION: TitlePosition = 'center'
# Physical plotting-area dimensions shown in the Axis tab. Keeping them in the shared
# settings means the renderer and the interactive controls use the same starting size.
DEFAULT_X_AXIS_LENGTH_CM = 9.0
DEFAULT_Y_AXIS_LENGTH_CM = 8.0
# The font family every piece of text is drawn with unless a family is chosen for it. It is the
# family the renderer prefers, so a panel left untouched shows the font the graph is really
# using rather than a default that was never applied. It is taken from that preference list
# rather than written out again, so the two cannot drift apart.
DEFAULT_FONT_TYPE: str = FALLBACK_FONTS[0]
# The shape a point is drawn as, and the caption each is offered under. The shape is held
# here rather than in the window so that the caption a user reads and the mark the renderer
# draws cannot drift apart, the same reason the positions above are.
PointType = Literal['round', 'square', 'cross', 'triangle', 'diamond', 'star']
POINT_TYPES: tuple[PointType, ...] = ('round', 'square', 'cross', 'triangle', 'diamond', 'star')
POINT_LABELS: dict[PointType, str] = {
    'round': 'Round',
    'square': 'Square',
    'cross': 'Cross',
    'triangle': 'Triangle',
    'diamond': 'Diamond',
    'star': 'Star',
}
DEFAULT_POINT_TYPE: PointType = 'round'
# The marker each shape is drawn with. Prism draws an open symbol, a white centre inside a
# coloured edge, so the shape is a choice about the outline rather than about the fill.
POINT_MARKERS: dict[PointType, str] = {
    'round': 'o',
    'square': 's',
    'cross': '+',
    'triangle': '^',
    'diamond': 'D',
    'star': '*',
}
# The shapes that are strokes rather than outlines, and so have no interior to leave white.
# A cross or a star drawn open is a cross or a star drawn as bare lines, which disappears
# against the page, so those two are filled with the colour of the point instead.
SOLID_POINTS: frozenset[PointType] = frozenset({'cross', 'star'})

# Headroom used when the value axis range is left automatic: the linear axis tops out just
# above the tallest mean, and the log axis a little above the largest value. They live here
# so the renderer and the window that displays the automatic values cannot drift apart.
Y_MAX_HEADROOM = 1.15
LOG_HEADROOM = 3.0
# How many decimal places the data preview rounds its values to. Scientific sheets carry
# far more digits than anyone reads, and the preview exists to show the shape of a sheet,
# so two places is enough to tell a measurement from noise. ``None`` shows the sheet
# exactly as it is, which is the way out when the hidden digits are the wanted ones.
DEFAULT_DECIMALS: int | None = 2
MIN_DECIMALS = 0
MAX_DECIMALS = 10


@dataclass(frozen=True, slots=True)
class Sample:
    """A single measurement column of the worksheet.

    A sample is one condition measured inside one group, for example ``42C`` inside
    ``WT Phi29``. It holds every replicate read from the worksheet column.

    Attributes:
        name: Unique, human readable name of the condition.
        group: Name of the group the condition belongs to.
        values: Replicate measurements, in worksheet row order.

    """

    name: str
    group: str
    values: tuple[float, ...]

    @property
    def n(self) -> int:
        """Return the number of replicates."""
        return len(self.values)

    @property
    def mean(self) -> float:
        """Return the arithmetic mean, or ``nan`` when the sample is empty."""
        return fmean(self.values) if self.values else math.nan

    @property
    def sd(self) -> float:
        """Return the sample standard deviation (``n - 1`` denominator).

        Returns:
            The standard deviation, or ``0.0`` when fewer than two replicates exist.

        """
        return stdev(self.values) if len(self.values) > 1 else 0.0

    @property
    def sem(self) -> float:
        """Return the standard error of the mean.

        Returns:
            The standard error, or ``nan`` when the sample is empty.

        """
        return self.sd / math.sqrt(self.n) if self.n else math.nan

    def error(self, kind: ErrorKind = 'sd') -> float:
        """Return the error bar length for the requested statistic.

        Args:
            kind: Which statistic to use, one of ``'sd'``, ``'sem'`` or ``'none'``.

        Returns:
            The absolute error to draw above and below the mean.

        """
        if kind == 'none':
            return 0.0
        return self.sd if kind == 'sd' else self.sem


@dataclass(frozen=True, slots=True)
class XYPoint:
    """One paired measurement from a scatter sheet.

    Attributes:
        x: The independent value.
        y: The dependent value.
        row: Worksheet row the pair came from, kept so a click can name the right point.

    """

    x: float
    y: float
    row: int = 0


@dataclass(frozen=True, slots=True)
class XYSeries:
    """One column of a scatter sheet, drawn as a set of points sharing one colour.

    Attributes:
        name: Series name, taken from the header or the series row the user pointed at.
        points: The points, in worksheet row order.

    """

    name: str
    points: tuple[XYPoint, ...] = ()

    @property
    def n(self) -> int:
        """Return the number of points."""
        return len(self.points)


@dataclass(frozen=True, slots=True)
class Dataset:
    """A complete experiment read from one worksheet.

    Attributes:
        samples: All measurement columns, in worksheet order.
        y_label: Quantity measured, taken from the first replicate row label.
        replicate_labels: Labels of the replicate rows, for example ``('Conc.1', 'Conc.2')``.
        series: Paired x and y columns for a scatter plot. Empty for a bar graph, which is what
            lets both kinds of chart share one window and one set of controls.
        x_label: Quantity on the x axis of a scatter plot.

    """

    samples: tuple[Sample, ...]
    y_label: str = ''
    replicate_labels: tuple[str, ...] = ()
    series: tuple[XYSeries, ...] = ()
    x_label: str = ''

    @property
    def points(self) -> int:
        """Return how many scatter points the sheet holds in total."""
        return sum(one.n for one in self.series)

    @property
    def groups(self) -> tuple[str, ...]:
        """Return the distinct group names in worksheet order."""
        return tuple(dict.fromkeys(sample.group for sample in self.samples))

    def group_of(self, group: str) -> tuple[Sample, ...]:
        """Return every sample belonging to one group.

        Args:
            group: Group name to look up.

        Returns:
            The matching samples in worksheet order, possibly empty.

        """
        return tuple(sample for sample in self.samples if sample.group == group)

    def ordered(self, order: Sequence[str] | None = None) -> tuple[Sample, ...]:
        """Return the samples reordered according to ``order``.

        Names that are not part of ``order`` keep their relative worksheet order and are
        appended at the end, so a partially specified order is always accepted.

        Args:
            order: Desired sample order, by sample name.

        Returns:
            The reordered samples.

        """
        if not order:
            return self.samples
        by_name = {sample.name: sample for sample in self.samples}
        requested = set(order)
        picked = [by_name[name] for name in order if name in by_name]
        rest = [sample for sample in self.samples if sample.name not in requested]
        return tuple(picked + rest)

    def ordered_series(self, order: Sequence[str] | None = None) -> tuple[XYSeries, ...]:
        """Return the scatter series reordered according to ``order``.

        Names that are not part of ``order`` keep their relative worksheet order and are
        appended at the end, so a partially specified order is always accepted.

        Args:
            order: Desired series order, by series name.

        Returns:
            The reordered scatter series.

        """
        if not order:
            return self.series
        by_name = {series.name: series for series in self.series}
        requested = set(order)
        picked = [by_name[name] for name in order if name in by_name]
        rest = [series for series in self.series if series.name not in requested]
        return tuple(picked + rest)


@dataclass(slots=True)
class PlotConfig:
    """User adjustable presentation settings for the graph.

    Attributes:
        colors: Explicit fill colour per sample name. Samples without an entry fall back to
            the GraphPad palette.
        edge_colors: Explicit bar outline colour per sample name.
        hatches: Explicit hatch pattern per sample name, using the matplotlib pattern
            characters such as ``'//'``.
        point_types: Shape each point is drawn as, by the name of the sample or scatter series
            it belongs to. A name with no entry follows ``point_type``, so the whole graph can
            be set at once and a series pulled out of it afterwards.
        group_overrides: Group each sample is drawn under, by sample name. This lets samples
            be regrouped without touching the data that was read from the worksheet.
        sample_order: Desired sample order, by sample name.
        series_order: Desired scatter-series order, by series name.
        log_axis: Render the value axis on a logarithmic scale.
        title: Optional figure title.
        title_position: Where the title is written relative to the plot, which is centred
            above it. The title is drawn inside the figure, so it stays visible whether or
            not a legend sits above the plot.
        title_font: Font family of the title, or ``None`` for the family the whole figure
            uses.
        error_kind: Statistic used for the error bars.
        color_by: Whether palette colours follow individual samples or whole groups.
        palette: Key of the colour palette used for samples with no colour of their own.
        grouped_layout: Leave the wider Prism gap between groups and list each group once in
            the legend, instead of spreading every bar evenly.
        jitter: Horizontal spread of the replicate points inside a bar, as a fraction of
            the bar width. ``0.0`` reproduces the centred GraphPad superplot look.
        show_points: Whether individual replicates are drawn on top of the bars.
        show_legend: Whether the sample legend is drawn.
        legend_position: Where the legend sits. ``'above'`` and ``'right'`` both keep it
            clear of the bars, the first by giving the plot a band at the top and the second
            by narrowing the plot; ``'inside'`` draws it on the plot, which is the only one
            of the three that can cover a bar.
        legend_font: Font family of the legend text, or ``None`` for the family the whole
            figure uses.
        y_label: Replacement text for the value axis label, or ``None`` to keep the one read
            from the worksheet.
        y_max: Upper limit of the value axis, or ``None`` to choose it from the data.
        y_min: Lower limit of the value axis, or ``None`` for the usual zero baseline.
        y_major_step: Spacing of the value axis major ticks, or ``None`` for automatic.
        font_size: Size of both axes' tick labels, or ``None`` for the Prism default. This
            is the fallback each axis falls back on when it has no size of its own.
        x_font_size: Size of the x axis tick labels, or ``None`` to follow ``font_size``.
        y_font_size: Size of the y axis tick labels, or ``None`` to follow ``font_size``.
            The two axes are sized apart because the labels along the bottom are usually
            sample names, which are long and want to be smaller than the numbers up the
            side, and a reader wants both to look like they belong to the same graph.
        y_label_size: Size of the value axis label, or ``None`` for the Prism default.
        title_size: Size of the figure title, or ``None`` for the Prism default.
        legend_size: Size of the legend text, or ``None`` for the Prism default.
        axis_line_width: Thickness of the axis lines and the value axis tick marks in points,
            or ``None`` for the Prism default.
        bar_line_width: Thickness of the bar outlines, the error bar lines and the group band
            lines in points, or ``None`` for the Prism default.
        chart: Which sort of graph to draw.
        orientation: Which way round the bars are drawn.
        x_row: Worksheet row holding the x values of a scatter plot, zero based, or
            ``None`` when they run down a column instead.
        x_columns: Worksheet columns holding the y values of a scatter plot, zero based and
            counting the label column.
        series_row: Worksheet row naming each scatter series, or ``None`` to name them after
            the header row.
        x_direction: Whether the x values run down a column or across a row.
        x_column: Worksheet column holding the x values of a scatter plot, zero based, or
            ``None`` when they run across a row instead.
        x_label_override: Replacement text for the x axis label, or ``None`` to keep the one
            read from the worksheet. A bar graph names its samples along that axis rather
            than labelling it, so this describes a scatter plot only.
        label_rotation: How far the x axis labels are turned, in degrees. ``0.0`` leaves
            them upright, which is the Prism default. A bar graph's sample names are the
            labels that start to overlap once there are more than a few, so this is what
            gives them room; a scatter plot numbers that axis and keeps them upright.
        preview_decimals: Decimal places the data preview rounds to, or ``None`` to show the
            sheet values exactly. This is a display setting only: it changes what the
            preview prints and nothing the reader or the graph ever sees.
        x_max: Upper limit of the x axis, or ``None`` to let matplotlib frame the points.
        x_major_step: Spacing of the x axis major ticks, or ``None`` for automatic.
            A bar graph has no x values to scale, so these describe a scatter plot only.
        x_axis_length_cm: Physical width of the plotting area, in centimeters.
        y_axis_length_cm: Physical height of the plotting area, in centimeters.
        connect_series: Scatter series whose points are joined by a line, by name. An
            empty tuple joins none of them, which is how a single series can be connected
            while its neighbours stay as points.
        point_labels: Whether series names are written beside their rightmost point. This
            is independent of ``show_legend``: either, both or neither may be shown.
        label_series: Scatter series named beside their rightmost point. An empty tuple
            labels none, so labels can be dropped for the series that would otherwise
            collide with one another.
        point_size: Size of a scatter point in points, or ``None`` for the default.
        point_type: Shape a point is drawn as when nothing has been chosen for it
            individually. The shapes that have no interior are filled rather than left open,
            because an open cross is a cross drawn as two bare lines.
        connect_points: Whether the points of a scatter series are joined by a line.

    """

    colors: dict[str, str] = field(default_factory=dict)
    edge_colors: dict[str, str] = field(default_factory=dict)
    hatches: dict[str, str] = field(default_factory=dict)
    point_types: dict[str, PointType] = field(default_factory=dict)
    group_overrides: dict[str, str] = field(default_factory=dict)
    sample_order: tuple[str, ...] = ()
    log_axis: bool = False
    title: str | None = None
    title_position: TitlePosition = DEFAULT_TITLE_POSITION
    title_font: str | None = None
    error_kind: ErrorKind = 'sd'
    color_by: ColorBy = 'sample'
    palette: str = DEFAULT_PALETTE
    grouped_layout: bool = False
    jitter: float = 0.0
    show_points: bool = True
    show_legend: bool = True
    legend_position: LegendPosition = DEFAULT_LEGEND_POSITION
    legend_font: str | None = None
    y_label: str | None = None
    y_max: float | None = None
    y_min: float | None = None
    y_major_step: float | None = None
    font_size: int | None = None
    x_font_size: int | None = None
    y_font_size: int | None = None
    y_label_size: int | None = None
    title_size: int | None = None
    legend_size: int | None = None
    axis_line_width: float | None = None
    bar_line_width: float | None = None
    chart: ChartKind = 'bar'
    orientation: Orientation = 'vertical'
    x_row: int | None = None
    x_columns: tuple[int, ...] = ()
    series_row: int | None = None
    x_direction: XDirection = 'column'
    x_column: int | None = None
    x_label_override: str | None = None
    label_rotation: float = 0.0
    point_size: int | None = None
    point_type: PointType = DEFAULT_POINT_TYPE
    connect_points: bool = False
    preview_decimals: int | None = DEFAULT_DECIMALS
    x_max: float | None = None
    x_major_step: float | None = None
    x_axis_length_cm: float = DEFAULT_X_AXIS_LENGTH_CM
    y_axis_length_cm: float = DEFAULT_Y_AXIS_LENGTH_CM
    connect_series: tuple[str, ...] = ()
    point_labels: bool = False
    label_series: tuple[str, ...] = ()
    series_order: tuple[str, ...] = ()
