"""Render a :class:`~src.models.Dataset` as a GraphPad Prism style figure."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from matplotlib import font_manager, rcParams
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.axes._secondary_axes import SecondaryAxis
from matplotlib.container import BarContainer
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator
from matplotlib.transforms import blended_transform_factory

from src.graphpad_style import (
    DEFAULT_LINE_WIDTH,
    apply_graphpad_style,
    default_color,
    new_figure,
    resolve_font,
)
from src.models import (
    LOG_HEADROOM,
    POINT_MARKERS,
    SOLID_POINTS,
    Y_MAX_HEADROOM,
    Dataset,
    LegendPosition,
    PlotConfig,
    Sample,
    XYSeries,
)

BAR_EDGE = '#000000'
ERROR_COLOR = '#000000'
POINT_FACE = '#ffffff'
BAR_WIDTH = 0.8
BAR_GAP = 0.25
# The extra room left between two groups when the Prism grouped layout is on. Prism marks
# the boundary between groups with roughly three times the space it leaves between bars
# inside a group, which is what the eye reads as "these bars belong together".
INTER_GROUP_GAP = 0.55
BAND_LINE_Y = -0.10
BAND_TEXT_Y = -0.17
BOTTOM_MARGIN = 0.34
TOP_MARGIN = 0.86
# The top of the plot when no legend sits above it, which is the room a legend would have
# taken. Reclaiming it gives the points the height they were losing to an empty band.
NO_LEGEND_TOP_MARGIN = 0.98
# The least the plot may be left with above it, however much the legend and title ask for.
# Anything less leaves a strip of bars too short to read, which is a worse failure than a
# legend that has run out of room.
MIN_TOP_MARGIN = 0.30
# The band one further row of an above-graph legend needs, as a share of the figure
# height. It is measured from the legend's own drawn text at the Prism legend size, where
# one row of eight point names occupies about four hundredths of the figure. The first row
# is already covered by ``TOP_MARGIN``, so this is only what a wrapped row adds.
LEGEND_BAND = 0.041
# The gap left above the plot title, in points, so the text does not touch the top edge of
# the figure. The title hangs down from the top of the figure by this gap and its own height.
TITLE_TOP_GAP = 4.0
# The gap between the legend and the title above it, as a share of the figure height, so the
# two do not read as one block of text.
TITLE_LEGEND_GAP = 0.015
# A line of text is taller than its point size, because of the leading above and below it.
# This converts a text size in points into the share of the figure height it occupies.
TITLE_HEIGHT_FACTOR = 1.4
# The height of a Prism figure in inches. Every margin in this module is a share of it, so a
# measurement given in points has to be converted through it.
FIGURE_HEIGHT = 4.8
FIGURE_WIDTH = 6.4
# The right hand margin a legend beside the plot leaves for itself, as a share of the
# figure width. The names are measured and the rest of the width is the plot's.
LEGEND_RIGHT_MARGIN = 0.80
# The extra room a fully turned set of sample names needs, as a share of the figure. An
# upright label occupies one line of text below the axis; a quarter turn makes it reach
# sideways as well as down, and a right angle needs the height of the name itself.
ROTATION_MARGIN = 0.12
# The legend anchors matplotlib understands, narrowed to the ones this module chooses
# between. The captions in the window say the same thing in words; these are the same
# choices in the form the renderer has to hand over.
LegendLoc = Literal['lower left', 'center left', 'upper right']
# The axes a tick label can sit on, and the anchors a turned label is given so that it stays
# attached to its own tick rather than drifting over its neighbour.
TickAxis = Literal['x', 'y']
HorizontalAlign = Literal['left', 'center', 'right']
# Where each legend position anchors the legend and how many columns of names it lays out.
# ``above`` and ``right`` are anchored outside the plot so they cannot cover a bar, while
# ``inside`` is anchored to the plot itself, which is compact but can cover a tall bar.
LEGEND_PLACEMENTS: dict[LegendPosition, tuple[LegendLoc, tuple[float, float] | None, int]] = {
    'above': ('lower left', (0.0, 1.02), 4),
    'right': ('center left', (1.02, 0.5), 1),
    'inside': ('upper right', None, 4),
}
# The size a bar graph writes its sample names in, unless the x axis text size says
# otherwise. These are the long labels along the bottom, so the default is small enough for
# a handful of them to stay apart under a narrow graph.
SAMPLE_LABEL_FONT = 8
# How far past the right hand edge of the plot a series name starts, as a share of the
# x range. A small gap keeps the name off the last point without wasting the margin.
LABEL_GAP = 0.02
# The most of the figure width the labels may take. Past this the plot is too narrow to
# read, which is a worse failure than a long name running to the edge of the window.
LABEL_MARGIN_CAP = 0.35
# Text size the label width is estimated at, in points. The real size is used when the
# text is drawn; this only decides how much room to leave for it.
DEFAULT_LABEL_SIZE = 9.0
# A horizontal graph puts the group bands and the sample names on the left instead, so the
# room they need is reserved there rather than along the bottom.
LEFT_MARGIN = 0.30
RIGHT_MARGIN = 0.98
# The surrounding canvas reserves enough physical room for the largest supported margins:
# rotated labels and groups on one side, an outside legend or series labels on the other,
# and the renderer's maximum top and bottom bands. These are capacities, not per-graph
# measurements, so moving a legend or adding a title never changes the overall figure size.
CANVAS_LEFT_IN = (LEFT_MARGIN + 2 * ROTATION_MARGIN) * FIGURE_WIDTH
CANVAS_RIGHT_IN = max(LABEL_MARGIN_CAP, 1.0 - LEGEND_RIGHT_MARGIN) * FIGURE_WIDTH
CANVAS_BOTTOM_IN = (BOTTOM_MARGIN + 2 * ROTATION_MARGIN) * FIGURE_HEIGHT
CANVAS_TOP_IN = (1.0 - MIN_TOP_MARGIN) * FIGURE_HEIGHT
# A scatter point is drawn larger than a replicate point, because it is the data itself
# rather than a detail sitting on top of a bar.
DEFAULT_POINT_SIZE = 6.0


@dataclass(frozen=True, slots=True)
class GroupSpan:
    """The horizontal extent covered by one group of conditions.

    Prism marks a group with a line drawn under its conditions rather than by leaving a
    gap, so a group is described by the span of bars it contains.

    Attributes:
        name: Group name shown below the line, empty when the line adds nothing.
        left: Left edge of the first bar in the group.
        right: Right edge of the last bar in the group.
        center: Horizontal midpoint of the span.
        is_single: Whether the group holds exactly one condition.

    """

    name: str
    left: float
    right: float
    center: float
    is_single: bool


def _span_label(group: str, members: tuple[str, ...]) -> str:
    """Return the name to print under a group, or an empty string when it is redundant.

    A group holding a single condition gets no band and no name, because it is not a
    grouping at all: one bar carries one name already, so a second label underneath it
    would either repeat that name or print a different one that appears to claim the bar.
    Prism only draws a group when it holds more than one condition, and this matches it.
    """
    return group if len(members) > 1 else ''


@dataclass(frozen=True, slots=True)
class BarLayout:
    """Horizontal positions of the bars, grouped the way Prism groups them.

    Bars keep a constant width and a constant gap no matter how the samples are grouped,
    so a group holding a single condition takes up exactly as much room as it needs.

    Attributes:
        centers: Bar centre per sample, in plotting order.
        groups: Span of every group, in plotting order.
        width: Width of a single bar.
        left: Left edge of the first bar.
        right: Right edge of the last bar.

    """

    centers: tuple[float, ...]
    groups: tuple[GroupSpan, ...]
    width: float
    left: float
    right: float


def _bar_centers(samples: tuple[Sample, ...], grouped: bool) -> tuple[float, ...]:
    """Return the centre of every bar, leaving extra room between groups when asked.

    Without grouping this is a flat arithmetic sequence. With it, each bar is laid down after
    the previous one and an extra :data:`INTER_GROUP_GAP` is added wherever the group
    changes, so the boundary between two groups is visible without needing a separator line.

    The samples must be in plotting order and already carry their effective group, so a group
    that reappears later is treated as a new run. Grouping is only ever a visual separation:
    the order of the samples themselves is never changed.

    Args:
        samples: Samples in plotting order, each carrying its effective group.
        grouped: Whether to leave the wider gap between groups.

    Returns:
        One centre per sample, in the same order.

    """
    centers: list[float] = []
    position = 0.0
    for index, sample in enumerate(samples):
        if index and grouped and sample.group != samples[index - 1].group:
            position += INTER_GROUP_GAP
        position += BAR_WIDTH / 2
        centers.append(position)
        position += BAR_WIDTH / 2 + BAR_GAP
    return tuple(centers)


def compute_layout(samples: tuple[Sample, ...], groups: tuple[str, ...], grouped: bool = False) -> BarLayout:
    """Spread the samples evenly over the x axis and record the extent of each group.

    Every bar gets the same width and the same gap, which is what removes the large
    empty slots that a fixed per-group width would leave for groups with few conditions.
    Grouping is expressed by :class:`GroupSpan` instead.

    The group of each sample must already reflect any user override, so a merged group is
    drawn as one span rather than as the separate groups it came from.

    Args:
        samples: Samples in plotting order, already carrying their effective group.
        groups: Group names in plotting order.
        grouped: Whether to leave the wider Prism gap between groups.

    Returns:
        The computed bar positions and group spans.

    """
    centers = _bar_centers(samples, grouped)
    spans = tuple(
        GroupSpan(
            name=_span_label(group, tuple(samples[position].name for position in indexes)),
            left=centers[indexes[0]] - BAR_WIDTH / 2,
            right=centers[indexes[-1]] + BAR_WIDTH / 2,
            center=(centers[indexes[0]] + centers[indexes[-1]]) / 2,
            is_single=len(indexes) == 1,
        )
        for group in groups
        if (indexes := [position for position, sample in enumerate(samples) if sample.group == group])
    )

    return BarLayout(
        centers=centers,
        groups=spans,
        width=BAR_WIDTH,
        left=-BAR_WIDTH / 2,
        right=centers[-1] + BAR_WIDTH / 2 if centers else BAR_WIDTH / 2,
    )


def _entry_colors(
    names: Sequence[str],
    positions: Sequence[int],
    total: int,
    config: PlotConfig,
) -> list[str]:
    """Return one colour per entry, honouring explicit overrides and the palette.

    An entry the user coloured by hand keeps that colour. Everything else takes the palette
    colour for its own position, spread across ``total`` entries so a continuous palette runs
    from one end to the other rather than repeating its first few colours.

    Args:
        names: Entry names in drawing order.
        positions: Which palette colour each entry takes.
        total: How many entries share the palette.
        config: User settings holding optional colour overrides.

    Returns:
        A colour per entry, in the same order as ``names``.

    """
    return [
        config.colors[name] if name in config.colors else default_color(position, config.palette, total)
        for name, position in zip(names, positions, strict=True)
    ]


def _colors(samples: tuple[Sample, ...], groups: tuple[str, ...], config: PlotConfig) -> list[str]:
    """Return one colour per sample, honouring explicit overrides and the palette.

    Args:
        samples: Samples in plotting order.
        groups: Group names in plotting order.
        config: User settings holding optional colour overrides.

    Returns:
        A colour per sample, in the same order as ``samples``.

    """
    names = [sample.name for sample in samples]
    if config.color_by == 'group':
        index_of = {name: position for position, name in enumerate(groups)}
        return _entry_colors(names, [index_of[sample.group] for sample in samples], len(groups), config)
    return _entry_colors(names, range(len(samples)), len(samples), config)


def _apply_value_axis(
    ax: Axes,
    samples: tuple[Sample, ...],
    dataset: Dataset,
    config: PlotConfig,
    horizontal: bool = False,
) -> None:
    """Set the value axis range, scale, ticks, label and font sizes.

    A horizontal graph runs its values along the x axis, so the limits, the log scale and the
    tick spacing are all set on that axis instead of the usual one.
    """
    values: list[float] = [value for sample in samples for value in sample.values]
    if config.log_axis:
        positive = [value for value in values if value > 0]
        if positive:
            low = config.y_min if config.y_min is not None else min(positive) / LOG_HEADROOM
            high = config.y_max if config.y_max is not None else max(positive) * LOG_HEADROOM
            if horizontal:
                ax.set_xscale('log')
                ax.set_xlim(low, high)
            else:
                ax.set_yscale('log')
                ax.set_ylim(low, high)
        return _finish_value_axis(ax, dataset, config, horizontal)
    if config.y_min is not None or config.y_max is not None:
        low = config.y_min if config.y_min is not None else 0
        if horizontal:
            ax.set_xlim(low, config.y_max)
        else:
            ax.set_ylim(low, config.y_max)
    else:
        # A bar graph starts at zero, because a bar that begins part way up its axis
        # misstates the value it stands for. The top leaves the Prism headroom above the
        # tallest mean rather than clipping the error bars that sit on it.
        high = max((sample.mean for sample in samples), default=1) * Y_MAX_HEADROOM
        if horizontal:
            ax.set_xlim(0, high)
        else:
            ax.set_ylim(0, high)
    if config.y_major_step:
        if horizontal:
            ax.xaxis.set_major_locator(MultipleLocator(config.y_major_step))
        else:
            ax.yaxis.set_major_locator(MultipleLocator(config.y_major_step))
    return _finish_value_axis(ax, dataset, config, horizontal)


def _finish_value_axis(ax: Axes, dataset: Dataset, config: PlotConfig, horizontal: bool) -> None:
    """Name the value axis and apply the shared line and font settings.

    A blank override falls back to the worksheet label, which is what an emptied field means
    rather than a request to draw the axis with no name at all.
    """
    label = config.y_label or dataset.y_label
    if horizontal:
        ax.set_xlabel(label, fontsize=config.y_label_size)
        ax.set_ylabel('')
    else:
        ax.set_xlabel('')
        ax.set_ylabel(label, fontsize=config.y_label_size)
    ax.grid(False)
    _apply_font_sizes(ax, config)
    _apply_axis_line_width(ax, config)


def _apply_axis_line_width(ax: Axes, config: PlotConfig) -> None:
    """Draw the axis lines and the value axis tick marks at the requested thickness.

    Prism draws the axis line and its tick marks as one visual unit, so both are set
    together. Changing the line while leaving the ticks thin looks like a mistake rather
    than a choice.

    Only the left and bottom spines are touched. The top and right ones are switched off in
    the style, and the secondary x axis that carries the sample names has its own spine,
    which is hidden because the primary one already draws that line.

    Args:
        ax: The axes to restyle.
        config: Settings holding the optional thickness.

    """
    width = config.axis_line_width
    if width is None:
        return
    for spine in (ax.spines['left'], ax.spines['bottom']):
        spine.set_linewidth(width)
    ax.tick_params(axis='y', which='major', width=width)


def _apply_font_sizes(ax: Axes, config: PlotConfig) -> None:
    """Apply the requested font sizes to the axis tick labels and the title.

    Each axis is sized by its own setting where it has one, and by the shared
    ``font_size`` otherwise. That fallback is what keeps a file written before the axes
    could be sized apart, and a caller that only sets the shared size, drawn exactly as it
    was rather than as one axis silently reverting to the default.

    Args:
        ax: The axes to restyle.
        config: Settings holding the optional sizes.

    """
    # Both axes carry tick labels, and on a scatter plot the x axis carries the independent
    # variable, so an axis with no size of its own still follows the shared one.
    y_size = config.y_font_size or config.font_size
    x_size = config.x_font_size or config.font_size
    if y_size:
        ax.tick_params(axis='y', labelsize=y_size)
    if x_size:
        ax.tick_params(axis='x', labelsize=x_size)
    if config.title_size:
        ax.title.set_fontsize(config.title_size)


def legend_above(config: PlotConfig) -> bool:
    """Return whether the legend is drawn in a band above the plotting area.

    Only that placement takes room away from the top of the plot, so it is what decides
    both how far down the axes start and how much clearance the title needs.

    Args:
        config: Settings deciding whether and where the legend is drawn.

    Returns:
        ``True`` when the legend sits above the plot.

    """
    return config.show_legend and config.legend_position == 'above'


def legend_entries(samples: tuple[Sample, ...], config: PlotConfig) -> int:
    """Return how many names a bar graph's legend lists.

    A grouped graph names each group once rather than repeating it for every bar in it, so
    the legend is shorter than the list of bars and the band it needs is shorter too.

    Args:
        samples: Samples in plotting order.
        config: Settings holding the grouped layout choice.

    Returns:
        The number of entries the legend will carry.

    """
    if not config.grouped_layout:
        return len(samples)
    return len({sample.group for sample in samples})


def legend_rows(entries: int, config: PlotConfig) -> int:
    """Return how many rows a legend of this many entries is drawn in.

    A legend above the plot is laid out in as many columns as it has room for and wraps onto
    a further row when the names do not all fit. The title has to clear the whole of it, so
    the number of rows is what sizes the band the plot gives up.

    Args:
        entries: How many names the legend lists.
        config: Settings deciding whether the legend is drawn and where.

    Returns:
        The row count, or ``0`` when there is no legend above the plot to make room for.

    """
    if not legend_above(config) or entries <= 0:
        return 0
    columns = LEGEND_PLACEMENTS[config.legend_position][2]
    return -(-entries // max(columns, 1))


def _top_margin(config: PlotConfig, rows: int = 1) -> float:
    """Return where the top of the plotting area sits, as a share of the figure height.

    The plot gives up the band a legend above it needs, one band per row, and the band a
    title needs on top of that. A graph with neither keeps the margins it has always had, so
    an untitled graph without a legend is drawn exactly as it was.

    The result is clamped so the plot is never left with no height at all. A sheet with a
    great many samples would otherwise ask for more band than the figure has, and
    ``subplots_adjust`` rejects a bottom at or above the top outright rather than drawing
    something squeezed. Losing height to the legend is the lesser failure.

    Args:
        config: Settings holding the title, the legend and where the legend sits.
        rows: How many rows the legend above the plot is drawn in.

    Returns:
        The top margin for :meth:`~matplotlib.figure.Figure.subplots_adjust`.

    """
    # ``TOP_MARGIN`` already reserves the room one legend row takes, so only the rows beyond
    # the first are taken off it. That keeps a one row legend drawn exactly as it always was.
    # A titled graph gives up the title's own height as well, so the title has room to sit in
    # rather than having to be pushed against the top edge.
    extra = LEGEND_BAND * (max(rows, 1) - 1) if legend_above(config) else 0.0
    top = (TOP_MARGIN - extra) if legend_above(config) else NO_LEGEND_TOP_MARGIN
    if config.title:
        # The title hangs above the legend and is as tall as the text size asks for, so the
        # plot gives up that much as well. Measuring it here rather than assuming the default
        # is what lets a large title still fit above a legend that already fills the band.
        top -= _title_height(config) + TITLE_LEGEND_GAP + TITLE_TOP_GAP / 72.0 / FIGURE_HEIGHT
    # Enough is always left for the axes and the room the group bands need below them.
    return max(top, MIN_TOP_MARGIN)


def _right_margin(config: PlotConfig) -> float:
    """Return where the right edge of the plotting area sits, as a share of the width.

    A legend beside the plot is drawn outside it, so the plot gives up the width the names
    need. Every other placement, including a horizontal graph, keeps the full width it has
    always had.

    Args:
        config: Settings deciding whether and where the legend is drawn.

    Returns:
        The right margin for :meth:`~matplotlib.figure.Figure.subplots_adjust`.

    """
    if config.show_legend and config.legend_position == 'right':
        return LEGEND_RIGHT_MARGIN
    return RIGHT_MARGIN


def _bottom_margin(config: PlotConfig) -> float:
    """Return where the bottom of the plotting area sits, as a share of the height.

    Turning the sample names makes them taller, because the text now reaches up and to the
    side rather than straight down, so the room below the plot has to grow with the turn. An
    upright graph keeps the margin it has always had.

    Args:
        config: Settings holding the label rotation.

    Returns:
        The bottom margin for :meth:`~matplotlib.figure.Figure.subplots_adjust`.

    """
    return BOTTOM_MARGIN + ROTATION_MARGIN * abs(config.label_rotation) / 90.0


def _left_margin(config: PlotConfig) -> float:
    """Return where the left edge of the plotting area sits, as a share of the width.

    A horizontal graph lays the sample names down the side, and turning them widens that
    column, so the margin grows with the turn for the same reason the bottom one does.

    Args:
        config: Settings holding the label rotation.

    Returns:
        The left margin for :meth:`~matplotlib.figure.Figure.subplots_adjust`.

    """
    return LEFT_MARGIN + ROTATION_MARGIN * abs(config.label_rotation) / 90.0


def _apply_title(fig: Figure, ax: Axes, config: PlotConfig) -> None:
    """Write the plot title above the graph, inside the figure.

    The title is placed in figure coordinates rather than as the axes title. With a legend
    above the graph it is hung above the legend; without one it sits just above the axes.

    Where it hangs is measured from the legend itself rather than worked out from the margins.
    A legend's height depends on how many rows its names wrap onto and on the font they are
    written in, neither of which the margins know: estimating it left the title printed across
    the legend names as soon as there were more than a handful of samples. Measuring the drawn
    legend is what makes the two keep apart however long the names are.

    Args:
        fig: The figure the title belongs to.
        ax: The axes whose width the title is centred over.
        config: Settings holding the title text, its position and its font.

    """
    if not config.title:
        return
    legend = ax.get_legend() if legend_above(config) else None
    height = _title_height(config)
    figure_height = float(fig.get_size_inches()[1])
    title_height_in = height * FIGURE_HEIGHT
    ceiling = 1.0 - (TITLE_TOP_GAP / 72.0 + title_height_in) / figure_height
    if legend is None:
        # The plot takes back the legend band when there is no legend, so the title follows
        # the plot instead of staying behind at the top edge of the figure.
        axes_top = ax.get_position().y1
        bottom = axes_top + TITLE_LEGEND_GAP * FIGURE_HEIGHT / figure_height
        bottom = min(bottom, ceiling)
    else:
        # The legend is drawn in the band above the plot, so its own top edge is where the
        # title has to start. The figure is drawn first, because the legend's extent is only
        # known once it has been laid out.
        fig.canvas.draw()
        legend_top = legend.get_window_extent().y1 / fig.bbox.height
        bottom = min(legend_top + TITLE_LEGEND_GAP * FIGURE_HEIGHT / figure_height, ceiling)
    text = fig.text(
        (ax.get_position().x0 + ax.get_position().x1) / 2,
        bottom,
        config.title,
        ha='center',
        va='bottom',
        fontsize=rcParams['axes.titlesize'],
    )
    if config.title_size:
        text.set_fontsize(config.title_size)
    if config.title_font:
        text.set_fontfamily(_usable_font(config.title_font))
    # The axes title is cleared so a title is never drawn twice, once here and once there.
    ax.set_title('')


def _fix_axes_dimensions(fig: Figure, ax: Axes, config: PlotConfig) -> None:
    """Grow the figure around the requested physical plotting-area dimensions.

    The axes position already accounts for the margins reserved by the renderer. Scaling the
    whole figure from that final position keeps the axes at their chosen physical size while
    leaving those margins and their artists outside the plot.

    Args:
        fig: Figure whose overall size is to be adjusted.
        ax: Axes whose physical width and height are fixed.
        config: Settings holding the requested lengths in centimeters.

    Raises:
        ValueError: If either requested length is not a finite positive number.

    """
    position = ax.get_position()
    width, height = position.width, position.height
    if width <= 0 or height <= 0:
        raise ValueError('The plot margins leave no room for the axes.')
    figure_width, figure_height = _canvas_size(config)
    left_in = position.x0 * FIGURE_WIDTH
    bottom_in = position.y0 * FIGURE_HEIGHT
    axis_width_in = config.x_axis_length_cm / 2.54
    axis_height_in = config.y_axis_length_cm / 2.54
    if left_in + axis_width_in > figure_width or bottom_in + axis_height_in > figure_height:
        raise ValueError('The reserved plot margins exceed the available figure canvas.')
    fig.set_size_inches(figure_width, figure_height)
    ax.set_position(
        (
            left_in / figure_width,
            bottom_in / figure_height,
            axis_width_in / figure_width,
            axis_height_in / figure_height,
        )
    )


def _canvas_size(config: PlotConfig) -> tuple[float, float]:
    """Return the fixed overall figure size for the configured axes and margin capacities.

    Args:
        config: Settings holding the requested physical axis lengths.

    Returns:
        Figure width and height in inches.

    Raises:
        ValueError: If either requested length is not a finite positive number.

    """
    width_cm = config.x_axis_length_cm
    height_cm = config.y_axis_length_cm
    if not math.isfinite(width_cm) or width_cm <= 0:
        raise ValueError('The X axis length must be a finite positive number of centimeters.')
    if not math.isfinite(height_cm) or height_cm <= 0:
        raise ValueError('The Y axis length must be a finite positive number of centimeters.')
    return (
        CANVAS_LEFT_IN + width_cm / 2.54 + CANVAS_RIGHT_IN,
        CANVAS_BOTTOM_IN + height_cm / 2.54 + CANVAS_TOP_IN,
    )


def _empty_figure(config: PlotConfig) -> Figure:
    """Create a blank figure using the same fixed canvas as a graph with these settings."""
    return new_figure(*_canvas_size(config))


def _title_height(config: PlotConfig) -> float:
    """Return the height the plot title occupies, as a share of the figure height.

    The title is hung from the top of the figure, so only its own height is needed here:
    where it sits relative to the legend is settled by the band the plot gave up for that.

    Args:
        config: Settings holding the title, its size and its font.

    Returns:
        The height of one line of title text, in figure coordinates.

    """
    size = config.title_size or rcParams['axes.titlesize']
    # A point size is a height on the page, and a figure fraction is a share of the page, so
    # the text height is converted through the figure's own height in inches. Dividing by the
    # number of points to an inch alone would be correct only for a one inch tall figure.
    return float(size) * TITLE_HEIGHT_FACTOR / 72.0 / FIGURE_HEIGHT


def _usable_font(family: str) -> str:
    """Return a font family matplotlib can actually draw with.

    A family that is not installed is silently replaced by the default one, which would
    leave the field showing a choice the graph ignored. Falling back to the family Prism
    prefers keeps the rest of the figure consistent, and the choice stays visible in the
    window as the one that was asked for.

    Args:
        family: The font family chosen in the window.

    Returns:
        The family to draw with, which is the one chosen when it is available.

    """
    available = {font.name for font in font_manager.fontManager.ttflist}
    return family if family in available else resolve_font()


def _point_marks(config: PlotConfig, name: str, color: str) -> tuple[str, str]:
    """Return the marker a point is drawn with and the colour inside it.

    The shape is the one chosen for that series or sample where one was, and the whole
    graph's shape otherwise, so a graph can be set at once and a single series pulled out of
    it afterwards without the rest having to be chosen again.

    Prism draws a point as an open symbol, so the shape is a choice about the outline and the
    centre is left the colour of the page. A cross and a star are strokes with no interior to
    leave white, and drawn open they are two bare lines that vanish against the page, so those
    are filled with the colour of the point itself.

    Args:
        config: Settings holding the chosen shapes.
        name: Name of the sample or scatter series the point belongs to.
        color: The colour the point is drawn in.

    Returns:
        The marker and the colour to fill it with.

    """
    point_type = config.point_types.get(name, config.point_type)
    marker = POINT_MARKERS[point_type]
    fill = color if point_type in SOLID_POINTS else POINT_FACE
    return marker, fill


def _legend_handles(
    names: Sequence[str],
    group_names: Sequence[str],
    colors: list[str],
    grouped: bool,
) -> list[Patch]:
    """Return the legend swatches, one per sample or one per group.

    In the Prism grouped layout a condition such as an age band repeats inside every group,
    so listing one entry per bar would print the same label several times. The legend then
    names each group once instead, and the swatch takes the colour of the group's first bar,
    which is the colour the whole group carries when colours follow groups.

    A scatter series is named the way a sample is, so one function serves both graphs.

    Args:
        names: Name of each sample or scatter series in plotting order.
        group_names: Group of each entry, which is its own name for a scatter series.
        colors: Fill colour per entry, positionally matching ``names``.
        grouped: Whether the legend should name groups rather than individual entries.

    Returns:
        The swatches to hand to the legend.

    """
    if not grouped:
        return [
            Patch(facecolor=color, edgecolor=BAR_EDGE, label=name)
            for name, color in zip(names, colors, strict=True)
        ]

    handles: list[Patch] = []
    seen: set[str] = set()
    for group, color in zip(group_names, colors, strict=True):
        if group in seen:
            continue
        seen.add(group)
        handles.append(Patch(facecolor=color, edgecolor=BAR_EDGE, label=group))
    return handles


def _add_legend(
    ax: Axes,
    names: Sequence[str],
    group_names: Sequence[str],
    colors: list[str],
    legend_size: int | None = None,
    grouped: bool = False,
    position: LegendPosition = 'above',
    legend_font: str | None = None,
) -> None:
    """Add a frameless legend naming either every entry or every group.

    Where it sits is the user's choice. Above the plot and beside it both keep the names
    clear of the bars, the first by giving the plot a band at the top and the second by
    narrowing it; the third sits on the plot, which is compact but can cover a tall bar.

    Args:
        ax: The axes to add the legend to.
        names: Name of each sample or scatter series in plotting order.
        group_names: Group of each entry, which is its own name for a scatter series.
        colors: Fill colour per entry.
        legend_size: Optional text size, or ``None`` for the Prism default.
        grouped: Whether the legend names groups rather than individual entries.
        position: Where the legend sits relative to the plot.
        legend_font: Optional font family for the names, or ``None`` for the figure family.

    """
    handles = _legend_handles(names, group_names, colors, grouped)
    loc, anchor, columns = LEGEND_PLACEMENTS[position]
    legend = ax.legend(
        handles=handles,
        loc=loc,
        bbox_to_anchor=anchor,
        ncol=min(len(handles), columns),
        borderaxespad=0.0,
        columnspacing=1.4,
        handlelength=1.6,
        fontsize=legend_size,
    )
    if legend_font:
        family = _usable_font(legend_font)
        for text in legend.get_texts():
            text.set_fontfamily(family)


def tag_bars(figure: Figure, bars: BarContainer, names: Sequence[str]) -> None:
    """Record which sample each bar belongs to, so a click can select it.

    The mapping is stored on the figure because the bars are rebuilt on every redraw and a
    Tk click event carries no reference to the artist it hit.

    Each patch is also made pickable. Without that, matplotlib never emits a ``pick_event``
    for it and the window has nothing to react to, so the mapping would sit on the figure
    unread. A rectangle is picked by point containment, so no pick radius is needed and the
    clickable area is exactly the bar.

    Args:
        figure: The figure the bars were drawn on.
        bars: The container returned by ``Axes.bar``.
        names: Sample names in the same order as the bars.

    """
    tag_artists(figure, bars.patches, names)


def tag_artists(figure: Figure, artists: Iterable[Artist], names: Sequence[str]) -> None:
    """Map each artist to its sample name and make it clickable.

    The replicate points are drawn on top of their bar, so they are tagged as well: a click
    that lands on a point would otherwise miss the bar underneath it, since the point is the
    artist actually under the cursor.

    Existing entries are kept rather than replaced, so the bars and the points can be
    tagged independently on the same figure.

    Args:
        figure: The figure the artists were drawn on.
        artists: Artists to make clickable, such as a bar's patches or a points line.
        names: Sample names, positionally matching ``artists``.

    """
    mapping: dict[int, str] = dict(getattr(figure, 'sample_by_bar', {}))
    for artist, name in zip(artists, names, strict=False):
        artist.set_picker(True)
        mapping[id(artist)] = name
    figure.sample_by_bar = mapping  # type: ignore[attr-defined]


def _add_group_bands(
    ax: Axes,
    layout: BarLayout,
    line_width: float = DEFAULT_LINE_WIDTH,
    horizontal: bool = False,
) -> None:
    """Draw the Prism group markers beside the sample names.

    Each group gets a plain line spanning its conditions and its name centred on it. Lines
    that would carry no information, meaning a group whose only bar is already labelled with
    the group name, are skipped.

    The line follows the data on whichever axis the bars are laid out along and uses axes
    fractions on the other, which places it outside the plotting area while keeping it
    aligned with the bars it describes.

    Args:
        ax: The axes to add the bands to.
        layout: Bar positions and group spans.
        line_width: Thickness of the band lines in points.
        horizontal: Whether the bars run along the x axis instead of the y axis.

    """
    transform = (
        blended_transform_factory(ax.transAxes, ax.transData)
        if horizontal
        else blended_transform_factory(ax.transData, ax.transAxes)
    )
    for span in layout.groups:
        if not span.name:
            continue
        if horizontal:
            ax.plot(
                [BAND_LINE_Y, BAND_LINE_Y],
                [span.left, span.right],
                transform=transform,
                clip_on=False,
                color=BAR_EDGE,
                linewidth=line_width,
                zorder=2,
            )
            ax.text(
                BAND_TEXT_Y,
                span.center,
                span.name,
                transform=transform,
                clip_on=False,
                ha='right',
                va='center',
                rotation=90,
                fontsize=10,
            )
            continue
        ax.plot(
            [span.left, span.right],
            [BAND_LINE_Y, BAND_LINE_Y],
            transform=transform,
            clip_on=False,
            color=BAR_EDGE,
            linewidth=line_width,
            zorder=2,
        )
        ax.text(
            span.center,
            BAND_TEXT_Y,
            span.name,
            transform=transform,
            clip_on=False,
            ha='center',
            va='top',
            fontsize=10,
        )


def _add_sample_labels(
    ax: Axes,
    layout: BarLayout,
    samples: tuple[Sample, ...],
    horizontal: bool = False,
    label_size: int | None = None,
    rotation: float = 0.0,
) -> None:
    """Label each bar with its condition name on a tickless secondary axis.

    The group names are not repeated here; they are drawn by :func:`_add_group_bands`.
    A sample that is named after its group keeps its name, because that name is the only
    description the bar gets.

    A horizontal graph labels down the left hand side instead of along the bottom, so the
    names have room to be read rather than being squeezed under a narrow plot.

    The names are the x axis labels of a bar graph, so they are sized by the x axis text
    size. They are the long labels that start to overlap once there are more than a few
    samples, which is why that size is worth having on its own, and why they may be turned
    to make room for one another.

    The labels live on a secondary axis, which is created here and then discarded. The
    rotation therefore has to be applied while it is still in hand: it cannot be reached
    through the primary axes afterwards, because a later call to ``secondary_xaxis`` builds
    a new axis rather than returning this one.
    """
    size = label_size or SAMPLE_LABEL_FONT
    names = [sample.name for sample in samples]
    if horizontal:
        ax.set_yticks([])
        ax.tick_params(axis='y', length=0)
        secondary = ax.secondary_yaxis('left')
        secondary.set_yticks(list(layout.centers), labels=names)
        secondary.tick_params(axis='y', length=0, pad=2, labelsize=size)
        secondary.spines['left'].set_visible(False)
        _rotate_labels(secondary, 'y', rotation)
        return
    ax.set_xticks([])
    ax.tick_params(axis='x', length=0)
    secondary = ax.secondary_xaxis('bottom')
    secondary.set_xticks(list(layout.centers), labels=names)
    secondary.tick_params(axis='x', length=0, pad=2, labelsize=size)
    secondary.spines['bottom'].set_visible(False)
    _rotate_labels(secondary, 'x', rotation)


def _rotate_labels(axes: SecondaryAxis, axis: TickAxis, rotation: float) -> None:
    """Turn a set of tick labels, anchoring them so they stay under their own bar.

    Matplotlib rotates a label about its centre, which at forty five degrees leaves the top
    of the text leaning over the neighbouring bar. Pulling the anchor back to the tick mark
    keeps each name attached to the bar it belongs to, which is the whole point of the
    setting.

    Args:
        axes: The secondary axes carrying the labels.
        axis: Which of their axes the labels sit on.
        rotation: How far to turn them, in degrees. ``0.0`` leaves them as they are.

    """
    if not rotation:
        return
    axes.tick_params(axis=axis, labelrotation=rotation)
    align: HorizontalAlign = 'right' if rotation > 0 else 'left'
    labels = axes.get_xticklabels() if axis == 'x' else axes.get_yticklabels()
    for label in labels:
        label.set_horizontalalignment(align)


def _grouped_samples(samples: tuple[Sample, ...], config: PlotConfig) -> tuple[Sample, ...]:
    """Return the samples with any user group override applied.

    Overriding a group never changes the data read from the worksheet, so the original
    grouping is recovered by simply dropping the override.

    Args:
        samples: Samples in plotting order.
        config: Settings holding the per-sample group overrides.

    Returns:
        The same samples, with ``group`` replaced wherever an override exists.

    """
    return tuple(
        sample
        if sample.name not in config.group_overrides
        else replace(sample, group=config.group_overrides[sample.name])
        for sample in samples
    )


def plot_dataset(dataset: Dataset, config: PlotConfig | None = None) -> Figure:
    """Draw the graph described by ``config``, choosing between a bar and a scatter plot.

    A bar graph summarises a column of replicates: bars are grouped by ``Sample.group`` and
    sub spaced by condition, each bar carries a mean with error bars, and every replicate is
    drawn on top as an open circle. A scatter plot instead draws the paired x and y values
    read from the sheet, one point per row.

    Args:
        dataset: The parsed experiment.
        config: Optional presentation settings; defaults are used when omitted.

    Returns:
        A styled matplotlib figure.

    """
    settings = config or PlotConfig()
    if settings.chart == 'scatter':
        return plot_scatter(dataset, settings)
    return plot_bars(dataset, settings)


def plot_bars(dataset: Dataset, config: PlotConfig | None = None) -> Figure:
    """Draw a grouped bar graph with individual replicate points, Prism style.

    Args:
        dataset: The parsed experiment.
        config: Optional presentation settings; defaults are used when omitted.

    Returns:
        A styled matplotlib figure, or an empty one when the sheet held no samples.

    """
    settings = config or PlotConfig()
    samples = dataset.ordered(settings.sample_order)
    if not samples:
        return _empty_figure(settings)

    apply_graphpad_style()
    fig = new_figure()
    ax: Axes = fig.add_subplot()
    grouped = _grouped_samples(samples, settings)
    groups = tuple(dict.fromkeys(sample.group for sample in grouped))
    layout = compute_layout(grouped, groups, settings.grouped_layout)
    colors = _colors(samples, groups, settings)
    horizontal = settings.orientation in ('horizontal', 'inverted')

    means = [sample.mean for sample in samples]
    bar_width = settings.bar_line_width or DEFAULT_LINE_WIDTH
    edges = [settings.edge_colors.get(sample.name, BAR_EDGE) for sample in samples]
    hatches = [settings.hatches.get(sample.name, '') for sample in samples]
    if horizontal:
        bars = ax.barh(
            list(layout.centers),
            means,
            height=layout.width,
            color=colors,
            edgecolor=edges,
            hatch=hatches,
            linewidth=bar_width,
            align='center',
            zorder=2,
        )
    else:
        bars = ax.bar(
            list(layout.centers),
            means,
            width=layout.width,
            color=colors,
            edgecolor=edges,
            hatch=hatches,
            linewidth=bar_width,
            align='center',
            zorder=2,
        )
    tag_bars(fig, bars, [sample.name for sample in samples])

    errors = [sample.error(settings.error_kind) for sample in samples]
    # The error bars are drawn along whichever axis the values run down, so the caps stay
    # square to the bars rather than being laid on their side.
    if horizontal:
        ax.errorbar(
            means,
            list(layout.centers),
            xerr=errors,
            fmt='none',
            ecolor=ERROR_COLOR,
            elinewidth=bar_width,
            capsize=3.0,
            capthick=bar_width,
            zorder=4,
        )
    else:
        ax.errorbar(
            list(layout.centers),
            means,
            yerr=errors,
            fmt='none',
            ecolor=ERROR_COLOR,
            elinewidth=bar_width,
            capsize=3.0,
            capthick=bar_width,
            zorder=4,
        )

    if settings.show_points:
        for center, sample, color in zip(layout.centers, samples, colors, strict=True):
            offsets = [
                center + _jitter_offset(index, sample.n, settings.jitter) * layout.width for index in range(sample.n)
            ]
            # The points sit on their own bar, so the axis the bars are measured along carries
            # the centre and the other axis carries the value being measured. Swapping these
            # two would plot the values along the bar axis and stretch the graph to fit them.
            along, across = (list(sample.values), offsets) if horizontal else (offsets, list(sample.values))
            marker, fill = _point_marks(settings, sample.name, color)
            points = ax.plot(
                along,
                across,
                linestyle='none',
                # The colour is given explicitly rather than left to the cycle, so a replicate
                # point is the colour of its own bar even though it draws no line.
                color=color,
                marker=marker,
                markersize=4.0,
                markerfacecolor=fill,
                markeredgecolor=color,
                markeredgewidth=1.0,
                zorder=5,
            )
            # The points sit on top of their own bar, so they carry the sample name too and
            # a click on a point selects the same sample as a click on the bar beneath it.
            tag_artists(fig, points, [sample.name])

    _apply_value_axis(ax, samples, dataset, settings, horizontal)
    # The sample names are the x axis labels of a bar graph, so they follow the x axis text
    # size. A horizontal graph lays them down the side, which is still the x axis turned on
    # its side, so the same size applies either way round.
    _add_sample_labels(ax, layout, samples, horizontal, settings.x_font_size, settings.label_rotation)
    _add_group_bands(ax, layout, bar_width, horizontal)
    # The axis the bars are laid out along is pinned to their span rather than left to
    # autoscale. Matplotlib sizes a bar chart correctly on its own, but any artist that
    # reaches further out, such as a replicate point drawn at the wrong coordinate, would
    # otherwise stretch the graph and squeeze every bar into a corner.
    if horizontal:
        ax.set_ylim(layout.left, layout.right)
    else:
        ax.set_xlim(layout.left, layout.right)
    if settings.show_legend:
        _add_legend(
            ax,
            [sample.name for sample in samples],
            [sample.group for sample in samples],
            colors,
            settings.legend_size,
            settings.grouped_layout,
            settings.legend_position,
            settings.legend_font,
        )
    # The group bands are drawn outside the axes, so tight_layout cannot account for them
    # and the room for them is reserved explicitly, on whichever side they are drawn.
    rows = legend_rows(legend_entries(samples, settings), settings)
    if horizontal:
        fig.subplots_adjust(
            left=_left_margin(settings),
            right=_right_margin(settings),
            top=_top_margin(settings, rows),
        )
    else:
        fig.subplots_adjust(
            bottom=_bottom_margin(settings),
            right=_right_margin(settings),
            top=_top_margin(settings, rows),
        )
    # The title is written last, because it is placed from the margins just set rather than
    # from the axes, and those are only final here.
    _fix_axes_dimensions(fig, ax, settings)
    _apply_title(fig, ax, settings)
    return fig


def _jitter_offset(index: int, total: int, jitter: float) -> float:
    """Return a symmetric horizontal offset in bar widths for replicate ``index``."""
    if not jitter or total < 2:
        return 0.0
    return (index - (total - 1) / 2) * jitter


def plot_scatter(dataset: Dataset, config: PlotConfig | None = None) -> Figure:
    """Draw the paired x and y values of a scatter sheet as Prism style points.

    One series is drawn per y column, each in its own palette colour and each named in the
    legend, which is the way a bar graph names its samples. A click on a point selects the
    series it belongs to, because every point carries its series name.

    A scatter plot has no bars, so it has no mean, no error bars and no zero baseline: the
    axis is framed around the points instead, because a point has no length that a baseline
    would have to start from.

    Args:
        dataset: The parsed experiment, whose ``series`` hold the points.
        config: Optional presentation settings; defaults are used when omitted.

    Returns:
        A styled matplotlib figure, or an empty one when the sheet held no points.

    """
    settings = config or PlotConfig()
    series = dataset.ordered_series(settings.series_order)
    if not series or not dataset.points:
        return _empty_figure(settings)

    apply_graphpad_style()
    fig = new_figure()
    ax: Axes = fig.add_subplot()
    names = [one.name for one in series]
    colors = _series_colors(names, settings)
    size = settings.point_size or DEFAULT_POINT_SIZE
    width = settings.bar_line_width or DEFAULT_LINE_WIDTH

    connected = _connected_series(names, settings)
    for one, color in zip(series, colors, strict=True):
        marker, fill = _point_marks(settings, one.name, color)
        line = ax.plot(
            [point.x for point in one.points],
            [point.y for point in one.points],
            linestyle='-' if one.name in connected else 'none',
            # The line is given the series colour explicitly. Left to itself matplotlib picks
            # the next colour off its cycle, which is not the colour of the points it joins,
            # and a traced series then reads as a different series from the one it traces.
            color=color,
            marker=marker,
            markersize=size,
            markerfacecolor=fill,
            markeredgecolor=color,
            markeredgewidth=width,
            zorder=3,
        )
        # Every point carries the series name, so a click on any of them selects the series
        # it belongs to in the same way a click on a bar selects its sample.
        tag_artists(fig, line, [one.name])

    if settings.log_axis:
        positive = [point.y for one in series for point in one.points if point.y > 0]
        if positive:
            ax.set_yscale('log')
            ax.set_ylim(
                settings.y_min if settings.y_min is not None else min(positive) / LOG_HEADROOM,
                settings.y_max if settings.y_max is not None else max(positive) * LOG_HEADROOM,
            )
    elif settings.y_max is not None:
        # The log branch above sets the limits, so this is the linear case that was left
        # with no way to set a top. A typed Y max that silently does nothing reads as a
        # broken control rather than as a value the graph ignored.
        points = [point.y for one in series for point in one.points]
        ax.set_ylim(settings.y_min if settings.y_min is not None else min(points), settings.y_max)
    if config_y_step := settings.y_major_step:
        ax.yaxis.set_major_locator(MultipleLocator(config_y_step))
    # The x axis is the scatter plot's own to frame, and it carries the same two controls
    # the value axis does. The lower end is left to matplotlib, which pads the points
    # sensibly; only the top and the tick spacing are the user's to set.
    if settings.x_max is not None:
        ax.set_xlim(left=ax.get_xlim()[0], right=settings.x_max)
    if settings.x_major_step:
        ax.xaxis.set_major_locator(MultipleLocator(settings.x_major_step))
    _finish_value_axis(ax, dataset, settings, horizontal=False)
    # The x label is written after the shared axis finishing, because that helper clears the
    # x label for a bar graph, where the samples are named along that axis instead.
    ax.set_xlabel(settings.x_label_override or dataset.x_label)
    if settings.show_legend:
        _add_legend(
            ax,
            names,
            names,
            colors,
            settings.legend_size,
            grouped=False,
            position=settings.legend_position,
            legend_font=settings.legend_font,
        )
    labelled = _add_series_labels(ax, series, colors, settings) if settings.point_labels else []
    rows = legend_rows(len(names), settings)
    fig.subplots_adjust(
        bottom=BOTTOM_MARGIN,
        right=_right_margin(settings),
        top=_top_margin(settings, rows),
    )
    if labelled:
        margins = _label_margins(fig, ax, labelled)
        if not legend_above(settings):
            # The legend sits in a band above the plot only in that one position, so only
            # without one may the plot take that band back. Otherwise the plot keeps out of
            # the legend's way.
            margins['top'] = _top_margin(settings, rows)
        if settings.show_legend and settings.legend_position == 'right':
            # A legend beside the plot already claims the right hand margin, so the labels
            # are not allowed to shrink the plot a second time for the same space.
            margins.pop('right', None)
        fig.subplots_adjust(**margins)
    _fix_axes_dimensions(fig, ax, settings)
    # The title is written last, because it is placed from the margins just set rather than
    # from the axes, and those are only final here.
    _apply_title(fig, ax, settings)
    return fig


def _add_series_labels(
    ax: Axes,
    series: Sequence[XYSeries],
    colors: Sequence[str],
    settings: PlotConfig,
) -> list[str]:
    """Name each chosen series beside its rightmost point, clear of the plot.

    Every label starts at the same x, just beyond the edge of the plotting area, so the
    names line up as a column rather than trailing off at whatever the last point of each
    series happened to be. That is also why the label is anchored to the right of the axes
    rather than to its own point: a series that ends early would otherwise print its name
    in the middle of the graph.

    Labels can overlap when two series finish at a similar height, which is why the user
    chooses which series are named rather than being given all of them.

    Args:
        ax: The axes to write into.
        series: The series in drawing order.
        colors: Fill colour per series, positionally matching ``series``.
        settings: User settings naming the series to label and the text size.

    Returns:
        The labels actually drawn, for reserving the margin they need.

    """
    chosen = [one for one in series if one.name in set(settings.label_series)]
    if not chosen:
        return []
    low, high = ax.get_xlim()
    size = settings.legend_size or rcParams['font.size']
    drawn: list[str] = []
    chosen_names = [one.name for one in chosen]
    for one, color in zip(chosen, _series_colors(chosen_names, settings), strict=True):
        last = max(one.points, key=lambda point: point.x)
        ax.text(
            high + (high - low) * LABEL_GAP,
            last.y,
            one.name,
            ha='left',
            va='center',
            color=color,
            fontsize=size,
            clip_on=False,
            zorder=4,
        )
        drawn.append(one.name)
    return drawn


def _label_margins(fig: Figure, ax: Axes, labels: Sequence[str]) -> dict[str, float]:
    """Return the ``right`` margin a set of right hand labels needs.

    The width is measured from the text itself rather than guessed from the character
    count, because the font is the reader's own and a name may be anything. The cap keeps
    one very long name from squeezing the plot into a sliver, since a graph that has
    nowhere to draw is worse than one whose labels reach the edge of the window.

    Args:
        fig: The figure the labels will be drawn on.
        ax: The axes holding the plot, used for its current width.
        labels: The labels being drawn.

    Returns:
        Keyword arguments for ``subplots_adjust``.

    """
    # A character is about 0.6 of the text size wide, so the longest name gives a width in
    # points, which is turned into a share of the figure and taken off the right margin the
    # plot already has. Measuring against the margin in use rather than a fixed constant is
    # what keeps the labels inside the figure for a scatter plot, which has no reserved room.
    longest = max(labels, key=len)
    needed_in = len(longest) * DEFAULT_LABEL_SIZE * 0.6 / 72.0
    share = min(needed_in / float(fig.get_size_inches()[0]), LABEL_MARGIN_CAP)
    current = ax.get_position().x1
    return {'right': max(current - share, 1.0 - LABEL_MARGIN_CAP)}


def _connected_series(names: Sequence[str], settings: PlotConfig) -> frozenset[str]:
    """Return the names of the series whose points are joined by a line.

    The all or nothing setting is kept, because joining every series is what it always
    meant and it is the quickest way to trace all of them at once. A series named in
    ``connect_series`` is joined whatever that setting says, so one series can be traced
    through its points while the rest stay as separate marks. A name that is no longer
    plotted is ignored rather than failing, which is what lets a removed column leave its
    setting behind harmlessly.

    Args:
        names: Every series name in drawing order.
        settings: User settings naming the series to join.

    Returns:
        The names of the series to draw with a line.

    """
    known = set(names)
    chosen = set(settings.connect_series) & known
    if settings.connect_points:
        return frozenset(known)
    return frozenset(chosen)


def _series_colors(names: list[str], config: PlotConfig) -> list[str]:
    """Return one colour per scatter series, honouring overrides and the palette.

    A scatter series is its own thing rather than a member of a group, so ``color_by`` does
    not apply here and every series is coloured by its own position.

    Args:
        names: Series names in drawing order.
        config: User settings holding optional colour overrides.

    Returns:
        A colour per series, in the same order as ``names``.

    """
    return _entry_colors(names, range(len(names)), len(names), config)
