"""The rows and blocks the control panel is assembled from.

Every control in the window is one of a handful of shapes: a caption above a dropdown, a
caption beside a number, two of those side by side, or a titled block holding a group of
them. They are built here so that each tab reads as a list of settings rather than as a
page of packing calls, and so that the differences between the shapes live in one place.

The builders are plain functions rather than methods because none of them needs anything
from the window: they are handed the frame to build on and the variable to write to.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk
from typing import cast

# The callback a control fires when it changes. Every handler in the panel takes the event and
# ignores it, so one type covers a dropdown, which sends one, and an entry, which sends none.
Handler = Callable[[tk.Event[tk.Misc] | None], None] | None
# One cell of a two column option row: the caption, the variable it writes to, the choices
# offered and the callback fired on a change. A ``None`` variable marks an empty slot, which
# is how a row with only one control on it is written.
OptionSpec = tuple[str | None, tk.StringVar | None, tuple[str, ...], Handler]
# One cell of a :func:`pair_row`. The difference from :data:`OptionSpec` is the choices: an
# empty tuple asks for a free text entry rather than a dropdown, which is what lets a number
# sit beside a dropdown on the same line. A ``None`` handler marks a field that is a
# placeholder for now and so has nothing to apply.
ControlSpec = tuple[str, tk.StringVar, tuple[str, ...], Handler]
# Either kind of control a cell can hold, depending on whether it was given any choices.
Control = ttk.Combobox | ttk.Entry
# The caption font used by every row in the panel.
LABEL_FONT: tuple[str, int] = ('Segoe UI', 8)
# Height of a palette swatch strip in pixels.
SWATCH_HEIGHT = 14


def swatch(parent: tk.Misc, blocks: int, width: int) -> tk.Canvas:
    """Create an empty canvas to draw a palette swatch on.

    Args:
        parent: The widget the swatch is packed into.
        blocks: How many colour blocks the strip is divided into.
        width: Width of the strip in pixels.

    Returns:
        The blank canvas, ready for :func:`draw_swatch`.

    """
    return tk.Canvas(
        parent,
        height=SWATCH_HEIGHT,
        width=width,
        highlightthickness=0,
        borderwidth=1,
        relief=tk.SUNKEN,
    )


def draw_swatch(canvas: tk.Canvas, colors: Sequence[str]) -> None:
    """Paint a palette's colours onto a swatch canvas, one block per colour.

    The blocks are drawn edge to edge so the strip reads as a row of swatches rather than a
    gradient, which is what makes the individual colours of a palette visible.

    Args:
        canvas: The canvas to draw on, as returned by :func:`swatch`.
        colors: The colours to show, one per block.

    """
    canvas.delete('all')
    if not colors:
        return
    # Tk reports a width of 1 for a canvas that has not been mapped yet, and 1 is truthy,
    # so a plain ``winfo_width() or width`` never falls back and lays every block out inside
    # a single pixel. The configured width is available immediately, and is what the strip is
    # measured from, so it is used until the real size is known.
    measured = canvas.winfo_width()
    if measured <= 1:
        measured = int(canvas.cget('width'))
    span = max(measured, 1) / len(colors)
    for index, color in enumerate(colors):
        canvas.create_rectangle(
            index * span,
            0,
            (index + 1) * span,
            SWATCH_HEIGHT,
            fill=color,
            outline='',
        )


def wheel_units(event: tk.Event[tk.Misc]) -> int:
    """Return how far a wheel event should scroll, in units.

    Windows reports the wheel in multiples of 120, but a high resolution or touchpad
    mouse can report a smaller delta, which the plain division turns into zero and so
    makes the wheel look broken. Any non zero delta therefore scrolls at least one unit.

    Args:
        event: The wheel event.

    Returns:
        A positive number of units to scroll up, a negative one to scroll down.

    """
    delta = int(getattr(event, 'delta', 0))
    if not delta:
        return 0
    return -max(-1, min(1, delta // 120)) or (-1 if delta > 0 else 1)


def bind_wheel(widget: tk.Misc, handler: Callable[[tk.Event[tk.Misc]], None]) -> None:
    """Bind the mouse wheel to one widget and to everything inside it.

    The options are a frame full of entries, comboboxes and checkbuttons rather than
    one scrollable widget, and Tk only delivers an event to the widget it happened on.
    Every child therefore has to be bound as well, or the wheel would work over the
    gaps in the panel and nowhere else.

    The walk sees only what exists at the moment it runs, so this has to be called
    after the widgets it is meant to cover have been built. Called any earlier it binds
    an empty container and leaves the whole panel unbound, with nothing to say so.

    Args:
        widget: Widget to bind, and then every widget below it.
        handler: Called with the wheel event.

    """
    widget.bind('<MouseWheel>', handler)
    for child in widget.winfo_children():
        bind_wheel(child, handler)


def section(parent: tk.Widget, text: str) -> ttk.Labelframe:
    """Create a titled block that a group of related settings sits inside.

    The block is packed ready to use, so a caller only has to add its rows. A plain frame
    with a label above it leaves the rows looking as though they belong to whatever came
    before them, which matters on a tab holding two axes.

    Args:
        parent: The frame the block is added to.
        text: Caption shown on the block's border.

    Returns:
        The packed block, ready for its rows to be added.

    """
    box = ttk.Labelframe(parent, text=text, padding=6)
    box.pack(fill=tk.X, pady=(10, 0))
    return box


def _entry(
    parent: tk.Widget,
    variable: tk.StringVar,
    handler: Handler,
) -> ttk.Entry:
    """Create a free text entry, bound to the events an entry actually sends.

    An entry has no selection event, so it reports when the value is committed instead, which
    is the return key and losing focus. The two are bound here so a value is applied however
    the user finishes typing it.

    Args:
        parent: The frame the entry is added to.
        variable: Variable the entry writes to.
        handler: Called whenever the entry changes, or ``None``.

    Returns:
        The entry, packed ready to use.

    """
    entry = ttk.Entry(parent, textvariable=variable, width=8)
    entry.pack(fill=tk.X)
    entry.bind('<Return>', handler)
    entry.bind('<FocusOut>', handler)
    return entry


def _dropdown(
    parent: tk.Widget,
    variable: tk.StringVar,
    values: tuple[str, ...],
    handler: Handler,
) -> ttk.Combobox:
    """Create a readonly dropdown, bound to the event a dropdown actually sends.

    Args:
        parent: The frame the dropdown is added to.
        variable: Variable the dropdown writes to.
        values: The choices offered.
        handler: Called when a choice is made, or ``None``.

    Returns:
        The dropdown, packed ready to use.

    """
    combo = ttk.Combobox(parent, textvariable=variable, values=values, state='readonly', width=12)
    combo.pack(fill=tk.X)
    combo.bind('<<ComboboxSelected>>', handler)
    return combo


def _cell(
    parent: tk.Widget,
    label: str,
    variable: tk.StringVar,
    values: tuple[str, ...],
    handler: Handler,
) -> Control:
    """Create a caption above one control, choosing the control the choices ask for.

    Empty choices mean a free text entry rather than a dropdown, which is what lets a number
    sit in the same shape of cell as a choice.

    Args:
        parent: The frame the cell is added to.
        label: Caption shown above the control.
        variable: Variable the control writes to.
        values: The choices offered, or empty for a free text entry.
        handler: Called whenever the control changes, or ``None``.

    Returns:
        The control, so a caller can grey it out when the choice does not apply.

    """
    ttk.Label(parent, text=label, font=LABEL_FONT).pack(anchor=tk.W)
    if values:
        return _dropdown(parent, variable, values, handler)
    return _entry(parent, variable, handler)


def _paired_cells(
    parent: tk.Widget,
    left: OptionSpec,
    right: OptionSpec,
) -> tuple[Control | None, Control | None]:
    """Build one row holding up to two captioned controls side by side.

    The two halves are given the room evenly, so a long caption on one side cannot squeeze
    the other. A ``None`` variable leaves its slot empty, which is how a row with only one
    control on it is written.

    Args:
        parent: The frame the row is added to.
        left: Label, variable, values and handler for the left cell, or an empty slot.
        right: The same tuple for the right cell.

    Returns:
        The left and right controls in the order they were given, or ``None`` for an empty
        slot.

    """
    row = ttk.Frame(parent)
    row.pack(fill=tk.X, pady=(10, 0))
    built: list[Control | None] = []
    for column, (label, variable, values, handler) in enumerate((left, right)):
        if variable is None:
            built.append(None)
            continue
        cell = ttk.Frame(row)
        cell.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6) if column == 0 else 0)
        built.append(_cell(cell, label or '', variable, values, handler))
    return built[0], built[1]


def dropdown_row(
    parent: tk.Widget,
    label: str,
    variable: tk.StringVar,
    values: tuple[str, ...],
    handler: Handler,
) -> ttk.Combobox:
    """Place a caption and a full width dropdown on a line of their own.

    :func:`option_row` puts two controls side by side, which is not what a lone choice
    needs, and it does not hand the control back. This does both, so a caller can grey the
    dropdown out when the choice does not apply to the graph being drawn.

    Args:
        parent: The frame the row is added to.
        label: Caption shown above the dropdown.
        variable: Variable backing the dropdown.
        values: The choices offered.
        handler: Called when a choice is made, or ``None`` for a placeholder.

    Returns:
        The dropdown, so a caller can change its state.

    """
    ttk.Label(parent, text=label, font=LABEL_FONT).pack(anchor=tk.W, pady=(10, 0))
    return _dropdown(parent, variable, values, handler)


def pair_row(
    parent: tk.Widget, left: ControlSpec, right: ControlSpec
) -> tuple[Control, Control]:
    """Place two label and control pairs side by side, to save vertical space.

    Unlike :func:`option_row`, either half may be a free text entry rather than a dropdown,
    which is what lets a font and its size, or a maximum and its step, share one line.

    The controls are returned so a caller can grey one out, which is how a field that does
    not apply to the graph being drawn is shown as unavailable rather than hidden.

    Args:
        parent: The frame the row is added to.
        left: Caption, variable, choices and handler for the left pair. Empty choices make it
            a text entry.
        right: The same tuple for the right pair.

    Returns:
        The left and right controls, in the order they were given.

    """
    built = _paired_cells(parent, left, right)
    return cast('Control', built[0]), cast('Control', built[1])


def option_row(parent: tk.Widget, left: OptionSpec, right: OptionSpec) -> None:
    """Place two label and control pairs side by side to save vertical space.

    Both halves are dropdowns, and either slot may be left empty.

    Args:
        parent: The frame the row is added to.
        left: Label, variable, values and handler for the left cell, or an empty slot.
        right: The same tuple for the right cell.

    """
    _paired_cells(parent, left, right)


def number_row(
    parent: tk.Widget,
    label: str,
    variable: tk.StringVar,
    handler: Callable[[tk.Event[tk.Misc] | None], None],
) -> None:
    """Place a label and a text entry side by side, used for the numeric settings.

    The caption sits beside the entry rather than above it, because a number is short enough
    to share a line with its own name.

    Args:
        parent: The frame the row is added to.
        label: Text shown next to the entry.
        variable: Variable backing the entry.
        handler: Called with the entry contents whenever it changes.

    """
    row = ttk.Frame(parent)
    row.pack(fill=tk.X, pady=(6, 0))
    ttk.Label(row, text=label, font=LABEL_FONT, width=16).pack(side=tk.LEFT)
    entry = ttk.Entry(row, textvariable=variable, width=8)
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    entry.bind('<Return>', handler)
    entry.bind('<FocusOut>', handler)
