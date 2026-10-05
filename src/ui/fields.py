"""Turning what a field holds into what a setting holds, and back again.

The window shows a caption and lets a number or a choice be typed, while the settings hold
an internal name and a real value. Everything that turns one into the other lives here, and
this module deliberately holds no tkinter code, so those rules can be read and tested
without opening a window.

Two ideas run through it. A field that is left showing the automatic value stores nothing,
so the graph goes on deciding for itself and a later change to the data is still reflected;
and text that is not a number yet is left alone rather than applied, so a half typed value
cannot quietly undo the choice that was already made.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.excel_reader import parse_columns
from src.models import XDirection
from src.sheet_view import LABEL_COLUMN

# What the x values field shows for the left index strip. The strip is not a numbered
# column, so this word is what stands in for a number the field would otherwise need.
INDEX_X = 'index'
# Sizes are clamped to a range matplotlib can actually render, since a value of zero or a
# negative number is silently ignored by the backend and would leave the control looking
# like it did nothing.
MIN_FONT_SIZE = 4
MAX_FONT_SIZE = 60


def label_to[Key](keys: tuple[Key, ...], labels: dict[Key, str], shown: str, fallback: Key) -> Key:
    """Return the key behind a caption shown in the window, or the default for an unknown one.

    The controls show captions rather than internal names, so a caption is turned back into
    the key it stands for. A caption the window does not know falls back to the default
    rather than being stored, which would leave the graph in a state nothing can undo.
    """
    return next((key for key in keys if labels[key] == shown), fallback)


def choice_index(shown: str) -> int | None:
    """Return the row a chooser entry stands for, or ``None`` for the "no such row" entry.

    The entries are written as ``3: Concentration`` so the choice can be read rather than
    counted, which means the number has to be taken back off the front.
    """
    head, separator, _rest = shown.partition(':')
    return int(head) - 1 if separator and head.strip().isdigit() else None


def where_word(direction: XDirection) -> str:
    """Return the word the caption uses for a direction of the x values.

    Args:
        direction: Whether the x values run down a column or across a row.

    Returns:
        Lower case word for that direction.

    """
    return 'column' if direction == 'column' else 'row'


def x_position(text: str) -> int | None:
    """Return the worksheet position named in the x values field, or ``None``.

    The left index is not a numbered column any more, because it is drawn in the strip
    rather than as a heading, so the one position that cannot be typed as a number is
    spelled out instead. Without this the tidy sheet, whose x values sit in exactly that
    column, could not be named in the field at all.

    Args:
        text: Contents of the x values field.

    Returns:
        Zero based worksheet position, or ``None`` when the field names no single one.

    """
    if text.strip().lower() == INDEX_X:
        return LABEL_COLUMN
    numbers = parse_columns(text)
    return numbers[0] - 1 if len(numbers) == 1 else None


def x_text(position: int) -> str:
    """Return how the x values field shows a worksheet position.

    Args:
        position: Zero based worksheet position.

    Returns:
        The field text for that position.

    """
    return INDEX_X if position == LABEL_COLUMN else str(position + 1)


def first_of(numbers: Sequence[int]) -> int | None:
    """Return the first number of a parsed field, or ``None`` when the field is empty.

    A field that names one thing, such as the series names row, is read as a range like
    the others so that ``2-4`` still works, but only its first number can be meant.

    Args:
        numbers: One based numbers parsed out of a field.

    Returns:
        The first number, or ``None``.

    """
    return numbers[0] if numbers else None


def optional_number(text: str) -> float | None:
    """Return the number in a field, or ``None`` when the field is blank or not a number.

    Treating a half typed or unparsable entry as automatic keeps the axis usable while it is
    being edited, instead of freezing the graph on the last value that did parse.

    Args:
        text: Contents of the entry.

    Returns:
        The value, or ``None`` to fall back to the automatic setting.

    """
    try:
        return float(text.strip())
    except ValueError:
        return None


def optional_size(text: str) -> int | None:
    """Return a whole number of points from a field, or ``None`` for the Prism default.

    Sizes are clamped to a range matplotlib can actually render, since a value of zero or a
    negative number is silently ignored by the backend and would leave the control looking
    like it did nothing.

    Args:
        text: Contents of the entry.

    Returns:
        The size, or ``None`` to use the default.

    """
    value = optional_number(text)
    if value is None or not MIN_FONT_SIZE <= round(value) <= MAX_FONT_SIZE:
        return None
    return round(value)


def shown_number(chosen: float | None, automatic: float | None) -> str:
    """Return the text for a numeric field, showing the automatic value when there is none.

    An empty box would say nothing about what the axis is doing, and the user would have no
    way of finding the automatic value to type back. Showing it means the field always reads
    as the value that is really in use.

    Args:
        chosen: The value the user picked, or ``None`` for automatic.
        automatic: The value used when nothing is chosen.

    Returns:
        The text to show in the field.

    """
    value = chosen if chosen is not None else automatic
    return '' if value is None else f'{value:g}'


def chosen_value(text: str, automatic: float | None) -> float | None:
    """Return the value a field is asking for, or ``None`` when it matches the automatic one.

    The numeric fields show the value that is actually in effect, including the automatic
    one, so a field left alone must not be read as a request to fix the axis at that number.
    Storing ``None`` for a match keeps the axis tracking the data when a new file is loaded,
    and makes "put it back to how it was" a matter of typing the number that is already
    there.

    Args:
        text: Contents of the entry.
        automatic: The value that means "let matplotlib decide", or ``None`` if there is none.

    Returns:
        The chosen value, or ``None`` to keep the automatic behaviour.

    """
    value = optional_number(text)
    if value is None:
        return None
    if automatic is not None and abs(value - automatic) <= abs(automatic) * 1e-6:
        return None
    return value


def chosen_size(text: str, automatic: int) -> int | None:
    """Return a font size a field is asking for, or ``None`` when it matches the default.

    Args:
        text: Contents of the entry.
        automatic: The size used when the user has not chosen one.

    Returns:
        The chosen size, or ``None`` to keep the Prism default.

    """
    size = optional_size(text)
    return None if size is None or size == automatic else size
