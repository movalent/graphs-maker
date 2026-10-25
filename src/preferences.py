"""Application-level defaults and their persistent JSON representation."""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Literal

from src.graphpad_style import DEFAULT_PALETTE, PALETTES
from src.models import (
    DEFAULT_CONNECT_POINTS,
    DEFAULT_LEGEND_POSITION,
    ORIENTATIONS,
    SAMPLE_CHARTS,
    ChartKind,
    ColorBy,
    ErrorBarDirection,
    ErrorKind,
    LegendPosition,
    Orientation,
)

ExportFormat = Literal['png', 'pdf', 'svg', 'jpg', 'tif']
EXPORT_FORMATS: tuple[ExportFormat, ...] = ('png', 'pdf', 'svg', 'jpg', 'tif')


@dataclass(slots=True)
class Preferences:
    """Persistent application defaults, separate from settings on an open graph."""

    default_chart: ChartKind = 'bar'
    default_orientation: Orientation = 'vertical'
    default_error_kind: ErrorKind = 'sd'
    default_error_bar_direction: ErrorBarDirection = 'both'
    default_color_by: ColorBy = 'sample'
    default_show_points: bool = True
    default_jitter: float = 0.0
    default_connect_points: bool = DEFAULT_CONNECT_POINTS
    default_legend_position: LegendPosition = DEFAULT_LEGEND_POSITION
    default_palette: str = DEFAULT_PALETTE
    default_export_format: ExportFormat = 'png'
    default_export_dpi: int = 300
    default_transparent_background: bool = False
    panel_width: int = 300
    ui_font_family: str = 'Segoe UI'
    ui_font_size: int = 8
    default_input_dir: str = ''
    default_output_dir: str = ''
    last_input_dir: str = ''
    last_output_dir: str = ''
    remember_last_directories: bool = True
    auto_refresh_preview: bool = True
    undo_history_limit: int = 20
    show_confirmations: bool = True

    @classmethod
    def from_dict(cls, values: object) -> Preferences:
        """Create preferences from JSON data, replacing invalid fields with factory defaults.

        Args:
            values: Decoded JSON value.

        Returns:
            Preferences populated with validated values.

        """
        defaults = cls()
        if not isinstance(values, dict):
            warnings.warn(
                'Preferences file must contain a JSON object; using factory defaults.',
                RuntimeWarning,
                stacklevel=2,
            )
            return defaults

        result = cls()
        validators = _validators()
        for preference in fields(cls):
            value = values.get(preference.name, getattr(defaults, preference.name))
            if validators[preference.name](value):
                if preference.name == 'default_jitter':
                    value = float(value)
                setattr(result, preference.name, value)
            else:
                warnings.warn(
                    f'Invalid preference {preference.name!r}; using its factory default.',
                    RuntimeWarning,
                    stacklevel=2,
                )
        return result


def preferences_path() -> Path:
    """Return the configured preferences file path."""
    return Path.home() / '.config' / 'graphpad-prism' / 'preferences.json'


def load_preferences(path: Path | None = None) -> Preferences:
    """Load preferences, returning factory defaults when no usable file exists.

    Args:
        path: Optional file path, primarily for tests.

    Returns:
        Validated preferences.

    """
    source = path or preferences_path()
    try:
        contents = source.read_text(encoding='utf-8')
    except FileNotFoundError:
        return Preferences()
    except OSError as error:
        warnings.warn(
            f'Could not read preferences from {source}: {error}; using factory defaults.',
            RuntimeWarning,
            stacklevel=2,
        )
        return Preferences()

    try:
        decoded = json.loads(contents)
    except json.JSONDecodeError as error:
        warnings.warn(
            f'Could not parse preferences from {source}: {error}; using factory defaults.',
            RuntimeWarning,
            stacklevel=2,
        )
        return Preferences()
    return Preferences.from_dict(decoded)


def save_preferences(preferences: Preferences, path: Path | None = None) -> None:
    """Persist preferences as formatted JSON.

    Args:
        preferences: Values to persist.
        path: Optional file path, primarily for tests.

    Raises:
        OSError: The settings directory or file could not be written.

    """
    destination = path or preferences_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(asdict(preferences), indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )


def _validators() -> dict[str, Callable[[object], bool]]:
    """Return validators for every persisted field."""

    def choice(options: tuple[object, ...]) -> Callable[[object], bool]:
        return lambda value: value in options

    def integer_between(minimum: int, maximum: int) -> Callable[[object], bool]:
        return lambda value: isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum

    def is_bool(value: object) -> bool:
        return isinstance(value, bool)

    def is_text(value: object) -> bool:
        return isinstance(value, str)

    def is_nonempty_text(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def is_jitter(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1

    return {
        'default_chart': choice(SAMPLE_CHARTS),
        'default_orientation': choice(ORIENTATIONS),
        'default_error_kind': choice(('sd', 'sem', 'none')),
        'default_error_bar_direction': choice(('top', 'bottom', 'both')),
        'default_color_by': choice(('sample', 'group')),
        'default_show_points': is_bool,
        'default_jitter': is_jitter,
        'default_connect_points': is_bool,
        'default_legend_position': choice(('above', 'right', 'inside')),
        'default_palette': choice(tuple(PALETTES)),
        'default_export_format': choice(EXPORT_FORMATS),
        'default_export_dpi': integer_between(72, 1200),
        'default_transparent_background': is_bool,
        'panel_width': integer_between(240, 600),
        'ui_font_family': is_nonempty_text,
        'ui_font_size': integer_between(6, 24),
        'default_input_dir': is_text,
        'default_output_dir': is_text,
        'last_input_dir': is_text,
        'last_output_dir': is_text,
        'remember_last_directories': is_bool,
        'auto_refresh_preview': is_bool,
        'undo_history_limit': integer_between(1, 1000),
        'show_confirmations': is_bool,
    }
