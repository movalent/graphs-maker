"""The list of samples, what is highlighted in it, and the style block that follows it.

The list is the control everything else acts on: grouping, colouring and per sample styling
all apply to whatever is highlighted here. It sits above the scrolling options and is kept
out of the scrollable area so it cannot slide out of view while a tall tab is being read.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk

from src.app_state import FALLBACK_COLOR, HATCH_LABELS, HATCH_PATTERNS, normalize_hex
from src.models import POINT_LABELS
from src.ui.base import _AppBase

# Height reserved for the sticky sample block: the caption, a scrollable set of rows and
# the arrow buttons. The list itself scrolls inside it, so the block never changes size.
LIST_BLOCK_HEIGHT = 190
LIST_ROWS = 7


class SampleListMixin(_AppBase):
    """The samples as a list, the selection in it, and the style of what is selected."""

    def _build_sample_list(self, panel: ttk.Frame) -> None:
        """Create the sample list, which stays put while the options below it scroll.

        The list is built outside the scrollable area on purpose. Grouping and styling act
        on the highlighted samples, so the list is the control that matters most and it must
        not slide out of view when a tall options panel is being scrolled.

        Args:
            panel: The control panel the list is added to.

        """
        holder = ttk.Frame(panel)
        holder.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(holder, text='Samples (Ctrl/Shift to pick several)', font=('Segoe UI', 9, 'bold')).pack(
            anchor=tk.W
        )
        row = ttk.Frame(holder)
        row.pack(fill=tk.X)
        # The list block is given a fixed height so it cannot grow past the panel and
        # paint over the controls below it. The list scrolls inside it, so the block
        # never changes size however many samples there are.
        row.pack_propagate(False)
        row.configure(height=LIST_BLOCK_HEIGHT)
        # The list takes only the height it needs. An expanding list in a panel that has a
        # fixed width and a hard bottom edge grows past what is left over once the tabs are
        # added, and then covers the controls underneath it.

        # A Treeview gives two real, independently left aligned columns, where a Listbox
        # can only hold one padded string per row. It also handles Ctrl and Shift selection
        # itself. Dragging is deliberately not bound: a press that also had to start a drag
        # could never leave the multi-selection alone, so reordering stays on the arrows.
        self.listbox = ttk.Treeview(
            row,
            columns=('sample', 'group'),
            show='headings',
            selectmode='extended',
            height=LIST_ROWS,
        )
        self.listbox.heading('sample', text='Sample', anchor=tk.W)
        self.listbox.heading('group', text='Group', anchor=tk.W)
        self.listbox.column('sample', width=100, minwidth=60, anchor=tk.W, stretch=False)
        self.listbox.column('group', width=110, minwidth=70, anchor=tk.W, stretch=True)
        # The list fills what is left over rather than expanding, so the scrollbar and the
        # buttons beside it are given their width first. Expanding the list squeezed that
        # column down to a few pixels and the buttons disappeared.
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH)
        list_scroll = ttk.Scrollbar(row, orient=tk.VERTICAL, command=self.listbox.yview)
        list_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=list_scroll.set)
        self.listbox.bind('<<TreeviewSelect>>', self._on_row_selected)
        self._refresh_list()
        buttons = ttk.Frame(row)
        buttons.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Button(buttons, text='▲', width=3, command=lambda: self._move_selected(-1)).pack(pady=1)
        ttk.Button(buttons, text='▼', width=3, command=lambda: self._move_selected(1)).pack(pady=1)
    def _row_id(self, index: int) -> str:
        """Return the Treeview item id used for the row at ``index``.

        Rows are addressed by their position rather than by name, so a sample name that
        repeats, or that contains a space, can never be confused for another row.

        Args:
            index: Row position in the list.

        Returns:
            The item id for that row.

        """
        return f'row{index}'
    def _row_index(self, item: str) -> int:
        """Return the row position of a Treeview item id.

        Args:
            item: Item id as returned by the Treeview selection.

        Returns:
            The row position, or ``-1`` when the id is not a row of this list.

        """
        return int(item[3:]) if item.startswith('row') and item[3:].isdigit() else -1
    def _selected_indices(self) -> tuple[int, ...]:
        """Return the positions of every highlighted row, in list order."""
        return tuple(
            sorted(index for index in (self._row_index(item) for item in self.listbox.selection()) if index >= 0)
        )
    def _refresh_list(self) -> None:
        """Rebuild the sample list, giving each name the colour it is drawn with.

        The selection is restored by row position, so a change that only affects the group
        column, such as a merge, leaves the user's highlight exactly where it was.
        """
        selected = self._selected_indices()
        children = self.listbox.get_children()
        for child in children:
            self.listbox.delete(child)
        for index, name in enumerate(self.state.entry_order):
            # A Treeview cannot colour one row directly, so each colour becomes a named tag.
            # The tag name is the hex colour, which keeps one tag per sample colour and no
            # lookup table to keep in step.
            color = self.state.color_of(name)
            self.listbox.tag_configure(color, foreground=color)
            self.listbox.insert(
                '',
                tk.END,
                iid=self._row_id(index),
                values=(name, self.state.group_of(name)),
                tags=(color,),
            )
        self._apply_indices(selected)
    def _apply_indices(self, indices: Sequence[int]) -> None:
        """Highlight the given rows, ignoring any that no longer exist.

        Args:
            indices: Row positions to highlight.

        """
        self.listbox.selection_set([self._row_id(index) for index in indices if index < len(self.state.entry_order)])
    def _select_row(self, index: int) -> None:
        """Highlight one row, scroll it into view, and show its colour in the hex field.

        The panels are updated here rather than only in the selection handler, because
        ``<<TreeviewSelect>>`` is a virtual event that only arrives from real user clicks.
        Code that changes the selection, such as moving a row or clicking a bar, would
        otherwise leave the fields showing the previous sample.

        Args:
            index: Row to highlight.

        """
        count = len(self.state.entry_order)
        if not count:
            # A bar graph switched to a scatter plot, or the other way round, can leave the
            # list holding nothing. Selecting from an empty list raises rather than simply
            # doing nothing, so the panels are simply left as they are.
            self._show_selected_style()
            return
        bounded = min(max(index, 0), count - 1)
        self.listbox.selection_remove(self.listbox.selection())
        self.listbox.selection_set(self._row_id(bounded))
        self._show_selected_style()
        self.listbox.focus(self._row_id(bounded))
        self.listbox.see(self._row_id(bounded))
        self._show_selected_color()
        self._show_selected_style()
    def _show_selected_color(self) -> None:
        """Copy the colour of the selected sample into the hex field and the swatch."""
        selected = self._selected_indices()
        if not selected:
            return
        order = self.state.entry_order
        if selected[0] >= len(order):
            return
        color = self.state.color_of(order[selected[0]])
        self.syncing = True
        try:
            self.hex_var.set(color.lower())
            # The swatch previews the colour, so it only ever receives a value that has
            # already been through the colour validator.
            self.swatch.configure(background=normalize_hex(color) or FALLBACK_COLOR)
        finally:
            self.syncing = False
    def _move_rows(self, source: int, target: int) -> None:
        """Move a single row, keeping the highlight on the row that moved.

        Args:
            source: Row to move.
            target: Position to move it to.

        """
        count = len(self.state.visible_order)
        if not 0 <= source < count:
            return
        bounded = min(max(target, 0), count - 1)
        if bounded != source:
            # The state is the single source of truth for the order, so it is changed here
            # and the list is rebuilt from it. Row ids encode the row position, so a move
            # invalidates the id of every row that shifted, which a rebuild fixes at once.
            self.state.move_sample(source, bounded)
            self._refresh_list()
        self._select_row(bounded)
    def _move_selected(self, delta: int) -> None:
        """Move the selected sample one row up or down.

        Args:
            delta: ``-1`` to move up, ``1`` to move down.

        """
        selected = self._selected_indices()
        if not selected:
            return
        index = selected[0]
        self._move_rows(index, index + delta)
        self.redraw()
    def _on_row_selected(self, _event: object = None) -> None:
        """Refresh the panels for the samples that are now highlighted."""
        self._show_selected_style()
        self._show_selected_color()
    def _selected_samples(self) -> tuple[str, ...]:
        """Return the names of every highlighted entry, in list order.

        The list holds series rather than samples when a scatter plot is drawn, so this
        follows whichever the current chart shows. The styling controls call it, which is
        what lets a scatter series be recoloured the way a bar is.
        """
        order = self.state.entry_order
        return tuple(order[index] for index in self._selected_indices() if index < len(order))
    def _selection_caption(self) -> str:
        """Return the style panel heading, naming how many samples a change will affect.

        A change applies to every highlighted sample at once, so the heading says how many
        that is rather than naming one of them and leaving the rest a surprise.
        """
        names = self._selected_samples()
        if not names:
            return 'No sample selected'
        if len(names) == 1:
            return names[0]
        return f'{names[0]}  +{len(names) - 1} more'
    def _show_selected_style(self) -> None:
        """Fill the style panel with the settings of the highlighted samples."""
        names = self._selected_samples()
        self.style_name.configure(text=self._selection_caption())
        if not self.style_frame.winfo_manager():
            self.style_frame.pack(fill=tk.X, pady=(8, 0))
        # The per series controls act on whatever is highlighted, so they are packed only
        # when something is. Packed with an empty selection they were live but did
        # nothing: a click toggled the box and left the graph unchanged, which reads as a
        # broken control rather than as a missing selection.
        scatter = self.state.config.chart == 'scatter' and bool(names)
        if scatter and not self.series_style_frame.winfo_manager():
            self.series_style_frame.pack(fill=tk.X)
        elif not scatter and self.series_style_frame.winfo_manager():
            self.series_style_frame.pack_forget()
        if not names:
            # The boxes are put back to off as well, so a panel can never be left showing
            # a tick that the graph does not agree with.
            self.connect_series_var.set(False)
            self.label_series_var.set(False)
            # With nothing highlighted there is no series the shape belongs to, so the field
            # falls back to the shape the whole graph is drawn with.
            self.point_type_var.set(POINT_LABELS[self.state.config.point_type])
            return
        if scatter:
            # The boxes reflect the first highlighted series, because one value has to
            # stand for all of them and a change applies to every one of them anyway.
            first = names[0]
            self.connect_series_var.set(first in set(self.state.config.connect_series))
            self.label_series_var.set(first in set(self.state.config.label_series))
            # The shape is read the same way, through the accessor that applies the same
            # fallback the renderer does, so the field cannot show a shape the graph ignores.
            self.point_type_var.set(POINT_LABELS[self.state.point_type_of(first)])
        # The fields show the first highlighted sample, because one value has to stand for
        # all of them, and a change applies to every one of them anyway.
        first = names[0]
        self.edge_var.set(self.state.edge_of(first))
        # The list shows a label rather than the pattern, so the two index aligned tuples
        # are used to turn one into the other, and an unknown pattern shows as none.
        pattern = self.state.hatch_of(first)
        known = HATCH_PATTERNS.index(pattern) if pattern in HATCH_PATTERNS else 0
        self.hatch_var.set(HATCH_LABELS[known])
