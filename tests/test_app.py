"""Tests that the interactive window builds and reacts, without ever showing it."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from collections.abc import Iterator
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pandas as pd
import pytest
from matplotlib.colors import to_hex
from matplotlib.text import Text
from src.app_state import DEFAULT_LINE_WIDTH, HATCH_LABELS, HATCH_PATTERNS, AppState
from src.graphpad_style import DEFAULT_PALETTE, PALETTES, palette_colors
from src.models import CHART_KINDS, CHART_LABELS, ORIENTATION_LABELS, ORIENTATIONS, Dataset, Sample
from src.sheet_view import CELL_HEIGHT, COLUMN_HEADER_HEIGHT, Role
from src.ui import data_pane, shell, style_tab

if TYPE_CHECKING:
    from src.app import GraphPadApp

INPUT_FILE = Path(__file__).resolve().parents[1] / 'input' / 'Conc_bar_26-09-27.xlsx'
SCATTER_FILE = Path(__file__).resolve().parents[1] / 'input' / 'Conc_scatter_26-09-27.xlsx'


@pytest.fixture
def state() -> AppState:
    dataset = Dataset(
        samples=(
            Sample('Control', 'A', (10.0, 12.0)),
            Sample('42C', 'A', (20.0, 24.0)),
            Sample('B', 'C', (30.0, 36.0)),
        ),
        y_label='Value',
    )
    return AppState(dataset)


def _stub_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the message boxes with no-ops, because a real one blocks the test run."""
    for name in ('showerror', 'showwarning', 'showinfo'):
        monkeypatch.setattr(data_pane.messagebox, name, lambda *_a, **_k: None)
    monkeypatch.setattr(data_pane.messagebox, 'askyesno', lambda *_a, **_k: True)


def _hide(window: GraphPadApp) -> None:
    """Move the window off screen so it never flashes up, but keep it laid out.

    A withdrawn window is never mapped, so Tk reports placeholder sizes such as a one pixel
    button. That made real layout checks impossible.
    """
    window.root.geometry('4000x3000-4000-3000')
    window.root.update()
    window.root.update_idletasks()


@pytest.fixture
def app(state: AppState, monkeypatch: pytest.MonkeyPatch) -> Iterator[GraphPadApp]:
    """Build the real window, moved off screen so nothing is visible during the tests."""
    from src.app import GraphPadApp

    _stub_dialogs(monkeypatch)
    try:
        window = GraphPadApp(state, INPUT_FILE)
    except Exception as error:  # pragma: no cover - only on a machine with no display
        pytest.skip(f'No usable display: {error}')
    _hide(window)
    try:
        yield window
    finally:
        window.root.destroy()


def test_window_builds_and_draws(app: GraphPadApp) -> None:
    assert row_count(app) == 3
    assert len(app.canvas.figure.axes) == 1


def test_the_list_has_a_column_for_each_name(app: GraphPadApp) -> None:
    assert app.listbox.cget('columns') == ('sample', 'group')
    assert app.listbox.heading('sample', 'text') == 'Sample'
    assert app.listbox.heading('group', 'text') == 'Group'


def test_both_columns_are_left_aligned(app: GraphPadApp) -> None:
    assert str(app.listbox.column('sample', 'anchor')) == 'w'
    assert str(app.listbox.column('group', 'anchor')) == 'w'


def test_the_group_has_its_own_column(app: GraphPadApp) -> None:
    assert column_values(app, 'sample') == ['Control', '42C', 'B']
    assert column_values(app, 'group') == ['A', 'A', 'C']


def test_the_shown_group_follows_an_override(app: GraphPadApp) -> None:
    app.state.set_group('B', 'Renamed')
    app._refresh_list()
    assert column_values(app, 'group') == ['A', 'A', 'Renamed']


def test_a_sample_name_is_not_merged_with_its_group(app: GraphPadApp) -> None:
    """The two columns are separate, so a name with spaces stays in its own column."""
    app.state.set_group('B', 'Group with spaces')
    app._refresh_list()
    assert column_values(app, 'sample') == ['Control', '42C', 'B']
    assert column_values(app, 'group')[2] == 'Group with spaces'


def test_arrow_buttons_reorder(app: GraphPadApp) -> None:
    app._select_row(2)
    app._move_selected(-1)
    assert app.state.visible_order == ('Control', 'B', '42C')
    assert column_values(app, 'sample')[0] == 'Control'


def test_arrow_button_at_the_edge_is_a_no_op(app: GraphPadApp) -> None:
    app._select_row(0)
    app._move_selected(-1)
    assert app.state.visible_order == ('Control', '42C', 'B')


def test_selection_follows_the_moved_row(app: GraphPadApp) -> None:
    """The highlight has to stay on the sample that moved, not on its old position."""
    app._select_row(0)
    app._move_selected(1)
    assert app._selected_indices() == (1,)
    assert column_values(app, 'sample')[1] == 'Control'
    app._move_selected(1)
    assert app._selected_indices() == (2,)
    assert column_values(app, 'sample')[2] == 'Control'


def test_the_group_travels_with_its_sample(app: GraphPadApp) -> None:
    """A row shows two columns, so a move has to carry the group across with the name."""
    app._select_row(2)
    app._move_selected(-1)
    assert column_values(app, 'sample') == ['Control', 'B', '42C']
    assert column_values(app, 'group') == ['A', 'C', 'A']


def test_move_rows_clamps_and_ignores_bad_indices(app: GraphPadApp) -> None:
    app._move_rows(0, 99)
    assert column_values(app, 'sample')[-1] == 'Control'
    app._move_rows(99, 0)
    assert row_count(app) == 3


def _select_rows(app: GraphPadApp, *indices: int) -> None:
    """Highlight several rows, as a Ctrl-click sequence would."""
    app.listbox.selection_remove(app.listbox.selection())
    for index in indices:
        app.listbox.selection_add(app._row_id(index))
    app._show_selected_color()
    app._show_selected_style()


def row_count(app: GraphPadApp) -> int:
    """Return the number of rows the sample list holds."""
    return len(app.listbox.get_children())


def column_values(app: GraphPadApp, column: str) -> list[str]:
    """Return one column's text for every row, in order."""
    index = app.listbox.cget('columns').index(column)
    return [app.listbox.item(child, 'values')[index] for child in app.listbox.get_children()]


def test_the_list_allows_several_rows_at_once(app: GraphPadApp) -> None:
    _select_rows(app, 0, 2)
    assert app._selected_indices() == (0, 2)
    assert app._selected_samples() == ('Control', 'B')


def test_a_plain_selection_is_a_single_sample(app: GraphPadApp) -> None:
    _select_rows(app, 1)
    assert app._selected_samples() == ('42C',)
    assert app._selection_caption() == '42C'


def test_the_caption_states_how_many_are_selected(app: GraphPadApp) -> None:
    _select_rows(app, 0, 1, 2)
    assert app._selection_caption() == 'Control  +2 more'


def test_selecting_several_rows_by_hand(app: GraphPadApp) -> None:
    _select_rows(app, 0)
    app.listbox.selection_add(app._row_id(2))
    assert app._selected_samples() == ('Control', 'B')
    app.listbox.selection_remove(app._row_id(2))
    assert app._selected_samples() == ('Control',)


def test_selecting_a_run_of_rows_by_hand(app: GraphPadApp) -> None:
    _select_rows(app, 0, 1, 2)
    assert app._selected_samples() == ('Control', '42C', 'B')


def test_a_hatch_applies_to_every_selected_sample(app: GraphPadApp) -> None:
    _select_rows(app, 0, 1)
    app.hatch_var.set('xxx')
    app._apply_hatch()
    assert app.state.hatch_of('Control') == 'xxx'
    assert app.state.hatch_of('42C') == 'xxx'


def test_an_outline_applies_to_every_selected_sample(app: GraphPadApp) -> None:
    _select_rows(app, 0, 2)
    app.edge_var.set('#123456')
    app._apply_edge()
    assert app.state.edge_of('Control') == '#123456'
    assert app.state.edge_of('B') == '#123456'


def test_a_colour_applies_to_every_selected_sample(app: GraphPadApp) -> None:
    _select_rows(app, 0, 2)
    app.hex_var.set('#ff0000')
    app._apply_hex()
    assert app.state.color_of('Control') == '#ff0000'
    assert app.state.color_of('B') == '#ff0000'


def test_clearing_the_style_applies_to_every_selected_sample(app: GraphPadApp) -> None:
    _select_rows(app, 0, 1)
    for name in ('Control', '42C'):
        app.state.set_edge_color(name, '#00ff00')
        app.state.set_hatch(name, '//')
    app._clear_style()
    for name in ('Control', '42C'):
        assert app.state.edge_of(name) == '#000000'
        assert app.state.hatch_of(name) == ''


def test_grouping_the_selection_moves_every_sample(app: GraphPadApp) -> None:
    _select_rows(app, 0, 2)
    app.merge_name_var.set('Together')
    app._group_selection()
    assert app.state.group_of('Control') == 'Together'
    assert app.state.group_of('B') == 'Together'
    # 42C was not selected, so it keeps its own group.
    assert app.state.group_of('42C') == 'A'
    assert app.state.groups() == ('Together', 'A')


def test_grouping_asks_for_a_name(app: GraphPadApp) -> None:
    _select_rows(app, 0, 2)
    app._group_selection()
    assert app.state.groups() == ('A', 'C')


def test_grouping_asks_for_a_sample(app: GraphPadApp) -> None:
    _select_rows(app)
    app.merge_name_var.set('Together')
    app._group_selection()
    assert app.state.groups() == ('A', 'C')


def test_ungrouping_restores_the_worksheet_group(app: GraphPadApp) -> None:
    _select_rows(app, 0, 2)
    app.merge_name_var.set('Together')
    app._group_selection()
    _select_rows(app, 0, 2)
    app._ungroup_selection()
    assert app.state.group_of('Control') == 'A'
    assert app.state.group_of('B') == 'C'
    assert app.state.groups() == ('A', 'C')


def test_ungrouping_asks_for_a_sample(app: GraphPadApp) -> None:
    _select_rows(app)
    app._ungroup_selection()
    assert app.state.groups() == ('A', 'C')


def test_grouping_updates_the_list_the_checkboxes_and_the_graph(app: GraphPadApp) -> None:
    _select_rows(app, 0, 2)
    app.merge_name_var.set('Together')
    app._group_selection()
    assert column_values(app, 'group')[0] == 'Together'
    assert set(app.group_vars) == {'Together'}
    # The one bar left in group A is a group of one, so it no longer gets a band.
    assert [text.get_text() for text in app.canvas.figure.axes[0].texts] == ['Together']


def test_the_selection_survives_a_group_change(app: GraphPadApp) -> None:
    _select_rows(app, 0, 2)
    app.merge_name_var.set('Together')
    app._group_selection()
    assert app._selected_indices() == (0, 2)


def _real_click(app: GraphPadApp, row: int, ctrl: bool = False, shift: bool = False) -> None:
    """Send a genuine mouse click to the list, so Tk's own selection logic runs.

    Setting the selection by hand would bypass exactly the binding under test, so the
    modifier behaviour has to be exercised through real events. The click is aimed using
    the row's own bounding box, since a Treeview row is taller than a listbox row.
    """
    listbox = app.listbox
    listbox.focus_set()
    box = listbox.bbox(app._row_id(row))
    if box is None:
        pytest.skip('The row has no bounding box yet, so a click cannot be aimed at it.')
    x, y, _width, _height = box
    modifiers = {'state': 0x0004} if ctrl else ({'state': 0x0001} if shift else {})
    listbox.event_generate('<ButtonPress-1>', x=x + 5, y=y + 5, **modifiers)
    listbox.event_generate('<ButtonRelease-1>', x=x + 5, y=y + 5, **modifiers)
    app.root.update()


def test_a_real_click_selects_one_row(app: GraphPadApp) -> None:
    _real_click(app, 0)
    assert app._selected_samples() == ('Control',)


def test_a_real_ctrl_click_adds_one_row(app: GraphPadApp) -> None:
    _real_click(app, 0)
    _real_click(app, 2, ctrl=True)
    assert app._selected_samples() == ('Control', 'B')


def test_a_real_shift_click_takes_a_run_of_rows(app: GraphPadApp) -> None:
    _real_click(app, 0)
    _real_click(app, 2, shift=True)
    assert app._selected_samples() == ('Control', '42C', 'B')


def test_a_plain_click_replaces_the_whole_selection(app: GraphPadApp) -> None:
    """The way back to a single sample, since Ctrl-click cannot toggle a row off.

    Tk's EXTENDED listbox on Windows adds rows on Ctrl-click but never removes one, so a
    plain click is the only way to drop back to a single sample. Pinned here because the
    behaviour comes from Tk and would not be caught by a test that only added rows.
    """
    _real_click(app, 0)
    _real_click(app, 2, ctrl=True)
    _real_click(app, 0)
    assert app._selected_samples() == ('Control',)


def test_the_panel_heading_updates_on_a_real_click(app: GraphPadApp) -> None:
    _real_click(app, 0)
    assert app.style_name.cget('text') == 'Control'
    _real_click(app, 2, ctrl=True)
    assert app.style_name.cget('text') == 'Control  +1 more'


def test_legend_can_be_hidden(app: GraphPadApp) -> None:
    assert app.canvas.figure.axes[0].get_legend() is not None
    app.legend_var.set(False)
    app._update_legend()
    assert app.state.config.show_legend is False
    assert app.canvas.figure.axes[0].get_legend() is None


def _palette_color(app: GraphPadApp, index: int) -> str:
    """Return the colour the chosen palette gives to the sample at ``index``."""
    return palette_colors(app.state.config.palette, len(app.state.visible_order))[index]


def _swatches_in(widget: tk.Misc) -> list[tk.Canvas]:
    """Return every palette swatch canvas inside a widget, at any depth.

    Only the palette swatches count, which are recognised by the number of colour blocks they
    draw. The scrollable options area holds a plain canvas of its own, which is not a swatch.
    """
    from src.ui.style_tab import SWATCH_BLOCKS

    found: list[tk.Canvas] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Canvas) and len(child.find_all()) == SWATCH_BLOCKS:
            found.append(child)
        found.extend(_swatches_in(child))
    return found


def test_hex_field_applies_to_the_selected_sample(app: GraphPadApp) -> None:
    app._select_row(0)
    assert app.hex_var.get() == _palette_color(app, 0)
    app.hex_var.set('#00ff00')
    app._apply_hex()
    assert app.state.color_of('Control') == '#00ff00'


def test_hex_field_follows_the_selection(app: GraphPadApp) -> None:
    app._select_row(1)
    assert app.hex_var.get() == _palette_color(app, 1)
    app._select_row(0)
    assert app.hex_var.get() == _palette_color(app, 0)


def test_reset_colors_restores_the_palette(app: GraphPadApp) -> None:
    app._select_row(0)
    app.hex_var.set('#123456')
    app._apply_hex()
    assert app.state.color_of('Control') == '#123456'
    app._reset_colors()
    assert app.state.color_of('Control') == _palette_color(app, 0)
    assert app.state.config.colors == {}


@pytest.mark.parametrize(
    ('typed', 'expected'),
    [('#ff0000', '#ff0000'), ('#FF0000', '#ff0000'), ('ff0000', '#ff0000'), ('#f00', '#ff0000'), ('#abc', '#aabbcc')],
)
def test_normalize_hex_accepts_valid_colours(typed: str, expected: str) -> None:
    from src.app_state import normalize_hex

    assert normalize_hex(typed) == expected


@pytest.mark.parametrize('typed', ['', 'red', '#zzz', '#ff00', 'rgb(1,2,3)', '#1234567'])
def test_normalize_hex_rejects_invalid_colours(typed: str) -> None:
    from src.app_state import normalize_hex

    assert normalize_hex(typed) is None


def test_invalid_hex_is_rejected_and_the_colour_kept(app: GraphPadApp) -> None:
    app._select_row(0)
    before = _palette_color(app, 0)
    app.hex_var.set('not-a-colour')
    app._apply_hex()
    assert app.state.color_of('Control') == before
    assert app.hex_var.get() == before


@pytest.fixture
def grouped_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[GraphPadApp]:
    """Build a window over a dataset that really has two groups worth merging.

    The shared fixture has one group of two and a group of one, which leaves nothing to
    merge once groups of one are hidden from the list.
    """
    from src.app import GraphPadApp

    dataset = Dataset(
        samples=(
            Sample('Control', 'A', (10.0, 12.0)),
            Sample('42C', 'A', (20.0, 24.0)),
            Sample('Low', 'B', (30.0, 36.0)),
            Sample('High', 'B', (40.0, 44.0)),
            Sample('Solo', 'C', (50.0, 54.0)),
        ),
        y_label='Value',
    )
    _stub_dialogs(monkeypatch)
    try:
        window = GraphPadApp(AppState(dataset), INPUT_FILE)
    except Exception as error:  # pragma: no cover - only on a machine with no display
        pytest.skip(f'No usable display: {error}')
    _hide(window)
    try:
        yield window
    finally:
        window.root.destroy()


def test_style_panel_is_hidden_with_no_samples_to_style(state: AppState, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing to style yet, so the panel stays out of the way."""
    from src.app import GraphPadApp

    _stub_dialogs(monkeypatch)
    empty = GraphPadApp(AppState(Dataset(samples=(), y_label='Value')), INPUT_FILE)
    _hide(empty)
    try:
        assert empty.style_frame.winfo_manager() == ''
    finally:
        empty.root.destroy()


def test_choosing_a_row_reveals_and_fills_the_style_panel(app: GraphPadApp) -> None:
    app.state.set_edge_color('42C', '#00ff00')
    app.state.set_hatch('42C', 'xxx')
    app._select_row(1)
    assert app.style_frame.winfo_manager() == 'pack'
    assert app.style_name.cget('text') == '42C'
    assert app.edge_var.get() == '#00ff00'
    assert app.hatch_var.get() == 'xxx'


def test_the_style_panel_shows_a_newly_chosen_sample(app: GraphPadApp) -> None:
    app.state.set_hatch('42C', 'xxx')
    app._select_row(1)
    app._select_row(0)
    assert app.hatch_var.get() == HATCH_LABELS[0]


def test_outline_field_applies_to_the_selected_sample(app: GraphPadApp) -> None:
    app._select_row(0)
    app.edge_var.set('#123456')
    app._apply_edge()
    assert app.state.edge_of('Control') == '#123456'


def test_short_outline_colour_is_expanded(app: GraphPadApp) -> None:
    app._select_row(0)
    app.edge_var.set('#abc')
    app._apply_edge()
    assert app.state.edge_of('Control') == '#aabbcc'


def test_a_bad_outline_colour_is_refused_and_the_old_one_kept(app: GraphPadApp) -> None:
    app._select_row(0)
    app.state.set_edge_color('Control', '#00ff00')
    app.edge_var.set('not-a-colour')
    app._apply_edge()
    assert app.state.edge_of('Control') == '#00ff00'


def test_a_blank_outline_field_changes_nothing(app: GraphPadApp) -> None:
    app._select_row(0)
    app.state.set_edge_color('Control', '#00ff00')
    app.edge_var.set('')
    app._apply_edge()
    assert app.state.edge_of('Control') == '#00ff00'


def test_hatch_choice_applies_to_the_selected_sample(app: GraphPadApp) -> None:
    app._select_row(0)
    app.hatch_var.set('xxx')
    app._apply_hatch()
    assert app.state.hatch_of('Control') == 'xxx'


def test_choosing_none_removes_the_hatch(app: GraphPadApp) -> None:
    app._select_row(0)
    app.hatch_var.set('xxx')
    app._apply_hatch()
    app.hatch_var.set(HATCH_LABELS[0])
    app._apply_hatch()
    assert app.state.hatch_of('Control') == ''


def test_every_offered_hatch_is_accepted_by_the_state(app: GraphPadApp) -> None:
    app._select_row(0)
    for label in HATCH_LABELS:
        app.hatch_var.set(label)
        app._apply_hatch()
    assert app.state.hatch_of('Control') == HATCH_PATTERNS[-1]


def test_clear_style_returns_the_bar_to_plain(app: GraphPadApp) -> None:
    app._select_row(0)
    app.state.set_edge_color('Control', '#00ff00')
    app.state.set_hatch('Control', '//')
    app._clear_style()
    assert app.state.edge_of('Control') == '#000000'
    assert app.state.hatch_of('Control') == ''


def test_style_applies_only_to_the_selected_sample(app: GraphPadApp) -> None:
    app._select_row(0)
    app.state.set_hatch('Control', '//')
    assert app.state.hatch_of('42C') == ''


def test_the_hatch_reaches_the_drawn_bar(app: GraphPadApp) -> None:
    app._select_row(0)
    app.hatch_var.set('xxx')
    app._apply_hatch()
    bar = app.canvas.figure.axes[0].containers[0][0]
    assert bar.get_hatch() == 'xxx'


def test_the_outline_reaches_the_drawn_bar(app: GraphPadApp) -> None:
    app._select_row(0)
    app.edge_var.set('#123456')
    app._apply_edge()
    bar = app.canvas.figure.axes[0].containers[0][0]
    assert to_hex(bar.get_edgecolor()) == '#123456'


def _pick_event(artist: object, modifiers: tuple[str, ...] = ()) -> SimpleNamespace:
    """Build a stand-in for the pick event matplotlib delivers to the window.

    The real event carries a mouse event holding the modifier keys, and the handler reads
    them to decide whether a click extends the selection, so a bare artist is not enough.
    """
    return SimpleNamespace(artist=artist, mouseevent=SimpleNamespace(modifiers=list(modifiers)))


def _bar(app: GraphPadApp, index: int = 0) -> object:
    """Return the drawn bar patch for one sample."""
    return app.canvas.figure.axes[0].containers[0][index]


def _bar_left_edges(app: GraphPadApp) -> list[float]:
    """Return the left edge of every drawn bar, which is where the spacing shows."""
    return [float(bar.get_x()) for bar in app.canvas.figure.axes[0].containers[0]]


def test_clicking_a_bar_selects_that_sample(app: GraphPadApp) -> None:
    bar = _bar(app, 1)
    name = app.state.visible_order[1]
    app._on_pick(_pick_event(bar))
    assert app._selected_samples() == (name,)
    assert app.style_frame.winfo_manager() == 'pack'
    assert app.style_name.cget('text') == name


def test_the_bars_are_pickable_so_a_real_click_can_reach_the_window(app: GraphPadApp) -> None:
    """The mapping alone is not enough: an unpickable bar never emits a pick event.

    The click handler was fully written and its unit test passed while the bars were not
    pickable at all, so a real click in the window reached nothing. This asserts the part
    the earlier test could not see.
    """
    assert all(bar.pickable() for bar in app.canvas.figure.axes[0].containers[0])


def test_the_drawn_figure_belongs_to_the_live_canvas(app: GraphPadApp) -> None:
    """A figure that does not point back at the canvas has all picking silently dropped.

    Rebuilding the graph assigned the new figure to the canvas without the canvas being
    told, so every artist looked like it belonged to a different canvas and matplotlib
    discarded each pick. Nothing in the graph looked wrong; it just ignored every click.
    """
    assert app.canvas.figure.canvas is app.canvas


def test_the_pick_handler_is_connected_after_a_redraw(app: GraphPadApp) -> None:
    """Swapping the figure replaces the callback registry, which drops the handler.

    The connection made once at build time is silently gone after the first redraw, so it
    has to be made again with each new figure.
    """
    app.redraw()
    assert app.canvas.callbacks.callbacks.get('pick_event')


def test_a_bar_accepts_a_pick_from_the_live_canvas(app: GraphPadApp) -> None:
    """The hit test itself has to pass, which is what turns a click into a pick event.

    ``contains`` starts by checking the event came from the artist's own canvas, so a
    mismatch makes every bar report a miss even when the click is right on it.
    """
    from matplotlib.backend_bases import MouseEvent

    bar = _bar(app, 0)
    centre = app.canvas.figure.axes[0].transData.transform(
        (bar.get_x() + bar.get_width() / 2, bar.get_y() + bar.get_height() / 2)
    )
    event = MouseEvent('button_press_event', app.canvas, *centre, 1)
    assert bar.contains(event)[0]


def test_clicking_a_bar_does_not_open_the_colour_chooser(
    app: GraphPadApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing a sample must not also recolour it."""
    opened: list[bool] = []
    monkeypatch.setattr(style_tab.colorchooser, 'askcolor', lambda *_a, **_k: opened.append(True) or (None, None))
    app._on_pick(_pick_event(_bar(app, 0)))
    assert not opened
    assert app.state.config.colors == {}


def test_a_ctrl_click_on_a_bar_extends_the_selection(app: GraphPadApp) -> None:
    """Bars follow the same Ctrl and Shift rules as the list, so the two agree."""
    app._select_row(0)
    app._on_pick(_pick_event(_bar(app, 2), modifiers=('ctrl',)))
    assert app._selected_samples() == (app.state.visible_order[0], app.state.visible_order[2])


def test_a_second_ctrl_click_on_the_same_bar_takes_it_back_out(app: GraphPadApp) -> None:
    app._select_row(0)
    bar = _bar(app, 0)
    app._on_pick(_pick_event(bar, modifiers=('ctrl',)))
    assert app._selected_samples() == ()


def test_clicking_a_point_selects_the_bar_under_it(app: GraphPadApp) -> None:
    """The replicate points sit on top of their bar, so a click there must still land."""
    lines = [line for line in app.canvas.figure.axes[0].lines if line.get_picker()]
    assert lines
    app._on_pick(_pick_event(lines[0]))
    assert app._selected_samples() == (app.state.visible_order[0],)


def test_the_toolbar_guard_allows_a_click_while_it_is_idle(app: GraphPadApp) -> None:
    """The guard must not block ordinary clicks, which is the whole point of the feature."""
    assert not app._toolbar_is_active()
    app._on_pick(_pick_event(_bar(app, 1)))
    assert app._selected_samples() == (app.state.visible_order[1],)


def test_the_options_live_on_tabs(app: GraphPadApp) -> None:
    names = [app.tabs.tab(index, 'text') for index in range(app.tabs.index('end'))]
    assert names == ['General', 'Axis', 'Plot style', 'Data preview']


def test_the_axis_thickness_lives_on_the_axis_tab(app: GraphPadApp) -> None:
    assert 'Axis line width' in _captions_in(_tab_frame(app, 1))
    assert 'Axis line width' not in _captions_in(_tab_frame(app, 2))


def test_the_bar_thickness_lives_on_the_plot_style_tab(app: GraphPadApp) -> None:
    assert 'Bar outline width' in _captions_in(_tab_frame(app, 2))
    assert 'Bar outline width' not in _captions_in(_tab_frame(app, 1))


def test_the_grouped_layout_lives_on_the_plot_style_tab(app: GraphPadApp) -> None:
    """It is a statement about the drawing, so it moved off the Groups tab."""
    assert 'Group bars (Prism)' in _captions_in(_tab_frame(app, 2))
    assert 'Group bars (Prism)' not in _captions_in(_tab_frame(app, 3))


def _comboboxes_in(widget: tk.Misc) -> list[ttk.Combobox]:
    """Return every combobox inside a widget, at any depth."""
    found: list[ttk.Combobox] = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Combobox):
            found.append(child)
        found.extend(_comboboxes_in(child))
    return found


def _show_style_tab(app: GraphPadApp) -> None:
    """Bring the Plot style tab to the front, so its widgets are mapped and can be clicked.

    A widget on a tab that is not showing is unmapped, and Tk delivers a synthetic click to
    an unmapped widget as a no-op, so a click test has to select the tab first. The palette
    picker moved here from the Groups tab, so the clicks now go to this one.
    """
    app.tabs.select(app.tabs.tabs()[2])
    app.root.update()
    app.root.update_idletasks()


def _real_widget_click(widget: tk.Misc) -> None:
    """Send a genuine press and release to a widget, so Tk delivers its own bindings."""
    widget.event_generate('<ButtonPress-1>', x=2, y=2)
    widget.event_generate('<ButtonRelease-1>', x=2, y=2)


def test_the_palette_box_matches_the_other_dropdowns(app: GraphPadApp) -> None:
    """A picker of a different height to the comboboxes beside it looks like a mistake."""
    _show_style_tab(app)
    combos = _comboboxes_in(_tab_frame(app, 2))
    assert combos
    assert app.palette_button.winfo_reqheight() == combos[0].winfo_reqheight()
    assert app.palette_button.winfo_height() == combos[0].winfo_height()


def test_the_palette_name_is_left_aligned(app: GraphPadApp) -> None:
    """A centred name reads as right aligned once a swatch sits beside it."""
    assert str(app.palette_name.cget('anchor')) == 'w'


def test_the_palette_swatch_is_not_nested_in_a_themed_widget(app: GraphPadApp) -> None:
    """A ttk widget is not a container, so a swatch inside one fights the theme's layout."""
    # The picker itself must be a plain frame: a ttk widget owns its own element layout and
    # does not lay a packed canvas out the way the frame below does.
    assert not isinstance(app.palette_button, ttk.Widget)
    assert isinstance(app.palette_swatch.master, tk.Frame)


def test_clicking_the_palette_swatch_still_opens_the_menu(app: GraphPadApp) -> None:
    """The swatch is a sibling of the label now, so it needs the click of its own."""
    _show_style_tab(app)
    try:
        _real_widget_click(app.palette_swatch)
        assert app.palette_popup is not None
    finally:
        app._close_palette_menu()


def test_the_graph_type_and_orientation_are_offered(app: GraphPadApp) -> None:
    """The kind of graph is a statement about the whole graph; the turn of it is a style one."""
    general = _captions_in(_tab_frame(app, 0))
    style = _captions_in(_tab_frame(app, 2))
    assert 'Graph type' in general
    assert 'Graph type' not in style
    assert 'Graph orientation' in style
    assert 'Graph orientation' not in general
    # The window opens on the default for each, which must be a real member of its own list.
    assert app.chart_var.get() == CHART_LABELS[CHART_KINDS[0]]
    assert app.orientation_var.get() == ORIENTATION_LABELS[ORIENTATIONS[0]]


def test_the_inverted_orientation_is_not_offered(app: GraphPadApp) -> None:
    """A reader picks between the two ways round, not between three.

    The layout is still drawn when a saved file or the command line asks for it, so this is
    about the choice offered rather than about the setting being taken away.
    """
    offered = {
        str(value)
        for control in _comboboxes_in(_tab_frame(app, 2))
        for value in control.cget('values')
    }
    assert ORIENTATION_LABELS['inverted'] not in offered
    assert {ORIENTATION_LABELS['vertical'], ORIENTATION_LABELS['horizontal']} <= offered


def test_an_unknown_caption_falls_back_to_the_default(app: GraphPadApp) -> None:
    """A caption the window does not know must not be stored, or nothing could undo it."""
    app.orientation_var.set('Sideways')
    app._update_orientation()
    assert app.state.config.orientation == 'vertical'


def test_choosing_a_horizontal_orientation_moves_the_bars(app: GraphPadApp) -> None:
    """Values have to run across the graph, not up it, for the choice to mean anything."""
    from matplotlib.colors import to_hex

    app.orientation_var.set('Horizontal bars')
    app._update_orientation()
    ax = app.canvas.figure.axes[0]
    horizontal = to_hex(ax.patches[0].get_facecolor())
    assert app.state.config.orientation == 'horizontal'
    assert ax.get_ylabel() == ''
    app.orientation_var.set('Vertical bars')
    app._update_orientation()
    assert app.state.config.orientation == 'vertical'
    assert to_hex(app.canvas.figure.axes[0].patches[0].get_facecolor()) == horizontal


def test_the_scatter_controls_appear_only_for_a_scatter_plot(app: GraphPadApp) -> None:
    """A bar graph has no x values to point at, so the controls would be dead weight."""
    assert not app.xy_frame.winfo_manager()
    app.chart_var.set('Scatter plot')
    app._update_chart()
    app.root.update()
    assert app.state.config.chart == 'scatter'
    assert app.xy_frame.winfo_manager()
    app.chart_var.set('Bar graph')
    app._update_chart()
    app.root.update()
    assert app.state.config.chart == 'bar'
    assert not app.xy_frame.winfo_manager()


def test_a_chooser_entry_carries_its_row_number() -> None:
    """The entries are read rather than counted, so the number has to survive the round trip."""
    from src.ui.fields import choice_index

    assert choice_index('3: Conc.1, ng/uL') == 2
    assert choice_index('1: Group') == 0
    assert choice_index('(none)') is None
    assert choice_index('nonsense') is None


def test_a_range_of_rows_or_columns_is_accepted() -> None:
    """Naming three adjacent columns one at a time is tedious, so a range is expanded."""
    from src.ui.fields import parse_columns

    assert parse_columns('2-4') == [2, 3, 4]
    assert parse_columns('2,3,4') == [2, 3, 4]
    assert parse_columns(' 5 ; 7 ') == [5, 7]
    assert parse_columns('x') == []
    assert parse_columns('0') == []


def test_there_is_no_row_chooser_button(blank_app: GraphPadApp) -> None:
    """The rows are chosen in the preview beside the graph, not from a separate dialog."""
    buttons = {
        str(child.cget('text'))
        for child in blank_app.panel.winfo_children()
        if child.winfo_class() == 'TButton'
    }
    assert 'Choose rows…' not in buttons


def test_the_preview_offers_the_roles_the_graph_can_use(blank_app: GraphPadApp) -> None:
    """A role the graph cannot use does nothing, so it is not offered at all."""
    blank_app.sheet.set_mode('columns')
    shown = {str(button.cget('text')) for button in blank_app.sheet._role_buttons.values() if button.winfo_manager()}
    assert shown == {'Group', 'Conditions', 'Y values'}
    blank_app.sheet.set_mode('x_and_y')
    blank_app.root.update()
    shown = {str(button.cget('text')) for button in blank_app.sheet._role_buttons.values() if button.winfo_manager()}
    assert shown == {'X values', 'Y values', 'Conditions'}
    assert 'Group' not in shown


def test_a_marked_sheet_arrives_with_its_rows_already_assigned(blank_app: GraphPadApp) -> None:
    """The real sheet carries the markers, so the preview starts showing what was read."""
    assert blank_app.load_file(INPUT_FILE)
    assert blank_app.sheet.role_row(Role.GROUP) == 0
    assert blank_app.sheet.role_row(Role.CONDITIONS) == 1
    assert blank_app.sheet.columns == blank_app.sheet.measured_columns()


def test_a_row_pick_only_changes_the_graph_once_it_is_given_a_role(blank_app: GraphPadApp) -> None:
    """A row is only meaningful once it is named, so picking one re-reads nothing.

    Columns are the opposite: a click there is the whole gesture, because whether a column
    is plotted needs no further explanation.
    """
    assert blank_app.load_file(INPUT_FILE)
    before = row_count(blank_app)
    blank_app.sheet._toggle_pending(blank_app.sheet._pending_rows, 0)
    assert row_count(blank_app) == before
    assert blank_app.sheet.columns == blank_app.sheet.measured_columns()


def test_clicking_a_column_number_takes_its_bar_off_the_graph(blank_app: GraphPadApp) -> None:
    """One click has to leave a single column out, not name the columns that stayed.

    Going through a role button for this would mean naming all seven columns the user
    wanted to keep, which is why the heading itself is the toggle.
    """
    assert blank_app.load_file(INPUT_FILE)
    assert row_count(blank_app) == 8
    blank_app.sheet.toggle_column(3)
    blank_app.root.update()
    assert blank_app.sheet.columns == (1, 2, 4, 5, 6, 7, 8)
    assert row_count(blank_app) == 7


def test_clicking_a_column_number_again_puts_its_bar_back(blank_app: GraphPadApp) -> None:
    """A column left out has to be recoverable, or one stray click is permanent."""
    assert blank_app.load_file(INPUT_FILE)
    blank_app.sheet.toggle_column(3)
    blank_app.sheet.toggle_column(3)
    blank_app.root.update()
    assert blank_app.sheet.columns == blank_app.sheet.measured_columns()
    assert row_count(blank_app) == 8


def test_the_last_column_cannot_be_taken_off_the_graph(blank_app: GraphPadApp) -> None:
    """An empty graph cannot be clicked back out of, so the last column is kept."""
    assert blank_app.load_file(INPUT_FILE)
    blank_app.sheet.set_selection((2,), None)
    blank_app.sheet.toggle_column(2)
    blank_app.root.update()
    assert blank_app.sheet.columns == (2,)


def test_the_label_column_is_never_plotted(blank_app: GraphPadApp) -> None:
    """Column one holds the row labels, so a click on it is refused rather than honoured."""
    assert blank_app.load_file(INPUT_FILE)
    blank_app.sheet.toggle_column(0)
    blank_app.root.update()
    assert blank_app.sheet.columns == blank_app.sheet.measured_columns()


def test_giving_a_role_re_reads_the_sheet(blank_app: GraphPadApp) -> None:
    """Giving a y role to fewer columns is a real change, so the graph is redrawn from it."""
    assert blank_app.load_file(INPUT_FILE)
    assert row_count(blank_app) == 8
    blank_app.sheet._pending_columns.update({3, 4})
    blank_app.sheet.assign(Role.Y_VALUES)
    blank_app.root.update()
    assert blank_app.sheet.columns == (3, 4)
    assert row_count(blank_app) == 2


def test_a_sheet_with_markers_is_not_asked_about(blank_app: GraphPadApp) -> None:
    """The real sheet carries the usual markers, so no dialog may interrupt the load."""
    assert blank_app.load_file(INPUT_FILE)
    assert row_count(blank_app) == 8
    # No dialog was opened, so nothing was remembered and the file is read the same way again.
    assert INPUT_FILE.name not in blank_app._remembered_layout


def test_the_palette_button_lives_on_the_plot_style_tab(app: GraphPadApp) -> None:
    assert 'Colour palette' in _captions_in(_tab_frame(app, 2))
    assert 'Colour palette' not in _captions_in(_tab_frame(app, 0))


def test_the_palette_button_shows_the_palette_in_use(app: GraphPadApp) -> None:
    app._sync_from_state()
    assert app.palette_key_var.get() == DEFAULT_PALETTE
    assert app.palette_var.get() == PALETTES[DEFAULT_PALETTE].label


def test_the_palette_button_carries_a_swatch(app: GraphPadApp) -> None:
    """The swatch is what shows the choice without opening the menu."""
    from src.ui.style_tab import SWATCH_BLOCKS

    assert app.palette_swatch.winfo_class() == 'Canvas'
    assert len(app.palette_swatch.find_all()) == SWATCH_BLOCKS


def test_the_swatch_shows_the_palette_that_will_be_drawn(app: GraphPadApp) -> None:
    """A preview that disagreed with the graph would be worse than no preview.

    The swatch always shows a fixed number of blocks, while a sequential palette spreads its
    colours over as many bars as there are. So with fewer bars than blocks the graph picks
    every nth colour, and the two agree on the ends rather than on every block.
    """
    from src.ui.style_tab import SWATCH_BLOCKS

    app._choose_palette('viridis')
    drawn = [to_hex(patch.get_facecolor()) for patch in app.canvas.figure.axes[0].containers[0]]
    filled = [app.palette_swatch.itemcget(item, 'fill') for item in app.palette_swatch.find_all()]
    assert filled[0] == drawn[0]
    assert filled[-1] == drawn[-1]
    assert len(filled) == SWATCH_BLOCKS


def test_a_categorical_swatch_matches_the_graph_exactly(app: GraphPadApp) -> None:
    """A categorical palette shows the same colours however many bars there are."""
    from src.ui.style_tab import SWATCH_BLOCKS

    app._choose_palette('tab10')
    drawn = [to_hex(patch.get_facecolor()) for patch in app.canvas.figure.axes[0].containers[0]]
    filled = [app.palette_swatch.itemcget(item, 'fill') for item in app.palette_swatch.find_all()]
    assert filled[: len(drawn)] == drawn
    assert len(filled) == SWATCH_BLOCKS


def test_the_palette_menu_lists_every_palette_under_a_heading(app: GraphPadApp) -> None:
    app._open_palette_menu()
    try:
        text = _captions_in(app.palette_popup)
        assert {'Categorical', 'Sequential', 'GraphPad'} <= text
        assert {palette.label for palette in PALETTES.values()} <= text
    finally:
        app._close_palette_menu()


def test_the_palette_menu_draws_a_swatch_for_every_palette(app: GraphPadApp) -> None:
    from src.ui.style_tab import SWATCH_BLOCKS

    app._open_palette_menu()
    try:
        swatches = _swatches_in(app.palette_popup)
        assert len(swatches) == len(PALETTES)
        for swatch in swatches:
            assert len(swatch.find_all()) == SWATCH_BLOCKS
    finally:
        app._close_palette_menu()


def test_every_menu_swatch_fills_its_strip(app: GraphPadApp) -> None:
    """A strip drawn from a placeholder width collapses to a hairline and shows no colour."""
    from src.ui.style_tab import SWATCH_BLOCKS, SWATCH_WIDTH

    app._open_palette_menu()
    try:
        for swatch in _swatches_in(app.palette_popup):
            widths = [swatch.coords(item)[2] - swatch.coords(item)[0] for item in swatch.find_all()]
            assert len(widths) == SWATCH_BLOCKS
            assert sum(widths) >= SWATCH_WIDTH
    finally:
        app._close_palette_menu()


def test_choosing_a_palette_from_the_menu_applies_it(app: GraphPadApp) -> None:
    app._choose_palette('viridis')
    assert app.state.config.palette == 'viridis'
    assert app.palette_var.get() == PALETTES['viridis'].label


def test_choosing_a_palette_closes_the_menu(app: GraphPadApp) -> None:
    app._open_palette_menu()
    app._choose_palette('magma')
    assert app.palette_popup is None


def test_escape_closes_the_palette_menu(app: GraphPadApp) -> None:
    app._open_palette_menu()
    app.palette_popup.event_generate('<Escape>')
    app.root.update()
    assert app.palette_popup is None


def test_opening_the_palette_menu_twice_closes_it(app: GraphPadApp) -> None:
    """The button toggles, so a second press must not stack two menus on the screen."""
    app._open_palette_menu()
    first = app.palette_popup
    app._open_palette_menu()
    assert app.palette_popup is None
    assert not first.winfo_exists()


def test_choosing_a_palette_recolours_the_bars(app: GraphPadApp) -> None:
    before = to_hex(_bar(app, 0).get_facecolor())
    app._choose_palette('viridis')
    assert to_hex(_bar(app, 0).get_facecolor()) != before
    assert to_hex(_bar(app, 0).get_facecolor()) == _palette_color(app, 0)


def test_choosing_a_palette_recolours_the_sample_list(app: GraphPadApp) -> None:
    """The list swatches share the palette, so they must not be left on the old colours."""
    before = app.state.color_of(app.state.visible_order[0])
    app._choose_palette('viridis')
    assert app.state.color_of(app.state.visible_order[0]) != before


def test_choosing_a_palette_drops_colours_set_by_hand(app: GraphPadApp) -> None:
    """Otherwise one overridden bar would keep a colour that is not in the scheme."""
    app.state.set_color('Control', '#123456')
    assert app.state.color_of('Control') == '#123456'
    app._choose_palette('viridis')
    assert app.state.config.colors == {}


def test_a_single_bar_can_be_recoloured_after_a_palette_change(app: GraphPadApp) -> None:
    """The palette sets the scheme; an individual bar can still be pulled out of it."""
    app._choose_palette('viridis')
    app._select_row(0)
    app.state.set_color('Control', '#123456')
    app.redraw()
    assert to_hex(_bar(app, 0).get_facecolor()) == '#123456'
    assert to_hex(_bar(app, 1).get_facecolor()) != '#123456'


def test_choosing_the_palette_already_in_use_changes_nothing(app: GraphPadApp) -> None:
    """Re-picking the same entry must not throw away the colours set since."""
    app.state.set_color('Control', '#123456')
    app._choose_palette(DEFAULT_PALETTE)
    assert app.state.color_of('Control') == '#123456'


def test_a_reset_returns_the_palette_to_the_default(app: GraphPadApp) -> None:
    app._choose_palette('viridis')
    app._reset()
    assert app.palette_key_var.get() == DEFAULT_PALETTE
    assert app.state.config.palette == DEFAULT_PALETTE
    assert app.palette_var.get() == PALETTES[DEFAULT_PALETTE].label


def test_the_grouped_layout_starts_off(app: GraphPadApp) -> None:
    app._sync_from_state()
    assert app.grouped_var.get() is False
    assert app.state.config.grouped_layout is False


def test_ticking_the_grouped_layout_widens_the_group_gap(app: GraphPadApp) -> None:
    plain = _bar_left_edges(app)
    app.grouped_var.set(True)
    app._update_grouped()
    assert app.state.config.grouped_layout is True
    grouped = _bar_left_edges(app)
    assert grouped[2] - plain[2] > grouped[0] - plain[0]


def test_unticking_the_grouped_layout_restores_the_flat_spacing(app: GraphPadApp) -> None:
    plain = _bar_left_edges(app)
    app.grouped_var.set(True)
    app._update_grouped()
    app.grouped_var.set(False)
    app._update_grouped()
    assert app.state.config.grouped_layout is False
    assert _bar_left_edges(app) == pytest.approx(plain)


def test_grouping_does_nothing_when_every_sample_shares_one_group(app: GraphPadApp) -> None:
    """With a single group there is no boundary to show, so the layout stays flat."""
    for name in app.state.visible_order:
        app.state.set_group(name, 'Only')
    app.grouped_var.set(True)
    app._update_grouped()
    assert app.state.config.grouped_layout is False


def test_a_reset_unticks_the_grouped_layout(app: GraphPadApp) -> None:
    app.grouped_var.set(True)
    app._update_grouped()
    app._reset()
    assert app.grouped_var.get() is False
    assert app.state.config.grouped_layout is False


def test_the_thickness_fields_start_at_the_prism_value(app: GraphPadApp) -> None:
    app._sync_from_state()
    assert app.axis_width_var.get() == f'{DEFAULT_LINE_WIDTH:g}'
    assert app.bar_width_var.get() == f'{DEFAULT_LINE_WIDTH:g}'


def test_a_typed_axis_thickness_reaches_the_graph(app: GraphPadApp) -> None:
    app.axis_width_var.set('3')
    app._update_line_width()
    assert app.state.config.axis_line_width == 3.0
    assert app.canvas.figure.axes[0].spines['left'].get_linewidth() == pytest.approx(3.0)


def test_a_typed_bar_thickness_reaches_the_drawn_bar(app: GraphPadApp) -> None:
    app.bar_width_var.set('2.5')
    app._update_line_width()
    assert app.state.config.bar_line_width == 2.5
    assert _bar(app, 0).get_linewidth() == pytest.approx(2.5)


def test_changing_one_thickness_keeps_the_other(app: GraphPadApp) -> None:
    """Both fields are read on every change, so one must not overwrite the other."""
    app.bar_width_var.set('2.5')
    app._update_line_width()
    app.axis_width_var.set('3')
    app._update_line_width()
    assert app.state.config.bar_line_width == 2.5
    assert app.state.config.axis_line_width == 3.0


def test_a_half_typed_thickness_is_ignored(app: GraphPadApp) -> None:
    """Text that is not a number yet must not disturb the thickness already chosen."""
    app.axis_width_var.set('3')
    app._update_line_width()
    app.axis_width_var.set('tbc')
    app._update_line_width()
    assert app.state.config.axis_line_width == 3.0
    assert app.axis_width_var.get() == '3'


def test_an_undrawable_thickness_is_put_back(app: GraphPadApp) -> None:
    app.bar_width_var.set('-4')
    app._update_line_width()
    assert app.state.config.bar_line_width is None
    assert app.bar_width_var.get() == f'{DEFAULT_LINE_WIDTH:g}'


def test_an_empty_thickness_restores_the_default(app: GraphPadApp) -> None:
    app.bar_width_var.set('2.5')
    app._update_line_width()
    app.bar_width_var.set('')
    app._update_line_width()
    assert app.state.config.bar_line_width is None
    assert _bar(app, 0).get_linewidth() == pytest.approx(DEFAULT_LINE_WIDTH)


def test_a_reset_puts_both_thickness_fields_back(app: GraphPadApp) -> None:
    app.axis_width_var.set('3')
    app.bar_width_var.set('2.5')
    app._update_line_width()
    app._reset()
    assert app.axis_width_var.get() == f'{DEFAULT_LINE_WIDTH:g}'
    assert app.bar_width_var.get() == f'{DEFAULT_LINE_WIDTH:g}'


def _tab_frame(app: GraphPadApp, index: int) -> tk.Misc:
    """Return the frame backing one of the notebook's tabs."""
    return app.tabs.nametowidget(app.tabs.tabs()[index].split('.')[-1])


def _captions_in(widget: tk.Misc) -> set[str]:
    """Return every label and button caption on screen inside a widget, at any depth.

    Only packed widgets are counted, so a block that is deliberately hidden until a sample
    is chosen does not appear just because its child widgets still exist. A bordered block
    is counted by the caption on its border, which is how a reader tells the two axis
    blocks apart and so has to be part of what the layout is checked against.
    """
    found: set[str] = set()
    for child in widget.winfo_children():
        if child.winfo_manager():
            if child.winfo_class() in ('TLabel', 'TButton', 'TCheckbutton', 'TLabelframe'):
                found.add(str(child.cget('text')))
            found |= _captions_in(child)
    return found


def test_the_y_title_field_shows_the_sheet_title(app: GraphPadApp) -> None:
    app._sync_from_state()
    assert app.y_title_var.get() == app.state.dataset.y_label == 'Value'


def test_a_new_y_title_reaches_the_graph(app: GraphPadApp) -> None:
    app.y_title_var.set('Yield (mg/L)')
    app._update_y_title()
    assert app.state.config.y_label == 'Yield (mg/L)'
    assert app.canvas.figure.axes[0].get_ylabel() == 'Yield (mg/L)'


def test_the_sheet_title_is_not_stored_as_an_override(app: GraphPadApp) -> None:
    """Showing the sheet's own title must not fix it as if the user had typed it."""
    app.y_title_var.set(app.state.dataset.y_label)
    app._update_y_title()
    assert app.state.config.y_label is None


def test_clearing_the_y_title_falls_back_to_the_sheet(app: GraphPadApp) -> None:
    app.y_title_var.set('Yield')
    app._update_y_title()
    app.y_title_var.set('   ')
    app._update_y_title()
    assert app.state.config.y_label is None
    assert app.canvas.figure.axes[0].get_ylabel() == 'Value'


def test_a_y_title_is_trimmed(app: GraphPadApp) -> None:
    app.y_title_var.set('  Yield  ')
    app._update_y_title()
    assert app.state.config.y_label == 'Yield'


def test_reset_restores_the_sheet_y_title(app: GraphPadApp) -> None:
    app.y_title_var.set('Yield')
    app._update_y_title()
    app._reset()
    assert app.state.config.y_label is None
    assert app.y_title_var.get() == 'Value'
    assert app.canvas.figure.axes[0].get_ylabel() == 'Value'


def test_axis_lengths_update_and_reject_nonpositive_values(app: GraphPadApp) -> None:
    app.x_axis_length_var.set('10.5')
    app.y_axis_length_var.set('0')
    app._update_axis_lengths()

    assert app.state.config.x_axis_length_cm == 10.5
    assert app.state.config.y_axis_length_cm == 8.0
    assert app.x_axis_length_var.get() == '10.5'
    assert app.y_axis_length_var.get() == '8'


def test_reset_restores_default_axis_lengths(app: GraphPadApp) -> None:
    app.x_axis_length_var.set('12')
    app.y_axis_length_var.set('6')
    app._update_axis_lengths()
    app._reset()

    assert app.state.config.x_axis_length_cm == 9.0
    assert app.state.config.y_axis_length_cm == 8.0
    assert app.x_axis_length_var.get() == '9'
    assert app.y_axis_length_var.get() == '8'


def test_saving_uses_the_natural_figure_size(
    app: GraphPadApp,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    saved_sizes: list[tuple[float, float]] = []
    figure = app.canvas.figure
    natural_size = app._natural_figure_size
    figure.set_size_inches(natural_size[0] * 0.75, natural_size[1] * 0.75, forward=False)

    def record_save_size(_path: Path) -> None:
        saved_sizes.append(tuple(float(value) for value in figure.get_size_inches()))

    monkeypatch.setattr(figure, 'savefig', record_save_size)
    monkeypatch.setattr(shell.filedialog, 'asksaveasfilename', lambda **_kwargs: str(tmp_path / 'graph.pdf'))
    app._save('pdf')

    assert saved_sizes == [natural_size]


def test_each_setting_sits_on_the_tab_it_belongs_to(app: GraphPadApp) -> None:
    general = _captions_in(_tab_frame(app, 0))
    axis = _captions_in(_tab_frame(app, 1))
    style = _captions_in(_tab_frame(app, 2))

    assert 'Plot title' in general
    assert {'Title font type', 'Title text size', 'Title position'} <= general
    assert 'Show legend' in general
    assert {'Legend font type', 'Legend text size', 'Legend position'} <= general
    assert 'Graph type' in general
    # How the marks are drawn is a style choice, so it moved off the General tab.
    assert {'Replicate points', 'Replicate spread', 'Graph orientation'} <= style
    assert not {'Replicate points', 'Replicate spread', 'Graph orientation'} & general

    # The Axis tab is split into one block per axis, each with its own name, range and font.
    # The rotation sits with the x axis, whose labels are the ones long enough to need it.
    assert {
        'X axis',
        'X max',
        'X step',
        'X axis type',
        'X tick text size',
        'X axis length (cm)',
        'Label rotation',
    } <= axis
    assert {
        'Y axis',
        'Y max',
        'Y step',
        'Y axis type',
        'Y tick text size',
        'Y axis length (cm)',
        'Y title text size',
    } <= axis
    # The line width and the label family draw both axes, so they sit above the two blocks
    # rather than inside either of them.
    assert {'Axis line width', 'Axis font type'} <= axis
    assert 'Automatic values' not in axis
    # The axis captions are plain "Title" inside their block rather than naming the axis,
    # because the block on the border already says which axis it is.
    assert 'Y axis title' not in axis
    assert 'From the sheet' not in axis
    # The title and the legend are not part of an axis, so their sizes sit on General.
    assert 'Legend font size' not in axis
    assert 'Title font size' not in axis

    # The Plot style tab carries the whole drawing, in the order it is dressed in.
    assert {
        'Join the points with a line',
        'Replicate points',
        'Replicate spread',
        'Graph orientation',
        'Error bars',
        'Bar outline width',
        'Bar hatch',
        'Colour palette',
        'Colour by',
        'Group bars (Prism)',
    } <= style
    assert {'Outline', 'Hatch', 'Clear style'} <= style
    # The shape of a point belongs to whichever series is highlighted, so it sits with the
    # Connect and Name boxes rather than in the drawing above them. Those live in a block that
    # only appears for a scatter plot with a series chosen, so it is checked in its own test
    # rather than here, where the tab is being read for a bar graph.
    assert 'Point type' not in style

    # Grouping had a tab of its own until it was left with nothing else, so it now sits at
    # the bottom of the Plot style tab, after the per sample block it acts alongside.
    assert 'Groups' in style
    assert 'Group samples as' in style
    assert not _captions_in(_tab_frame(app, 3)) & {'Colour by', 'Group samples as', 'Groups'}


def test_the_legend_has_a_block_of_its_own(app: GraphPadApp) -> None:
    """Every legend setting sits inside one titled block.

    Left in the open they read as belonging to the title above them, so the sub-header is
    what tells a reader that the switch, the two fonts and the position are one thing.
    """
    general = _tab_frame(app, 0)
    blocks = {
        str(child.cget('text')): child
        for child in general.winfo_children()
        if child.winfo_class() == 'TLabelframe'
    }
    assert 'Legend' in blocks
    inside = _captions_in(app.legend_frame)
    assert {'Show legend', 'Legend font type', 'Legend text size', 'Legend position'} <= inside
    # The title settings are not the legend's, so they stay outside the block.
    assert 'Plot title' not in inside
    assert 'Title text size' not in inside


def test_the_title_reaches_the_graph_in_the_window(app: GraphPadApp) -> None:
    """Typing a title draws it, centred above the plot, on the canvas that is on screen."""
    app.title_var.set('Growth rate')
    app._update_title()
    app.canvas.figure.canvas.draw()
    title = next(text for text in app.canvas.figure.texts if text.get_text() == 'Growth rate')
    box = title.get_window_extent()
    assert box.y0 >= 0 and box.y1 <= app.canvas.figure.bbox.height


def test_the_legend_position_reaches_the_graph_in_the_window(app: GraphPadApp) -> None:
    """Choosing a position moves the legend without changing the figure's size."""
    natural_size = app._natural_figure_size
    app.legend_position_var.set('Right of graph')
    app._update_legend_position()
    assert app.state.config.legend_position == 'right'
    assert app._natural_figure_size == natural_size
    app.canvas.draw()
    axes = app.canvas.figure.axes[0]
    legend = axes.get_legend()
    assert legend is not None
    assert legend.get_window_extent().x0 >= axes.get_window_extent().x1


def test_an_unknown_legend_position_falls_back_to_the_default(app: GraphPadApp) -> None:
    """A caption the window does not know is not stored, which nothing could undo."""
    app.legend_position_var.set('Somewhere else entirely')
    app._update_legend_position()
    assert app.state.config.legend_position == 'above'


def test_the_font_types_reach_the_graph_in_the_window(app: GraphPadApp) -> None:
    """Both families are applied to the piece of text they were chosen for."""
    app.title_var.set('Growth rate')
    app._update_title()
    app.title_font_type_var.set('Verdana')
    app._update_title_font()
    app.legend_font_type_var.set('Courier New')
    app._update_legend_font()
    title = next(text for text in app.canvas.figure.texts if text.get_text() == 'Growth rate')
    assert title.get_fontfamily() == ['Verdana']
    legend = app.canvas.figure.axes[0].get_legend()
    assert legend is not None
    assert legend.get_texts()[0].get_fontfamily() == ['Courier New']


def test_the_default_font_type_is_not_stored_as_a_choice(app: GraphPadApp) -> None:
    """The family a graph already uses stores nothing, so it keeps following the figure."""
    app.title_font_type_var.set('Arial')
    app._update_title_font()
    app.legend_font_type_var.set('Arial')
    app._update_legend_font()
    assert app.state.config.title_font is None
    assert app.state.config.legend_font is None


def test_the_legend_and_title_settings_survive_a_sync(app: GraphPadApp) -> None:
    """Loading and resetting put the fields back to the settings really in use."""
    app.state.config.legend_position = 'right'
    app.state.config.legend_font = 'Courier New'
    app.state.config.title_font = 'Verdana'
    app._sync_from_state()
    assert app.legend_position_var.get() == 'Right of graph'
    assert app.legend_font_type_var.get() == 'Courier New'
    assert app.title_font_type_var.get() == 'Verdana'
    assert app.title_position_var.get() == 'Centered above the graph'


def test_a_reset_puts_the_legend_block_back_to_its_defaults(app: GraphPadApp) -> None:
    """A reset is meant to undo the legend choices too, not only the sample ones."""
    app.legend_position_var.set('Right of graph')
    app._update_legend_position()
    app.legend_font_type_var.set('Courier New')
    app._update_legend_font()
    app._reset()
    assert app.state.config.legend_position == 'above'
    assert app.state.config.legend_font is None
    assert app.legend_position_var.get() == 'Above graph'
    assert app.legend_font_type_var.get() == 'Arial'


def test_the_panel_carries_no_explaining_sentences(app: GraphPadApp) -> None:
    """A sentence under every field turns the panel into something to read.

    The hints that were there repeated what the fields already said, and said where a choice
    lives rather than what the choice does, so they are gone.
    """
    everywhere = _captions_in(app.panel)
    for gone in (
        'Applies to every series. A single one is connected from the block below.',
        'Turn the legend off on the General tab to see the names alone.',
        'Choosing a palette recolours every bar; set a bar colour afterwards to keep one.',
    ):
        assert gone not in everywhere


def test_the_bar_style_block_hides_with_no_selection(state: AppState, monkeypatch: pytest.MonkeyPatch) -> None:
    """The per sample style block has nothing to act on until a sample is chosen."""
    from src.app import GraphPadApp

    _stub_dialogs(monkeypatch)
    window = GraphPadApp(AppState(Dataset(samples=(), y_label='Value')), INPUT_FILE)
    _hide(window)
    try:
        assert 'Clear style' not in _captions_in(_tab_frame(window, 2))
        assert window.style_frame.winfo_manager() == ''
    finally:
        window.root.destroy()


def test_the_colour_chooser_sits_beside_the_hex_value(app: GraphPadApp) -> None:
    assert app.swatch.master is app.hex_entry.master
    assert app.swatch.winfo_x() > app.hex_entry.winfo_x()


def test_clicking_the_arrow_buttons_reorders(app: GraphPadApp) -> None:
    """The buttons have to be reachable, not merely present.

    They were once squeezed to a few pixels by the list expanding over them, which left the
    list with no way to be reordered at all.
    """
    frame = next(child for child in app.listbox.master.winfo_children() if child.winfo_class() == 'TFrame')
    up, down = frame.winfo_children()
    app._select_row(0)
    assert frame.winfo_children()[1] is down
    down.invoke()
    assert app.state.visible_order[0] == '42C'
    up.invoke()
    assert app.state.visible_order[0] == 'Control'
    _select_rows(app, 0, 2)
    up.invoke()
    assert app.state.visible_order == ('Control', 'B', '42C')
    assert app._selected_indices() == (0, 1)
    mapping = getattr(app.canvas.figure, 'sample_by_bar', {})
    bars = app.canvas.figure.axes[0].containers[0]
    assert [mapping[id(bar)] for bar in bars] == list(app.state.visible_order)
    down.invoke()
    assert app.state.visible_order == ('42C', 'Control', 'B')
    assert app._selected_indices() == (1, 2)


def test_the_arrow_buttons_get_a_usable_width(app: GraphPadApp) -> None:
    """The list must not expand into the button column and squeeze the buttons away.

    Found by looking at a screenshot: the list was packed with ``expand=True``, which took
    almost all the width and left the button frame five pixels wide, so both arrows were
    drawn off the panel and the list could no longer be reordered at all.
    """
    row = app.listbox.master
    frame = next(child for child in row.winfo_children() if child.winfo_class() == 'TFrame')
    assert frame.winfo_width() >= 24
    for button in frame.winfo_children():
        assert button.winfo_width() >= 20
        assert button.winfo_ismapped()


def test_the_arrow_buttons_are_fully_inside_their_block(app: GraphPadApp) -> None:
    """The reordering buttons used to be clipped by the fixed height of the list block."""
    row = app.listbox.master
    frame = next(child for child in row.winfo_children() if child.winfo_class() == 'TFrame')
    block_top = app.listbox.winfo_rooty()
    block_bottom = block_top + row.winfo_height()
    for button in frame.winfo_children():
        assert block_top <= button.winfo_rooty()
        assert button.winfo_rooty() + button.winfo_height() <= block_bottom


def _entries_in(widget: tk.Misc) -> list[tk.Entry]:
    """Return every text entry inside a widget, at any depth."""
    found: list[tk.Entry] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Entry):
            found.append(child)
        found.extend(_entries_in(child))
    return found


def test_the_wheel_scrolls_the_options_over_the_controls_themselves(app: GraphPadApp) -> None:
    """The wheel must work where the pointer actually is, not just over the gaps.

    The Plot style tab is the tallest of the four, so it is the one that has to be
    scrolled. A Tk binding fires on the widget it was made on and nowhere below it, so the
    wheel has to be bound to every control as well as to the canvas behind them: bound to
    the canvas alone it worked over the gaps in the panel and did nothing at all over the
    fields and checkboxes, which is where the pointer spends its time.
    """
    _show_style_tab(app)
    canvas = app._body_canvas
    before = canvas.yview()[0]
    # A field on the tab, not the canvas behind it: this is the case that was broken.
    entry = _entries_in(_tab_frame(app, 2))[0]
    entry.event_generate('<MouseWheel>', delta=-120)
    app.root.update()
    assert canvas.yview()[0] > before


def test_the_tallest_tab_really_is_taller_than_the_panel(app: GraphPadApp) -> None:
    """The scroll above is only worth anything if there is something to scroll to.

    Found while fixing the wheel: the Plot style tab had grown past the space left for the
    options, and the wheel did not work, so the bottom of the tab was simply unreachable.
    """
    _show_style_tab(app)
    app.root.update()
    content = int(app._body_canvas.cget('scrollregion').split()[3])
    assert content > app._body_canvas.winfo_height()


def test_the_notebook_does_not_reserve_the_tallest_tab_for_all_of_them(app: GraphPadApp) -> None:
    """Each tab should be as tall as itself, so a short one does not scroll into blank space.

    The notebook is given the height of its tallest tab whatever is selected, so the short
    tabs carry dead space below their last field and the scrollbar over them leads nowhere.
    This is what the scrollregion is measured against, so it is what decides whether a tab
    appears to need scrolling at all.
    """
    heights = {}
    for index in range(app.tabs.index('end')):
        app.tabs.select(app.tabs.tabs()[index])
        app.root.update()
        frame = _tab_frame(app, index)
        frame.update_idletasks()
        heights[app.tabs.tab(index, 'text')] = frame.winfo_reqheight()
    # The Data preview tab is a single field and must not be as tall as the Plot style tab.
    assert heights['Data preview'] < heights['Plot style']


def test_tab_content_is_a_child_of_the_scrollable_body(app: GraphPadApp) -> None:
    """Canvas clipping must contain the tab content instead of letting it cover fixed controls."""
    for index in range(app.tabs.index('end')):
        assert _tab_frame(app, index).master is app._body_inner


def test_switching_tabs_returns_options_to_the_top(app: GraphPadApp) -> None:
    """A new tab starts at its first option instead of inheriting a stale scroll offset."""
    _show_style_tab(app)
    app._body_canvas.yview_moveto(1)
    app.root.update()
    assert app._body_canvas.yview()[0] > 0

    app.tabs.select(1)
    app.root.update()

    assert app._body_canvas.yview()[0] == 0


def test_scrolling_up_does_not_leave_blank_space_above_options(app: GraphPadApp) -> None:
    """Scrolling back to the top aligns the options with the top of the scrollable body."""
    _show_style_tab(app)
    canvas = app._body_canvas
    canvas.yview_moveto(1)
    app.root.update()
    style = _tab_frame(app, 2)
    for _ in range(40):
        style.event_generate('<MouseWheel>', delta=120)
    app.root.update()

    assert canvas.yview()[0] == 0
    assert style.winfo_rooty() == canvas.winfo_rooty()


def test_general_options_stay_at_the_top_after_scrolling_up(app: GraphPadApp) -> None:
    """Returning to the top of General must place the first setting below the tab header."""
    _show_style_tab(app)
    app._body_canvas.yview_moveto(1)
    app.root.update()
    app.tabs.select(0)
    app.root.update()

    general = _tab_frame(app, 0)
    first_option = next(child for child in general.winfo_children() if child.winfo_manager())
    for _ in range(20):
        general.event_generate('<MouseWheel>', delta=120)
    app.root.update()

    assert app._body_canvas.yview()[0] == 0
    assert general.winfo_rooty() == app._body_canvas.winfo_rooty()
    assert first_option.winfo_rooty() == general.winfo_rooty() + 6


def test_data_preview_ignores_wheel_when_content_fits(app: GraphPadApp) -> None:
    """Upward wheel input on a short tab must not shift its options down in the viewport."""
    app.tabs.select(3)
    app.root.update()
    preview = _tab_frame(app, 3)
    first_option = next(child for child in preview.winfo_children() if child.winfo_manager())
    assert app._body_canvas.bbox('all')[3] <= app._body_canvas.winfo_height()

    for _ in range(8):
        preview.event_generate('<MouseWheel>', delta=120)
    app.root.update()

    assert app._body_canvas.yview()[0] == 0
    assert preview.winfo_rooty() == app._body_canvas.winfo_rooty()
    assert first_option.winfo_rooty() == preview.winfo_rooty() + 6


def test_the_swatch_shows_the_selected_colour(app: GraphPadApp) -> None:
    app._select_row(0)
    assert str(app.swatch.cget('background')).lower() == app.state.color_of('Control').lower()


def test_the_axis_fields_are_on_the_axis_tab(app: GraphPadApp) -> None:
    assert app.tabs.index('current') == 0
    assert app.y_max_var.get() != ''


def test_the_sample_list_does_not_cover_the_controls_below(app: GraphPadApp) -> None:
    """The sticky list must fit its own block, or it hides the colour row underneath.

    Found by looking at a screenshot: every layout assertion passed while the list was
    painted straight over the controls below it.
    """
    list_bottom = app.listbox.winfo_rooty() + app.listbox.winfo_height()
    assert list_bottom <= app.hex_entry.winfo_rooty()


def test_the_sample_list_keeps_its_size(app: GraphPadApp) -> None:
    before = app.listbox.winfo_height()
    for _ in range(5):
        app.root.event_generate('<MouseWheel>', delta=-120)
    app.root.update()
    assert app.listbox.winfo_height() == before


def test_the_sample_list_stays_put_when_the_options_scroll(app: GraphPadApp) -> None:
    """The list is what grouping acts on, so it must not scroll out of reach."""
    top = app.listbox.winfo_rooty()
    for _ in range(10):
        app.root.event_generate('<MouseWheel>', delta=-120)
    app.root.update()
    assert app.listbox.winfo_rooty() == top
    assert app.listbox.winfo_ismapped()


def test_the_scrollable_body_stays_below_the_sample_list(app: GraphPadApp) -> None:
    """Scrolling the tab must not move its viewport over the fixed sample list."""
    _show_style_tab(app)
    list_top = app.listbox.winfo_rooty()
    body_top = app._body_canvas.winfo_rooty()
    assert body_top >= list_top + app.listbox.winfo_height()

    app._body_canvas.yview_moveto(1)
    app.root.update()

    assert app.listbox.winfo_rooty() == list_top
    assert app._body_canvas.winfo_rooty() == body_top


def test_the_axis_fields_show_the_automatic_values(app: GraphPadApp) -> None:
    app._sync_from_state()
    assert app.y_max_var.get() == f'{app.state.automatic_y_max():g}'
    assert app.x_tick_font_var.get() == '11'
    assert app.y_tick_font_var.get() == '11'
    assert app.legend_font_var.get() == '8'


def test_the_tick_step_field_shows_what_matplotlib_picks(app: GraphPadApp) -> None:
    app._sync_from_state()
    assert app.y_step_var.get() == f'{app._automatic_step():g}'


def test_the_automatic_y_max_is_not_stored_as_a_choice(app: GraphPadApp) -> None:
    """Leaving the automatic number in the field must not freeze the axis at it."""
    app._sync_from_state()
    app._update_axis()
    assert app.state.config.y_max is None
    assert app.state.config.y_major_step is None


def test_the_default_font_size_is_not_stored_as_a_choice(app: GraphPadApp) -> None:
    app.x_tick_font_var.set('11')
    app.y_tick_font_var.set('11')
    app.legend_font_var.set('8')
    app._update_fonts()
    assert app.state.config.x_font_size is None
    assert app.state.config.y_font_size is None
    assert app.state.config.legend_size is None


def test_a_changed_axis_value_is_stored(app: GraphPadApp) -> None:
    app.y_max_var.set('500')
    app._update_axis()
    assert app.state.config.y_max == 500.0
    assert app.canvas.figure.axes[0].get_ylim()[1] == 500.0


def test_typing_the_automatic_value_again_returns_to_automatic(app: GraphPadApp) -> None:
    app.y_max_var.set('500')
    app._update_axis()
    app.y_max_var.set(f'{app.state.automatic_y_max():g}')
    app._update_axis()
    assert app.state.config.y_max is None


def test_a_changed_font_size_is_stored(app: GraphPadApp) -> None:
    app.x_tick_font_var.set('15')
    app._update_fonts()
    assert app.state.config.x_font_size == 15


def test_the_two_axes_can_be_sized_apart(app: GraphPadApp) -> None:
    """A row of sample names and a column of numbers are not the same kind of text.

    Each axis keeps its own size, and an axis left on the default stores nothing so it goes
    on following whatever the other one, or the shared setting, asks for.
    """
    app.x_tick_font_var.set('7')
    app.y_tick_font_var.set('15')
    app._update_fonts()
    # A bar graph writes no x ticks of its own, so the x size shows up on the sample names
    # along the bottom rather than on a tick label. The legend carries the same names, so it
    # is set aside rather than being read as one of those labels.
    ax = app.canvas.figure.axes[0]
    legend = ax.get_legend()
    in_legend = {id(text) for text in legend.get_texts()} if legend is not None else set()
    drawn = {
        text.get_fontsize()
        for text in app.canvas.figure.findobj(Text)
        if text.get_text() in app.state.visible_order and id(text) not in in_legend
    }
    assert drawn == {7.0}
    assert ax.get_yticklabels()[0].get_fontsize() == 15.0
    app.x_tick_font_var.set('11')
    app._update_fonts()
    assert app.state.config.x_font_size is None
    assert ax.yaxis.get_ticklabels()[0].get_fontsize() == 15.0


def test_the_automatic_top_follows_the_data(app: GraphPadApp) -> None:
    """A different workbook must move the automatic value, not leave the old one behind."""
    automatic = app.state.automatic_y_max()
    app.state.config.y_max = None
    app._sync_from_state()
    assert app.y_max_var.get() == f'{automatic:g}'


def test_group_checkboxes_skip_groups_of_one(app: GraphPadApp) -> None:
    """A group of one is not a grouping, so it is not worth listing."""
    assert set(app.group_vars) == {'A'}


def test_a_group_becomes_listed_once_it_holds_several(app: GraphPadApp) -> None:
    """Moving a second sample onto a lone group turns it into a group worth listing."""
    app.state.set_group('42C', 'C')
    app._refresh_groups()
    assert set(app.group_vars) == {'C'}


def test_a_group_disappears_when_it_drops_to_one(app: GraphPadApp) -> None:
    app.state.set_group('42C', 'Solo')
    app._refresh_groups()
    assert set(app.group_vars) == set()


def test_merging_two_groups_from_the_window(grouped_app: GraphPadApp) -> None:
    grouped_app.group_vars['A'].set(True)
    grouped_app.group_vars['B'].set(True)
    grouped_app.merge_name_var.set('A+B')
    grouped_app._merge_groups()
    assert grouped_app.state.group_of('42C') == 'A+B'
    # 'Solo' keeps its own group of one, so it stays in the state but is not listed.
    assert grouped_app.state.groups() == ('A+B', 'C')
    assert set(grouped_app.group_vars) == {'A+B'}


def test_merging_asks_for_a_name_when_the_field_is_blank(grouped_app: GraphPadApp) -> None:
    grouped_app.group_vars['A'].set(True)
    grouped_app.group_vars['B'].set(True)
    grouped_app._merge_groups()
    assert grouped_app.state.groups() == ('A', 'B', 'C')


def test_merging_needs_two_groups(grouped_app: GraphPadApp) -> None:
    grouped_app.group_vars['A'].set(True)
    grouped_app.merge_name_var.set('A+B')
    grouped_app._merge_groups()
    assert grouped_app.state.groups() == ('A', 'B', 'C')


def test_splitting_gives_each_sample_its_own_group(app: GraphPadApp) -> None:
    app.group_vars['A'].set(True)
    app._split_group()
    assert app.state.group_of('Control') == 'Control'
    assert app.state.group_of('42C') == '42C'
    assert app.state.groups() == ('Control', '42C', 'C')


def test_splitting_without_a_tick_changes_nothing(app: GraphPadApp) -> None:
    app._split_group()
    assert app.state.groups() == ('A', 'C')


def test_ticks_survive_a_redraw(app: GraphPadApp) -> None:
    app.group_vars['A'].set(True)
    app.redraw()
    assert app.group_vars['A'].get()


def test_merging_redraws_the_graph(grouped_app: GraphPadApp) -> None:
    grouped_app.group_vars['A'].set(True)
    grouped_app.group_vars['B'].set(True)
    grouped_app.merge_name_var.set('A+B')
    grouped_app._merge_groups()
    assert [text.get_text() for text in grouped_app.canvas.figure.axes[0].texts] == ['A+B']


def test_y_max_field_sets_the_axis_top(app: GraphPadApp) -> None:
    app.y_max_var.set('250')
    app._update_axis()
    assert app.state.config.y_max == 250.0
    assert app.canvas.figure.axes[0].get_ylim()[1] == 250.0


def test_a_blank_y_max_returns_to_automatic(app: GraphPadApp) -> None:
    app.y_max_var.set('250')
    app._update_axis()
    app.y_max_var.set('')
    app._update_axis()
    assert app.state.config.y_max is None


def test_a_half_typed_y_max_does_not_raise(app: GraphPadApp) -> None:
    app.y_max_var.set('2.')
    app._update_axis()
    assert app.state.config.y_max == 2.0


def test_y_step_field_sets_the_tick_spacing(app: GraphPadApp) -> None:
    app.y_max_var.set('100')
    app.y_step_var.set('25')
    app._update_axis()
    assert app.state.config.y_major_step == 25.0
    ticks = [tick for tick in app.canvas.figure.axes[0].get_yticks() if 0 <= tick <= 100]
    assert ticks == pytest.approx([0.0, 25.0, 50.0, 75.0, 100.0])


def test_tick_and_legend_font_sizes_are_applied(app: GraphPadApp) -> None:
    app.y_tick_font_var.set('15')
    app.legend_font_var.set('11')
    app._update_fonts()
    ax = app.canvas.figure.axes[0]
    assert ax.yaxis.get_ticklabels()[0].get_fontsize() == 15.0
    legend = ax.get_legend()
    assert legend is not None
    assert legend.get_texts()[0].get_fontsize() == 11.0


def test_an_unusable_font_size_is_ignored(app: GraphPadApp) -> None:
    app.y_tick_font_var.set('9999')
    app._update_fonts()
    assert app.state.config.y_font_size is None


def test_the_new_fields_are_filled_from_the_state(app: GraphPadApp) -> None:
    app.state.config.y_max = 400.0
    app.state.config.y_major_step = 50.0
    app.state.config.x_font_size = 13
    app.state.config.legend_size = 9
    app._sync_from_state()
    assert app.y_max_var.get() == '400'
    assert app.y_step_var.get() == '50'
    assert app.x_tick_font_var.get() == '13'
    assert app.y_tick_font_var.get() == '11'
    assert app.legend_font_var.get() == '9'


def test_reset_clears_the_new_fields(app: GraphPadApp) -> None:
    app._select_row(0)
    app.state.set_edge_color('Control', '#00ff00')
    app.state.set_hatch('Control', '//')
    app.state.set_group('B', 'A')
    app.y_max_var.set('250')
    app._update_axis()

    app._reset()

    assert app.state.edge_of('Control') == '#000000'
    assert app.state.hatch_of('Control') == ''
    assert app.state.group_of('B') == 'C'
    assert app.state.config.y_max is None
    assert set(app.group_vars) == {'A'}


def test_saving_still_works_after_a_merge(grouped_app: GraphPadApp, tmp_path: Path) -> None:
    grouped_app.group_vars['A'].set(True)
    grouped_app.group_vars['B'].set(True)
    grouped_app.merge_name_var.set('A+B')
    grouped_app._merge_groups()
    target = tmp_path / 'merged.png'
    grouped_app.canvas.figure.savefig(target)
    assert target.exists() and target.stat().st_size > 0


def test_bars_are_tagged_with_their_sample_names(app: GraphPadApp) -> None:
    mapping = getattr(app.canvas.figure, 'sample_by_bar', {})
    bars = app.canvas.figure.axes[0].containers[0]
    assert [mapping[id(bar)] for bar in bars] == list(app.state.visible_order)


def test_every_clickable_artist_maps_to_a_real_sample(app: GraphPadApp) -> None:
    """The replicate points are tagged too, so the mapping holds bars and points alike."""
    mapping = getattr(app.canvas.figure, 'sample_by_bar', {})
    assert set(mapping.values()) == set(app.state.visible_order)


def test_empty_hex_field_does_not_raise_an_error(app: GraphPadApp) -> None:
    """Clicking into the field and back out must not pop a dialog."""
    app._select_row(0)
    before = _palette_color(app, 0)
    app.hex_var.set('')
    app._apply_hex()
    assert app.state.color_of('Control') == before
    assert app.hex_var.get() == before


def test_hex_field_accepts_every_valid_form(app: GraphPadApp) -> None:
    for typed, expected in (('#0f0', '#00ff00'), ('00AA33', '#00aa33'), ('#ABCDEF', '#abcdef')):
        app._select_row(0)
        app.hex_var.set(typed)
        app._apply_hex()
        assert app.state.color_of('Control') == expected


def test_pick_color_never_passes_a_bad_colour_to_the_chooser(app: GraphPadApp) -> None:
    """The chooser calls winfo_rgb on the colour it is given, so it must be parseable."""
    seen: list[str] = []

    def fake_askcolor(**kwargs: object) -> tuple[tuple[int, ...], str]:
        seen.append(str(kwargs.get('color')))
        return (0, 0, 0), '#000000'


    style_tab.colorchooser.askcolor = fake_askcolor  # type: ignore[assignment]
    app.state.config.colors['Control'] = 'garbage'
    app._select_row(0)
    app._pick_color()
    assert seen and seen[0].startswith('#')
    assert len(seen[0]) == 7


def _settle(app: GraphPadApp, width: int, height: int) -> None:
    """Resize the window off screen and let Tk finish the layout, so measurements are real."""
    app.root.geometry(f'{width}x{height}-4000-3000')
    app.root.update()
    app.root.update_idletasks()


def test_there_is_no_navigation_toolbar_under_the_graph(app: GraphPadApp) -> None:
    """The matplotlib home, pan, zoom and save row is not wanted under the graph."""
    assert app.canvas.toolbar is None


def test_no_toolbar_widget_is_packed_anywhere(app: GraphPadApp) -> None:
    """A toolbar rebuilt by another route would come back unnoticed, so check the widgets."""
    from matplotlib.backends._backend_tk import NavigationToolbar2Tk

    def toolbars(widget: tk.Misc) -> list[tk.Misc]:
        found = [child for child in widget.winfo_children() if isinstance(child, NavigationToolbar2Tk)]
        for child in widget.winfo_children():
            if child.winfo_manager():
                found.extend(toolbars(child))
        return found

    assert not toolbars(app.root)


def test_graph_never_grows_past_its_natural_size(app: GraphPadApp) -> None:
    """The graph can shrink to fit, but never grows beyond its natural dimensions."""
    for width, height in ((1000, 700), (1200, 800), (900, 640)):
        _settle(app, width, height)
        app.redraw()
        size = app.canvas.figure.get_size_inches()
        assert all(0 < float(value) <= 6.4 + 0.01 for value in size)


def test_graph_never_exceeds_the_canvas(app: GraphPadApp) -> None:
    """A small window must not leave bars drawn outside the visible area."""
    _settle(app, 900, 640)
    widget = app.canvas.get_tk_widget()
    app.redraw()
    dpi = app.canvas.figure.dpi
    width_in, height_in = (float(value) for value in app.canvas.figure.get_size_inches())
    assert width_in * dpi <= widget.winfo_width() + 1
    assert height_in * dpi <= widget.winfo_height() + 1


def test_enlarging_the_window_does_not_grow_the_graph(app: GraphPadApp) -> None:
    """Resizing the preview does not change the natural size used to render and export."""
    _settle(app, 1100, 720)
    app.redraw()
    before = app._natural_figure_size
    _settle(app, 1700, 950)
    app.redraw()
    assert app._natural_figure_size == pytest.approx(before)
    display_size = tuple(float(value) for value in app.canvas.figure.get_size_inches())
    assert display_size[0] <= before[0]
    assert display_size[1] <= before[1]


def test_resizing_keeps_the_graph_ratio_and_restores_natural_size(app: GraphPadApp) -> None:
    """The fixed canvas keeps its aspect ratio as the window allows it to grow or shrink."""
    _settle(app, 700, 600)
    small_size = tuple(float(value) for value in app.canvas.figure.get_size_inches())
    natural_width, natural_height = app._natural_figure_size
    assert small_size[0] / small_size[1] == pytest.approx(natural_width / natural_height, abs=0.01)

    _settle(app, 1100, 720)
    larger_size = tuple(float(value) for value in app.canvas.figure.get_size_inches())
    assert larger_size[0] / larger_size[1] == pytest.approx(natural_width / natural_height, abs=0.01)
    assert larger_size[0] >= small_size[0]
    assert larger_size[1] >= small_size[1]
    assert larger_size[0] <= natural_width
    assert larger_size[1] <= natural_height


def test_action_buttons_are_visible_at_the_default_size(app: GraphPadApp) -> None:
    """Reset, Save PNG and Save PDF were squeezed to a few pixels when the window was short."""
    _settle(app, 1100, 720)
    _show_style_tab(app)
    labels = {'Reset', 'Save PNG…', 'Save PDF…'}
    found = {
        str(child.cget('text')): child
        for child in app.panel.winfo_children()
        if child.winfo_class() == 'TButton' and str(child.cget('text')) in labels
    }
    assert set(found) == labels
    before = {label: button.winfo_rooty() for label, button in found.items()}
    for label, button in found.items():
        assert button.winfo_height() >= 20, f'{label} is squashed to {button.winfo_height()}px'
    app._body_canvas.yview_moveto(1)
    app.root.update()
    panel_bottom = app.panel.winfo_rooty() + app.panel.winfo_height()
    for label, button in found.items():
        assert button.winfo_rooty() == before[label]
        assert button.winfo_rooty() + button.winfo_height() <= panel_bottom


def test_action_buttons_survive_a_short_window(app: GraphPadApp) -> None:
    minimum = app.root.minsize()
    _settle(app, minimum[0], minimum[1])
    for child in app.panel.winfo_children():
        if child.winfo_class() == 'TButton' and str(child.cget('text')) in {'Reset', 'Save PNG…', 'Save PDF…'}:
            assert child.winfo_height() >= 20, f'{child.cget("text")} is squashed to {child.winfo_height()}px'


def test_window_has_a_usable_minsize(app: GraphPadApp) -> None:
    minimum = app.root.minsize()
    assert minimum[0] >= 700
    assert minimum[1] >= 500


def test_reordering_moves_only_the_chosen_sample(app: GraphPadApp) -> None:
    """The arrow buttons reorder one sample, leaving the others where they were."""
    before = column_values(app, 'sample')
    app._select_row(0)
    app._move_selected(1)
    after = column_values(app, 'sample')
    assert after == [before[1], before[0], before[2]]
    assert sorted(after) == sorted(before)


def test_controls_update_the_state(app: GraphPadApp) -> None:
    app.log_var.set('Log')
    app._update_log()
    app.error_var.set('SEM')
    app._update_error()
    app.color_by_var.set('Group')
    app._update_color_by()
    app.points_var.set(False)
    app._update_points()
    app._update_jitter('0.4')

    assert app.state.config.log_axis is True
    assert app.state.config.error_kind == 'sem'
    assert app.state.config.color_by == 'group'
    assert app.state.config.show_points is False
    assert app.state.config.jitter == pytest.approx(0.4)


def _drawn_bar_color(app: GraphPadApp, index: int) -> str:
    """Return the fill the canvas is actually showing for one bar, as a hex string."""
    app.canvas.figure.canvas.draw()
    patches = app.canvas.figure.axes[0].containers[0].patches
    return to_hex(patches[index].get_facecolor())


def test_the_point_type_reaches_the_graph(app: GraphPadApp) -> None:
    """With no sample highlighted a shape applies to the whole graph."""
    app._apply_indices(())
    app.root.update()
    app.point_type_var.set('Diamond')
    app._update_point_type()
    assert app.state.config.point_type == 'diamond'
    markers = {line.get_marker() for line in app.canvas.figure.axes[0].get_lines()}
    assert 'D' in markers


def test_a_point_type_belongs_to_the_highlighted_series(blank_app: GraphPadApp) -> None:
    """A shape chosen with a series highlighted is that series' own, not the graph's."""
    _scatter(blank_app)
    names = list(blank_app.state.entry_order)
    blank_app._select_row(0)
    blank_app.point_type_var.set('Square')
    blank_app._update_point_type()
    assert blank_app.state.config.point_type == 'round'
    assert blank_app.state.point_type_of(names[0]) == 'square'
    assert blank_app.state.point_type_of(names[1]) == 'round'


def test_two_series_can_be_given_different_shapes(blank_app: GraphPadApp) -> None:
    """Each highlighted series takes the shape in turn and keeps it."""
    _scatter(blank_app)
    names = list(blank_app.state.entry_order)
    blank_app._select_row(0)
    blank_app.point_type_var.set('Square')
    blank_app._update_point_type()
    blank_app._select_row(1)
    blank_app.point_type_var.set('Star')
    blank_app._update_point_type()
    assert blank_app.state.point_type_of(names[0]) == 'square'
    assert blank_app.state.point_type_of(names[1]) == 'star'
    markers = [line.get_marker() for line in blank_app.canvas.figure.axes[0].get_lines()]
    assert markers[:2] == ['s', '*']


def test_the_point_type_field_shows_the_highlighted_series_shape(blank_app: GraphPadApp) -> None:
    """Moving the highlight moves the shape shown, so the field never reports a stale one."""
    _scatter(blank_app)
    names = list(blank_app.state.entry_order)
    blank_app.state.set_point_type(names[0], 'triangle')
    blank_app._select_row(0)
    assert blank_app.point_type_var.get() == 'Triangle'
    blank_app._select_row(1)
    assert blank_app.point_type_var.get() == 'Round'


def test_setting_the_graph_shape_releases_the_series_that_had_one(blank_app: GraphPadApp) -> None:
    """Choosing a shape with nothing highlighted takes the graph back to one shape."""
    _scatter(blank_app)
    blank_app._select_row(0)
    blank_app.point_type_var.set('Square')
    blank_app._update_point_type()
    blank_app._apply_indices(())
    blank_app.root.update()
    blank_app.point_type_var.set('Triangle')
    blank_app._update_point_type()
    assert blank_app.state.config.point_type == 'triangle'
    assert blank_app.state.config.point_types == {}


def test_clearing_the_style_releases_the_highlighted_shape(blank_app: GraphPadApp) -> None:
    """Clearing a series' style returns its points to the shape the graph is drawn with."""
    _scatter(blank_app)
    names = list(blank_app.state.entry_order)
    blank_app._select_row(0)
    blank_app.point_type_var.set('Square')
    blank_app._update_point_type()
    blank_app._clear_style()
    assert blank_app.state.point_type_of(names[0]) == 'round'


def test_an_unknown_point_type_falls_back_to_the_default(app: GraphPadApp) -> None:
    """A caption the window does not know is not stored, which nothing could undo."""
    app._apply_indices(())
    app.root.update()
    app.point_type_var.set('Somewhere else entirely')
    app._update_point_type()
    assert app.state.config.point_type == 'round'


def test_the_point_type_survives_a_sync(app: GraphPadApp) -> None:
    """With nothing highlighted the field shows the shape the whole graph is drawn with."""
    app._apply_indices(())
    app.state.config.point_type = 'triangle'
    app._sync_from_state()
    assert app.point_type_var.get() == 'Triangle'


def test_a_reset_puts_the_point_type_back(app: GraphPadApp) -> None:
    """A reset is meant to undo the shape too, not only the colours."""
    app._apply_indices(())
    app.root.update()
    app.point_type_var.set('Star')
    app._update_point_type()
    app._reset()
    assert app.state.config.point_type == 'round'
    assert app.point_type_var.get() == 'Round'


def test_a_reset_puts_a_series_shape_back(app: GraphPadApp) -> None:
    """A reset undoes a shape given to one series as well as the graph's own."""
    app._select_row(0)
    app.point_type_var.set('Star')
    app._update_point_type()
    assert app.state.config.point_types
    app._reset()
    assert app.state.config.point_types == {}
    assert app.state.config.point_type == 'round'


def test_every_point_shape_is_offered(app: GraphPadApp) -> None:
    """The dropdown lists every shape the settings know how to draw."""
    assert app.point_type_combo.cget('values') == (
        'Round', 'Square', 'Cross', 'Triangle', 'Diamond', 'Star',
    )


def test_the_point_type_lives_on_the_plot_style_tab(blank_app: GraphPadApp) -> None:
    """A point's shape is set on the style tab, beside the other per series choices.

    It sits with the Connect and Name boxes rather than in the drawing above, because all
    three belong to whichever series is highlighted. The block only appears once one is,
    which is why a row is chosen before the captions are read.
    """
    assert 'Point type' not in _captions_in(_tab_frame(blank_app, 0))
    _scatter(blank_app)
    blank_app._select_row(0)
    assert 'Point type' in _captions_in(_tab_frame(blank_app, 2))
    assert 'Point type' in _captions_in(blank_app.series_style_frame)


def test_the_swatch_shows_the_colour_the_bar_is_drawn_in(app: GraphPadApp) -> None:
    """Switching to group colours has to update the hex field and the swatch too.

    They are what tells the reader what the bar looks like, so leaving the previous mode's
    colour on screen is what made the colour controls look as though nothing had happened.
    """
    app._select_row(1)
    assert app.hex_var.get() == _drawn_bar_color(app, 1)

    app.color_by_var.set('Group')
    app._update_color_by()
    drawn = _drawn_bar_color(app, 1)

    assert app.hex_var.get() == drawn
    assert to_hex(app.swatch.cget('background')) == drawn


def test_every_bar_colour_is_reported_by_the_list(app: GraphPadApp) -> None:
    """No bar may be drawn in a colour the panel is not showing for it."""
    for mode in ('Sample', 'Group'):
        app.color_by_var.set(mode)
        app._update_color_by()
        drawn = [_drawn_bar_color(app, index) for index in range(len(app.state.entry_order))]
        listed = [app.state.color_of(name) for name in app.state.entry_order]
        assert listed == drawn, f'{mode} mode disagreed with the canvas'


def test_samples_in_one_group_show_one_colour(app: GraphPadApp) -> None:
    """Colour by group is the whole point of the option, so it has to be visible."""
    app.color_by_var.set('Group')
    app._update_color_by()
    by_group: dict[str, set[str]] = {}
    for name in app.state.entry_order:
        by_group.setdefault(app.state.group_of(name), set()).add(app.state.color_of(name))
    assert all(len(colors) == 1 for colors in by_group.values())


def test_a_bar_coloured_by_hand_still_shows_its_own_colour(app: GraphPadApp) -> None:
    """Group colouring assigns palette colours; a chosen one still wins."""
    app.color_by_var.set('Group')
    app._update_color_by()
    app._select_row(1)
    app.hex_var.set('#ff00ff')
    app._apply_hex()
    assert _drawn_bar_color(app, 1) == '#ff00ff'
    assert app.hex_var.get() == '#ff00ff'


def test_title_is_trimmed_and_blank_becomes_none(app: GraphPadApp) -> None:
    app.title_var.set('  Report  ')
    app._update_title()
    assert app.state.config.title == 'Report'
    app.title_var.set('   ')
    app._update_title()
    assert app.state.config.title is None


def test_reset_button_restores_everything(app: GraphPadApp) -> None:
    app._update_jitter('0.5')
    app.points_var.set(False)
    app._update_points()
    app._reset()
    assert app.state.config.jitter == 0.0
    assert app.state.config.show_points is True
    assert app.jitter_var.get() == pytest.approx(0.0)


def test_reset_button_also_restores_the_sheet_order(app: GraphPadApp) -> None:
    app._move_selected(1)
    app._reset()
    assert app.state.visible_order == ('Control', '42C', 'B')


def test_save_writes_the_current_figure(app: GraphPadApp, tmp_path: Path) -> None:
    target = tmp_path / 'saved.png'
    app.canvas.figure.savefig(target)
    assert target.exists() and target.stat().st_size > 0


def test_entry_points_run_as_scripts() -> None:
    """``python src/app.py`` must work, not only ``python -m src.app``.

    Running a file inside the package puts src/ on sys.path instead of the project root,
    so the package would not be importable without the bootstrap in those files.
    """
    root = Path(__file__).resolve().parents[1]
    for script in ('src/app.py', 'src/__main__.py'):
        result = subprocess.run(
            [sys.executable, str(root / script), '--help'],
            capture_output=True,
            text=True,
            cwd=root,
            check=False,
        )
        assert result.returncode == 0, f'{script} failed: {result.stderr}'
        assert 'usage' in result.stdout.lower()


def test_input_argument_is_optional() -> None:
    """The window must be openable without passing a file."""
    from src.app import build_parser

    assert build_parser().parse_args([]).input is None
    assert build_parser().parse_args(['--input', 'a.xlsx']).input == Path('a.xlsx')


@pytest.fixture
def blank_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[GraphPadApp]:
    """Build a window with no file loaded, as when run without ``--input``."""
    from src.app import GraphPadApp

    _stub_dialogs(monkeypatch)
    try:
        window = GraphPadApp()
    except Exception as error:  # pragma: no cover - only on a machine with no display
        pytest.skip(f'No usable display: {error}')
    _hide(window)
    try:
        yield window
    finally:
        window.root.destroy()


def test_window_opens_without_a_file(blank_app: GraphPadApp) -> None:
    assert row_count(blank_app) == 0
    assert blank_app.canvas.figure.axes == []
    assert blank_app.input_path is None
    assert 'Open' in blank_app.file_var.get()


def test_load_file_shows_the_sheet(blank_app: GraphPadApp) -> None:
    assert blank_app.load_file(INPUT_FILE)
    assert row_count(blank_app) == 8
    assert blank_app.input_path == INPUT_FILE
    assert blank_app.file_var.get() == INPUT_FILE.name
    assert len(blank_app.canvas.figure.axes) == 1
    assert blank_app.dirty is False


@pytest.mark.parametrize(
    'broken',
    [Path('AGENTS.md'), Path('input/does_not_exist.xlsx')],
    ids=['not-a-workbook', 'missing'],
)
def test_failed_load_keeps_the_current_graph(blank_app: GraphPadApp, broken: Path) -> None:
    """A broken file must be reported without discarding what is already on screen."""
    assert blank_app.load_file(INPUT_FILE)
    assert not blank_app.load_file(broken)
    assert row_count(blank_app) == 8
    assert blank_app.input_path == INPUT_FILE


def test_loading_marks_the_graph_clean(blank_app: GraphPadApp) -> None:
    """Populating the widgets during a load must not look like a user edit."""
    assert blank_app.load_file(INPUT_FILE)
    assert blank_app.dirty is False


def test_editing_marks_the_graph_dirty(blank_app: GraphPadApp) -> None:
    blank_app.load_file(INPUT_FILE)
    blank_app._update_jitter('0.4')
    assert blank_app.dirty is True
    blank_app._reset()
    assert blank_app.dirty is False


def test_loading_again_discards_the_dirty_flag(blank_app: GraphPadApp) -> None:
    blank_app.load_file(INPUT_FILE)
    blank_app._update_jitter('0.4')
    assert blank_app.load_file(INPUT_FILE)
    assert blank_app.dirty is False


def _record_dialogs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Collect the titles of the message boxes the window raises, without showing any."""
    titles: list[str] = []
    for name in ('showerror', 'showwarning', 'showinfo'):
        monkeypatch.setattr(data_pane.messagebox, name, lambda *a, **_k: titles.append(str(a[0])))
    return titles


def test_a_scatter_sheet_is_drawn_without_being_asked_about(
    blank_app: GraphPadApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The common tidy shape works itself out, so no dialog may interrupt the switch."""
    titles = _record_dialogs(monkeypatch)
    assert blank_app.load_file(SCATTER_FILE)
    titles.clear()
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    assert titles == []
    assert len(blank_app.state.dataset.series) == 8
    assert len(blank_app.canvas.figure.axes) == 1


def test_a_scatter_sheet_names_its_series_from_the_conditions_row(blank_app: GraphPadApp) -> None:
    """Five columns headed Standard have to be told apart, or the legend repeats itself."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    names = [one.name for one in blank_app.state.dataset.series]
    assert names[:4] == ['Control', '42C', 'Low Mg', 'Low pDNA']
    assert blank_app.series_var.get() == '2'


def test_a_sheet_with_no_x_values_says_so(
    blank_app: GraphPadApp,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty graph with no explanation reads as a broken program, not as an empty sheet."""
    titles = _record_dialogs(monkeypatch)
    nameless = tmp_path / 'nameless.xlsx'
    pd.DataFrame([['alpha', 'beta'], ['gamma', 'delta']]).to_excel(nameless, index=False, header=False)
    assert blank_app.load_file(nameless)
    titles.clear()
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    assert titles == ['No x values detected']
    assert blank_app.x_var.get() == ''


def test_the_caption_points_at_the_controls_when_no_x_is_chosen(blank_app: GraphPadApp) -> None:
    """The caption is the always visible half of the answer, so it has to name the way out."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    blank_app.sheet.set_selection((), None)
    blank_app._describe_scatter_selection()
    caption = str(blank_app.sheet_caption.cget('text'))
    assert 'tick the columns' in caption
    assert 'x values' in caption


def test_the_x_values_can_be_named_by_hand(blank_app: GraphPadApp) -> None:
    """The fields are the way out of a sheet nothing could be read out of.

    Two y columns and no series row is a reading the detection would not have chosen, so
    it also shows the fields overriding what was worked out for them.
    """
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    assert len(blank_app.state.dataset.series) == 8
    blank_app.x_direction_var.set('Column')
    blank_app.x_var.set('1')
    # The columns to plot are chosen in the preview rather than typed on the panel, and
    # the grid numbers its columns the way the sheet does, from one.
    blank_app.sheet.set_selection((2, 3), None)
    blank_app.series_var.set('')
    blank_app._update_xy()
    blank_app.root.update()
    assert len(blank_app.state.dataset.series) == 2
    assert blank_app.state.config.x_column == 0


def test_the_x_values_can_be_read_across_a_row(blank_app: GraphPadApp, tmp_path: Path) -> None:
    """A GraphPad XY table keeps its x values across the top, and the other shape is offered.

    The reader has always supported this, but the window only ever asked for a row, so the
    layout was unreachable from the interface however the file was written.
    """
    path = tmp_path / 'xy_row_case.xlsx'
    pd.DataFrame(
        [['X values', 1.0, 2.0, 4.0], ['Group', 10.0, 20.0, 40.0], ['Group', 12.0, 22.0, 42.0]]
    ).to_excel(path, index=False, header=False)
    assert blank_app.load_file(path)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    assert blank_app.x_direction_var.get() == 'Row'
    assert blank_app.x_var.get() == '1'
    assert blank_app.state.config.x_row == 0
    assert blank_app.state.config.x_column is None
    # Three y columns, each pairing the x value above it with the two rows below it.
    assert len(blank_app.state.dataset.series) == 3
    assert all(one.n == 2 for one in blank_app.state.dataset.series)


def test_a_picked_row_says_the_x_values_run_across_the_sheet(blank_app: GraphPadApp) -> None:
    """Choosing a row in the grid must not leave the direction contradicting the choice."""
    from src.sheet_view import Role

    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    blank_app.sheet.assignment[Role.X_VALUES] = (0,)
    blank_app._apply_scatter_selection()
    blank_app.root.update()
    assert blank_app.x_direction_var.get() == 'Row'


def _strip_texts(app: GraphPadApp) -> list[tuple[int, int, str]]:
    """Return every text on the preview grid with its position, for reading the layout."""
    canvas = app.sheet.canvas
    items: list[tuple[int, int, str]] = []
    for item in canvas.find_all():
        if canvas.type(item) == 'text':
            x, y = canvas.coords(item)[0], canvas.coords(item)[1]
            items.append((round(x), round(y), str(canvas.itemcget(item, 'text'))))
    return items


def _line_at(app: GraphPadApp, y: float) -> list[tuple[int, str]]:
    """Return the grid text on one horizontal band, left to right."""
    return sorted((x, t) for x, top, t in _strip_texts(app) if abs(top - y) < 3)


def test_the_row_description_is_shown_in_the_index_strip(blank_app: GraphPadApp) -> None:
    """The label column used to sit in the grid, which cost every sample a column number."""
    from src.sheet_view import CELL_HEIGHT, COLUMN_HEADER_HEIGHT

    assert blank_app.load_file(INPUT_FILE)
    # Row one of the sheet, whose description is the Group marker itself.
    first = [text for _x, text in _line_at(blank_app, COLUMN_HEADER_HEIGHT + CELL_HEIGHT / 2)]
    assert 'Group' in first


def test_every_numbered_column_is_a_sample(blank_app: GraphPadApp) -> None:
    """The headings run 1..n over the samples, with the description given no number."""
    from src.sheet_view import COLUMN_HEADER_HEIGHT, ROW_HEADER_WIDTH

    assert blank_app.load_file(INPUT_FILE)
    headings = _line_at(blank_app, COLUMN_HEADER_HEIGHT / 2)
    numbers = [text for x, text in headings if x > ROW_HEADER_WIDTH]
    assert numbers == [str(column) for column in blank_app.sheet.measured_columns()]
    assert numbers[0] == '1'


def test_the_strip_keeps_the_row_numbers(blank_app: GraphPadApp) -> None:
    """The scatter controls and the caption both name rows by number, so the strip must."""
    from src.sheet_view import COLUMN_HEADER_HEIGHT, ROW_NUMBER_WIDTH

    assert blank_app.load_file(INPUT_FILE)
    row_two = _line_at(blank_app, COLUMN_HEADER_HEIGHT + 1.5 * 20)
    assert row_two[0] == (ROW_NUMBER_WIDTH // 2, '2')
    assert any(text == 'Condition' for _x, text in row_two)


def test_the_first_sample_is_column_one(blank_app: GraphPadApp) -> None:
    """With the description moved aside, the first measured column is the first one."""
    assert blank_app.load_file(INPUT_FILE)
    assert blank_app.sheet.measured_columns()[0] == 1
    blank_app.sheet.toggle_column(1)
    blank_app.root.update()
    assert blank_app.sheet.columns == (2, 3, 4, 5, 6, 7, 8)
    assert blank_app.state.dataset.samples[0].name == '42C'


def test_a_scatter_sheet_names_its_x_values_as_the_index(blank_app: GraphPadApp) -> None:
    """The x values of a tidy sheet sit in the strip, which has no number to type."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    assert blank_app.x_direction_var.get() == 'Column'
    assert blank_app.x_var.get() == 'index'
    assert blank_app.state.config.x_column == 0


def test_a_scatter_sheet_numbers_its_series_from_one(blank_app: GraphPadApp) -> None:
    """The series are renumbered with the description gone, so the grid holds eight columns."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    assert blank_app.sheet.columns == (1, 2, 3, 4, 5, 6, 7, 8)
    assert len(blank_app.state.dataset.series) == 8


def test_a_scatter_series_can_be_taken_off_the_graph(blank_app: GraphPadApp) -> None:
    """The x values were detected rather than picked, and a series must still be droppable."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    blank_app.sheet.toggle_column(1)
    blank_app.root.update()
    assert blank_app.sheet.columns == (2, 3, 4, 5, 6, 7, 8)
    assert len(blank_app.state.dataset.series) == 7


def test_the_caption_agrees_with_the_field_about_the_index(blank_app: GraphPadApp) -> None:
    """The caption and the field must not describe the same x values two different ways."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    assert 'x values: index' in str(blank_app.sheet_caption.cget('text'))
    assert 'columns 1, 2' in str(blank_app.sheet_caption.cget('text'))


def test_the_preview_rounds_to_two_places_by_default(blank_app: GraphPadApp) -> None:
    """Scientific sheets carry digits nobody reads, and two places show the shape."""
    from src.models import DEFAULT_DECIMALS

    assert DEFAULT_DECIMALS == 2
    assert blank_app.load_file(SCATTER_FILE)
    assert blank_app.decimals_var.get() == '2'
    row = _line_at(blank_app, COLUMN_HEADER_HEIGHT + 2.5 * CELL_HEIGHT)
    assert '50.00' in [text for _x, text in row]
    assert '229.86' in [text for _x, text in row]


def test_a_whole_number_keeps_its_trailing_zeros(blank_app: GraphPadApp) -> None:
    """A fixed width is what makes the digits line up, so 200 is shown as 200.00."""
    assert blank_app.load_file(SCATTER_FILE)
    row = _line_at(blank_app, COLUMN_HEADER_HEIGHT + 2.5 * CELL_HEIGHT)
    assert '200.00' in [text for _x, text in row]
    assert '200' not in [text for _x, text in row]


def test_the_number_of_places_can_be_chosen(blank_app: GraphPadApp) -> None:
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.decimals_var.set('4')
    blank_app._update_preview_decimals()
    blank_app.root.update()
    row = _line_at(blank_app, COLUMN_HEADER_HEIGHT + 2.5 * CELL_HEIGHT)
    assert '229.8625' in [text for _x, text in row]


def test_no_places_can_be_asked_for(blank_app: GraphPadApp) -> None:
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.decimals_var.set('0')
    blank_app._update_preview_decimals()
    blank_app.root.update()
    row = _line_at(blank_app, COLUMN_HEADER_HEIGHT + 2.5 * CELL_HEIGHT)
    assert '230' in [text for _x, text in row]


def test_an_empty_field_shows_the_sheet_exactly(blank_app: GraphPadApp) -> None:
    """The way out when the digits being hidden are the ones being looked for."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.decimals_var.set('')
    blank_app._update_preview_decimals()
    blank_app.root.update()
    row = [text for _x, text in _line_at(blank_app, COLUMN_HEADER_HEIGHT + 2.5 * CELL_HEIGHT)]
    assert any(text.startswith('229.8625409') for text in row)


def test_the_places_are_capped_at_something_readable(blank_app: GraphPadApp) -> None:
    """A field left disagreeing with the grid would be worse than either one alone."""
    from src.models import MAX_DECIMALS

    assert blank_app.load_file(SCATTER_FILE)
    blank_app.decimals_var.set('99')
    blank_app._update_preview_decimals()
    blank_app.root.update()
    assert blank_app.decimals_var.get() == str(MAX_DECIMALS)
    assert blank_app.state.config.preview_decimals == MAX_DECIMALS


def test_rounding_the_preview_does_not_change_the_graph(blank_app: GraphPadApp) -> None:
    """The setting is a reading convenience, so the values plotted must be untouched."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    plotted = [point.y for one in blank_app.state.dataset.series for point in one.points]
    # The sheet really does carry more digits than the preview shows, so this is a real
    # risk of the rounding leaking into the data rather than a check that cannot fail.
    assert any(value != round(value, 2) for value in plotted)
    blank_app.decimals_var.set('2')
    blank_app._update_preview_decimals()
    blank_app.root.update()
    assert [point.y for one in blank_app.state.dataset.series for point in one.points] == plotted


def test_the_setting_survives_a_reset(blank_app: GraphPadApp) -> None:
    """A reset is meant to put everything back, and this is one of the things."""
    from src.models import DEFAULT_DECIMALS

    assert blank_app.load_file(SCATTER_FILE)
    blank_app.decimals_var.set('5')
    blank_app._update_preview_decimals()
    blank_app._reset()
    blank_app.root.update()
    assert blank_app.state.config.preview_decimals == DEFAULT_DECIMALS


def test_a_text_typed_number_rounds_with_the_rest_of_its_column(blank_app: GraphPadApp) -> None:
    """The real sheet holds one replicate as text, and it must not be left behind.

    The reader already reads it as a number and the graph is drawn from it, so a preview
    that left it at the sheet's own precision would show a ragged column that looks broken
    rather than typed.
    """
    assert blank_app.load_file(INPUT_FILE)
    shown = [text for _x, text in _line_at(blank_app, COLUMN_HEADER_HEIGHT + 2.5 * CELL_HEIGHT)]
    assert '120.22' in shown
    assert '120.224' not in shown


def _scatter(blank_app: GraphPadApp) -> None:
    """Load the scatter sheet and switch to it, the common starting point for these."""
    assert blank_app.load_file(SCATTER_FILE)
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()


def test_a_scatter_plot_can_be_saved(blank_app: GraphPadApp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A scatter sheet holds no samples, which must not read as an empty graph.

    The guard that refused the save was written for a bar graph alone, so every other
    thing in this file would have been pointless if the result could not be written out.
    """
    target = tmp_path / 'scatter.png'
    monkeypatch.setattr(shell.filedialog, 'asksaveasfilename', lambda **_k: str(target))
    _scatter(blank_app)
    assert blank_app.state.dataset.series
    blank_app._save('png')
    assert target.exists()
    assert target.stat().st_size > 0


def test_the_list_names_the_scatter_series(blank_app: GraphPadApp) -> None:
    """The list held nothing for a scatter plot, so nothing could be picked or styled."""
    _scatter(blank_app)
    shown = [blank_app.listbox.item(item, 'values')[0] for item in blank_app.listbox.get_children()]
    assert shown == list(blank_app.state.series_names)


def test_scatter_arrow_buttons_reorder_series_and_legend(blank_app: GraphPadApp) -> None:
    _scatter(blank_app)
    frame = next(child for child in blank_app.listbox.master.winfo_children() if child.winfo_class() == 'TFrame')
    up, down = frame.winfo_children()
    before = blank_app.state.entry_order
    blank_app._select_row(0)
    down.invoke()

    expected = (before[1], before[0], *before[2:])
    assert blank_app.state.entry_order == expected
    assert column_values(blank_app, 'sample') == list(expected)
    mapping = getattr(blank_app.canvas.figure, 'sample_by_bar', {})
    lines = blank_app.canvas.figure.axes[0].lines
    assert [mapping[id(line)] for line in lines] == list(expected)
    legend = blank_app.canvas.figure.axes[0].get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == list(expected)

    blank_app.chart_var.set('Bar graph')
    blank_app._update_chart()
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    assert blank_app.state.entry_order == expected
    blank_app._select_row(1)
    up.invoke()
    assert blank_app.state.entry_order == before


def test_clicking_a_point_selects_its_series(blank_app: GraphPadApp) -> None:
    """A click resolved the name against the sample list, which a series is not in."""
    _scatter(blank_app)
    line = blank_app.canvas.figure.axes[0].lines[2]
    blank_app._on_pick(_pick_event(line))
    assert blank_app.state.series_names[2] in blank_app._selected_samples()


def test_scatter_adjustments_mark_the_graph_dirty(blank_app: GraphPadApp) -> None:
    """Closing after a change has to ask, or an adjusted scatter is lost silently.

    The old check asked whether any samples existed, and a scatter sheet has none, so it
    never fired for one however much the graph was adjusted.
    """
    _scatter(blank_app)
    blank_app.dirty = False
    blank_app.x_max_var.set('300')
    blank_app._update_x_axis()
    assert blank_app.dirty is True


def test_both_axes_stay_on_screen_for_either_kind_of_graph(blank_app: GraphPadApp) -> None:
    """The Axis tab always offers both axes.

    A bar graph has no x values to scale, but hiding the block and showing it again as the
    graph type changes is harder to follow than leaving it there and letting the range be
    ignored, so the two blocks are fixed parts of the tab.
    """
    _scatter(blank_app)
    axis = _captions_in(_tab_frame(blank_app, 1))
    assert {'X axis', 'X max', 'Y axis', 'Y max'} <= axis
    blank_app.chart_var.set('Bar graph')
    blank_app._update_chart()
    blank_app.root.update()
    assert {'X axis', 'X max', 'Y axis', 'Y max'} <= _captions_in(_tab_frame(blank_app, 1))


def test_the_x_range_is_greyed_out_for_a_bar_graph(blank_app: GraphPadApp) -> None:
    """A bar graph has no x values to scale, so the fields are shown but not editable.

    They are greyed rather than hidden so the X axis block keeps one shape, and they keep
    whatever was typed into them, so switching back to a scatter plot does not lose a range
    that was already worked out.
    """
    _scatter(blank_app)
    assert str(blank_app.x_max_entry.cget('state')) == 'normal'
    assert str(blank_app.x_step_entry.cget('state')) == 'normal'
    blank_app.x_max_var.set('300')
    blank_app._update_x_axis()
    blank_app.chart_var.set('Bar graph')
    blank_app._update_chart()
    blank_app.root.update()
    assert str(blank_app.x_max_entry.cget('state')) == 'disabled'
    assert str(blank_app.x_step_entry.cget('state')) == 'disabled'
    # The value is kept, so going back to a scatter plot restores the range that was set.
    assert blank_app.x_max_var.get() == '300'
    blank_app.chart_var.set('Scatter plot')
    blank_app._update_chart()
    blank_app.root.update()
    assert str(blank_app.x_max_entry.cget('state')) == 'normal'
    assert blank_app.x_max_var.get() == '300'


def test_the_label_rotation_belongs_to_the_x_axis(app: GraphPadApp) -> None:
    """It is the x axis that carries a long label, so the field sits in that block.

    A bar graph writes a sample name under every bar and those overlap as soon as there
    are more than a few, which is what the rotation is for. The value axis carries one
    number, which stays readable upright.
    """
    tab = _tab_frame(app, 1)
    blocks = {str(child.cget('text')): child for child in tab.winfo_children() if child.winfo_class() == 'TLabelframe'}
    assert set(blocks) == {'X axis', 'Y axis'}
    assert 'Label rotation' in _captions_in(blocks['X axis'])
    assert 'Label rotation' not in _captions_in(blocks['Y axis'])


def test_the_label_rotation_is_kept_inside_its_range(blank_app: GraphPadApp) -> None:
    """The field accepts a whole turn either way, and refuses to hold more than that."""
    assert blank_app.rotation_var.get() == '0'
    blank_app.rotation_var.set('90')
    blank_app._update_rotation()
    assert blank_app.rotation_var.get() == '90'
    blank_app.rotation_var.set('270')
    blank_app._update_rotation()
    assert blank_app.rotation_var.get() == '180'
    blank_app.rotation_var.set('-270')
    blank_app._update_rotation()
    assert blank_app.rotation_var.get() == '-180'


def test_the_label_rotation_reaches_the_graph(app: GraphPadApp) -> None:
    """A turn typed into the field is a turn the names are actually drawn at."""
    app.rotation_var.set('90')
    app._update_rotation()
    assert app.state.config.label_rotation == 90.0
    assert _sample_name_rotations(app) == {90.0}


def test_the_label_rotation_comes_back_upright(app: GraphPadApp) -> None:
    """Putting the field back to zero puts the names back the way they were drawn."""
    app.rotation_var.set('45')
    app._update_rotation()
    app.rotation_var.set('0')
    app._update_rotation()
    assert app.state.config.label_rotation == 0.0
    assert _sample_name_rotations(app) == {0.0}


def test_the_label_rotation_survives_a_sync(app: GraphPadApp) -> None:
    """The field shows the turn in force, so a reset or a load puts it back."""
    app.state.config.label_rotation = 45.0
    app._sync_from_state()
    assert app.rotation_var.get() == '45'


def test_a_reset_turns_the_names_upright_again(app: GraphPadApp) -> None:
    """A reset undoes the turn, which is a choice like any other."""
    app.rotation_var.set('90')
    app._update_rotation()
    app._reset()
    assert app.state.config.label_rotation == 0.0
    assert app.rotation_var.get() == '0'


def test_the_x_title_is_drawn_for_a_scatter_plot(blank_app: GraphPadApp) -> None:
    """A scatter plot has a real x axis, so it can be named."""
    _scatter(blank_app)
    blank_app.x_title_var.set('Amount added')
    blank_app._update_x_title()
    blank_app.root.update()
    assert blank_app.state.config.x_label_override == 'Amount added'
    assert blank_app.canvas.figure.axes[0].get_xlabel() == 'Amount added'


def test_a_blank_x_title_falls_back_to_the_sheet(blank_app: GraphPadApp) -> None:
    """An emptied field means "name it after the sheet", not "draw no label at all"."""
    _scatter(blank_app)
    blank_app.x_title_var.set('Amount added')
    blank_app._update_x_title()
    blank_app.x_title_var.set('')
    blank_app._update_x_title()
    blank_app.root.update()
    assert blank_app.state.config.x_label_override is None
    assert blank_app.canvas.figure.axes[0].get_xlabel() == blank_app.state.dataset.x_label


def test_typing_the_sheets_own_x_title_back_is_not_an_override(blank_app: GraphPadApp) -> None:
    """The sheet's own name is what the graph already says, so storing it would pin it."""
    _scatter(blank_app)
    blank_app.x_title_var.set(blank_app.state.dataset.x_label)
    blank_app._update_x_title()
    assert blank_app.state.config.x_label_override is None


def test_a_reset_puts_the_x_title_back_to_the_sheet(blank_app: GraphPadApp) -> None:
    """A reset restores the sheet's own name for the axis."""
    _scatter(blank_app)
    blank_app.x_title_var.set('Amount added')
    blank_app._update_x_title()
    blank_app._reset()
    assert blank_app.state.config.x_label_override is None


def test_the_x_title_is_greyed_out_for_a_bar_graph(blank_app: GraphPadApp) -> None:
    """A bar graph names its samples along that axis, so there is nothing to title."""
    blank_app.chart_var.set('Bar graph')
    blank_app._update_chart()
    blank_app.root.update()
    assert str(blank_app.x_title_entry.cget('state')) == 'disabled'


def test_the_x_title_becomes_editable_for_a_scatter_plot(blank_app: GraphPadApp) -> None:
    """Switching to a scatter plot hands the field back, rather than leaving it dead."""
    _scatter(blank_app)
    assert str(blank_app.x_title_entry.cget('state')) == 'normal'


def _sample_name_rotations(app: GraphPadApp) -> set[float]:
    """Return the angles the sample names under the bars are drawn at in the window."""
    app.canvas.figure.canvas.draw()
    from matplotlib.text import Text

    legend = app.canvas.figure.axes[0].get_legend()
    in_legend = {id(text) for text in legend.get_texts()} if legend is not None else set()
    wanted = set(app.state.visible_order)
    return {
        round(text.get_rotation(), 1)
        for text in app.canvas.figure.findobj(Text)
        if text.get_text() in wanted and id(text) not in in_legend and text.get_window_extent().height > 5
    }


def test_the_x_axis_top_can_be_set(blank_app: GraphPadApp) -> None:
    _scatter(blank_app)
    blank_app.x_max_var.set('300')
    blank_app._update_x_axis()
    blank_app.root.update()
    low, high = blank_app.canvas.figure.axes[0].get_xlim()
    assert high == pytest.approx(300.0)
    assert low < 300.0


def test_the_x_tick_step_can_be_set(blank_app: GraphPadApp) -> None:
    _scatter(blank_app)
    blank_app.x_step_var.set('50')
    blank_app._update_x_axis()
    blank_app.root.update()
    ticks = blank_app.canvas.figure.axes[0].get_xticks()
    assert any(abs(tick % 50) < 1e-9 for tick in ticks)


def test_a_typed_y_max_reaches_a_linear_scatter(blank_app: GraphPadApp) -> None:
    """The limit was only read inside the log branch, so the field did nothing."""
    _scatter(blank_app)
    blank_app.y_max_var.set('1000')
    blank_app._update_axis()
    blank_app.root.update()
    _low, high = blank_app.canvas.figure.axes[0].get_ylim()
    assert high == pytest.approx(1000.0)


def test_the_per_series_controls_appear_only_for_a_scatter_plot(blank_app: GraphPadApp) -> None:
    """Connecting points and naming them are decisions a bar never has to make."""
    _scatter(blank_app)
    _show_bar_style_tab(blank_app)
    blank_app._select_row(0)
    assert blank_app.series_style_frame.winfo_manager()
    blank_app.chart_var.set('Bar graph')
    blank_app._update_chart()
    blank_app.root.update()
    assert not blank_app.series_style_frame.winfo_manager()


def test_one_series_can_be_connected_from_the_style_panel(blank_app: GraphPadApp) -> None:
    """The all or nothing switch stays, and a single series is a second way to do it."""
    _scatter(blank_app)
    first = blank_app.state.series_names[0]
    blank_app._select_row(0)
    blank_app.connect_series_var.set(True)
    blank_app._apply_series_style()
    blank_app.root.update()
    assert blank_app.state.config.connect_series == (first,)
    styles = [line.get_linestyle() for line in blank_app.canvas.figure.axes[0].lines]
    assert styles.count('-') == 1


def test_a_series_can_be_named_from_the_style_panel(blank_app: GraphPadApp) -> None:
    """The per series box alone names a series, with the master switch it would need."""
    _scatter(blank_app)
    blank_app._select_row(0)
    blank_app.label_series_var.set(True)
    blank_app._apply_series_style()
    blank_app.root.update()
    ax = blank_app.canvas.figure.axes[0]
    assert [text.get_text() for text in ax.texts] == [blank_app.state.series_names[0]]


def test_naming_a_series_switches_the_labels_on(blank_app: GraphPadApp) -> None:
    """The renderer only draws a name when the master is on, so ticking one has to set it.

    Left off, the click would record the series and draw nothing, which is the whole of the
    reported fault: the option looked broken rather than dependent on another control.
    """
    _scatter(blank_app)
    assert blank_app.state.config.point_labels is False
    blank_app._select_row(0)
    blank_app.label_series_var.set(True)
    blank_app._apply_series_style()
    blank_app.root.update()
    assert blank_app.state.config.point_labels is True
    assert blank_app.point_labels_var.get() is True


def test_the_master_switch_names_every_series(blank_app: GraphPadApp) -> None:
    """It is an all or nothing switch, so the user is not left labelling one at a time."""
    _scatter(blank_app)
    names = blank_app.state.series_names
    blank_app.point_labels_var.set(True)
    blank_app._update_point_labels()
    blank_app.root.update()
    assert blank_app.state.config.label_series == names
    ax = blank_app.canvas.figure.axes[0]
    assert {text.get_text() for text in ax.texts} == set(names)


def test_turning_the_master_switch_off_names_none(blank_app: GraphPadApp) -> None:
    _scatter(blank_app)
    blank_app.point_labels_var.set(True)
    blank_app._update_point_labels()
    blank_app.point_labels_var.set(False)
    blank_app._update_point_labels()
    blank_app.root.update()
    assert blank_app.state.config.label_series == ()
    assert not blank_app.canvas.figure.axes[0].texts


def test_naming_one_series_leaves_the_others_unnamed(blank_app: GraphPadApp) -> None:
    """Labels collide when series finish together, so one can be taken back out."""
    _scatter(blank_app)
    names = blank_app.state.series_names
    blank_app.point_labels_var.set(True)
    blank_app._update_point_labels()
    blank_app._select_row(0)
    blank_app.label_series_var.set(False)
    blank_app._apply_series_style()
    blank_app.root.update()
    assert set(blank_app.state.config.label_series) == set(names) - {names[0]}
    assert names[0] not in [text.get_text() for text in blank_app.canvas.figure.axes[0].texts]


def test_unticking_a_series_does_not_switch_the_labels_off(blank_app: GraphPadApp) -> None:
    """Clearing the last name leaves the master on, so the switch still reads as on."""
    _scatter(blank_app)
    blank_app.point_labels_var.set(True)
    blank_app._update_point_labels()
    blank_app._select_row(0)
    blank_app.label_series_var.set(False)
    blank_app._apply_series_style()
    blank_app.root.update()
    assert blank_app.state.config.point_labels is True
    assert blank_app.point_labels_var.get() is True


def test_the_style_boxes_follow_the_master_switch(blank_app: GraphPadApp) -> None:
    """The box must not be left showing a tick the graph has stopped obeying."""
    _scatter(blank_app)
    blank_app._select_row(0)
    blank_app.point_labels_var.set(True)
    blank_app._update_point_labels()
    blank_app.root.update()
    assert blank_app.label_series_var.get() is True
    blank_app.point_labels_var.set(False)
    blank_app._update_point_labels()
    blank_app.root.update()
    assert blank_app.label_series_var.get() is False


def test_the_style_boxes_reflect_the_selected_series(blank_app: GraphPadApp) -> None:
    """The boxes show what is in force, so ticking one that is already on is not a no-op."""
    _scatter(blank_app)
    blank_app._select_row(0)
    blank_app.connect_series_var.set(True)
    blank_app._apply_series_style()
    blank_app._select_row(1)
    blank_app.root.update()
    assert blank_app.connect_series_var.get() is False
    blank_app._select_row(0)
    blank_app.root.update()
    assert blank_app.connect_series_var.get() is True


def test_the_labels_and_the_legend_are_independent_in_the_window(blank_app: GraphPadApp) -> None:
    """The names beside the points and the legend above them are separate switches."""
    _scatter(blank_app)
    assert blank_app.legend_var.get() is True
    assert blank_app.point_labels_var.get() is False
    blank_app.point_labels_var.set(True)
    blank_app._update_point_labels()
    blank_app.root.update()
    ax = blank_app.canvas.figure.axes[0]
    assert ax.get_legend() is not None
    blank_app.legend_var.set(False)
    blank_app._update_legend()
    blank_app.root.update()
    assert blank_app.canvas.figure.axes[0].get_legend() is None


def _show_bar_style_tab(app: GraphPadApp) -> None:
    """Bring the Bar style tab to the front, where the per series controls live.

    A widget on a tab that is not showing is unmapped, and Tk delivers a synthetic click to
    an unmapped widget as a no-op, so a click test has to select the tab first.
    """
    app.tabs.select(app.tabs.tabs()[2])
    app.root.update()


def _series_box(app: GraphPadApp, index: int = 0) -> tk.Misc:
    """Return one of the per series checkboxes from the style panel."""
    return [child for child in app.series_style_frame.winfo_children() if child.winfo_class() == 'TCheckbutton'][index]


def test_clicking_the_connect_box_connects_that_series(blank_app: GraphPadApp) -> None:
    """A real click, because calling the handler by hand proved nothing about the box.

    Every earlier test for this control set the variable and called the method, which
    passes whether or not the checkbutton was ever wired to anything.
    """
    _scatter(blank_app)
    _show_bar_style_tab(blank_app)
    blank_app._select_row(0)
    name = blank_app.state.series_names[0]
    _real_widget_click(_series_box(blank_app))
    blank_app.root.update()
    assert blank_app.state.config.connect_series == (name,)
    assert [line.get_linestyle() for line in blank_app.canvas.figure.axes[0].lines].count('-') == 1


def test_clicking_the_label_box_names_that_series(blank_app: GraphPadApp) -> None:
    """A real click with the master switch untouched, which is the reported fault exactly.

    The master is left off on purpose: with it on the box is already ticked for every
    series, so the click would untick rather than name, and the path a user actually
    takes would go unproven.
    """
    _scatter(blank_app)
    _show_bar_style_tab(blank_app)
    assert blank_app.state.config.point_labels is False
    blank_app._select_row(0)
    name = blank_app.state.series_names[0]
    _real_widget_click(_series_box(blank_app, 1))
    blank_app.root.update()
    assert blank_app.state.config.label_series == (name,)
    assert blank_app.state.config.point_labels is True
    assert [text.get_text() for text in blank_app.canvas.figure.axes[0].texts] == [name]


def test_the_per_series_boxes_are_absent_with_nothing_selected(blank_app: GraphPadApp) -> None:
    """They act on the highlighted series, so with none highlighted there is nothing to act on."""
    _scatter(blank_app)
    _show_bar_style_tab(blank_app)
    assert not blank_app.series_style_frame.winfo_manager()
    blank_app._select_row(0)
    blank_app.root.update()
    assert blank_app.series_style_frame.winfo_manager()


def test_a_click_with_nothing_selected_changes_nothing(blank_app: GraphPadApp) -> None:
    """The box used to tick while the graph stayed put, which reads as a broken control."""
    _scatter(blank_app)
    _show_bar_style_tab(blank_app)
    blank_app._select_row(0)
    blank_app.root.update()
    blank_app._apply_indices(())
    blank_app.root.update()
    blank_app.connect_series_var.set(True)
    blank_app._apply_series_style()
    blank_app.root.update()
    assert blank_app.state.config.connect_series == ()
    assert blank_app.connect_series_var.get() is False


def test_the_boxes_come_back_unticked_when_the_selection_empties(blank_app: GraphPadApp) -> None:
    """A tick left behind for a series that is no longer highlighted is a lie about the graph."""
    _scatter(blank_app)
    _show_bar_style_tab(blank_app)
    blank_app._select_row(0)
    _real_widget_click(_series_box(blank_app))
    blank_app.root.update()
    assert blank_app.connect_series_var.get() is True
    blank_app._apply_indices(())
    blank_app.root.update()
    assert blank_app.connect_series_var.get() is False
