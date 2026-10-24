"""A spreadsheet style preview of the imported worksheet, shown under the graph.

The pane is deliberately a plain grid of the raw cells rather than a table of parsed
samples, because the whole point is to let the user see the sheet itself and click a
column heading to leave that column out of the graph. A Treeview is not used because it
cannot hold a per column highlight down a whole column of rows without rebuilding every
row, and rebuilding on each click is what makes a large sheet feel slow.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable, Sequence
from enum import StrEnum
from statistics import fmean, median, stdev
from tkinter import ttk
from typing import Literal

import pandas as pd

from src.excel_reader import cell_number, cell_text
from src.models import DEFAULT_DECIMALS

# Which kind of sheet is shown. The mode also decides which summary rows are useful.
SheetMode = Literal['columns', 'x_and_y']


class Role(StrEnum):
    """What a chosen part of the sheet is used for.

    A row or a column carries one role at a time, which is why the roles are exclusive: the
    same cells cannot be both the group names and the sample names.
    """

    GROUP = 'Group'
    CONDITIONS = 'Conditions'
    Y_VALUES = 'Y values'


CELL_WIDTH = 92
CELL_HEIGHT = 20
# Width of the strip down the left edge, and of the row number at the head of it. The
# strip carries the description that used to be a column of its own, so it has to be wide
# enough for a row label such as ``Conc.1, ng/uL`` to be read without being cut short. The
# row number stays because the scatter controls address rows by number, and the caption
# names them the same way.
ROW_HEADER_WIDTH = 150
ROW_NUMBER_WIDTH = 26
COLUMN_HEADER_HEIGHT = 22
# Enough rows to recognise the shape of a sheet. A worksheet can hold tens of thousands of
# rows and drawing them all would make every scroll stutter, so the preview shows the top
# of the sheet and says how much more there is.
MAX_PREVIEW_ROWS = 200
# Longest description shown in the index strip. The strip is narrower than a full cell, so
# row labels are cut a little earlier than cell values are.
INDEX_TEXT_LIMIT = 20

# Colours of the grid, kept close to the Windows theme so the pane matches the rest of
# the window rather than inventing a shade of its own.
GRID_FACE = '#ffffff'
GRID_LINE = '#d0d0d0'
HEADER_FACE = '#f0f0f0'
HEADER_SELECTED_FACE = '#cfe2ff'
HEADER_SELECTED_LINE = '#7aa7e8'
ROW_SELECTED_FACE = '#ffe9b3'
ROW_SELECTED_LINE = '#d9ad3c'
HEADER_TEXT = '#202020'
HEADER_SELECTED_TEXT = '#10305c'
CELL_TEXT = '#303030'
# The worksheet column holding the row descriptions, shown down the left index rather than
# as a column of the grid, so that every numbered column of the grid is a measurement. It
# is still position 0 of the table, so every index elsewhere stays as it was.
LABEL_COLUMN = 0
# Held as module constants because the canvas stubs type a font as a tuple, and a tuple
# built inline infers as a fixed length that the overload does not accept.
CELL_FONT: tuple[str, int] = ('Segoe UI', 8)
HEADER_FONT: tuple[str, int, str] = ('Segoe UI', 8, 'bold')


def _rounded(value: object, decimals: int | None) -> str | None:
    """Return a number as fixed width text, or ``None`` when it is not a number.

    The trailing zeros are kept on purpose. A column read at two decimal places shows the
    same width for every row, so the digits line up down the pane and a value that happens
    to be a whole number is visibly a rounded one rather than a shorter entry.

    A number typed into the sheet as text is rounded as well, because the reader already
    reads it as that number and the graph is already drawn from it. Leaving it at the
    sheet's own precision would show one value in a column behind the others, which reads
    as a fault in the preview rather than as the typing it really was.

    A number too small for the chosen precision has nothing to show, and a value that
    rounds to zero from below would otherwise print as ``-0.00``, which reads as a fault in
    the sheet rather than as a rounded number.

    Args:
        value: Raw cell value taken from the worksheet.
        decimals: Decimal places to show, or ``None`` to leave the value alone.

    Returns:
        The formatted number, or ``None`` when the cell is not numeric or is blank.

    """
    if decimals is None:
        return None
    number = cell_number(value)
    if number is None or math.isnan(number) or math.isinf(number):
        return None
    text = f'{number:.{decimals}f}'
    return text[1:] if text.startswith('-') and float(text) == 0.0 else text


def _short(value: object, limit: int = 14, decimals: int | None = DEFAULT_DECIMALS) -> str:
    """Return the text of a cell, shortened to fit the grid without wrapping.

    Args:
        value: Raw cell value taken from the worksheet.
        limit: Longest string to show before it is cut short.
        decimals: Decimal places a number is rounded to, or ``None`` to show it exactly.

    Returns:
        The cell as text, with an ellipsis when it had to be shortened.

    """
    text = _rounded(value, decimals)
    if text is None:
        text = cell_text(value)
    return text if len(text) <= limit else f'{text[: limit - 1]}…'



class SheetView(ttk.Frame):
    """The imported worksheet drawn as a clickable grid, used to choose what is plotted.

    The grid is drawn on one canvas rather than built from widgets, so a sheet of a few
    thousand cells costs a few thousand canvas items instead of a few thousand widgets. A
    widget per cell would take seconds to create, and every change of highlight would mean
    rebuilding all of them.

    Clicking a column heading toggles that column in and out of the graph. Role state is
    supplied by worksheet detection or the chart fields rather than assigned in the preview.

    Attributes:
        canvas: The canvas the grid is drawn on.
        table: The worksheet being previewed, or ``None`` when no file is loaded.
        columns: Worksheet columns currently included in the graph, zero based and counting
            the label column.
        x_row: Worksheet row holding the scatter x values, or ``None`` when unset.

    """

    def __init__(
        self,
        master: tk.Misc,
        on_change: Callable[[], None] | None = None,
        on_cell_edit: Callable[[int, int, str], None] | None = None,
    ) -> None:
        """Build the empty grid.

        Args:
            master: The widget the pane is packed into.
            on_change: Called whenever the user picks different columns or a different x
                row, so the window can re-read the sheet and redraw the graph.
            on_cell_edit: Called with the worksheet row, column, and new text when a name
                cell is committed.

        """
        super().__init__(master)
        self._on_change = on_change
        self._on_cell_edit = on_cell_edit
        self.table: pd.DataFrame | None = None
        self.columns: tuple[int, ...] = ()
        self.x_row: int | None = None
        self._mode: SheetMode = 'columns'
        self._syncing = False
        self._decimals: int | None = DEFAULT_DECIMALS
        # Roles inferred from the sheet, as zero based positions. The group, conditions and
        # x roles each hold one cell, while the y role holds every measured column.
        self.assignment: dict[Role, tuple[int, ...]] = {}

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=GRID_FACE)
        self._vertical = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self._horizontal = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self._on_x_scroll, yscrollcommand=self._on_y_scroll)
        # The grid is laid out with grid rather than pack, because the scrollbars have to
        # sit in the corner the cells do not reach. A packed canvas expands underneath
        # them, and being drawn last they would cover the last row and column.
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self._vertical.grid(row=0, column=1, sticky='ns')
        self._horizontal.grid(row=1, column=0, sticky='ew')
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.canvas.bind('<Configure>', lambda _e: self._draw())
        self.canvas.bind('<Button-1>', self._on_click)
        self.canvas.bind('<Double-Button-1>', self._on_double_click)
        self.canvas.bind('<Motion>', self._on_motion)

        self._active_editor: tk.Entry | None = None
        self._edit_row: int | None = None
        self._edit_col: int | None = None
        self._original_value: str = ""
        self._canvas_edit_binding: str | None = None
        self._draw()

    def set_table(self, table: pd.DataFrame | None) -> None:
        """Show a worksheet, or clear the grid when there is none.

        Args:
            table: The trimmed worksheet table, or ``None`` when no file is loaded.

        """
        if self._active_editor is not None:
            self._cleanup_editor()
        self.table = table
        self._draw()

    def set_mode(self, mode: SheetMode) -> None:
        """Say what a click in the grid means for the graph being drawn.

        Args:
            mode: ``'columns'`` for a bar graph, or ``'x_and_y'`` for a scatter plot.

        """
        self._mode = mode
        self._draw()

    def set_selection(self, columns: Sequence[int], x_row: int | None) -> None:
        """Show a selection without reporting it as a user change.

        The window sets the selection whenever it re-reads the sheet, and a read that
        dropped a column has to be reflected here without that being mistaken for a click
        and triggering another read.

        Args:
            columns: Worksheet columns included in the graph, zero based.
            x_row: Worksheet row holding the x values, or ``None``.

        """
        self._syncing = True
        try:
            self.columns = tuple(sorted(set(columns)))
            self.x_row = x_row
        finally:
            self._syncing = False
        self._draw()

    def set_decimals(self, decimals: int | None) -> None:
        """Round the values the grid shows, or show them exactly when given ``None``.

        The rounding is a reading convenience and stops here: the sheet, the samples and
        the graph keep the values the reader gave them, so nothing downstream can be
        changed by what the preview happens to print.

        Args:
            decimals: Decimal places to show, or ``None`` to show the sheet as it is.

        """
        if decimals == self._decimals:
            return
        self._decimals = decimals
        self._draw()

    def measured_columns(self) -> tuple[int, ...]:
        """Return the worksheet columns that hold measurements, zero based.

        The first column holds the row descriptions, which are drawn down the left index
        instead of the grid, so it is never offered as something to plot.

        Returns:
            One index per measured column, empty when no file is loaded.

        """
        return () if self.table is None else tuple(range(LABEL_COLUMN + 1, self.table.shape[1]))

    def select_all_columns(self) -> None:
        """Show every measured column as included in the graph.

        This only updates the preview. Re-reading the sheet is left to the caller, because
        most callers are showing a selection the window has just applied, and re-reading on
        top of that would report a change the user never made.

        """
        if self.table is not None:
            self.set_selection(self.measured_columns(), None)

    # -- drawing ---------------------------------------------------------------------

    def _draw(self) -> None:
        """Paint the grid from the current table and selection."""
        self.canvas.delete('all')
        if self.table is None or self.table.empty:
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        rows = min(len(self.table.index), MAX_PREVIEW_ROWS)
        columns = self.table.shape[1]
        for row in range(rows):
            self._draw_row(row, columns)
        self._draw_headers(rows, columns)
        summary_rows = self._summary_rows()
        display_rows: tuple[tuple[str, tuple[str, ...]], ...] = ()
        if summary_rows:
            self._draw_empty_row(rows, columns)
            display_rows = (
                ('Min', tuple(self._format_summary_value(value) for value in summary_rows['Min'])),
                (
                    'Mean/Median',
                    tuple(
                        f'{self._format_summary_value(mean)} / {self._format_summary_value(median_value)}'
                        if mean is not None and median_value is not None
                        else ''
                        for mean, median_value in zip(summary_rows['Mean'], summary_rows['Median'], strict=True)
                    ),
                ),
                ('Max', tuple(self._format_summary_value(value) for value in summary_rows['Max'])),
                ('SD', tuple(self._format_summary_value(value) for value in summary_rows['SD'])),
                (
                    '%CV',
                    tuple(
                        f'{self._format_summary_value(value)}%'
                        if value is not None
                        else ''
                        for value in summary_rows['%CV']
                    ),
                ),
            )
            for offset, (label, values) in enumerate(display_rows):
                self._draw_summary_row(rows + offset + 1, label, values)
        drawn = max(columns - LABEL_COLUMN - 1, 0)
        self.canvas.configure(
            scrollregion=(
                0,
                0,
                ROW_HEADER_WIDTH + drawn * CELL_WIDTH,
                COLUMN_HEADER_HEIGHT + (rows + len(display_rows) + bool(display_rows)) * CELL_HEIGHT,
            )
        )

    def _summary_rows(self) -> dict[str, tuple[float | None, ...]]:
        """Calculate normal-table summaries from every numeric value in each column."""
        if self.table is None or self._mode != 'columns':
            return {}
        columns = [
            [
                number
                for value in self.table.iloc[:, column]
                if (number := cell_number(value)) is not None and math.isfinite(number)
            ]
            for column in self.measured_columns()
        ]
        return {
            'Min': tuple(min(values) if values else None for values in columns),
            'Mean': tuple(fmean(values) if values else None for values in columns),
            'Median': tuple(median(values) if values else None for values in columns),
            'Max': tuple(max(values) if values else None for values in columns),
            'SD': tuple(stdev(values) if len(values) > 1 else 0.0 if values else None for values in columns),
            '%CV': tuple(
                stdev(values) / abs(fmean(values)) * 100.0
                if len(values) > 1 and fmean(values) != 0.0
                else 0.0
                if len(values) == 1
                else None
                for values in columns
            ),
        }

    def _format_summary_value(self, value: float | None) -> str:
        """Format a numeric statistic using the preview's current decimal setting."""
        return '' if value is None else _short(value, decimals=self._decimals)

    def _draw_empty_row(self, row: int, columns: int) -> None:
        """Draw a blank grid row between the source values and their summaries."""
        top = COLUMN_HEADER_HEIGHT + row * CELL_HEIGHT
        self.canvas.create_rectangle(0, top, ROW_NUMBER_WIDTH, top + CELL_HEIGHT, fill=HEADER_FACE, outline=GRID_LINE)
        self.canvas.create_rectangle(
            ROW_NUMBER_WIDTH,
            top,
            ROW_HEADER_WIDTH,
            top + CELL_HEIGHT,
            fill=GRID_FACE,
            outline=GRID_LINE,
        )
        for column in range(LABEL_COLUMN + 1, columns):
            left = ROW_HEADER_WIDTH + (column - LABEL_COLUMN - 1) * CELL_WIDTH
            self.canvas.create_rectangle(
                left,
                top,
                left + CELL_WIDTH,
                top + CELL_HEIGHT,
                fill=GRID_FACE,
                outline=GRID_LINE,
            )

    def _draw_summary_row(self, row: int, label: str, values: tuple[str, ...]) -> None:
        """Draw one summary label and its per-column values beneath the worksheet preview."""
        top = COLUMN_HEADER_HEIGHT + row * CELL_HEIGHT
        self.canvas.create_rectangle(0, top, ROW_NUMBER_WIDTH, top + CELL_HEIGHT, fill=HEADER_FACE, outline=GRID_LINE)
        self.canvas.create_rectangle(
            ROW_NUMBER_WIDTH,
            top,
            ROW_HEADER_WIDTH,
            top + CELL_HEIGHT,
            fill=HEADER_FACE,
            outline=GRID_LINE,
        )
        self.canvas.create_text(
            ROW_NUMBER_WIDTH + 4.0,
            top + CELL_HEIGHT / 2,
            anchor=tk.W,
            text=label,
            fill=HEADER_TEXT,
            font=CELL_FONT,
        )
        for index, value in enumerate(values):
            left = ROW_HEADER_WIDTH + index * CELL_WIDTH
            self.canvas.create_rectangle(
                left,
                top,
                left + CELL_WIDTH,
                top + CELL_HEIGHT,
                fill=GRID_FACE,
                outline=GRID_LINE,
            )
            self.canvas.create_text(
                left + 4.0,
                top + CELL_HEIGHT / 2,
                anchor=tk.W,
                text=value,
                fill=CELL_TEXT,
                font=CELL_FONT,
            )

    def _draw_row(self, row: int, columns: int) -> None:
        """Draw the index strip and the data cells of one row.

        The description of the row is drawn in the strip, so the cells themselves are only
        ever measurements and every column of the grid is numbered as one.

        Args:
            row: Zero based worksheet row to draw.
            columns: How many columns the worksheet holds, counting the label column.

        """
        table = self.table
        if table is None:
            return
        top = COLUMN_HEADER_HEIGHT + row * CELL_HEIGHT
        is_x = self._mode == 'x_and_y' and self.x_row == row
        face = ROW_SELECTED_FACE if is_x else GRID_FACE
        for column in range(LABEL_COLUMN + 1, columns):
            left = ROW_HEADER_WIDTH + (column - LABEL_COLUMN - 1) * CELL_WIDTH
            self.canvas.create_rectangle(left, top, left + CELL_WIDTH, top + CELL_HEIGHT, fill=face, outline=GRID_LINE)
            self.canvas.create_text(
                left + 4.0,
                top + CELL_HEIGHT / 2,
                anchor=tk.W,
                text=_short(table.iat[row, column], decimals=self._decimals),
                fill=CELL_TEXT,
                font=CELL_FONT,
            )

    def _draw_headers(self, rows: int, columns: int) -> None:
        """Draw the column headings and the row numbers, highlighting the chosen ones.

        The column headings carry the one based number the rest of the window uses and the
        row numbers match the sheet's own numbering, so what is clicked here and what is
        typed into the scatter fields always mean the same cell. The label column carries
        no heading because it is not a column of the grid: it is drawn down the left strip,
        so the first heading is column 1 and every heading names a measurement.

        Args:
            rows: How many rows are being drawn.
            columns: How many columns the worksheet holds, counting the label column.

        """
        chosen = set(self.columns)
        for column in range(LABEL_COLUMN + 1, columns):
            left = ROW_HEADER_WIDTH + (column - LABEL_COLUMN - 1) * CELL_WIDTH
            if column in chosen:
                face, text_color, outline = HEADER_SELECTED_FACE, HEADER_SELECTED_TEXT, HEADER_SELECTED_LINE
            else:
                face, text_color, outline = HEADER_FACE, HEADER_TEXT, GRID_LINE
            self.canvas.create_rectangle(left, 0, left + CELL_WIDTH, COLUMN_HEADER_HEIGHT, fill=face, outline=outline)
            self.canvas.create_text(
                left + CELL_WIDTH / 2,
                COLUMN_HEADER_HEIGHT / 2,
                text=str(column),
                fill=text_color,
                font=HEADER_FONT,
            )

        table = self.table
        for row in range(rows):
            top = COLUMN_HEADER_HEIGHT + row * CELL_HEIGHT
            picked = self._mode == 'x_and_y' and self.x_row == row
            face = ROW_SELECTED_FACE if picked else HEADER_FACE
            outline = ROW_SELECTED_LINE if picked else GRID_LINE
            # The strip is drawn in two parts. The number comes first and stays a fixed
            # width so that the descriptions line up down the column, which is what makes
            # the sheet readable at a glance rather than a ragged list of words.
            self.canvas.create_rectangle(
                0,
                top,
                ROW_NUMBER_WIDTH,
                top + CELL_HEIGHT,
                fill=face,
                outline=outline,
            )
            self.canvas.create_text(
                ROW_NUMBER_WIDTH / 2,
                top + CELL_HEIGHT / 2,
                text=str(row + 1),
                fill=HEADER_SELECTED_TEXT if picked else HEADER_TEXT,
                font=HEADER_FONT,
            )
            self.canvas.create_rectangle(
                ROW_NUMBER_WIDTH,
                top,
                ROW_HEADER_WIDTH,
                top + CELL_HEIGHT,
                fill=face,
                outline=outline,
            )
            if table is not None:
                self.canvas.create_text(
                    ROW_NUMBER_WIDTH + 4.0,
                    top + CELL_HEIGHT / 2,
                    anchor=tk.W,
                    text=_short(table.iat[row, LABEL_COLUMN], INDEX_TEXT_LIMIT, self._decimals),
                    fill=HEADER_SELECTED_TEXT if picked else HEADER_TEXT,
                    font=CELL_FONT,
                )

        # The corner closes off the two header strips. It is drawn last so it sits over
        # both of them, which is what makes the grid read as one table. It carries no
        # caption because the strip below it is the row index rather than a chosen column.
        self.canvas.create_rectangle(0, 0, ROW_HEADER_WIDTH, COLUMN_HEADER_HEIGHT, fill=HEADER_FACE, outline=GRID_LINE)

    # -- interaction -----------------------------------------------------------------

    def _on_click(self, event: tk.Event[tk.Misc]) -> None:
        """Toggle a measurement column when its heading is clicked.

        The click is translated back into a cell through the canvas scroll offset, so a
        click on a heading still picks the column under the pointer once the grid has been
        scrolled sideways.

        Args:
            event: The mouse click, with coordinates relative to the canvas.

        """
        if self.table is None:
            return
        left = self.canvas.canvasx(event.x)
        top = self.canvas.canvasy(event.y)
        if top < COLUMN_HEADER_HEIGHT:
            # The first heading is column 1, because the label column is drawn in the
            # index strip rather than as a heading of its own.
            column = LABEL_COLUMN + 1 + int((left - ROW_HEADER_WIDTH) // CELL_WIDTH)
            if left >= ROW_HEADER_WIDTH and LABEL_COLUMN < column < self.table.shape[1]:
                self.toggle_column(column)
            return
    def _on_motion(self, event: tk.Event[tk.Misc]) -> None:
        """Change cursor to indicate editable cells on hover."""
        if self.table is None or self._active_editor is not None:
            return
        left = self.canvas.canvasx(event.x)
        top = self.canvas.canvasy(event.y)
        if top >= COLUMN_HEADER_HEIGHT and left >= ROW_HEADER_WIDTH:
            row = int((top - COLUMN_HEADER_HEIGHT) // CELL_HEIGHT)
            col = LABEL_COLUMN + 1 + int((left - ROW_HEADER_WIDTH) // CELL_WIDTH)
            if self._is_editable_cell(row, col):
                self.canvas.config(cursor='ibeam')
                return
        self.canvas.config(cursor='')

    def _on_double_click(self, event: tk.Event[tk.Misc]) -> None:
        """Start inline editing if the clicked cell has an editable role."""
        if self.table is None or self._active_editor is not None:
            return
        left = self.canvas.canvasx(event.x)
        top = self.canvas.canvasy(event.y)
        if top < COLUMN_HEADER_HEIGHT or left < ROW_HEADER_WIDTH:
            return
        row = int((top - COLUMN_HEADER_HEIGHT) // CELL_HEIGHT)
        col = LABEL_COLUMN + 1 + int((left - ROW_HEADER_WIDTH) // CELL_WIDTH)
        if (
            0 <= row < min(len(self.table.index), MAX_PREVIEW_ROWS)
            and col < self.table.shape[1]
            and self._is_editable_cell(row, col)
        ):
            self._start_edit(row, col)

    def _is_editable_cell(self, row: int, col: int) -> bool:
        """Return True if the cell at (row, col) has an editable role (GROUP or CONDITIONS)."""
        if (
            self.table is None
            or not 0 <= row < min(len(self.table.index), MAX_PREVIEW_ROWS)
            or not LABEL_COLUMN < col < self.table.shape[1]
        ):
            return False
        for role in (Role.GROUP, Role.CONDITIONS):
            assigned = self.assignment.get(role)
            if assigned and row == assigned[0]:
                return True
        return False

    def _start_edit(self, row: int, col: int) -> None:
        """Overlay an Entry widget on the specified cell for inline editing."""
        if self.table is None or not self._is_editable_cell(row, col):
            return

        original_value = cell_text(self.table.iat[row, col])
        text = original_value
        if self.assignment.get(Role.GROUP) == (row,):
            text = next(
                (
                    cell_text(self.table.iat[row, index])
                    for index in range(col, LABEL_COLUMN, -1)
                    if cell_text(self.table.iat[row, index])
                ),
                '',
            )
        self._original_value = original_value

        x: float = ROW_HEADER_WIDTH + (col - LABEL_COLUMN - 1) * CELL_WIDTH
        y: float = COLUMN_HEADER_HEIGHT + row * CELL_HEIGHT
        x -= self.canvas.canvasx(0)
        y -= self.canvas.canvasy(0)

        editor = tk.Entry(self.canvas, borderwidth=1, highlightthickness=1, relief='solid')
        editor.insert(0, text)
        editor.select_range(0, tk.END)
        editor.place(x=x, y=y, width=CELL_WIDTH, height=CELL_HEIGHT)
        editor.bind('<Return>', self._commit_edit)
        editor.bind('<KP_Enter>', self._commit_edit)
        editor.bind('<Escape>', self._cancel_edit)
        editor.bind('<FocusOut>', self._commit_edit)
        self._active_editor = editor
        self._edit_row = row
        self._edit_col = col
        self._canvas_edit_binding = self.canvas.bind('<Button-1>', self._commit_edit, add='+')
        editor.focus_set()

    def _commit_edit(self, event: object = None) -> str | None:
        """Commit the editor text and notify the owner when it changed."""
        if self._active_editor is None or self.table is None:
            return 'break' if event is not None else None
        if self._edit_row is None or self._edit_col is None:
            return 'break' if event is not None else None

        new_text = self._active_editor.get()
        row, column = self._edit_row, self._edit_col
        changed = new_text != self._original_value
        self._cleanup_editor()
        if changed:
            if self._on_cell_edit is not None:
                self._on_cell_edit(row, column, new_text)
            else:
                self.table.iat[row, column] = new_text
                self._draw()
        return 'break' if event is not None else None

    def _cancel_edit(self, event: object = None) -> str | None:
        """Discard changes and remove editor."""
        self._cleanup_editor()
        self._draw()
        return 'break' if event is not None else None

    def _cleanup_editor(self) -> None:
        """Destroy the active editor and reset state."""
        if self._active_editor is not None:
            self._active_editor.unbind('<Return>')
            self._active_editor.unbind('<KP_Enter>')
            self._active_editor.unbind('<Escape>')
            self._active_editor.unbind('<FocusOut>')
            self._active_editor.destroy()
            self._active_editor = None
        if self._canvas_edit_binding is not None:
            self.canvas.unbind('<Button-1>', self._canvas_edit_binding)
            self._canvas_edit_binding = None
        self._edit_row = None
        self._edit_col = None
        self._original_value = ""

    def toggle_column(self, column: int) -> None:
        """Add or remove one column from the graph, and tell the window to re-read.

        Clicking a column heading is the whole gesture, so the change is reported straight
        away. That is what lets a single column be left out of a graph instead of having to
        name every column that stayed.

        The label column is never a measurement, so it is refused rather than offered and
        then dropped. The last remaining column is also refused: a graph with nothing to
        draw is not a state the user can recover from by clicking, because there would be
        no column left to click back on.

        Args:
            column: Zero based worksheet column to add or remove.

        """
        if self.table is None or column == LABEL_COLUMN or column not in self.measured_columns():
            return
        chosen = set(self.columns)
        if column in chosen:
            if len(chosen) == 1:
                return
            chosen.discard(column)
        else:
            chosen.add(column)
        self.columns = tuple(sorted(chosen))
        self._draw()
        self._report()

    def set_assignment(self, assignment: dict[Role, tuple[int, ...]]) -> None:
        """Show an assignment made elsewhere without reporting it as a user change.

        Args:
            assignment: Role to the rows or columns carrying it.

        """
        self._syncing = True
        try:
            self.assignment = dict(assignment)
        finally:
            self._syncing = False
        self._draw()

    def role_row(self, role: Role) -> int | None:
        """Return the single row carrying a role, or ``None`` when it holds none.

        Args:
            role: The role to look up.

        Returns:
            Zero based row index, or ``None``.

        """
        held = self.assignment.get(role)
        return held[0] if held else None

    def _report(self) -> None:
        """Tell the window the selection changed, unless it was the window that changed it."""
        if not self._syncing and self._on_change is not None:
            self._on_change()

    def _on_x_scroll(self, first: float, last: float) -> None:
        """Follow the horizontal scrollbar.

        Args:
            first: Fraction of the grid shown at its left edge.
            last: Fraction of the grid shown at its right edge.

        """
        self._horizontal.set(first, last)

    def _on_y_scroll(self, first: float, last: float) -> None:
        """Follow the vertical scrollbar.

        Args:
            first: Fraction of the grid shown at its top edge.
            last: Fraction of the grid shown at its bottom edge.

        """
        self._vertical.set(first, last)
