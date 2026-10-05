"""Tests for the Prism style rendering and the command line entry point."""

from __future__ import annotations

import itertools
from dataclasses import replace
from pathlib import Path

import pytest
import src  # noqa: F401  (sets the MKL workaround before matplotlib is imported)
from matplotlib import colors
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.text import Text
from src.app_state import HEX_PATTERN
from src.cli import resolve_output
from src.graphpad_style import (
    DEFAULT_PALETTE,
    LEGACY_PALETTE,
    OKABE_ITO,
    PALETTE_KINDS,
    PALETTES,
    PRISM_COLORS,
    palette_colors,
    resolve_font,
)
from src.models import (
    DEFAULT_POINT_TYPE,
    ORIENTATIONS,
    POINT_MARKERS,
    POINT_TYPES,
    SOLID_POINTS,
    Dataset,
    Orientation,
    PlotConfig,
    PointType,
    Sample,
    XYPoint,
    XYSeries,
)
from src.plotting import (
    BAND_LINE_Y,
    BAR_EDGE,
    BAR_GAP,
    BAR_WIDTH,
    BOTTOM_MARGIN,
    DEFAULT_LINE_WIDTH,
    INTER_GROUP_GAP,
    NO_LEGEND_TOP_MARGIN,
    POINT_FACE,
    RIGHT_MARGIN,
    SAMPLE_LABEL_FONT,
    TOP_MARGIN,
    compute_layout,
    plot_dataset,
)

# The colour left at the middle of a point, which the tests compare a drawn fill against
# rather than hard coding the web colour name at each use.
POINT_FACE_HEX = to_hex(POINT_FACE)

INPUT_FILE = Path(__file__).resolve().parents[1] / 'input' / 'Conc_bar_26-09-27.xlsx'
# Three samples with two replicates each, shared by the tests that need a bar graph to
# compare against rather than a purpose built one.
BAR_SAMPLES = (
    Sample('Control', 'A', (10.0, 12.0)),
    Sample('42C', 'A', (20.0, 24.0)),
    Sample('Other', 'B', (30.0, 36.0)),
)


@pytest.fixture
def simple_dataset() -> Dataset:
    return Dataset(
        samples=(
            Sample('Control', 'A', (10.0, 12.0)),
            Sample('42C', 'A', (20.0, 24.0)),
            Sample('Other', 'B', (30.0, 36.0)),
        ),
        y_label='Value',
        replicate_labels=('Value 1', 'Value 2'),
    )


def axes_of(figure: Figure) -> Axes:
    return figure.axes[0]


def test_a_connected_series_is_drawn_in_its_own_colour(scatter_dataset: Dataset) -> None:
    """The line joining a series' points is that series' colour, not the next one along.

    The line was left to pick up the next colour off matplotlib's cycle, which is not the
    colour of the points it joins, so a traced series read as a different series from the one
    it was tracing.
    """
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', connect_points=True))
    figure.canvas.draw()
    for line in axes_of(figure).get_lines():
        assert colors.to_hex(line.get_color()) == colors.to_hex(line.get_markeredgecolor())


def test_two_connected_series_keep_different_colours(scatter_dataset: Dataset) -> None:
    """Matching the line to its points must not make every line the same colour."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', connect_points=True))
    figure.canvas.draw()
    drawn = [colors.to_hex(line.get_color()) for line in axes_of(figure).get_lines()]
    assert len(set(drawn)) == len(drawn)


def test_an_unconnected_series_is_left_without_a_line(scatter_dataset: Dataset) -> None:
    """The colour fix must not start drawing a line on a series that asked for none."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', connect_points=False))
    for line in axes_of(figure).get_lines():
        assert line.get_linestyle() == 'None'


def replicate_point_lines(figure: Figure, point_type: PointType = DEFAULT_POINT_TYPE) -> list[Line2D]:
    """Return the lines that draw a bar graph's replicate points.

    A bar graph also draws group band lines and the tick line along the bottom, none of which
    are points, so the ones that are are picked out by the marker the shape was drawn with.
    """
    figure.canvas.draw()
    marker = POINT_MARKERS[point_type]
    return [line for line in figure.axes[0].get_lines() if line.get_marker() == marker]


def test_the_replicate_points_are_the_colour_of_their_own_bar(simple_dataset: Dataset) -> None:
    """A replicate point draws no line, but it is still the colour of its bar."""
    figure = plot_dataset(simple_dataset, PlotConfig(show_points=True))
    figure.canvas.draw()
    points = replicate_point_lines(figure)
    bar_colors = [colors.to_hex(patch.get_facecolor()) for patch in bars_of(figure)]
    assert [colors.to_hex(line.get_color()) for line in points] == bar_colors


def test_the_default_point_is_a_round_open_one(scatter_dataset: Dataset) -> None:
    """Nothing chosen means the point is drawn as it always has been."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter'))
    figure.canvas.draw()
    line = axes_of(figure).get_lines()[0]
    assert line.get_marker() == POINT_MARKERS[DEFAULT_POINT_TYPE]
    assert colors.to_hex(line.get_markerfacecolor()) == POINT_FACE_HEX


@pytest.mark.parametrize('point_type', POINT_TYPES)
def test_every_point_type_is_drawn_on_a_scatter_plot(scatter_dataset: Dataset, point_type: str) -> None:
    """Each shape offered in the window reaches the points it was chosen for."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', point_type=point_type))
    figure.canvas.draw()
    assert axes_of(figure).get_lines()[0].get_marker() == POINT_MARKERS[point_type]


@pytest.mark.parametrize('point_type', POINT_TYPES)
def test_every_point_type_is_drawn_on_a_bar_graph(simple_dataset: Dataset, point_type: PointType) -> None:
    """A bar graph's replicate points take the shape too, not only a scatter plot's."""
    figure = plot_dataset(simple_dataset, PlotConfig(point_type=point_type))
    figure.canvas.draw()
    assert {line.get_marker() for line in replicate_point_lines(figure, point_type)} == {POINT_MARKERS[point_type]}


@pytest.mark.parametrize('point_type', sorted(SOLID_POINTS))
def test_a_shape_with_no_interior_is_filled(scatter_dataset: Dataset, point_type: str) -> None:
    """A cross or a star drawn open is two bare lines, so it is filled with the point colour."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', point_type=point_type))
    figure.canvas.draw()
    line = axes_of(figure).get_lines()[0]
    edge = colors.to_hex(line.get_markeredgecolor())
    assert colors.to_hex(line.get_markerfacecolor()) == edge


@pytest.mark.parametrize('point_type', sorted(set(POINT_TYPES) - set(SOLID_POINTS)))
def test_a_shape_with_an_interior_is_left_open(scatter_dataset: Dataset, point_type: str) -> None:
    """The shapes that have a centre keep the Prism look of a white middle."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', point_type=point_type))
    figure.canvas.draw()
    assert colors.to_hex(axes_of(figure).get_lines()[0].get_markerfacecolor()) == POINT_FACE_HEX


def test_two_series_can_be_told_apart_by_shape(scatter_dataset: Dataset) -> None:
    """A shape chosen for one series leaves every other series as it was.

    One shape for the whole plot cannot tell two series apart, which is the whole reason a
    series is allowed one of its own.
    """
    names = [series.name for series in scatter_dataset.series]
    figure = plot_dataset(
        scatter_dataset, PlotConfig(chart='scatter', point_types={names[0]: 'square'})
    )
    figure.canvas.draw()
    markers = [line.get_marker() for line in axes_of(figure).get_lines()]
    assert markers == [POINT_MARKERS['square'], POINT_MARKERS[DEFAULT_POINT_TYPE]]


def test_a_series_shape_beats_the_whole_graph_one(scatter_dataset: Dataset) -> None:
    """A series picked out of the graph keeps its shape when the graph's shape changes."""
    names = [series.name for series in scatter_dataset.series]
    figure = plot_dataset(
        scatter_dataset,
        PlotConfig(chart='scatter', point_type='triangle', point_types={names[0]: 'star'}),
    )
    figure.canvas.draw()
    markers = [line.get_marker() for line in axes_of(figure).get_lines()]
    assert markers == [POINT_MARKERS['star'], POINT_MARKERS['triangle']]


def test_a_series_with_no_shape_follows_the_graph(scatter_dataset: Dataset) -> None:
    """Setting the shape for the whole graph still reaches a series that claimed none."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', point_type='diamond'))
    figure.canvas.draw()
    assert {line.get_marker() for line in axes_of(figure).get_lines()} == {POINT_MARKERS['diamond']}


def test_a_series_shape_decides_whether_the_point_is_filled(scatter_dataset: Dataset) -> None:
    """The fill follows the shape that was resolved, not the shape the graph asked for.

    A graph set to an open round with one series picked out as a solid star is the case where
    a rule keyed off the global setting would fill or hollow the wrong one.
    """
    names = [series.name for series in scatter_dataset.series]
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', point_types={names[0]: 'star'}))
    figure.canvas.draw()
    star, other = axes_of(figure).get_lines()
    star_edge = colors.to_hex(star.get_markeredgecolor())
    assert colors.to_hex(star.get_markerfacecolor()) == star_edge
    assert colors.to_hex(other.get_markerfacecolor()) == POINT_FACE_HEX


def test_a_sample_can_have_a_point_shape_of_its_own(simple_dataset: Dataset) -> None:
    """A bar graph's replicate points take a shape per sample, as hatch and outline do."""
    name = simple_dataset.samples[0].name
    figure = plot_dataset(simple_dataset, PlotConfig(point_types={name: 'diamond'}))
    figure.canvas.draw()
    drawn = {line.get_marker() for line in replicate_point_lines(figure, 'diamond')}
    assert drawn == {POINT_MARKERS['diamond']}


def test_the_whole_graph_shape_reaches_a_bar_sample_with_none_of_its_own(
    simple_dataset: Dataset,
) -> None:
    """A sample that claimed no shape follows the graph's, as every other setting does."""
    figure = plot_dataset(simple_dataset, PlotConfig(point_type='triangle'))
    figure.canvas.draw()
    drawn = {line.get_marker() for line in replicate_point_lines(figure, 'triangle')}
    assert drawn == {POINT_MARKERS['triangle']}


def plot_title_of(figure: Figure) -> Text | None:
    """Return the text artist holding the plot title, or ``None`` when there is no title.

    The title is drawn in figure coordinates rather than as the axes title, so that raising
    the plot to make room for a legend cannot push the title off the top of the figure with
    it. It is therefore found among the figure's own texts rather than on the axes.
    """
    return next((text for text in figure.texts if text.get_text()), None)


def sample_label_rotations(figure: Figure, dataset: Dataset) -> set[float]:
    """Return the angles the sample names along an axis are drawn at.

    The legend carries the same names at the legend size, so its entries are set aside
    rather than being read as the labels under the bars. Legend entries also report a stale
    position before the figure is drawn, so the figure is drawn here for the caller.
    """
    figure.canvas.draw()
    legends = [axes.get_legend() for axes in figure.axes]
    in_legend = {id(text) for legend in legends if legend is not None for text in legend.get_texts()}
    wanted = {sample.name for sample in dataset.samples}
    return {
        round(text.get_rotation(), 1)
        for text in figure.findobj(Text)
        if text.get_text() in wanted and id(text) not in in_legend and text.get_window_extent().height > 5
    }


def test_the_sample_names_are_upright_by_default(simple_dataset: Dataset) -> None:
    """No rotation asked for means the labels stay as they have always been drawn."""
    assert sample_label_rotations(plot_dataset(simple_dataset), simple_dataset) == {0.0}


@pytest.mark.parametrize('rotation', [45, 90, -45, 180])
def test_the_sample_names_can_be_turned(simple_dataset: Dataset, rotation: int) -> None:
    """The angle asked for is the angle the names are drawn at."""
    figure = plot_dataset(simple_dataset, PlotConfig(label_rotation=rotation))
    expected = rotation % 360
    assert sample_label_rotations(figure, simple_dataset) == {float(expected)}


def test_a_turned_name_stays_under_its_own_bar(simple_dataset: Dataset) -> None:
    """A turned label is anchored at its tick, so it leans away from its neighbour."""
    figure = plot_dataset(simple_dataset, PlotConfig(label_rotation=45))
    figure.canvas.draw()
    labels = [
        text
        for text in figure.findobj(Text)
        if text.get_text() in {sample.name for sample in simple_dataset.samples}
        and text.get_window_extent().height > 5
        and text.get_rotation() == 45.0
    ]
    assert labels
    assert {label.get_horizontalalignment() for label in labels} == {'right'}


def test_turning_the_names_gives_the_plot_more_room_at_the_bottom(simple_dataset: Dataset) -> None:
    """Turned names reach further down, so the plot has to start higher up."""
    upright = axes_of(plot_dataset(simple_dataset)).get_position().y0
    turned = axes_of(plot_dataset(simple_dataset, PlotConfig(label_rotation=90))).get_position()
    assert upright == pytest.approx(BOTTOM_MARGIN)
    assert turned.y0 > upright


def test_a_horizontal_graph_turns_its_names_too(simple_dataset: Dataset) -> None:
    """The setting means the same thing whichever way round the graph is drawn."""
    figure = plot_dataset(simple_dataset, PlotConfig(label_rotation=90, orientation='horizontal'))
    assert sample_label_rotations(figure, simple_dataset) == {90.0}


def test_a_scatter_x_label_can_be_replaced(scatter_dataset: Dataset) -> None:
    """An x axis title is drawn for a scatter plot, which is what has a real x axis."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', x_label_override='Amount added'))
    assert axes_of(figure).get_xlabel() == 'Amount added'


def test_a_blank_scatter_x_label_keeps_the_sheets(scatter_dataset: Dataset) -> None:
    """An emptied field means "name it after the sheet", not "draw no label at all"."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', x_label_override=None))
    assert axes_of(figure).get_xlabel() == scatter_dataset.x_label


def test_a_bar_graph_draws_no_x_label(simple_dataset: Dataset) -> None:
    """A bar graph names its samples along that axis instead of labelling it."""
    assert axes_of(plot_dataset(simple_dataset, PlotConfig(label_rotation=45))).get_xlabel() == ''


def sample_label_size(figure: Figure, dataset: Dataset) -> float:
    """Return the text size of the sample names a bar graph writes along the bottom.

    A bar graph draws no x ticks on its own axis, so the names go on a secondary axis that
    is not in ``figure.axes``. They are still the x axis labels as far as a reader is
    concerned, which is the text the x axis text size is meant to change. The legend is
    written with the same names at the legend size, so its entries are set aside rather
    than being mistaken for the labels along the bottom.
    """
    legends = [axes.get_legend() for axes in figure.axes]
    in_legend = {id(text) for legend in legends if legend is not None for text in legend.get_texts()}
    wanted = {sample.name for sample in dataset.samples}
    sizes = {
        text.get_fontsize()
        for text in figure.findobj(Text)
        if text.get_text() in wanted and id(text) not in in_legend
    }
    assert len(sizes) == 1, f'expected every sample name in one size, found {sizes}'
    return sizes.pop()


@pytest.fixture
def scatter_dataset() -> Dataset:
    """Return a sheet of paired x and y values, which is what a scatter plot is drawn from."""
    return Dataset(
        samples=(),
        series=(
            XYSeries('S1', (XYPoint(1.0, 10.0, 1), XYPoint(2.0, 12.0, 2), XYPoint(4.0, 15.0, 3))),
            XYSeries('S2', (XYPoint(1.0, 5.0, 1), XYPoint(2.0, 6.5, 2))),
        ),
        x_label='Dose',
        y_label='Response',
    )


def test_layout_gives_every_bar_a_position(simple_dataset: Dataset) -> None:
    layout = compute_layout(simple_dataset.samples, simple_dataset.groups)
    assert len(layout.centers) == 3
    assert len(layout.groups) == 2
    assert all(a < b for a, b in zip(layout.centers, layout.centers[1:], strict=False))


def test_all_bars_share_uniform_spacing(simple_dataset: Dataset) -> None:
    """Spacing must not depend on grouping, which is what removes the empty slots."""
    layout = compute_layout(simple_dataset.samples, simple_dataset.groups)
    gaps = [b - a for a, b in zip(layout.centers, layout.centers[1:], strict=False)]
    assert gaps == pytest.approx([gaps[0]] * len(gaps))


@pytest.fixture
def nested_dataset() -> Dataset:
    """Two groups of three conditions each, the shape of a nested bar graph."""
    return Dataset(
        samples=(
            Sample('20-30', 'Women', (35.0, 40.0)),
            Sample('31-40', 'Women', (45.0, 50.0)),
            Sample('41-50', 'Women', (55.0, 60.0)),
            Sample('20-30', 'Men', (60.0, 65.0)),
            Sample('31-40', 'Men', (70.0, 75.0)),
            Sample('41-50', 'Men', (80.0, 85.0)),
        ),
        y_label='% owning a car',
    )


def _gaps(centers: tuple[float, ...]) -> list[float]:
    return [b - a for a, b in itertools.pairwise(centers)]


def test_grouping_leaves_a_wider_gap_at_the_group_boundary(nested_dataset: Dataset) -> None:
    """Prism marks the boundary between groups with more room than it leaves inside them."""
    layout = compute_layout(nested_dataset.samples, nested_dataset.groups, grouped=True)
    gaps = _gaps(layout.centers)
    assert gaps[2] > gaps[0]
    assert gaps[2] - gaps[0] == pytest.approx(INTER_GROUP_GAP)
    # The two bars inside a group keep the ordinary gap.
    assert gaps[0] == pytest.approx(gaps[1])


def test_grouping_changes_nothing_when_it_is_off(nested_dataset: Dataset) -> None:
    """The default layout must be exactly the flat spacing that was there before."""
    plain = compute_layout(nested_dataset.samples, nested_dataset.groups)
    assert _gaps(plain.centers) == pytest.approx([BAR_WIDTH + BAR_GAP] * 5)


def test_grouping_never_changes_the_order_of_the_bars(nested_dataset: Dataset) -> None:
    """Grouping is a visual separation only; it must not reorder anything."""
    layout = compute_layout(nested_dataset.samples, nested_dataset.groups, grouped=True)
    assert len(layout.centers) == len(nested_dataset.samples)
    assert list(layout.centers) == sorted(layout.centers)


def test_grouped_spans_still_cover_exactly_their_own_bars(nested_dataset: Dataset) -> None:
    """The band lines have to follow the bars once the spacing changes."""
    layout = compute_layout(nested_dataset.samples, nested_dataset.groups, grouped=True)
    first, second = layout.groups
    assert first.left == pytest.approx(layout.centers[0] - BAR_WIDTH / 2)
    assert first.right == pytest.approx(layout.centers[2] + BAR_WIDTH / 2)
    assert second.left == pytest.approx(layout.centers[3] - BAR_WIDTH / 2)
    assert second.right == pytest.approx(layout.centers[5] + BAR_WIDTH / 2)


def test_grouped_bounds_still_enclose_every_bar(nested_dataset: Dataset) -> None:
    """The x limits keep the same padding around the outermost bars as the flat layout."""
    flat = compute_layout(nested_dataset.samples, nested_dataset.groups)
    grouped = compute_layout(nested_dataset.samples, nested_dataset.groups, grouped=True)
    assert grouped.left - grouped.centers[0] == pytest.approx(flat.left - flat.centers[0])
    assert grouped.centers[-1] - grouped.right == pytest.approx(flat.centers[-1] - flat.right)


def test_the_legend_names_every_group_once(nested_dataset: Dataset) -> None:
    """A repeated condition would otherwise be listed as many times as it appears."""
    figure = plot_dataset(nested_dataset, PlotConfig(grouped_layout=True))
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert labels == ['Women', 'Men']


def test_the_legend_names_every_sample_when_not_grouped(nested_dataset: Dataset) -> None:
    figure = plot_dataset(nested_dataset)
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert labels == ['20-30', '31-40', '41-50', '20-30', '31-40', '41-50']


def test_a_group_legend_swatch_carries_the_group_colour(nested_dataset: Dataset) -> None:
    figure = plot_dataset(nested_dataset, PlotConfig(grouped_layout=True, color_by='group'))
    swatches = figure.axes[0].get_legend().legend_handles
    bar_colors = [to_hex(patch.get_facecolor()) for patch in bars_of(figure)]
    assert [to_hex(handle.get_facecolor()) for handle in swatches] == [bar_colors[0], bar_colors[3]]


def test_the_drawn_gap_matches_the_requested_layout(nested_dataset: Dataset) -> None:
    """The bar patches themselves have to sit where the layout said they would."""
    plain = plot_dataset(nested_dataset, PlotConfig(error_kind='none'))
    grouped = plot_dataset(nested_dataset, PlotConfig(grouped_layout=True, error_kind='none'))
    plain_gaps = _gaps(tuple(patch.get_x() for patch in bars_of(plain)))
    grouped_gaps = _gaps(tuple(patch.get_x() for patch in bars_of(grouped)))
    assert grouped_gaps[2] - plain_gaps[2] == pytest.approx(INTER_GROUP_GAP)


def test_bars_never_reach_into_a_neighbouring_group() -> None:
    """A group with many conditions must not push the next group away."""
    many = (*(Sample(f'c{i}', 'A', (1.0, 2.0)) for i in range(6)), Sample('only', 'B', (3.0, 4.0)))
    dataset = Dataset(samples=many, y_label='v')
    layout = compute_layout(dataset.samples, dataset.groups)
    assert layout.centers[-1] - layout.centers[-2] == pytest.approx(layout.centers[1] - layout.centers[0])


def test_group_spans_cover_exactly_their_bars(simple_dataset: Dataset) -> None:
    layout = compute_layout(simple_dataset.samples, simple_dataset.groups)
    first, second = layout.groups
    assert first.name == 'A'
    assert not first.is_single
    assert first.left == pytest.approx(layout.centers[0] - layout.width / 2)
    assert first.right == pytest.approx(layout.centers[1] + layout.width / 2)
    # Group B holds one bar, so it gets no name and therefore no band to draw.
    assert second.name == ''
    assert second.is_single
    assert second.left == pytest.approx(layout.centers[2] - layout.width / 2)
    assert second.right == pytest.approx(layout.centers[2] + layout.width / 2)


def test_group_span_center_is_the_midpoint(simple_dataset: Dataset) -> None:
    layout = compute_layout(simple_dataset.samples, simple_dataset.groups)
    for span in layout.groups:
        assert span.center == pytest.approx((span.left + span.right) / 2)


def test_only_a_group_of_several_gets_a_line_and_a_name(simple_dataset: Dataset) -> None:
    """A group of one is not drawn, even when its bar carries a different name."""
    figure = plot_dataset(simple_dataset)
    ax = axes_of(figure)
    assert [text.get_text() for text in ax.texts] == ['A']
    assert len(band_lines(ax)) == 1


def bars_of(figure: Figure) -> list:
    """Return the drawn bar patches in plotting order."""
    return list(axes_of(figure).containers[0])


def test_each_bar_keeps_its_own_outline_colour(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(edge_colors={'42C': '#ff0000', 'Other': '#00ff00'}))
    assert [to_hex(patch.get_edgecolor()) for patch in bars_of(figure)] == [
        BAR_EDGE,
        '#ff0000',
        '#00ff00',
    ]


def test_bars_default_to_the_shared_outline_colour(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset)
    assert {to_hex(patch.get_edgecolor()) for patch in bars_of(figure)} == {BAR_EDGE}


def test_each_bar_keeps_its_own_hatch(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(hatches={'42C': '//', 'Other': 'xx'}))
    assert [patch.get_hatch() for patch in bars_of(figure)] == ['', '//', 'xx']


def test_bars_have_no_hatch_by_default(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset)
    assert {patch.get_hatch() for patch in bars_of(figure)} == {''}


def test_lines_use_the_default_thickness(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset)
    axes = axes_of(figure)
    assert {patch.get_linewidth() for patch in bars_of(figure)} == {DEFAULT_LINE_WIDTH}
    assert axes.spines['left'].get_linewidth() == pytest.approx(DEFAULT_LINE_WIDTH)
    assert axes.spines['bottom'].get_linewidth() == pytest.approx(DEFAULT_LINE_WIDTH)


def test_the_bar_thickness_reaches_every_bar_line(simple_dataset: Dataset) -> None:
    """The outlines, the error bars and the group band are all part of the bar graph."""
    figure = plot_dataset(simple_dataset, PlotConfig(bar_line_width=2.5))
    figure.canvas.draw()
    axes = axes_of(figure)
    assert {patch.get_linewidth() for patch in bars_of(figure)} == {2.5}
    assert {line.get_linewidth() for line in band_lines(axes)} == {2.5}
    error_bars = [collection for collection in axes.collections if isinstance(collection, LineCollection)]
    assert error_bars, 'the error bars are drawn as a line collection'
    for collection in error_bars:
        assert set(collection.get_linewidth()) == {2.5}


def test_the_axis_thickness_reaches_the_axis_lines(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(axis_line_width=3.0))
    figure.canvas.draw()
    axes = axes_of(figure)
    assert axes.spines['left'].get_linewidth() == pytest.approx(3.0)
    assert axes.spines['bottom'].get_linewidth() == pytest.approx(3.0)


def test_the_axis_thickness_also_thickens_the_tick_marks(simple_dataset: Dataset) -> None:
    """Prism draws the axis line and its ticks as one unit, so they move together."""
    figure = plot_dataset(simple_dataset, PlotConfig(axis_line_width=3.0))
    figure.canvas.draw()
    ticks = axes_of(figure).yaxis.get_major_ticks()
    assert ticks
    assert {tick._width for tick in ticks} == {3.0}


def test_the_two_thicknesses_are_independent(simple_dataset: Dataset) -> None:
    """Changing one must not drag the other along with it."""
    figure = plot_dataset(simple_dataset, PlotConfig(axis_line_width=3.0, bar_line_width=2.5))
    figure.canvas.draw()
    axes = axes_of(figure)
    assert axes.spines['left'].get_linewidth() == pytest.approx(3.0)
    assert {patch.get_linewidth() for patch in bars_of(figure)} == {2.5}


def test_the_axis_thickness_leaves_the_bars_alone(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(axis_line_width=4.0))
    assert {patch.get_linewidth() for patch in bars_of(figure)} == {DEFAULT_LINE_WIDTH}


def test_merging_groups_draws_one_band(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(group_overrides={'Other': 'A'}))
    ax = axes_of(figure)
    assert [text.get_text() for text in ax.texts] == ['A']
    assert len(band_lines(ax)) == 1


def test_a_merged_group_keeps_its_own_name(simple_dataset: Dataset) -> None:
    """A group named by the user is never a bar name, so it must still be printed."""
    figure = plot_dataset(simple_dataset, PlotConfig(group_overrides={'Control': 'Zed', '42C': 'Zed'}))
    # Group B is left holding a single bar, so it is no longer drawn at all.
    assert [text.get_text() for text in axes_of(figure).texts] == ['Zed']


def test_splitting_a_group_draws_the_new_group_when_it_holds_several(simple_dataset: Dataset) -> None:
    """Two samples in the new group keep it visible, and the emptied old group drops away."""
    figure = plot_dataset(simple_dataset, PlotConfig(group_overrides={'42C': 'Solo', 'Other': 'Solo'}))
    # 'Control' is left alone in group A, so A is now a group of one and is not drawn.
    assert [text.get_text() for text in axes_of(figure).texts] == ['Solo']


def test_merging_leaves_no_stray_group_name(simple_dataset: Dataset) -> None:
    """Every bar ends up in the merged group, so that is the only name printed."""
    figure = plot_dataset(
        simple_dataset,
        PlotConfig(group_overrides={'Control': 'Zed', '42C': 'Zed', 'Other': 'Zed'}),
    )
    assert [text.get_text() for text in axes_of(figure).texts] == ['Zed']


def test_splitting_a_group_down_to_one_hides_it(simple_dataset: Dataset) -> None:
    """Once the new group holds a single bar it stops being a group worth drawing."""
    figure = plot_dataset(simple_dataset, PlotConfig(group_overrides={'Other': 'Solo'}))
    assert [text.get_text() for text in axes_of(figure).texts] == ['A']


def test_group_overrides_do_not_change_the_dataset(simple_dataset: Dataset) -> None:
    plot_dataset(simple_dataset, PlotConfig(group_overrides={'Other': 'A'}))
    assert {sample.name: sample.group for sample in simple_dataset.samples}['Other'] == 'B'


def test_y_max_sets_the_top_of_the_axis(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(y_max=250.0))
    assert axes_of(figure).get_ylim() == (0.0, 250.0)


def test_y_min_raises_the_baseline(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(y_min=10.0, y_max=100.0))
    assert axes_of(figure).get_ylim() == (10.0, 100.0)


def test_a_blank_axis_setting_keeps_the_automatic_range(simple_dataset: Dataset) -> None:
    default = axes_of(plot_dataset(simple_dataset)).get_ylim()
    assert axes_of(plot_dataset(simple_dataset, PlotConfig(y_max=None, y_min=None))).get_ylim() == default


def test_y_major_step_sets_the_tick_spacing(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(y_max=100.0, y_major_step=25.0))
    ticks = [tick for tick in axes_of(figure).get_yticks() if 0 <= tick <= 100]
    assert ticks == pytest.approx([0.0, 25.0, 50.0, 75.0, 100.0])


def test_the_y_label_can_be_replaced(simple_dataset: Dataset) -> None:
    assert axes_of(plot_dataset(simple_dataset, PlotConfig(y_label='Yield'))).get_ylabel() == 'Yield'


def test_a_blank_y_label_falls_back_to_the_sheet(simple_dataset: Dataset) -> None:
    """An emptied field means "use the sheet's title", not "draw no title at all"."""
    assert axes_of(plot_dataset(simple_dataset, PlotConfig(y_label=''))).get_ylabel() == 'Value'


def test_no_override_keeps_the_sheet_label(simple_dataset: Dataset) -> None:
    assert axes_of(plot_dataset(simple_dataset)).get_ylabel() == 'Value'


def test_font_sizes_are_applied(simple_dataset: Dataset) -> None:
    figure = plot_dataset(
        simple_dataset,
        PlotConfig(title='T', font_size=15, y_label_size=17, title_size=19, legend_size=11),
    )
    ax = axes_of(figure)
    assert ax.yaxis.get_ticklabels()[0].get_fontsize() == 15.0
    assert ax.yaxis.label.get_fontsize() == 17.0
    title = plot_title_of(figure)
    assert title is not None
    assert title.get_fontsize() == 19.0
    legend = ax.get_legend()
    assert legend is not None
    assert legend.get_texts()[0].get_fontsize() == 11.0


def test_the_title_is_drawn_inside_the_figure(simple_dataset: Dataset) -> None:
    """A title pushed past the top of the figure is drawn but never seen.

    The title used to sit at a fixed distance above the axes, which put it outside the
    canvas: the graph showed a legend and no title at all, and only a saved file grew to
    include it.
    """
    figure = plot_dataset(simple_dataset, PlotConfig(title='Growth rate'))
    figure.canvas.draw()
    title = plot_title_of(figure)
    assert title is not None
    box = title.get_window_extent()
    assert title.get_text() == 'Growth rate'
    assert box.y0 >= 0 and box.y1 <= figure.bbox.height


def test_the_title_is_centred_above_the_graph(simple_dataset: Dataset) -> None:
    """The default is a centred title, which is where a reader looks for it."""
    figure = plot_dataset(simple_dataset, PlotConfig(title='Growth rate'))
    figure.canvas.draw()
    title = plot_title_of(figure)
    assert title is not None
    box = title.get_window_extent()
    position = axes_of(figure).get_position()
    assert (box.x0 + box.x1) / 2 == pytest.approx((position.x0 + position.x1) / 2 * figure.bbox.width, abs=2)


@pytest.mark.parametrize('shown', [True, False])
def test_the_title_fits_above_or_below_a_legend(simple_dataset: Dataset, shown: bool) -> None:
    """With or without a legend in the way, the title stays on the canvas.

    Clearing the legend is what the title has to do when there is one, and a plot that has
    given up the legend band has room to spare, so both cases have to hold.
    """
    figure = plot_dataset(simple_dataset, PlotConfig(title='Growth rate', show_legend=shown))
    figure.canvas.draw()
    title = plot_title_of(figure)
    assert title is not None
    assert title.get_window_extent().y1 <= figure.bbox.height


def test_a_title_does_not_land_on_top_of_the_legend(simple_dataset: Dataset) -> None:
    """The two share the band above the plot, so one of them has to be above the other."""
    figure = plot_dataset(simple_dataset, PlotConfig(title='Growth rate'))
    figure.canvas.draw()
    legend = axes_of(figure).get_legend()
    title = plot_title_of(figure)
    assert legend is not None and title is not None
    title_box = title.get_window_extent()
    legend_box = legend.get_window_extent()
    assert not (title_box.y0 < legend_box.y1 and title_box.x0 < legend_box.x1 and title_box.x1 > legend_box.x0)


def test_a_title_clears_a_legend_that_wraps_onto_a_second_row() -> None:
    """A legend long enough to wrap is taller, and the title has to clear that too.

    The band the plot gives up grows with the legend, and the title is placed above whatever
    the legend ends up being, so a graph with a dozen samples is no more likely to print the
    title across the legend names than one with three.
    """
    dataset = Dataset(
        samples=tuple(
            Sample(f'Condition {index}', 'A' if index < 6 else 'B', (10.0 + index, 12.0)) for index in range(12)
        ),
        y_label='Value',
    )
    figure = plot_dataset(dataset, PlotConfig(title='Growth after 24 h'))
    figure.canvas.draw()
    legend = axes_of(figure).get_legend()
    title = plot_title_of(figure)
    assert legend is not None and title is not None
    title_box = title.get_window_extent()
    legend_box = legend.get_window_extent()
    assert title_box.y0 >= legend_box.y1
    assert title_box.y1 <= figure.bbox.height


def test_a_large_title_still_clears_the_legend(simple_dataset: Dataset) -> None:
    """A title set larger than the default is taller, and the plot has to make room.

    The band the plot gives up is measured from the title's own text size rather than
    assuming the Prism one, so enlarging the title does not print it across the legend names.
    """
    figure = plot_dataset(simple_dataset, PlotConfig(title='Growth after 24 h', title_size=28))
    figure.canvas.draw()
    legend = axes_of(figure).get_legend()
    title = plot_title_of(figure)
    assert legend is not None and title is not None
    assert title.get_window_extent().y0 >= legend.get_window_extent().y1
    assert title.get_window_extent().y1 <= figure.bbox.height


def test_a_titled_graph_keeps_its_legend_inside_the_figure(simple_dataset: Dataset) -> None:
    """The band the title takes comes off the plot, not off the legend's room."""
    figure = plot_dataset(simple_dataset, PlotConfig(title='Growth rate'))
    figure.canvas.draw()
    legend = axes_of(figure).get_legend()
    assert legend is not None
    assert legend.get_window_extent().y1 <= figure.bbox.height


def test_an_untitled_graph_keeps_the_margins_it_always_had(simple_dataset: Dataset) -> None:
    """Adding the title band must not move a graph that was not asking for one."""
    with_legend = plot_dataset(simple_dataset, PlotConfig(show_legend=True))
    assert axes_of(with_legend).get_position().y1 == pytest.approx(TOP_MARGIN)
    without = plot_dataset(simple_dataset, PlotConfig(show_legend=False))
    assert axes_of(without).get_position().y1 == pytest.approx(NO_LEGEND_TOP_MARGIN)


def test_the_legend_goes_beside_the_graph_when_asked(simple_dataset: Dataset) -> None:
    """A legend beside the plot is outside it, so the plot gives up the width for it."""
    above = plot_dataset(simple_dataset, PlotConfig(legend_position='above'))
    beside = plot_dataset(simple_dataset, PlotConfig(legend_position='right'))
    assert axes_of(above).get_position().x1 == pytest.approx(RIGHT_MARGIN)
    assert axes_of(beside).get_position().x1 < axes_of(above).get_position().x1


def test_the_legend_goes_inside_the_graph_when_asked(simple_dataset: Dataset) -> None:
    """An inside legend takes no room, so the plot is as wide as it always was."""
    inside = plot_dataset(simple_dataset, PlotConfig(legend_position='inside'))
    above = plot_dataset(simple_dataset, PlotConfig(legend_position='above'))
    assert axes_of(inside).get_position().x1 == axes_of(above).get_position().x1


def test_a_legend_beside_the_graph_needs_no_band_above_it(simple_dataset: Dataset) -> None:
    """Moving the legend frees the band the title would otherwise have had to clear."""
    beside = plot_dataset(simple_dataset, PlotConfig(title='T', legend_position='right'))
    above = plot_dataset(simple_dataset, PlotConfig(title='T', legend_position='above'))
    assert axes_of(beside).get_position().y1 > axes_of(above).get_position().y1


def test_the_legend_font_type_is_applied(simple_dataset: Dataset) -> None:
    """The family chosen for the legend reaches the names, rather than the whole figure."""
    figure = plot_dataset(simple_dataset, PlotConfig(legend_font='Courier New'))
    legend = axes_of(figure).get_legend()
    assert legend is not None
    assert legend.get_texts()[0].get_fontfamily() == ['Courier New']


def test_the_title_font_type_is_applied(simple_dataset: Dataset) -> None:
    """The family chosen for the title reaches the title alone."""
    figure = plot_dataset(simple_dataset, PlotConfig(title='T', title_font='Verdana'))
    title = plot_title_of(figure)
    assert title is not None
    assert title.get_fontfamily() == ['Verdana']


def test_a_font_that_is_not_installed_falls_back_rather_than_failing(simple_dataset: Dataset) -> None:
    """An unknown family is replaced by the Prism one instead of being drawn as nothing."""
    figure = plot_dataset(simple_dataset, PlotConfig(title='T', title_font='No Such Face'))
    title = plot_title_of(figure)
    assert title is not None
    assert title.get_fontfamily() == [resolve_font()]


def test_the_title_is_kept_on_a_scatter_plot_too(scatter_dataset: Dataset) -> None:
    """Both graphs write the title the same way, so both have to keep it on the canvas."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', title='Dose response'))
    figure.canvas.draw()
    title = plot_title_of(figure)
    assert title is not None
    assert title.get_text() == 'Dose response'
    assert title.get_window_extent().y1 <= figure.bbox.height


def test_a_scatter_legend_can_go_beside_the_graph(scatter_dataset: Dataset) -> None:
    """A scatter plot offers the same three positions as a bar graph."""
    above = plot_dataset(scatter_dataset, PlotConfig(chart='scatter'))
    beside = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', legend_position='right'))
    assert axes_of(beside).get_position().x1 < axes_of(above).get_position().x1


def test_a_blank_font_size_keeps_the_default(simple_dataset: Dataset) -> None:
    default = axes_of(plot_dataset(simple_dataset, PlotConfig(title='T')))
    blank = axes_of(plot_dataset(simple_dataset, PlotConfig(title='T', font_size=None)))
    assert default.yaxis.get_ticklabels()[0].get_fontsize() == blank.yaxis.get_ticklabels()[0].get_fontsize()


def test_the_two_axes_can_be_sized_apart(simple_dataset: Dataset) -> None:
    """Sample names along the bottom and numbers up the side are sized independently."""
    figure = plot_dataset(simple_dataset, PlotConfig(title='T', x_font_size=7, y_font_size=15))
    figure.canvas.draw()
    ax = axes_of(figure)
    assert sample_label_size(figure, simple_dataset) == 7.0
    assert ax.get_yticklabels()[0].get_fontsize() == 15.0


def test_the_sample_names_keep_their_own_default(simple_dataset: Dataset) -> None:
    """With no x size chosen the names stay as small as they have always been drawn."""
    figure = plot_dataset(simple_dataset, PlotConfig(title='T'))
    figure.canvas.draw()
    assert sample_label_size(figure, simple_dataset) == float(SAMPLE_LABEL_FONT)


def test_one_axis_size_does_not_disturb_the_other(simple_dataset: Dataset) -> None:
    """Setting the x axis must leave the y axis on the shared size rather than on nothing."""
    figure = plot_dataset(simple_dataset, PlotConfig(title='T', font_size=15, x_font_size=7))
    figure.canvas.draw()
    ax = axes_of(figure)
    assert sample_label_size(figure, simple_dataset) == 7.0
    assert ax.get_yticklabels()[0].get_fontsize() == 15.0


def test_a_scatter_plot_sizes_its_x_ticks_apart(scatter_dataset: Dataset) -> None:
    """A scatter plot carries its x values on a real axis, and that axis has its own size."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', x_font_size=7, y_font_size=15))
    figure.canvas.draw()
    ax = axes_of(figure)
    assert ax.get_xticklabels()[0].get_fontsize() == 7.0
    assert ax.get_yticklabels()[0].get_fontsize() == 15.0


def test_an_axis_with_no_size_of_its_own_follows_the_shared_one(scatter_dataset: Dataset) -> None:
    """A caller that only sets the shared size must get both axes sized by it.

    This is what keeps a caller written before the axes could be sized apart drawing the
    way it did, rather than one axis quietly reverting to the Prism default.
    """
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter', font_size=15))
    figure.canvas.draw()
    ax = axes_of(figure)
    assert ax.get_xticklabels()[0].get_fontsize() == 15.0
    assert ax.get_yticklabels()[0].get_fontsize() == 15.0


def test_single_condition_group_is_not_repeated() -> None:
    """A group whose only bar carries the group name needs no extra line or label."""
    dataset = Dataset(samples=(Sample('Solo', 'Solo', (1.0, 2.0)),), y_label='v')
    layout = compute_layout(dataset.samples, dataset.groups)
    assert layout.groups[0].is_single
    assert layout.groups[0].name == ''
    ax = axes_of(plot_dataset(dataset))
    assert list(ax.texts) == []
    assert band_lines(ax) == []


def test_group_band_never_overlaps_its_neighbour() -> None:
    """Adjacent single-condition groups must not print colliding duplicate names."""
    dataset = Dataset(
        samples=(
            Sample('A', 'A', (1.0, 2.0)),
            Sample('B', 'B', (3.0, 4.0)),
            Sample('C', 'C', (5.0, 6.0)),
        ),
        y_label='v',
    )
    layout = compute_layout(dataset.samples, dataset.groups)
    assert all(span.name == '' for span in layout.groups)


def band_lines(ax: Axes) -> list[Line2D]:
    """Return the group lines, identified by the constant y coordinate they are drawn at."""
    return [line for line in ax.lines if list(line.get_ydata()) == [BAND_LINE_Y, BAND_LINE_Y]]


def marker_lines(ax: Axes) -> list[Line2D]:
    """Return the circle marker lines, which are the drawn replicate points.

    Error bar caps are plain lines without a marker, so filtering on the marker keeps
    this independent of how matplotlib stores the error bars.
    """
    return [line for line in ax.lines if line.get_marker() == 'o']


def test_plot_draws_bars_error_bars_and_points(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset)
    ax = axes_of(figure)
    assert len(ax.containers[0]) == 3
    assert ax.get_ylabel() == 'Value'
    assert len(marker_lines(ax)) == 3
    assert ax.get_legend() is not None


def test_points_can_be_hidden(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(show_points=False))
    assert marker_lines(axes_of(figure)) == []


def test_log_axis_is_applied(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(log_axis=True))
    assert axes_of(figure).get_yscale() == 'log'


def test_linear_axis_starts_at_zero(simple_dataset: Dataset) -> None:
    bottom, _ = axes_of(plot_dataset(simple_dataset)).get_ylim()
    assert bottom == 0.0


def test_sample_order_is_respected() -> None:
    dataset = Dataset(
        samples=(Sample('A', 'g', (1.0, 2.0)), Sample('B', 'g', (3.0, 4.0))),
        y_label='v',
    )
    figure = plot_dataset(dataset, PlotConfig(sample_order=('B', 'A')))
    assert [label.get_text() for label in axes_of(figure).get_legend().get_texts()] == ['B', 'A']


def test_color_override_is_used(simple_dataset: Dataset) -> None:
    figure = plot_dataset(simple_dataset, PlotConfig(colors={'Control': '#123456'}))
    patch = axes_of(figure).get_legend().legend_handles[0]
    assert to_hex(patch.get_facecolor()).upper() == '#123456'


def test_empty_dataset_still_returns_a_figure() -> None:
    assert plot_dataset(Dataset(samples=())).axes == []


def test_resolve_output_adds_the_suffix(tmp_path: Path) -> None:
    assert resolve_output(Path('in.xlsx'), None, 'png') == Path('output/in.png')
    assert resolve_output(Path('in.xlsx'), tmp_path / 'a.pdf', 'png') == tmp_path / 'a.pdf'
    assert resolve_output(Path('in.xlsx'), tmp_path / 'b', 'pdf') == tmp_path / 'b.pdf'


def test_cli_writes_a_png(tmp_path: Path) -> None:
    from src.cli import main

    target = tmp_path / 'figure.png'
    assert main(['--input', str(INPUT_FILE), '--output', str(target), '--title', 'T']) == 0
    assert target.exists() and target.stat().st_size > 0
def test_a_discrete_palette_is_read_from_the_front(simple_dataset: Dataset) -> None:
    """Okabe-Ito is a fixed list, so the graph must use its published order."""
    figure = plot_dataset(simple_dataset, PlotConfig(palette='okabe_ito'))
    assert [to_hex(patch.get_facecolor()) for patch in bars_of(figure)] == list(OKABE_ITO[:3])


def test_a_continuous_palette_spreads_over_its_whole_range(simple_dataset: Dataset) -> None:
    """Stepping a fixed increment would give a small graph several identical purples."""
    figure = plot_dataset(simple_dataset, PlotConfig(palette='viridis'))
    colors = [to_hex(patch.get_facecolor()) for patch in bars_of(figure)]
    assert len(set(colors)) == len(colors)
    assert colors[0] != colors[-1]


def test_a_palette_reaches_the_drawn_bars(simple_dataset: Dataset) -> None:
    default = [to_hex(patch.get_facecolor()) for patch in bars_of(plot_dataset(simple_dataset))]
    changed = [
        to_hex(patch.get_facecolor()) for patch in bars_of(plot_dataset(simple_dataset, PlotConfig(palette='viridis')))
    ]
    assert default != changed


def test_an_explicit_colour_still_wins_over_the_palette(simple_dataset: Dataset) -> None:
    """A per bar colour is the user's last word, whichever palette is selected."""
    figure = plot_dataset(simple_dataset, PlotConfig(palette='viridis', colors={'42C': '#123456'}))
    assert to_hex(bars_of(figure)[1].get_facecolor()) == '#123456'


def test_every_palette_returns_exactly_one_colour_per_bar(simple_dataset: Dataset) -> None:
    for key in PALETTES:
        assert len(palette_colors(key, len(simple_dataset.samples))) == len(simple_dataset.samples)


def test_every_palette_colour_is_a_colour_tk_can_parse(simple_dataset: Dataset) -> None:
    """The list swatches hand these straight to Tk, which raises on anything unparsable."""
    for key in PALETTES:
        for color in palette_colors(key, 9):
            assert HEX_PATTERN.match(color)


def test_a_palette_cycles_when_there_are_more_bars_than_colours() -> None:
    assert len(palette_colors('okabe_ito', len(OKABE_ITO) + 2)) == len(OKABE_ITO) + 2
    assert palette_colors('okabe_ito', len(OKABE_ITO) + 2)[: len(OKABE_ITO)] == list(OKABE_ITO)


def test_the_graphpad_palette_is_still_available() -> None:
    """The original colours are kept in the menu even though they are no longer the default."""
    assert palette_colors('prism', 3) == list(PRISM_COLORS[:3])
    assert PALETTES['prism'].label == 'GraphPad'


def test_the_default_palette_is_a_categorical_one() -> None:
    """Unrelated conditions need clearly different colours, so the default must not imply order."""
    assert DEFAULT_PALETTE in PALETTES
    assert PALETTES[DEFAULT_PALETTE].kind == 'categorical'
    assert DEFAULT_PALETTE == 'tab10'


def test_an_unknown_palette_falls_back_to_the_default() -> None:
    assert palette_colors('does-not-exist', 3) == palette_colors(DEFAULT_PALETTE, 3)
    assert palette_colors('', 3) == palette_colors(DEFAULT_PALETTE, 3)


def test_the_colorblind_note_appears_on_exactly_the_flagged_palettes() -> None:
    """The label must not claim a guarantee the palette does not carry, or hide one it does."""
    for palette in PALETTES.values():
        assert ('(colorblind)' in palette.label) == palette.colorblind


def test_the_colorblind_palettes_are_the_ones_flagged() -> None:
    flagged = {key for key, palette in PALETTES.items() if palette.colorblind}
    assert flagged == {'okabe_ito', 'viridis', 'cividis'}


def test_the_menu_is_offered_in_two_groups() -> None:
    assert PALETTE_KINDS == ('categorical', 'sequential')
    assert {palette.kind for palette in PALETTES.values()} == set(PALETTE_KINDS)


def test_categorical_palettes_come_before_sequential_ones() -> None:
    """The group a palette belongs to must match where it is listed, or the headings mislead."""
    keys = [key for key in PALETTES if key != LEGACY_PALETTE]
    kinds = [PALETTES[key].kind for key in keys]
    assert kinds == sorted(kinds, key=lambda kind: PALETTE_KINDS.index(kind))


def test_the_legacy_palette_is_listed_last() -> None:
    """It has a heading of its own, so it must not sit inside the categorical section."""
    assert list(PALETTES)[-1] == LEGACY_PALETTE


def test_a_categorical_palette_holds_its_own_colours() -> None:
    """A categorical palette is a fixed list, so it must not be sampled from a colormap."""
    for palette in PALETTES.values():
        if palette.kind == 'categorical':
            assert palette.colors and not palette.is_sequential


def test_a_sequential_palette_is_sampled_from_its_colormap() -> None:
    for palette in PALETTES.values():
        if palette.kind == 'sequential':
            assert palette.colormap and not palette.colors


def test_no_sequential_palette_starts_too_close_to_white() -> None:
    """A pale first bar vanishes against the page, which a shared sampling window caused.

    The light maps such as Blues and Reds are pale at their low end, so they are sampled from
    further along the map. Saturation is what is asserted rather than brightness, because
    Reds starts at a bright orange and Blues at a pale blue: neither is white, but an
    unsampled Blues would be almost white and carry almost no colour.
    """
    for key, palette in PALETTES.items():
        if not palette.is_sequential:
            continue
        first = colors.to_rgb(palette_colors(key, 6)[0])
        top, bottom = max(first), min(first)
        saturation = 0.0 if top == 0 else (top - bottom) / top
        assert saturation > 0.20, f'{key} starts with an almost colourless bar'


def test_a_scatter_plot_draws_one_line_per_series(scatter_dataset: Dataset) -> None:
    """Each series is a set of points sharing a colour and a name, the way a sample is."""
    ax = axes_of(plot_dataset(scatter_dataset, PlotConfig(chart='scatter')))
    assert len(ax.lines) == 2
    assert list(ax.lines[0].get_xdata()) == [1.0, 2.0, 4.0]
    assert list(ax.lines[0].get_ydata()) == [10.0, 12.0, 15.0]


def test_a_scatter_point_selects_its_series(scatter_dataset: Dataset) -> None:
    """A click has to name the series, or a point is decoration nobody can use."""
    figure = plot_dataset(scatter_dataset, PlotConfig(chart='scatter'))
    mapping = getattr(figure, 'sample_by_bar', {})
    assert {mapping[id(line)] for line in figure.axes[0].lines} == {'S1', 'S2'}


def test_a_scatter_plot_names_both_axes(scatter_dataset: Dataset) -> None:
    """A point with unlabelled axes cannot be read, so both names come from the sheet."""
    ax = axes_of(plot_dataset(scatter_dataset, PlotConfig(chart='scatter')))
    assert ax.get_xlabel() == 'Dose'
    assert ax.get_ylabel() == 'Response'


def test_a_scatter_plot_names_every_series_in_the_legend(scatter_dataset: Dataset) -> None:
    ax = axes_of(plot_dataset(scatter_dataset, PlotConfig(chart='scatter')))
    assert ax.get_legend() is not None
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ['S1', 'S2']


def test_a_scatter_plot_is_not_pinned_to_a_zero_baseline(scatter_dataset: Dataset) -> None:
    """A point has no length, so a zero baseline would leave most of the graph empty.

    matplotlib frames the points itself, so the check is that the axis is not forced to the
    bottom of the range rather than that it happens to be below zero.
    """
    scatter = plot_dataset(scatter_dataset, PlotConfig(chart='scatter'))
    bars = plot_dataset(replace(scatter_dataset, series=(), samples=BAR_SAMPLES), PlotConfig())
    lowest_point = min(point.y for one in scatter_dataset.series for point in one.points)
    assert scatter.axes[0].get_ylim()[0] < lowest_point < scatter.axes[0].get_ylim()[1]
    assert bars.axes[0].get_ylim()[0] == 0


def test_a_scatter_plot_of_nothing_is_empty(scatter_dataset: Dataset) -> None:
    """A sheet with no points must not raise, or one bad file breaks the window."""
    figure = plot_dataset(replace(scatter_dataset, series=()), PlotConfig(chart='scatter'))
    assert not figure.axes or not figure.axes[0].lines


def test_points_can_be_joined_by_a_line(scatter_dataset: Dataset) -> None:
    """A scatter plot is often a trend rather than a cloud, so a connecting line is offered."""
    plain = axes_of(plot_dataset(scatter_dataset, PlotConfig(chart='scatter')))
    joined = axes_of(plot_dataset(scatter_dataset, PlotConfig(chart='scatter', connect_points=True)))
    assert plain.lines[0].get_linestyle() == 'None'
    assert joined.lines[0].get_linestyle() == '-'


@pytest.mark.parametrize('orientation', ORIENTATIONS)
def test_every_orientation_draws_the_same_bars(simple_dataset: Dataset, orientation: Orientation) -> None:
    """Turning the graph must not change how many bars there are or which they are."""
    turned = plot_dataset(simple_dataset, PlotConfig(orientation=orientation))
    upright = plot_dataset(simple_dataset, PlotConfig())
    assert [to_hex(patch.get_facecolor()) for patch in bars_of(turned)] == [
        to_hex(patch.get_facecolor()) for patch in bars_of(upright)
    ]


def test_a_horizontal_graph_moves_the_value_label_onto_the_x_axis(simple_dataset: Dataset) -> None:
    """The value axis is the one the values run down, whichever way round the graph is."""
    ax = axes_of(plot_dataset(simple_dataset, PlotConfig(orientation='horizontal')))
    assert ax.get_xlabel() == simple_dataset.y_label
    assert ax.get_ylabel() == ''


def _replicate_lines(figure: Figure) -> list[Line2D]:
    """Return only the replicate point lines, leaving out the group bands.

    The bands are drawn with a blended transform and are not pickable, which is the same
    property the window uses to tell the two apart, so the picker is what selects them.
    """
    return [line for line in figure.axes[0].lines if line.get_picker()]


def test_replicate_points_sit_on_their_own_bar(simple_dataset: Dataset) -> None:
    """A point belongs to the bar it was drawn for, not somewhere along the value axis.

    Swapping the two coordinates of a point puts the raw measurement on the bar axis, which
    silently stretches the graph to fit it and squeezes every bar into a corner.
    """
    figure = plot_dataset(simple_dataset, PlotConfig())
    layout = compute_layout(simple_dataset.samples, simple_dataset.groups)
    for sample, center, line in zip(simple_dataset.samples, layout.centers, _replicate_lines(figure), strict=True):
        for x_value, y_value in zip(line.get_xdata(), line.get_ydata(), strict=True):
            assert center - layout.width / 2 <= x_value <= center + layout.width / 2
            assert y_value in sample.values


@pytest.mark.parametrize('orientation', ORIENTATIONS)
def test_the_bar_axis_covers_exactly_the_bars(
    simple_dataset: Dataset, orientation: Orientation
) -> None:
    """The bar axis is pinned to the bars, so nothing else can stretch it."""
    ax = axes_of(plot_dataset(simple_dataset, PlotConfig(orientation=orientation)))
    layout = compute_layout(simple_dataset.samples, simple_dataset.groups)
    limits = ax.get_ylim() if orientation != 'vertical' else ax.get_xlim()
    assert limits == pytest.approx((layout.left, layout.right))


@pytest.mark.parametrize('orientation', ORIENTATIONS)
def test_replicate_points_stay_with_their_bar_in_every_orientation(
    simple_dataset: Dataset, orientation: Orientation
) -> None:
    """The same rule holds whichever way round the graph is drawn."""
    figure = plot_dataset(simple_dataset, PlotConfig(orientation=orientation))
    horizontal = orientation != 'vertical'
    layout = compute_layout(simple_dataset.samples, simple_dataset.groups)
    for sample, center, line in zip(simple_dataset.samples, layout.centers, _replicate_lines(figure), strict=True):
        along = line.get_ydata() if horizontal else line.get_xdata()
        across = line.get_xdata() if horizontal else line.get_ydata()
        for position, value in zip(along, across, strict=True):
            assert center - layout.width / 2 <= position <= center + layout.width / 2
            assert value in sample.values


def test_a_vertical_graph_keeps_the_value_label_on_the_y_axis(simple_dataset: Dataset) -> None:
    ax = axes_of(plot_dataset(simple_dataset, PlotConfig(orientation='vertical')))
    assert ax.get_ylabel() == simple_dataset.y_label
    assert ax.get_xlabel() == ''



def _scatter_figure(dataset: Dataset, config: PlotConfig) -> Figure:
    """Draw a scatter dataset with the given settings."""
    return plot_dataset(dataset, config)


def test_one_series_can_be_connected_without_the_others(scatter_dataset: Dataset) -> None:
    """Connecting all of them at once is still a single click, so both must be possible."""
    ax = axes_of(_scatter_figure(scatter_dataset, PlotConfig(chart='scatter', connect_series=('S2',))))
    styles = [line.get_linestyle() for line in ax.lines]
    assert styles.count('-') == 1


def test_the_all_series_setting_still_connects_everything(scatter_dataset: Dataset) -> None:
    """The switch that joined every series is what it always was and must not narrow."""
    ax = axes_of(_scatter_figure(scatter_dataset, PlotConfig(chart='scatter', connect_points=True)))
    assert all(line.get_linestyle() == '-' for line in ax.lines)


def test_no_series_is_connected_by_default(scatter_dataset: Dataset) -> None:
    ax = axes_of(_scatter_figure(scatter_dataset, PlotConfig(chart='scatter')))
    assert all(line.get_linestyle() == 'None' for line in ax.lines)


def test_a_name_is_chosen_for_the_rightmost_point(scatter_dataset: Dataset) -> None:
    """The label belongs at the end of the line, whichever row that happens to be."""
    ax = axes_of(_scatter_figure(scatter_dataset, PlotConfig(chart='scatter', point_labels=True, label_series=('S1',))))
    _low, high = ax.get_xlim()
    rightmost = max(point.x for point in scatter_dataset.series[0].points)
    # The name sits beyond the right hand edge, while the point it names is inside it.
    assert ax.texts[0].get_position()[0] > high
    assert rightmost <= high


def test_only_the_named_series_are_labelled(scatter_dataset: Dataset) -> None:
    """Labels collide when two series finish together, so the user picks which to name."""
    ax = axes_of(_scatter_figure(scatter_dataset, PlotConfig(chart='scatter', point_labels=True, label_series=('S1',))))
    assert [text.get_text() for text in ax.texts] == ['S1']


def test_the_labels_line_up_in_a_column(scatter_dataset: Dataset) -> None:
    """They all start at the same x, which is what makes them read as a list."""
    ax = axes_of(
        _scatter_figure(scatter_dataset, PlotConfig(chart='scatter', point_labels=True, label_series=('S1', 'S2')))
    )
    assert len({round(text.get_position()[0], 9) for text in ax.texts}) == 1


def test_the_labels_are_left_aligned(scatter_dataset: Dataset) -> None:
    """Right aligning them would push the long names back over the plot."""
    ax = axes_of(_scatter_figure(scatter_dataset, PlotConfig(chart='scatter', point_labels=True, label_series=('S1',))))
    assert ax.texts[0].get_horizontalalignment() == 'left'


def test_the_legend_and_the_labels_are_separate_choices(scatter_dataset: Dataset) -> None:
    """Either, both or neither may be shown, so neither switches off the other."""
    both = axes_of(
        _scatter_figure(
            scatter_dataset, PlotConfig(chart='scatter', point_labels=True, show_legend=True, label_series=('S1',))
        )
    )
    assert both.get_legend() is not None
    assert both.texts
    labels_only = axes_of(
        _scatter_figure(
            scatter_dataset, PlotConfig(chart='scatter', point_labels=True, show_legend=False, label_series=('S1',))
        )
    )
    assert labels_only.get_legend() is None
    assert labels_only.texts


def test_no_labels_means_no_labels(scatter_dataset: Dataset) -> None:
    """The setting is off by default, so a graph nobody asked about is unchanged."""
    assert not axes_of(_scatter_figure(scatter_dataset, PlotConfig(chart='scatter'))).texts


def test_the_plot_gives_up_the_legend_band_only_without_a_legend(scatter_dataset: Dataset) -> None:
    """With a legend shown the plot has to stay out of its way."""
    labelled = PlotConfig(chart='scatter', point_labels=True, label_series=('S1',))
    with_legend = axes_of(_scatter_figure(scatter_dataset, replace(labelled, show_legend=True)))
    without = axes_of(_scatter_figure(scatter_dataset, replace(labelled, show_legend=False)))
    assert with_legend.get_position().y1 < without.get_position().y1


def test_room_is_reserved_for_the_labels(scatter_dataset: Dataset) -> None:
    """Without it the names are drawn past the edge of the figure and simply vanish."""
    plain = axes_of(_scatter_figure(scatter_dataset, PlotConfig(chart='scatter')))
    labelled = axes_of(
        _scatter_figure(scatter_dataset, PlotConfig(chart='scatter', point_labels=True, label_series=('S1',)))
    )
    assert labelled.get_position().x1 < plain.get_position().x1
