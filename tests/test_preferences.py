"""Tests for application preferences and their effect on newly created graph state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.app_state import AppState
from src.models import Dataset, Sample
from src.preferences import Preferences, load_preferences, preferences_path, save_preferences


def test_preferences_round_trip(tmp_path: Path) -> None:
    preferences = Preferences(
        default_chart='violin',
        default_orientation='horizontal',
        default_error_kind='sem',
        default_error_bar_direction='top',
        default_color_by='group',
        default_show_points=False,
        default_jitter=0.35,
        default_connect_points=False,
        default_legend_position='right',
        default_palette='okabe_ito',
        default_export_format='svg',
        default_export_dpi=600,
        default_transparent_background=True,
        panel_width=360,
        ui_font_family='Arial',
        ui_font_size=10,
        default_input_dir='C:/input',
        default_output_dir='C:/output',
        last_input_dir='C:/recent-input',
        last_output_dir='C:/recent-output',
        remember_last_directories=False,
        auto_refresh_preview=False,
        undo_history_limit=12,
        show_confirmations=False,
    )
    path = tmp_path / 'settings' / 'preferences.json'

    save_preferences(preferences, path)

    assert load_preferences(path) == preferences


def test_missing_and_partial_preferences_use_factory_defaults(tmp_path: Path) -> None:
    path = tmp_path / 'preferences.json'
    assert load_preferences(path) == Preferences()

    path.write_text(json.dumps({'default_chart': 'box', 'undo_history_limit': 5}), encoding='utf-8')

    loaded = load_preferences(path)

    assert loaded.default_chart == 'box'
    assert loaded.undo_history_limit == 5
    assert loaded.default_export_format == Preferences().default_export_format
    assert loaded.panel_width == Preferences().panel_width


def test_invalid_preference_values_warn_and_fall_back_to_factory_defaults(tmp_path: Path) -> None:
    path = tmp_path / 'preferences.json'
    path.write_text(json.dumps({'default_chart': 'scatter', 'panel_width': 900}), encoding='utf-8')

    with pytest.warns(RuntimeWarning, match='Invalid preference'):
        loaded = load_preferences(path)

    assert loaded.default_chart == Preferences().default_chart
    assert loaded.panel_width == Preferences().panel_width


def test_corrupt_preferences_warn_and_use_defaults(tmp_path: Path) -> None:
    path = tmp_path / 'preferences.json'
    path.write_text('{broken', encoding='utf-8')

    with pytest.warns(RuntimeWarning, match='Could not parse preferences'):
        assert load_preferences(path) == Preferences()


def test_preferences_path_uses_selected_user_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)

    assert preferences_path() == tmp_path / '.config' / 'graphpad-prism' / 'preferences.json'


def test_new_graph_and_reset_use_application_graph_defaults() -> None:
    preferences = Preferences(
        default_chart='box_violin',
        default_orientation='horizontal',
        default_error_kind='sem',
        default_error_bar_direction='bottom',
        default_color_by='group',
        default_show_points=False,
        default_jitter=0.4,
        default_connect_points=False,
        default_legend_position='right',
        default_palette='okabe_ito',
    )
    dataset = Dataset(samples=(Sample('Control', 'A', (1.0, 2.0)),))

    state = AppState(dataset, preferences=preferences)

    assert state.config.chart == 'box_violin'
    assert state.config.orientation == 'horizontal'
    assert state.config.error_kind == 'sem'
    assert state.config.error_bar_direction == 'bottom'
    assert state.config.color_by == 'group'
    assert state.config.show_points is False
    assert state.config.jitter == 0.4
    assert state.config.connect_points is False
    assert state.config.legend_position == 'right'
    assert state.config.palette == 'okabe_ito'

    state.config.chart = 'bar'
    state.config.orientation = 'vertical'
    state.config.palette = 'tab10'
    state.reset()

    assert state.config.chart == 'box_violin'
    assert state.config.orientation == 'horizontal'
    assert state.config.error_bar_direction == 'bottom'
    assert state.config.palette == 'okabe_ito'


def test_undo_history_capacity_uses_preferences() -> None:
    state = AppState(
        Dataset(samples=(Sample('Control', 'A', (1.0,)),)),
        preferences=Preferences(undo_history_limit=2),
    )

    for index in range(4):
        state.config.title = str(index)
        state.record_edit()

    assert state.undo()
    assert state.undo()
    assert not state.undo()
