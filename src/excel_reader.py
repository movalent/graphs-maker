"""Read GraphPad style Excel worksheets into a :class:`~src.models.Dataset`."""

from __future__ import annotations

import math
import warnings
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from src.models import Dataset, Sample, XDirection, XYPoint, XYSeries

GROUP_MARKER = 'group'
CONDITION_MARKER = 'condition'


@dataclass(frozen=True, slots=True)
class SheetLayout:
    """Which worksheet rows hold the group names, the sample names and the measurements.

    The reader works this out for itself when the sheet uses the usual markers, but the
    window can show them and let the user point at different rows, which is the only way to
    read a sheet that carries no ``Group`` or ``Condition`` header at all.

    Attributes:
        group_row: Row holding the group names, or ``None`` when the sheet has no groups.
        condition_row: Row holding the sample names, or ``None`` to name samples after their
            group.
        first_data_row: First row holding a measurement.

    """

    group_row: int | None
    condition_row: int | None
    first_data_row: int

    def replace(self, **changes: int | None) -> SheetLayout:
        """Return a copy of this layout with the given rows changed.

        Args:
            **changes: Rows to replace, named ``group_row``, ``condition_row`` or
                ``first_data_row``.

        Returns:
            The updated layout.

        """
        return replace(self, **changes)  # type: ignore[arg-type]


class ExcelLayoutError(ValueError):
    """Raised when a worksheet does not follow the expected Group/Condition layout."""


class ExcelLayoutWarning(UserWarning):
    """Warned when a column is repaired, for example when a replicate is not numeric."""


# How many numbers a line of the sheet must hold before it is read as data rather than as
# a heading. A single number is a label far more often than it is a measurement, and two is
# the smallest number of x values or y series that can draw a scatter plot worth looking at.
MIN_SCATTER_VALUES = 2


@dataclass(frozen=True, slots=True)
class ScatterLayout:
    """Where a scatter sheet keeps its x values, its y series and their names.

    A sheet that carries no ``Group`` or ``Condition`` markers cannot be read as a bar
    graph at all, so a scatter plot is the only reading it has. This works out the common
    shapes of such a sheet, so the graph can be drawn without the user naming anything, and
    so the window can say plainly when a sheet is none of them.

    Attributes:
        x_direction: ``'column'`` when the x values run down a column, one per data row, or
            ``'row'`` when they run across a row, one above each plotted column.
        x_index: The worksheet column or row holding the x values, zero based.
        y_columns: Columns holding the y values, one series each, zero based.
        series_row: Row naming each series, or ``None`` to name them from the header row.
        first_data_row: First row that may hold a point.

    """

    x_direction: XDirection
    x_index: int
    y_columns: tuple[int, ...]
    series_row: int | None
    first_data_row: int


def detect_layout(table: pd.DataFrame, path: Path) -> SheetLayout:
    """Work out which rows hold the group names, the sample names and the measurements.

    The ``Group`` marker in column A anchors the sheet. A ``Condition`` row directly beneath
    it is optional, and the measurements start on whichever row comes next.

    Args:
        table: The trimmed worksheet table.
        path: Source file, used for the error message.

    Returns:
        The detected layout.

    Raises:
        ExcelLayoutError: If no ``Group`` header row can be found in column A.

    """
    row_labels = [cell_text(value) for value in table.iloc[:, 0].tolist()]
    group_row = _find_marker(row_labels, GROUP_MARKER)
    if group_row is None:
        raise ExcelLayoutError(f'No {GROUP_MARKER.capitalize()} header row found in column A of {path.name}.')
    condition_row = group_row + 1 if _is_marker(row_labels[group_row + 1], CONDITION_MARKER) else None
    first_data_row = group_row + 1 if condition_row is None else condition_row + 1
    return SheetLayout(group_row=group_row, condition_row=condition_row, first_data_row=first_data_row)



def detect_scatter_layout(table: pd.DataFrame) -> ScatterLayout | None:
    """Work out where a scatter sheet keeps its x values and its y series.

    Only the two shapes that need no explanation from the user are recognised, because a
    wrong guess drawn as a graph is worse than no guess at all. A tidy dataset keeps its
    x values in the first column, so that column is checked first and everything to its
    right that holds numbers becomes a series. A GraphPad XY table keeps its x values in
    its first row, one above each plotted column, and that is checked second.

    Anything else returns ``None``, which is the window's cue to ask rather than draw.

    Args:
        table: The trimmed worksheet table.

    Returns:
        The detected layout, or ``None`` when the sheet is in neither recognised shape.

    """
    rows, columns = table.shape
    if rows < MIN_SCATTER_VALUES or columns < 2:
        return None
    if _numbers_below(table, 0) >= MIN_SCATTER_VALUES:
        y_columns = tuple(
            column for column in range(1, columns) if _numbers_below(table, column) >= MIN_SCATTER_VALUES
        )
        if y_columns:
            series_row = _first_text_row(table, y_columns)
            first_data_row = 1 if series_row is None else series_row + 1
            return ScatterLayout(
                x_direction='column',
                x_index=0,
                y_columns=y_columns,
                series_row=series_row,
                first_data_row=first_data_row,
            )
    if _numbers_in_row(table, 0) >= MIN_SCATTER_VALUES:
        y_columns = tuple(
            column for column in range(1, columns) if _numbers_below(table, column) >= MIN_SCATTER_VALUES
        )
        if y_columns:
            series_row = _first_text_row(table, y_columns)
            first_data_row = 1 if series_row is None else series_row + 1
            return ScatterLayout(
                x_direction='row',
                x_index=0,
                y_columns=y_columns,
                series_row=series_row,
                first_data_row=first_data_row,
            )
    return None


def _numbers_below(table: pd.DataFrame, column: int, start: int = 1) -> int:
    """Return how many cells of a column below ``start`` hold a number.

    Args:
        table: The trimmed worksheet table.
        column: Zero based worksheet column to count.
        start: First row to count, so that the heading is never counted as data.

    Returns:
        The number of numeric cells.

    """
    return sum(cell_number(value) is not None for value in table.iloc[start:, column].tolist())


def _numbers_in_row(table: pd.DataFrame, row: int) -> int:
    """Return how many cells of a row hold a number.

    Args:
        table: The trimmed worksheet table.
        row: Zero based worksheet row to count.

    Returns:
        The number of numeric cells.

    """
    return sum(cell_number(value) is not None for value in table.iloc[row, :].tolist())


def _first_text_row(table: pd.DataFrame, columns: Sequence[int], start: int = 1) -> int | None:
    """Return the first row that names the series rather than measuring them.

    A tidy scatter sheet names each series in a row of text above the measurements. Naming
    the series from that row rather than from the duplicated heading above it is what stops
    a legend reading ``Standard`` five times.

    Args:
        table: The trimmed worksheet table.
        columns: Columns the names are read from.
        start: First row to look at.

    Returns:
        Zero based row index, or ``None`` when no row holds only text.

    """
    for row in range(start, len(table.index)):
        cells = [table.iloc[row, column] for column in columns]
        if all(cell_number(cell) is None and cell_text(cell) for cell in cells):
            return row
    return None


def read_table(path: Path) -> pd.DataFrame:
    """Read the first worksheet of an Excel file as a header-less table.

    Empty leading rows and empty trailing columns are dropped, so the returned table
    starts exactly at the first cell that holds data.

    Args:
        path: Path to an ``.xlsx`` file.

    Returns:
        The worksheet content without empty outer rows and columns.

    """
    raw = pd.read_excel(path, header=None, engine='openpyxl')
    trimmed = raw.dropna(axis=0, how='all').dropna(axis=1, how='all')
    return trimmed.reset_index(drop=True)


def parse_columns(text: str) -> list[int]:
    """Return the one based row or column numbers named in a piece of text.

    Numbers may be separated by commas or semicolons, and a whole range such as ``2-4`` is
    expanded, because naming three adjacent columns one at a time is tedious and the range is
    what a user reaches for. A range may be written either way round, so ``4-2`` gives the
    same three numbers in the same order. Anything that is not a number is skipped rather than
    raising, so a half typed field still yields whatever part of it does parse.

    Args:
        text: The text to read, from a panel field or a command line argument.

    Returns:
        The one based numbers found, in the order they were written, without duplicates
        removed. Anything at or below zero is dropped, because no worksheet row or column
        carries that number.

    """
    numbers: list[int] = []
    for part in text.replace(';', ',').split(','):
        piece = part.strip()
        if not piece:
            continue
        if '-' in piece[1:]:
            start, _, end = piece.partition('-')
            try:
                low, high = int(start), int(end)
            except ValueError:
                continue
            numbers.extend(range(low, high + 1) if low <= high else range(high, low + 1))
            continue
        try:
            numbers.append(int(piece))
        except ValueError:
            continue
    return [number for number in numbers if number > 0]


def cell_text(value: object) -> str:
    """Return a stripped string for a cell value, mapping missing data to an empty string.

    Args:
        value: Raw cell value taken from the worksheet.

    Returns:
        The cell as text, empty for a blank cell or one holding ``nan``.

    """
    if value is None or value is pd.NA:
        return ''
    if isinstance(value, float) and math.isnan(value):
        return ''
    text = str(value).strip()
    return '' if text.lower() == 'nan' else text


def cell_number(value: object) -> float | None:
    """Return a cell value as a float, or ``None`` when it is not numeric.

    A number typed into a sheet as text is read the same as one stored as a number, so
    that a single such cell does not quietly become a gap in an otherwise numeric column.
    The data preview relies on this too, so that a column rounds as one column rather than
    leaving one value behind at the sheet's own precision.

    Args:
        value: Raw cell value taken from the worksheet.

    Returns:
        The parsed float, or ``None`` for blanks and non-numeric text.

    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return None if math.isnan(number) else number
    text = cell_text(value)
    if ',' in text and '.' not in text:
        text = text.replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return None


def _find_marker(row_labels: list[str], marker: str) -> int | None:
    """Return the index of the first row whose column A label matches ``marker``."""
    return next((index for index, label in enumerate(row_labels) if _is_marker(label, marker)), None)


def read_dataset(
    path: Path,
    layout: SheetLayout | None = None,
    columns: Sequence[int] | None = None,
) -> Dataset:
    """Read one Excel worksheet into a :class:`~src.models.Dataset`.

    The expected layout is a ``Group`` header row, an optional ``Condition`` header row
    directly beneath it, and one replicate row per measurement. Group labels that span
    several columns, as GraphPad writes them, are forward filled.

    Args:
        path: Path to an ``.xlsx`` file.
        layout: Rows to read the names and the measurements from. It is detected from the
            usual ``Group`` and ``Condition`` markers when omitted.
        columns: Worksheet columns to read, zero based and counting the label column, or
            ``None`` to read every measured column. This is what the data preview lets the
            user tick and untick, so a column can be left out of the graph without editing
            the sheet.

    Returns:
        The parsed dataset with one :class:`~src.models.Sample` per measured column.

    Raises:
        ExcelLayoutError: If no layout is given and no ``Group`` header row can be found in
            column A, if a given layout names rows the sheet does not have, or if the
            chosen columns fall outside the sheet.

    """
    table = read_table(path)
    chosen = layout if layout is not None else detect_layout(table, path)
    _check_layout(chosen, len(table), path)
    wanted = _chosen_columns(columns, table.shape[1], path)

    row_labels = [cell_text(value) for value in table.iloc[:, 0].tolist()]
    if chosen.group_row is not None:
        group_names = _forward_filled(_column_text(table, chosen.group_row))
    else:
        # A sheet with no group row still holds one measurement per column, so every column
        # is given a blank group to read. Without this the samples are built by walking the
        # group names, and a blank list would read no columns at all.
        group_names = [''] * max(table.shape[1] - 1, 0)
    condition_names = (
        _column_text(table, chosen.condition_row) if chosen.condition_row is not None else None
    )
    replicate_labels = tuple(label for label in row_labels[chosen.first_data_row :] if label)

    preferred_names = _preferred_names(group_names, condition_names)

    return Dataset(
        samples=_build_samples(table, group_names, preferred_names, chosen.first_data_row, path, wanted),
        y_label=replicate_labels[0] if replicate_labels else '',
        replicate_labels=replicate_labels,
    )


def _chosen_columns(columns: Sequence[int] | None, width: int, path: Path) -> set[int] | None:
    """Return the measured columns to read, or ``None`` for all of them.

    A column that falls outside the sheet is refused rather than dropped, because a
    selection that silently loses a column would leave the graph showing less than the
    user asked for with no way to tell which one went missing.

    Args:
        columns: Worksheet columns named by the user, or ``None`` for every column.
        width: How many columns the sheet holds.
        path: Source file, used for the error message.

    Returns:
        The columns to read, or ``None`` to read them all.

    Raises:
        ExcelLayoutError: If a named column is outside the sheet or is the label column.

    """
    if columns is None:
        return None
    chosen: set[int] = set()
    for column in columns:
        if not 1 <= column < width:
            raise ExcelLayoutError(
                f'Column {column + 1} of {path.name} is outside the sheet, which has {width} columns.'
            )
        chosen.add(column)
    return chosen


def _check_layout(layout: SheetLayout, row_count: int, path: Path) -> None:
    """Refuse a layout that points at rows the sheet does not have.

    Args:
        layout: The rows the user pointed at.
        row_count: How many rows the sheet holds.
        path: Source file, used for the error message.

    Raises:
        ExcelLayoutError: If any named row falls outside the sheet.

    """
    named = {
        'first data row': layout.first_data_row,
        'group row': layout.group_row,
        'condition row': layout.condition_row,
    }
    for label, row in named.items():
        if row is not None and not 0 <= row < row_count:
            raise ExcelLayoutError(
                f'The {label} {row + 1} of {path.name} is outside the sheet, which has {row_count} rows.'
            )


def _is_marker(label: str, marker: str) -> bool:
    """Return whether a row label equals ``marker``, ignoring case and padding."""
    return label.strip().lower() == marker


def _column_text(table: pd.DataFrame, row: int) -> list[str]:
    """Return the non-empty cell texts of one header row, skipping the label column."""
    return [cell_text(value) for value in table.iloc[row, 1:].tolist()]


def _forward_filled(names: list[str]) -> list[str]:
    """Carry each non-empty group name to the right, so spanning labels fill their columns."""
    filled: list[str] = []
    current = ''
    for name in names:
        if name:
            current = name
        filled.append(current)
    return filled


def _unique_name(preferred: str, fallback: str, used: set[str]) -> str:
    """Return an unused display name for a sample.

    The condition name is preferred. When several samples share that name, for example
    the ``Standard`` condition repeated across groups, the group name is used instead so
    that every sample keeps a meaningful, readable label.

    Args:
        preferred: Condition name, or an empty string when the sheet has none.
        fallback: Group name, used when ``preferred`` is taken or empty.
        used: Names already assigned in this dataset.

    Returns:
        A name that is not yet present in ``used``.

    """
    for base in (preferred, fallback):
        if not base:
            continue
        if base not in used:
            used.add(base)
            return base
    counter = 2
    while f'{fallback} ({counter})' in used:
        counter += 1
    name = f'{fallback} ({counter})'
    used.add(name)
    return name


def _preferred_names(group_names: list[str], condition_names: list[str] | None) -> list[str]:
    """Return the name to try first for every measured column.

    A condition name is only used when it is unique in the sheet. Conditions such as
    ``Standard`` that repeat across groups are replaced by the group name, so all samples
    stay consistently labelled instead of a mixture of condition and group names.
    """
    if condition_names is None:
        return [''] * len(group_names)
    counts = Counter(name for name in condition_names if name)
    return ['' if counts[name] > 1 else name for name in condition_names]


def _build_samples(
    table: pd.DataFrame,
    group_names: list[str],
    preferred_names: list[str],
    first_data_row: int,
    path: Path,
    columns: set[int] | None = None,
) -> tuple[Sample, ...]:
    """Turn the measurement columns of the table into samples.

    Columns without any numeric value are skipped, and repairs are reported through
    :class:`ExcelLayoutWarning` instead of failing the whole import.

    Args:
        table: The trimmed worksheet table.
        group_names: Forward filled group name for every measured column.
        preferred_names: Name to show for every measured column, may be empty.
        first_data_row: Index of the first replicate row.
        path: Source file, used for warning messages.
        columns: Worksheet columns to read, zero based and counting the label column, or
            ``None`` for every measured column. A column left out here is skipped before
            its values are read, so it costs nothing and produces no sample.

    Returns:
        One sample per measured column, in worksheet order.

    """
    used_names: set[str] = set()
    samples: list[Sample] = []
    expected = table.shape[0] - first_data_row

    for offset, group in enumerate(group_names):
        column = offset + 1
        if columns is not None and column not in columns:
            continue
        preferred = preferred_names[offset]
        raw_values = [cell_number(table.iloc[row, column]) for row in range(first_data_row, len(table))]
        values = tuple(value for value in raw_values if value is not None)
        if not values:
            continue
        if len(values) < expected:
            warnings.warn(
                f'Column {column + 1} of {path.name} has non-numeric replicates that were skipped.',
                ExcelLayoutWarning,
                stacklevel=2,
            )
        if len(values) < 2:
            warnings.warn(
                f'Sample {preferred or group!r} has a single replicate, so its error bars are zero.',
                ExcelLayoutWarning,
                stacklevel=2,
            )
        samples.append(
            Sample(
                name=_unique_name(preferred, group, used_names),
                group=group or 'Group 1',
                values=values,
            )
        )

    return tuple(samples)


def xy_row_labels(table: pd.DataFrame) -> tuple[str, ...]:
    """Return the text of the first cell of every row, for naming the row dropdowns.

    Args:
        table: The trimmed worksheet table.

    Returns:
        One label per row, empty where the first cell is blank.

    """
    return tuple(cell_text(value) for value in table.iloc[:, 0].tolist())


def xy_column_labels(table: pd.DataFrame) -> tuple[str, ...]:
    """Return the text of the first row of every column, for naming the column dropdowns.

    Args:
        table: The trimmed worksheet table.

    Returns:
        One label per column, empty where the top cell is blank.

    """
    return tuple(cell_text(value) for value in table.iloc[0, :].tolist())


def read_xy(
    table: pd.DataFrame,
    x_row: int | None = None,
    x_column: int | None = None,
    y_columns: tuple[int, ...] = (),
    series_row: int | None = None,
    header_row: int = 0,
    first_data_row: int = 1,
    path: Path | None = None,
) -> tuple[tuple[XYSeries, ...], str]:
    """Pair the x values with the y columns the user pointed at.

    Scientific sheets record the x values in either direction, and both are common. When
    ``x_column`` is given the x values run down that column, one per data row, which is the
    layout a tidy dataset uses. When ``x_row`` is given the x values run across that row, one
    per plotted column, which is the layout a GraphPad XY table uses. Exactly one of the two
    is required.

    A pair is kept only when both of its values are numbers, because a half drawn point is
    worse than a dropped one. Dropped pairs are reported through :class:`ExcelLayoutWarning`
    rather than failing the whole import.

    Args:
        table: The trimmed worksheet table.
        x_row: Row running across the sheet that holds the x values, one per plotted column.
        x_column: Column running down the sheet that holds the x values, one per data row.
        y_columns: Columns holding the y values, one series each.
        series_row: Row naming each series, or ``None`` to name them from ``header_row``.
        header_row: Row holding the series names when ``series_row`` is not given.
        first_data_row: First row that may hold a point.
        path: Source file, used for warning messages.

    Returns:
        The series, and the text naming the x axis.

    Raises:
        ExcelLayoutError: If neither or both x directions are given, if a pointed at row or
            column is outside the sheet, or if no y column was chosen.

    """
    source = path or Path('sheet')
    rows = len(table)
    columns = table.shape[1]
    if (x_row is None) == (x_column is None):
        raise ExcelLayoutError('Choose the x values as either one row or one column, not both.')
    if not y_columns:
        raise ExcelLayoutError('Choose at least one column to plot on the y axis.')
    if x_row is not None and not 0 <= x_row < rows:
        raise ExcelLayoutError(f'Row {x_row + 1} of {source.name} is outside the sheet.')
    for column in y_columns:
        if not 0 <= column < columns:
            raise ExcelLayoutError(f'Column {column + 1} of {source.name} is outside the sheet.')

    # The x axis is named by the heading the sheet writes above the x values. A row of x
    # values is headed by a cell in the first column, and a column of them by the cell at the
    # top of that column, so the name is read from the same corner the x values start at.
    name_row = series_row if series_row is not None else header_row
    x_label = cell_text(table.iloc[0, x_column]) if x_column is not None else cell_text(table.iloc[0, 0])
    x_label = x_label or 'x'

    used: set[str] = set()
    series: list[XYSeries] = []
    for column in y_columns:
        name = cell_text(table.iloc[name_row, column]) if 0 <= name_row < rows else ''
        points: list[XYPoint] = []
        skipped = 0
        if x_column is not None:
            for row in range(first_data_row, rows):
                x_value = cell_number(table.iloc[row, x_column])
                y_value = cell_number(table.iloc[row, column])
                if x_value is None or y_value is None:
                    skipped += 1
                    continue
                points.append(XYPoint(x=x_value, y=y_value, row=row))
        elif x_row is not None:
            # The x values run across the sheet, so each plotted column pairs the x above it
            # with the values below it, and the column index is the point's identity.
            x_value = cell_number(table.iloc[x_row, column])
            if x_value is not None:
                for row in range(first_data_row, rows):
                    y_value = cell_number(table.iloc[row, column])
                    if y_value is None:
                        skipped += 1
                        continue
                    points.append(XYPoint(x=x_value, y=y_value, row=row))
            else:
                skipped += 1
        if not points:
            continue
        if skipped:
            warnings.warn(
                f'Column {column + 1} of {source.name} has {skipped} row(s) without both an x and a y value.',
                ExcelLayoutWarning,
                stacklevel=2,
            )
        series.append(XYSeries(name=_unique_name(name, f'Series {column + 1}', used), points=tuple(points)))

    return tuple(series), x_label
