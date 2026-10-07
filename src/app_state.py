"""Adjustable state behind the interactive window.

This module deliberately holds no tkinter code so that the reordering and colouring rules
can be tested without opening a window.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from src.graphpad_style import DEFAULT_LINE_WIDTH, DEFAULT_PALETTE, default_color
from src.models import (
    DEFAULT_DECIMALS,
    DEFAULT_LEGEND_POSITION,
    DEFAULT_POINT_TYPE,
    DEFAULT_TITLE_POSITION,
    LOG_HEADROOM,
    POINT_TYPES,
    Y_MAX_HEADROOM,
    Dataset,
    PlotConfig,
    PointType,
    Sample,
)

FALLBACK_COLOR = '#000000'
HEX_PATTERN = re.compile(r'^#(?:[0-9a-f]{3}|[0-9a-f]{6})$', re.IGNORECASE)
# The Prism sizes and thicknesses live in src.graphpad_style, which this module already
# imports for the palette, so the number a field shows is the number the renderer draws with.
# Thicknesses outside this range are refused. Zero or less is silently ignored by the
# backend, which would leave the control looking as though it had done nothing, and a very
# thick line hides the bar it is meant to be drawing around.
MIN_LINE_WIDTH = 0.1
MAX_LINE_WIDTH = 10.0
# Which of the two sets of lines a thickness applies to: the frame of the graph, or the bars.
LineTarget = Literal['axis', 'bar']
HATCH_PATTERNS: tuple[str, ...] = ('', '//', '\\\\\\', '|||', '---', '+++', 'xxx', 'ooo', 'OOO', '...', '***')
# The same patterns as they are offered in the window. The two tuples are index aligned, so a
# pattern is picked from the list by the same position that the user sees.
HATCH_LABELS: tuple[str, ...] = (
    'None',
    '///',
    '\\\\\\',
    '|||',
    '---',
    '+++',
    'xxx',
    'ooo',
    'OOO',
    '...',
    '***',
)


def normalize_hex(value: str) -> str | None:
    """Return a colour as ``#rrggbb``, or ``None`` when the text is not a hex colour.

    The hex field accepts a leading ``#`` as optional and the three digit short form, and
    the result is lower cased so that it can be handed straight to Tk and matplotlib.

    Args:
        value: Text typed by the user.

    Returns:
        The colour in ``#rrggbb`` form, or ``None`` when it cannot be parsed.

    """
    text = value.strip()
    if not text.startswith('#'):
        text = f'#{text}'
    if not HEX_PATTERN.match(text):
        return None
    if len(text) == 4:
        return f'#{text[1] * 2}{text[2] * 2}{text[3] * 2}'.lower()
    return text.lower()


def _clamp_line_width(value: float | None) -> float | None:
    """Return a usable line thickness, or ``None`` when the text is not one.

    A value that cannot be rendered, because it is not a number or falls outside the range
    matplotlib draws sensibly, is refused rather than clamped. Clamping would turn a typo
    such as ``-3`` into a real setting the user never asked for.

    Args:
        value: Thickness typed by the user, in points.

    Returns:
        The thickness to use, or ``None`` to keep the Prism default.

    """
    if value is None or not MIN_LINE_WIDTH <= value <= MAX_LINE_WIDTH:
        return None
    return value


class AppState:
    """The dataset being edited together with the presentation settings to apply to it.

    Attributes:
        dataset: The experiment read from the input file.
        config: Current presentation settings, mutated in place by the controls.
        sheet_order: Sample names in their original worksheet order, restored by :meth:`reset`.
        columns: Worksheet columns currently read, zero based and counting the label
            column, or ``None`` when every measured column is read. The data preview sets
            this, so a column can be left out of the graph without editing the sheet.

    """

    def __init__(self, dataset: Dataset, config: PlotConfig | None = None) -> None:
        """Create the state for one dataset.

        Args:
            dataset: The experiment read from the input file.
            config: Initial settings; a default configuration is used when omitted.

        """
        self.dataset = dataset
        self.config = config or PlotConfig()
        self.columns: tuple[int, ...] | None = None
        self.sheet_order = tuple(sample.name for sample in dataset.samples)
        if not self.config.sample_order:
            # No explicit order was supplied, so start from the worksheet order. A supplied
            # one is kept, because the command line can pass a partial order through.
            self.config.sample_order = self.sheet_order

    def replace_dataset(self, dataset: Dataset) -> None:
        """Swap in a freshly read dataset, keeping the current settings.

        The chosen sample order and the colours are kept, but names that are no longer
        present are dropped, so unticking a column in the data preview leaves the rest of
        the graph exactly as it was rather than resetting it.

        Args:
            dataset: The dataset read with the new column selection.

        """
        self.dataset = dataset
        present = {sample.name for sample in dataset.samples}
        self.sheet_order = tuple(sample.name for sample in dataset.samples)
        self.config.sample_order = tuple(name for name in self.config.sample_order if name in present)
        if not self.config.sample_order:
            self.config.sample_order = self.sheet_order
        # Colours and overrides are keyed by sample name, so the ones belonging to a
        # column that has just been removed would linger and be reused if it came back.
        for mapping in (self.config.colors, self.config.edge_colors, self.config.hatches, self.config.group_overrides):
            for name in set(mapping) - present:
                del mapping[name]

    def set_columns(self, columns: Sequence[int] | None) -> None:
        """Record which worksheet columns are read, so the reader and the preview agree.

        Args:
            columns: Worksheet columns to read, zero based and counting the label column,
                or ``None`` for every measured column.

        """
        self.columns = None if columns is None else tuple(sorted(set(columns)))

    @property
    def samples(self) -> tuple[Sample, ...]:
        """Return every sample of the dataset, in the current order."""
        return self.dataset.ordered(self.config.sample_order)

    @property
    def visible_order(self) -> tuple[str, ...]:
        """Return the sample names in their current left to right order."""
        return tuple(sample.name for sample in self.samples)

    @property
    def series_names(self) -> tuple[str, ...]:
        """Return the scatter series names, in drawing order.

        A scatter sheet holds no samples at all: its columns are paired x and y values
        rather than replicates of one condition. Everything the window does for a sample
        therefore needs a scatter equivalent, and this is the list it works from.

        Returns:
            One name per series, in worksheet order.

        """
        return tuple(series.name for series in self.dataset.series)

    @property
    def entry_order(self) -> tuple[str, ...]:
        """Return the names the list and the graph pick between, for the current chart.

        A bar graph picks between samples and a scatter plot between series. Returning
        both from one place is what lets the list, the colour picker and a click on the
        graph agree on what a name refers to, whichever chart is drawn.

        Returns:
            The sample or series names, in drawing order.

        """
        return self.series_names if self.config.chart == 'scatter' else self.visible_order

    def index_of(self, name: str) -> int:
        """Return where a named entry sits, for either chart kind.

        Args:
            name: Sample or series name to look up.

        Returns:
            The position, or ``-1`` when the name is not in the current chart.

        """
        order = self.entry_order
        return order.index(name) if name in order else -1


    def move_sample(self, index: int, target: int) -> tuple[str, ...]:
        """Move one sample to another position, clamped to the valid range.

        Args:
            index: Current position of the sample to move.
            target: Desired position; values outside the list are clamped.

        Returns:
            The resulting sample order.

        """
        order = list(self.visible_order)
        if not order or not 0 <= index < len(order):
            return self.visible_order
        bounded = min(max(target, 0), len(order) - 1)
        if bounded == index:
            return self.visible_order
        name = order.pop(index)
        order.insert(bounded, name)
        self.config.sample_order = tuple(order)
        return self.config.sample_order

    def move_samples(self, indices: Sequence[int], delta: int) -> tuple[str, ...]:
        """Shift selected samples one position while preserving their relative order.

        Args:
            indices: Current positions of the selected samples.
            delta: ``-1`` to move up or ``1`` to move down.

        Returns:
            The resulting sample order.

        """
        order = list(self.visible_order)
        selected = sorted({index for index in indices if 0 <= index < len(order)})
        if delta not in (-1, 1):
            raise ValueError('delta must be -1 or 1')
        positions = selected if delta == -1 else selected[::-1]

        for index in positions:
            target = index + delta
            if 0 <= target < len(order):
                order[index], order[target] = order[target], order[index]

        result = tuple(order)
        if result != self.visible_order:
            self.config.sample_order = result
        return result

    def set_color(self, name: str, color: str) -> bool:
        """Set an explicit colour for one sample.

        Args:
            name: Name of the sample to recolour.
            color: Colour as a hex string, for example ``'#0000ff'``.

        Returns:
            ``True`` when the sample exists and the colour is usable. Text that is not a
            colour Tk understands is refused, because an unusable value would raise a
            ``TclError`` deep inside a widget and surface as a bare error window.

        """
        if self.index_of(name) < 0:
            return False
        if normalize_hex(color) is None:
            return False
        self.config.colors[name] = normalize_hex(color) or color
        return True

    def color_of(self, name: str) -> str:
        """Return the colour currently used for one sample.

        The explicit colour is used when the user set one, otherwise the sample keeps
        the palette colour that :mod:`src.plotting` would pick for it. The result is
        always a colour Tk accepts, so callers can hand it straight to a widget.

        Which palette entry a sample takes follows ``color_by``, and it has to be the same
        rule the renderer uses. Picking by sample position here while the renderer picks by
        group left the list, the hex field and the swatch showing a colour the bar was not
        drawn in, which made every colour control look as though it had done nothing.

        Args:
            name: Name of the sample.

        Returns:
            The colour as a hex string.

        """
        chosen = normalize_hex(self.config.colors.get(name, ''))
        if chosen:
            return chosen
        if self._colors_by_group():
            groups = self.groups()
            group = self.group_of(name)
            position = groups.index(group) if group in groups else 0
            return default_color(position, self.config.palette, len(groups))
        index = self.index_of(name)
        return default_color(
            index if index >= 0 else 0,
            self.config.palette,
            len(self.entry_order),
        )

    def _colors_by_group(self) -> bool:
        """Return whether palette colours follow whole groups rather than single samples.

        Only a bar graph groups its bars, so a scatter plot always colours by series. That
        mirrors :func:`src.plotting._series_colors`, which ignores ``color_by`` because a
        scatter series is its own thing rather than a member of a group.
        """
        return self.config.chart == 'bar' and self.config.color_by == 'group'

    def reset_colors(self) -> None:
        """Drop every manual colour so the samples return to the GraphPad palette."""
        self.config.colors.clear()
        self.config.edge_colors.clear()
        self.config.hatches.clear()

    def set_edge_color(self, name: str, color: str) -> bool:
        """Set the bar outline colour of one sample.

        Args:
            name: Name of the sample.
            color: Colour as a hex string, for example ``'#000000'``.

        Returns:
            ``True`` when the sample exists and the colour is usable.

        """
        if self.index_of(name) < 0 or normalize_hex(color) is None:
            return False
        self.config.edge_colors[name] = normalize_hex(color) or color
        return True

    def edge_of(self, name: str) -> str:
        """Return the bar outline colour of one sample, black when it was not changed."""
        if name in self.config.edge_colors and normalize_hex(self.config.edge_colors[name]):
            return normalize_hex(self.config.edge_colors[name]) or FALLBACK_COLOR
        return FALLBACK_COLOR

    def set_hatch(self, name: str, pattern: str) -> bool:
        """Set the hatch pattern of one sample.

        Args:
            name: Name of the sample.
            pattern: A matplotlib hatch pattern, for example ``'//'``. An empty string clears it.

        Returns:
            ``True`` when the sample exists and the pattern is one matplotlib understands.

        """
        if self.index_of(name) < 0 or pattern not in HATCH_PATTERNS:
            return False
        self.config.hatches[name] = pattern
        return True

    def hatch_of(self, name: str) -> str:
        """Return the hatch pattern of one sample, empty when it was not changed."""
        pattern = self.config.hatches.get(name, '')
        return pattern if pattern in HATCH_PATTERNS else ''

    def set_point_type(self, name: str, point_type: PointType) -> bool:
        """Set the shape the points of one sample or scatter series are drawn as.

        Args:
            name: Name of the sample or scatter series.
            point_type: Shape to draw its points as.

        Returns:
            ``True`` when the name is in the current graph and the shape is one the renderer
            has a marker for. An unknown name or shape is refused rather than stored, since
            neither could be drawn and neither could be undone from the window.

        """
        if self.index_of(name) < 0 or point_type not in POINT_TYPES:
            return False
        self.config.point_types[name] = point_type
        return True

    def clear_point_type(self, name: str) -> bool:
        """Return one sample or scatter series to the shape the whole graph is drawn with.

        Args:
            name: Name of the sample or scatter series.

        Returns:
            ``True`` when the name is in the current graph. A name that has no shape of its own
            is left alone, since it is already following the graph.

        """
        if self.index_of(name) < 0:
            return False
        self.config.point_types.pop(name, None)
        return True

    def point_type_of(self, name: str) -> PointType:
        """Return the shape the points of one sample or series are drawn as.

        Args:
            name: Name of the sample or scatter series.

        Returns:
            The shape chosen for that name where there is one, and the whole graph's shape
            otherwise, which is the one the renderer would fall back to.

        """
        return self.config.point_types.get(name, self.config.point_type)

    def group_of(self, name: str) -> str:
        """Return the group a sample is currently drawn under.

        Args:
            name: Name of the sample.

        Returns:
            The override when one is set, otherwise the group from the worksheet.

        """
        return self.config.group_overrides.get(name) or self._sheet_group(name)

    def _sheet_group(self, name: str) -> str:
        """Return the group the sample was read into, ignoring any override."""
        return next((sample.group for sample in self.dataset.samples if sample.name == name), '')

    def automatic_y_max(self) -> float:
        """Return the value axis top that is used when the user has not chosen one.

        This mirrors what the renderer does, so the number shown in the window is the number
        that is actually drawn rather than a second, slightly different rule.

        Returns:
            The tallest mean plus headroom, or ``1.0`` for an empty dataset.

        """
        samples = self.samples
        if self.config.log_axis:
            positive = [value for sample in samples for value in sample.values if value > 0]
            return max(positive) * LOG_HEADROOM if positive else 1.0
        if samples:
            return max((sample.mean for sample in samples), default=1.0) * Y_MAX_HEADROOM
        # A scatter plot holds no samples at all, so the top has to come from its points.
        # Reading it off the tallest sample would show 1.15 in the field, because there are
        # none, and typing a value would then be compared against that meaningless number.
        points = [point.y for series in self.dataset.series for point in series.points]
        if not points:
            # Nothing has been read at all, which is the case the fallback is there for.
            return 1.0 * Y_MAX_HEADROOM
        tallest = max(points)
        return tallest * LOG_HEADROOM if self.config.log_axis else tallest * Y_MAX_HEADROOM

    def groups(self) -> tuple[str, ...]:
        """Return the groups in drawing order, after applying any overrides.

        The order follows the position of each group's first bar, so a group always sits
        where its leftmost sample sits and the band lines stay in step with the bars.
        """
        return tuple(dict.fromkeys(self.group_of(sample.name) for sample in self.samples))

    def multi_groups(self) -> tuple[str, ...]:
        """Return only the groups holding more than one sample, in drawing order.

        A group of one is not a grouping: Prism does not draw a band for it, and listing
        it next to the real groups only makes them harder to pick out. This is the list the
        window shows, while :meth:`groups` stays complete for ordering and for the graph.
        """
        counts: dict[str, int] = {}
        for sample in self.samples:
            group = self.group_of(sample.name)
            counts[group] = counts.get(group, 0) + 1
        return tuple(group for group in self.groups() if counts.get(group, 0) > 1)

    def set_group(self, name: str, group: str) -> bool:
        """Draw one sample under a different group.

        Args:
            name: Name of the sample.
            group: Group to draw it under. An empty string restores the worksheet group.

        Returns:
            ``True`` when the sample exists.

        """
        if self.index_of(name) < 0:
            return False
        if not group.strip():
            self.config.group_overrides.pop(name, None)
        else:
            self.config.group_overrides[name] = group.strip()
        return True

    def merge_groups(self, names: Sequence[str], group: str) -> bool:
        """Combine several groups into one, as when joining two constructs into one group.

        Args:
            names: Groups to combine. Unknown names are ignored.
            group: Name of the resulting group.

        Returns:
            ``True`` when at least one sample was moved.

        """
        if not group.strip():
            return False
        moved = False
        for sample in self.samples:
            if sample.group in names:
                moved = self.set_group(sample.name, group) or moved
        return moved

    def split_sample(self, name: str) -> bool:
        """Give one sample a group of its own, taking it out of its current group.

        Args:
            name: Name of the sample to split off.

        Returns:
            ``True`` when the sample exists.

        """
        return self.set_group(name, name)

    def set_line_width(self, target: LineTarget, value: float | None) -> bool:
        """Set the thickness of either the axis lines or the bar lines.

        Args:
            target: Which lines to change, ``'axis'`` or ``'bar'``.
            value: Thickness in points. ``None`` restores the Prism default.

        Returns:
            ``True`` when the thickness is usable. A value outside the range matplotlib can
            draw sensibly is refused, so an unusable one cannot be stored.

        """
        width = _clamp_line_width(value)
        if value is not None and width is None:
            return False
        if target == 'axis':
            self.config.axis_line_width = width
        else:
            self.config.bar_line_width = width
        return True

    def line_width_of(self, target: LineTarget) -> float:
        """Return the thickness in force for the requested lines.

        Args:
            target: Which lines to look up, ``'axis'`` or ``'bar'``.

        Returns:
            The thickness in points, falling back to the Prism default.

        """
        chosen = self.config.axis_line_width if target == 'axis' else self.config.bar_line_width
        return chosen if chosen is not None else DEFAULT_LINE_WIDTH

    def reset(self) -> None:
        """Discard every adjustment, including the sample order, and restore the defaults.

        The original worksheet order and grouping are restored rather than what happened to
        be showing, so a reset really does undo everything the user changed.

        The column selection is reset as well, so a sample that was left out of the graph in
        the data preview comes back.
        """
        self.reset_colors()
        self.set_columns(None)
        self.config.group_overrides.clear()
        self.config.log_axis = False
        self.config.title = None
        self.config.title_position = DEFAULT_TITLE_POSITION
        self.config.title_font = None
        self.config.error_kind = 'sd'
        self.config.color_by = 'sample'
        self.config.palette = DEFAULT_PALETTE
        self.config.grouped_layout = False
        self.config.jitter = 0.0
        self.config.show_points = True
        self.config.show_legend = True
        self.config.legend_position = DEFAULT_LEGEND_POSITION
        self.config.legend_font = None
        self.config.y_label = None
        self.config.y_max = None
        self.config.y_min = None
        self.config.y_major_step = None
        self.config.font_size = None
        self.config.y_label_size = None
        self.config.title_size = None
        self.config.legend_size = None
        self.config.axis_line_width = None
        self.config.bar_line_width = None
        self.config.preview_decimals = DEFAULT_DECIMALS
        self.config.x_max = None
        self.config.x_major_step = None
        self.config.label_rotation = 0.0
        self.config.x_label_override = None
        self.config.point_type = DEFAULT_POINT_TYPE
        self.config.point_types.clear()
        self.config.connect_series = ()
        self.config.point_labels = False
        self.config.label_series = ()
        self.config.sample_order = self.sheet_order
