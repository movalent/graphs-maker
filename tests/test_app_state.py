"""Tests for the adjustable state that drives the interactive window."""

from __future__ import annotations

import matplotlib
import pytest
from src.app_state import DEFAULT_LINE_WIDTH, AppState, normalize_hex
from src.graphpad_style import DEFAULT_PALETTE, palette_colors
from src.models import LOG_HEADROOM, Y_MAX_HEADROOM, Dataset, PlotConfig, Sample


@pytest.fixture
def state() -> AppState:
    dataset = Dataset(
        samples=(
            Sample('Control', 'A', (10.0, 12.0)),
            Sample('42C', 'A', (20.0, 24.0)),
            Sample('Other', 'B', (30.0, 36.0)),
            Sample('Third', 'C', (40.0, 44.0)),
        ),
        y_label='Value',
    )
    return AppState(dataset)


def test_initial_order_matches_the_sheet(state: AppState) -> None:
    assert state.visible_order == ('Control', '42C', 'Other', 'Third')
    assert state.index_of('Other') == 2


def test_outline_colour_is_stored_and_normalized(state: AppState) -> None:
    assert state.set_edge_color('Other', '#abc')
    assert state.edge_of('Other') == '#aabbcc'


def test_outline_defaults_to_black(state: AppState) -> None:
    assert state.edge_of('Other') == '#000000'


@pytest.mark.parametrize('color', ['', 'red', '#zzz', '#ff00'])
def test_unusable_outline_colour_is_refused(state: AppState, color: str) -> None:
    assert not state.set_edge_color('Other', color)
    assert state.edge_of('Other') == '#000000'


def test_outline_for_an_unknown_sample_is_refused(state: AppState) -> None:
    assert not state.set_edge_color('nope', '#123456')


def test_hatch_is_stored_and_read_back(state: AppState) -> None:
    assert state.set_hatch('Other', '//')
    assert state.hatch_of('Other') == '//'


def test_hatch_defaults_to_none(state: AppState) -> None:
    assert state.hatch_of('Other') == ''


def test_unknown_hatch_is_refused(state: AppState) -> None:
    assert not state.set_hatch('Other', '///not-a-hatch///')
    assert state.hatch_of('Other') == ''


def test_clearing_the_hatch_returns_the_bar_to_plain(state: AppState) -> None:
    state.set_hatch('Other', 'xx')
    assert state.set_hatch('Other', '')
    assert state.hatch_of('Other') == ''


def test_multi_groups_skips_groups_of_one(state: AppState) -> None:
    """A group of one is not a grouping, so the window does not offer it."""
    assert state.multi_groups() == ('A',)


def test_multi_groups_grows_when_a_sample_joins(state: AppState) -> None:
    state.set_group('Other', 'C')
    assert state.multi_groups() == ('A', 'C')


def test_multi_groups_shrinks_when_a_sample_leaves(state: AppState) -> None:
    state.set_group('42C', 'B')
    assert state.multi_groups() == ('B',)


def test_multi_groups_keeps_the_drawing_order(state: AppState) -> None:
    state.set_group('Third', 'A')
    assert state.multi_groups() == ('A',)


def test_multi_groups_ignores_names_that_are_not_groups(state: AppState) -> None:
    state.merge_groups(('A', 'B'), 'A+B')
    assert state.multi_groups() == ('A+B',)


def test_a_line_thickness_is_stored_for_each_target(state: AppState) -> None:
    assert state.set_line_width('axis', 3.0)
    assert state.set_line_width('bar', 2.5)
    assert state.config.axis_line_width == 3.0
    assert state.config.bar_line_width == 2.5


def test_the_thicknesses_default_to_the_prism_value(state: AppState) -> None:
    assert state.line_width_of('axis') == DEFAULT_LINE_WIDTH
    assert state.line_width_of('bar') == DEFAULT_LINE_WIDTH
    assert state.config.axis_line_width is None


def test_clearing_a_thickness_restores_the_default(state: AppState) -> None:
    state.set_line_width('bar', 2.5)
    assert state.set_line_width('bar', None)
    assert state.config.bar_line_width is None
    assert state.line_width_of('bar') == DEFAULT_LINE_WIDTH


def test_an_unusable_thickness_is_refused(state: AppState) -> None:
    """A zero or negative width is ignored by the backend, so it must never be stored."""
    for value in (0.0, -1.0, 500.0):
        assert not state.set_line_width('axis', value)
    assert state.config.axis_line_width is None


def test_a_refused_thickness_leaves_the_previous_one_alone(state: AppState) -> None:
    state.set_line_width('axis', 3.0)
    assert not state.set_line_width('axis', -2.0)
    assert state.config.axis_line_width == 3.0


def test_a_reset_clears_both_thicknesses(state: AppState) -> None:
    state.set_line_width('axis', 3.0)
    state.set_line_width('bar', 2.5)
    state.reset()
    assert state.config.axis_line_width is None
    assert state.config.bar_line_width is None


def test_the_grouped_layout_is_off_until_it_is_asked_for(state: AppState) -> None:
    assert state.config.grouped_layout is False


def test_a_reset_turns_the_grouped_layout_off(state: AppState) -> None:
    state.config.grouped_layout = True
    state.reset()
    assert state.config.grouped_layout is False


def test_the_palette_starts_on_the_default(state: AppState) -> None:
    assert state.config.palette == DEFAULT_PALETTE
    assert state.color_of('Control') == palette_colors(DEFAULT_PALETTE, 4)[0]


def test_a_palette_change_recolours_every_sample(state: AppState) -> None:
    state.config.palette = 'viridis'
    viridis = palette_colors('viridis', 4)
    assert state.color_of('Control') == viridis[0]
    assert state.color_of('42C') == viridis[1]


def test_the_list_and_the_graph_agree_on_the_palette_colour(state: AppState) -> None:
    """Both read the same palette, so a swatch can never disagree with its bar."""
    from src.plotting import plot_dataset

    state.config.palette = 'okabe_ito'
    figure = plot_dataset(state.dataset, state.config)
    drawn = [patch.get_facecolor() for patch in figure.axes[0].containers[0]]
    listed = [matplotlib.colors.to_hex(state.color_of(sample.name)) for sample in state.samples]
    assert [matplotlib.colors.to_hex(color) for color in drawn] == listed


def test_the_list_and_the_graph_agree_when_colours_follow_groups(state: AppState) -> None:
    """The swatch has to follow the same rule the renderer does, in group mode too.

    Reporting a per sample palette entry while the renderer draws a per group one left the
    hex field and the swatch showing a colour the bar was not drawn in, so every colour
    control looked as though it had done nothing.
    """
    from src.plotting import plot_dataset

    state.config.color_by = 'group'
    state.config.palette = 'okabe_ito'
    figure = plot_dataset(state.dataset, state.config)
    drawn = [matplotlib.colors.to_hex(patch.get_facecolor()) for patch in figure.axes[0].containers[0]]
    listed = [matplotlib.colors.to_hex(state.color_of(sample.name)) for sample in state.samples]
    assert drawn == listed


@pytest.mark.parametrize('color_by', ['sample', 'group'])
def test_a_scatter_plot_is_coloured_by_series_whatever_the_mode(
    state: AppState, color_by: str
) -> None:
    """A scatter series is its own thing, so grouping never applies to it.

    The renderer ignores ``color_by`` for a scatter plot, and the reported colour has to do
    the same or the swatch would disagree with the points.
    """
    from src.models import XYPoint, XYSeries
    from src.plotting import plot_dataset

    state.dataset = Dataset(
        samples=(),
        series=(
            XYSeries('S1', (XYPoint(1.0, 10.0, 1), XYPoint(2.0, 12.0, 2))),
            XYSeries('S2', (XYPoint(1.0, 5.0, 1), XYPoint(2.0, 7.0, 2))),
        ),
        y_label='Response',
    )
    state.config.chart = 'scatter'
    state.config.color_by = color_by
    figure = plot_dataset(state.dataset, state.config)
    listed = [matplotlib.colors.to_hex(state.color_of(name)) for name in state.series_names]
    assert len(set(listed)) == 2, 'each series keeps its own colour'
    # A scatter point is an open circle, so the series colour is its edge rather than a fill.
    drawn = [matplotlib.colors.to_hex(line.get_markeredgecolor()) for line in figure.axes[0].get_lines()]
    assert drawn == listed


def test_samples_sharing_a_group_share_a_colour_in_group_mode(state: AppState) -> None:
    """Colouring by group means two samples in one group are drawn the same."""
    state.config.color_by = 'group'
    assert state.color_of('Control') == state.color_of('42C')
    assert state.color_of('Other') != state.color_of('Control')


def test_an_explicit_colour_still_wins_in_group_mode(state: AppState) -> None:
    """Colouring by group assigns palette colours; it does not forbid a chosen one."""
    state.config.color_by = 'group'
    state.set_color('42C', '#ff00ff')
    assert state.color_of('42C') == '#ff00ff'
    assert state.color_of('Control') != '#ff00ff'


def test_an_unknown_sample_still_reports_a_colour_in_group_mode(state: AppState) -> None:
    """A name that is not in the graph must not raise deep inside a widget."""
    state.config.color_by = 'group'
    assert normalize_hex(state.color_of('missing')) is not None


def test_an_explicit_colour_survives_a_palette_change(state: AppState) -> None:
    """Selecting a palette clears overrides, but one set afterwards is kept."""
    state.set_color('Control', '#123456')
    state.config.palette = 'viridis'
    assert state.color_of('Control') == '#123456'
    assert state.color_of('42C') == palette_colors('viridis', 4)[1]


def test_a_reset_returns_to_the_default_palette(state: AppState) -> None:
    state.config.palette = 'viridis'
    state.reset()
    assert state.config.palette == DEFAULT_PALETTE
    assert state.color_of('Control') == palette_colors(DEFAULT_PALETTE, 4)[0]


def test_an_unknown_palette_never_reaches_a_widget(state: AppState) -> None:
    """A hand-edited config must not leave the swatch with something Tk cannot parse."""
    state.config.palette = 'not-a-palette'
    assert normalize_hex(state.color_of('Control')) is not None


def test_automatic_y_max_leaves_headroom_above_the_tallest_mean(state: AppState) -> None:
    tallest = max(sample.mean for sample in state.samples)
    assert state.automatic_y_max() == pytest.approx(tallest * Y_MAX_HEADROOM)


def test_automatic_y_max_grows_with_the_data(state: AppState) -> None:
    before = state.automatic_y_max()
    state.dataset = Dataset(
        samples=(*state.dataset.samples, Sample('Huge', 'A', (100.0, 120.0))),
        y_label='Value',
    )
    assert state.automatic_y_max() > before


def test_automatic_y_max_uses_the_log_rule_on_a_log_axis(state: AppState) -> None:
    state.config.log_axis = True
    largest = max(value for sample in state.samples for value in sample.values)
    assert state.automatic_y_max() == pytest.approx(largest * LOG_HEADROOM)


def test_automatic_y_max_copes_with_an_empty_dataset() -> None:
    """With no data the axis still needs a finite top, so the fallback mean is used."""
    empty = AppState(Dataset(samples=(), y_label='Value'))
    assert empty.automatic_y_max() == pytest.approx(1.0 * Y_MAX_HEADROOM)


def test_group_reports_the_worksheet_value_by_default(state: AppState) -> None:
    assert state.group_of('Other') == 'B'
    assert state.groups() == ('A', 'B', 'C')


def test_moving_a_sample_onto_another_group(state: AppState) -> None:
    assert state.set_group('Other', 'A')
    assert state.group_of('Other') == 'A'
    assert state.groups() == ('A', 'C')


def test_moving_to_an_empty_group_restores_the_worksheet_value(state: AppState) -> None:
    state.set_group('Other', 'A')
    state.set_group('Other', '  ')
    assert state.group_of('Other') == 'B'
    assert 'Other' not in state.config.group_overrides


def test_group_override_leaves_the_worksheet_group_untouched(state: AppState) -> None:
    """The data read from the file must not be edited, only the way it is drawn."""
    state.set_group('Other', 'A')
    sheet_groups = {sample.name: sample.group for sample in state.dataset.samples}
    assert sheet_groups['Other'] == 'B'


def test_merging_groups_moves_every_member(state: AppState) -> None:
    assert state.merge_groups(('A', 'B'), 'A+B')
    assert state.group_of('Control') == 'A+B'
    assert state.group_of('Other') == 'A+B'
    assert state.groups() == ('A+B', 'C')


def test_merging_ignores_unknown_group_names(state: AppState) -> None:
    assert state.merge_groups(('B', 'missing'), 'Together')
    assert state.group_of('Other') == 'Together'


def test_merging_needs_a_name(state: AppState) -> None:
    assert not state.merge_groups(('A', 'B'), '   ')
    assert state.group_of('Control') == 'A'


def test_merging_an_unknown_group_alone_moves_nothing(state: AppState) -> None:
    assert not state.merge_groups(('missing',), 'X')
    assert state.groups() == ('A', 'B', 'C')


def test_splitting_gives_a_sample_its_own_group(state: AppState) -> None:
    state.merge_groups(('A', 'B'), 'A+B')
    assert state.split_sample('Other')
    assert state.group_of('Other') == 'Other'
    # 'Other' keeps its place in the drawing, so its own group sits between the two.
    assert state.groups() == ('A+B', 'Other', 'C')


def test_group_override_survives_reordering(state: AppState) -> None:
    state.set_group('Other', 'A')
    state.move_sample(0, 3)
    assert state.group_of('Other') == 'A'
    # Control moved to the end but is still in group A, which now starts at the first bar.
    assert state.groups() == ('A', 'C')


def test_reset_clears_every_new_setting(state: AppState) -> None:
    state.set_color('Other', '#ff0000')
    state.set_edge_color('Other', '#0000ff')
    state.set_hatch('Other', '//')
    state.set_group('Other', 'A')
    state.config.y_max = 500.0
    state.config.y_min = 10.0
    state.config.y_major_step = 25.0
    state.config.font_size = 14
    state.config.y_label_size = 16
    state.config.title_size = 18
    state.config.legend_size = 9
    state.config.title_font = 'Verdana'
    state.config.legend_font = 'Courier New'
    state.config.legend_position = 'right'
    state.config.title_position = 'center'

    state.reset()

    assert state.config.colors == {}
    assert state.config.edge_colors == {}
    assert state.config.hatches == {}
    assert state.config.group_overrides == {}
    assert state.config.y_max is None
    assert state.config.y_min is None
    assert state.config.y_major_step is None
    assert state.config.font_size is None
    assert state.config.y_label_size is None
    assert state.config.title_size is None
    assert state.config.legend_size is None
    assert state.config.y_label is None
    assert state.group_of('Other') == 'B'


def test_a_point_shape_is_stored_and_read_back(state: AppState) -> None:
    """A shape chosen for one sample is that sample's own."""
    assert state.set_point_type('42C', 'square')
    assert state.point_type_of('42C') == 'square'


def test_a_sample_with_no_shape_follows_the_whole_graph(state: AppState) -> None:
    """A sample that claimed none reads back the graph's shape, as the renderer would."""
    state.config.point_type = 'triangle'
    assert state.point_type_of('42C') == 'triangle'


def test_clearing_a_shape_returns_a_sample_to_the_graph(state: AppState) -> None:
    """Clearing drops the choice rather than pinning the sample to the shape it had."""
    state.set_point_type('42C', 'star')
    assert state.clear_point_type('42C')
    assert state.point_type_of('42C') == 'round'


def test_a_point_shape_for_an_unknown_sample_is_refused(state: AppState) -> None:
    """A name that is not in the graph cannot be drawn, so it is not stored."""
    assert not state.set_point_type('nope', 'star')
    assert state.config.point_types == {}


def test_clearing_a_shape_that_was_never_set_is_harmless(state: AppState) -> None:
    """A sample already following the graph has nothing to clear, which is not a failure."""
    assert state.clear_point_type('42C')
    assert state.config.point_types == {}


def test_a_reset_puts_the_points_back_to_the_default_shape(state: AppState) -> None:
    """A reset undoes the point shape, which is a choice like any other."""
    state.config.point_type = 'diamond'
    state.config.point_types['Control'] = 'star'
    state.reset()
    assert state.config.point_type == 'round'
    assert state.config.point_types == {}


def test_a_reset_puts_the_title_and_legend_back_to_their_defaults(state: AppState) -> None:
    """A reset undoes the fonts and the position, which are choices like any other."""
    state.config.title = 'Report'
    state.config.title_font = 'Verdana'
    state.config.legend_font = 'Courier New'
    state.config.legend_position = 'right'

    state.reset()

    assert state.config.title is None
    assert state.config.title_font is None
    assert state.config.legend_font is None
    assert state.config.legend_position == 'above'
    assert state.config.title_position == 'center'


def test_unknown_name_reports_minus_one(state: AppState) -> None:
    assert state.index_of('nope') == -1


def test_move_sample_reorders(state: AppState) -> None:
    assert state.move_sample(0, 2) == ('42C', 'Other', 'Control', 'Third')
    assert state.visible_order == ('42C', 'Other', 'Control', 'Third')


def test_move_sample_clamps_below_the_start(state: AppState) -> None:
    assert state.move_sample(2, -5) == ('Other', 'Control', '42C', 'Third')


def test_move_sample_clamps_past_the_end(state: AppState) -> None:
    assert state.move_sample(0, 99) == ('42C', 'Other', 'Third', 'Control')


def test_move_sample_ignores_a_bad_index(state: AppState) -> None:
    before = state.visible_order
    assert state.move_sample(9, 0) == before
    assert state.move_sample(-1, 0) == before
    assert state.visible_order == before


def test_moving_onto_itself_changes_nothing(state: AppState) -> None:
    assert state.move_sample(1, 1) == state.visible_order


def test_set_color_stores_an_override(state: AppState) -> None:
    assert state.set_color('42C', '#123456')
    assert state.color_of('42C') == '#123456'


def test_set_color_ignores_an_unknown_sample(state: AppState) -> None:
    assert not state.set_color('nope', '#123456')
    assert 'nope' not in state.config.colors


def test_color_falls_back_to_the_palette(state: AppState) -> None:
    """A sample with no colour of its own takes the next colour of the chosen palette."""
    expected = palette_colors(DEFAULT_PALETTE, len(state.visible_order))
    assert state.color_of('Control') == expected[0]
    assert state.color_of('42C') == expected[1]


def test_set_color_normalises_the_value(state: AppState) -> None:
    assert state.set_color('42C', '#00FF00')
    assert state.color_of('42C') == '#00ff00'


@pytest.mark.parametrize('bad', ['', 'not-a-colour', '#zzz', 'rgb(1,2,3)', '#12345'])
def test_set_color_refuses_unusable_text(state: AppState, bad: str) -> None:
    """A value Tk cannot parse would raise a bare error window deep inside a widget."""
    before = state.color_of('42C')
    assert not state.set_color('42C', bad)
    assert state.color_of('42C') == before


def test_color_of_never_returns_an_unusable_value(state: AppState) -> None:
    """Even a hand-edited config must not leak a bad colour into a widget."""
    state.config.colors['42C'] = 'garbage'
    assert normalize_hex(state.color_of('42C')) is not None


def test_color_of_unknown_sample_is_still_a_colour(state: AppState) -> None:
    assert normalize_hex(state.color_of('missing')) is not None


def test_reset_restores_the_defaults() -> None:
    config = PlotConfig(
        colors={'Control': '#123456'},
        log_axis=True,
        title='Changed',
        error_kind='sem',
        color_by='group',
        jitter=0.4,
        show_points=False,
    )
    dataset = Dataset(samples=(Sample('Control', 'A', (1.0, 2.0)), Sample('B', 'A', (3.0, 4.0))), y_label='v')
    state = AppState(dataset, config)
    state.move_sample(0, 1)
    state.reset()

    assert state.config.colors == {}
    assert state.config.log_axis is False
    assert state.config.title is None
    assert state.config.error_kind == 'sd'
    assert state.config.color_by == 'sample'
    assert state.config.jitter == 0.0
    assert state.config.show_points is True
    assert state.visible_order == ('Control', 'B')


def test_supplied_config_is_used(state: AppState) -> None:
    config = PlotConfig(title='Hello', log_axis=True)
    dataset = Dataset(samples=(Sample('A', 'g', (1.0, 2.0)),), y_label='v')
    assert AppState(dataset, config).config is config
    assert config.title == 'Hello'


def test_order_survives_an_incomplete_request() -> None:
    """Samples missing from sample_order must still be plotted, at the end."""
    dataset = Dataset(
        samples=(Sample('A', 'g', (1.0, 2.0)), Sample('B', 'g', (3.0, 4.0)), Sample('C', 'g', (5.0, 6.0))),
        y_label='v',
    )
    state = AppState(dataset, PlotConfig(sample_order=('C',)))
    assert state.visible_order == ('C', 'A', 'B')
    state.move_sample(0, 2)
    assert state.visible_order == ('A', 'B', 'C')
