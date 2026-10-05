"""The frame the window is built in: the panel, the file bar, the notebook and the buttons.

This is the part of the window that exists before any setting is chosen. It puts the file
bar at the top, the save and reset buttons at the bottom, the scrollable column between
them, and the notebook of tabs inside that. Nothing here knows what any setting means; it
only decides where the settings are put.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.cli import resolve_output
from src.ui.base import _SYNTHETIC_EVENT, NO_FILE, PANEL_WIDTH, _AppBase
from src.ui.widgets import bind_wheel, wheel_units


class ShellMixin(_AppBase):
    """The panel the settings are put in, and the notebook of tabs they sit in."""

    def _build_controls(self) -> None:
        """Create the left hand control panel.

        The action buttons are packed to the bottom edge, so they are always given their
        space before the expanding sample list can take it. Packing them in order after
        the list squeezed the last one down to a few pixels whenever the window was
        shorter than the panel needed.
        """
        panel = ttk.Frame(self.root, padding=8, width=PANEL_WIDTH)
        panel.pack(side=tk.LEFT, fill=tk.Y)
        panel.pack_propagate(False)
        self.panel = panel

        self._build_file_bar(panel)
        self._build_action_buttons(panel)

        # Everything between the file bar and the buttons lives in a scrollable area, so a
        # short window can always be scrolled to reach every control.
        self._build_sample_list(panel)

        body = ttk.Frame(panel)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._scroll_body(body)
    def _build_action_buttons(self, panel: ttk.Frame) -> None:
        """Create the buttons that stay pinned to the bottom of the panel.

        Args:
            panel: The control panel the buttons are added to.

        """
        ttk.Separator(panel).pack(side=tk.BOTTOM, fill=tk.X, pady=6)
        ttk.Button(panel, text='Save PDF…', command=lambda: self._save('pdf')).pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(panel, text='Save PNG…', command=lambda: self._save('png')).pack(
            side=tk.BOTTOM, fill=tk.X, pady=(4, 0)
        )
        ttk.Button(panel, text='Reset', command=self._reset).pack(side=tk.BOTTOM, anchor=tk.W, pady=(4, 0))
        # The rows are only asked about when a sheet carries no markers, so a sheet that
        # does carry them can be re-read differently through this button instead.
    def _build_file_bar(self, panel: ttk.Frame) -> None:
        """Create the row that opens files and shows which one is loaded.

        Args:
            panel: The control panel the row is added to.

        """
        bar = ttk.Frame(panel)
        bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(bar, text='Open…', command=self._open_file).pack(side=tk.LEFT)
        self.file_var = tk.StringVar(value=self._file_label())
        ttk.Label(
            bar,
            textvariable=self.file_var,
            font=('Segoe UI', 9, 'italic'),
            foreground='#666666',
        ).pack(side=tk.LEFT, padx=8)
    def _scroll_body(self, body: ttk.Frame) -> None:
        """Fill ``body`` with a scrollable column holding every option.

        The wheel is bound to the widgets of this panel rather than to the whole window.
        A window wide binding also fires when the pointer is over the graph or the data
        preview, so scrolling there moved this column instead, which reads as though the
        two panes were joined together. Binding only here keeps the wheel where the
        content it moves actually is.

        Args:
            body: The frame that holds the scrollable area.

        """
        canvas = tk.Canvas(body, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        inner.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        self._body_canvas = canvas
        self._build_options(inner)
        # The wheel is bound once the options exist, not before. A Tk binding fires on the
        # widget it was made on and nowhere below it, so binding the canvas while it was
        # still empty bound nothing but the canvas: the notebook, its tabs and every entry
        # and checkbutton inside them were all added afterwards and were left unbound, which
        # is why the wheel did nothing over the controls themselves.
        bind_wheel(canvas, lambda e: canvas.yview_scroll(wheel_units(e), 'units'))
    def _build_options(self, inner: ttk.Frame) -> None:
        """Create the colour row above the tabs, and the tabs holding every other setting.

        Only the colour row stays outside, because the fill colour applies to whichever
        samples are highlighted in the list above and is therefore tied to that selection.
        Everything else is used one tab at a time.

        Args:
            inner: The scrollable frame the controls are added to.

        """
        self._build_color_row(inner)
        ttk.Separator(inner).pack(fill=tk.X, pady=8)
        self._build_tabs(inner)
    def _build_tabs(self, inner: ttk.Frame) -> None:
        """Create the notebook that holds every setting except the colour row.

        Each tab collects one kind of work: what the graph as a whole looks like, what its
        axes look like, and how the drawing itself is dressed. Grouping used to have a tab
        of its own, but it was the only thing left on it, so it now sits at the bottom of
        the Plot style tab beside the rest of the drawing. Splitting the panel this way
        keeps it short enough that the sample list above stays visible and the scrollable
        area rarely has to be scrolled at all.

        Args:
            inner: The scrollable frame the notebook is added to.

        """
        self.tabs = ttk.Notebook(inner)
        self.tabs.pack(fill=tk.BOTH, expand=True)
        general_tab = ttk.Frame(self.tabs, padding=6)
        axis_tab = ttk.Frame(self.tabs, padding=6)
        style_tab = ttk.Frame(self.tabs, padding=6)
        preview_tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(general_tab, text='General')
        self.tabs.add(axis_tab, text='Axis')
        self.tabs.add(style_tab, text='Plot style')
        # The preview tab goes last so that the tabs before it keep the positions the rest
        # of the window and the tests already refer to.
        self.tabs.add(preview_tab, text='Data preview')

        self._build_general_tab(general_tab)
        self._build_axis_tab(axis_tab)
        self._build_style_panel(style_tab)
        self._build_preview_tab(preview_tab)
    def _file_label(self) -> str:
        """Return the text describing the loaded file.

        Returns:
            The file name, a pending note about the output path, or a prompt to open one.

        """
        if self.input_path is not None:
            return self.input_path.name
        if self.output_hint is not None:
            return f'Will save to {self.output_hint.name}'
        return NO_FILE
    def _save(self, image_format: str) -> None:
        """Save the current graph through a file dialog.

        Args:
            image_format: File format extension, ``'png'`` or ``'pdf'``.

        """
        if not self.state.dataset.samples and not self.state.dataset.series:
            messagebox.showinfo('Nothing to save', 'Open an Excel file first.', parent=self.root)
            return
        suggested = self.output_hint or resolve_output(self.input_path or Path('graph'), None, image_format)
        target = filedialog.asksaveasfilename(
            parent=self.root,
            title='Save graph',
            defaultextension=f'.{image_format}',
            initialdir=str(suggested.parent) if str(suggested.parent) else self.last_dir,
            initialfile=suggested.name,
            filetypes=[(image_format.upper(), f'*.{image_format}'), ('All files', '*.*')],
        )
        if not target:
            return
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.canvas.figure.savefig(path)
        self.output_hint = path
        self.last_dir = str(path.parent)
        self.dirty = False
        self.file_var.set(self._file_label())
        self.root.title(f'{path.name} — GraphPad Prism style graph')
    def _reset(self) -> None:
        """Restore every setting to its default and redraw."""
        self.state.reset()
        self._sync_from_state()
        self.redraw(mark_dirty=False)
        self.dirty = False
        self._on_row_selected(_SYNTHETIC_EVENT)
        # The column selection is part of what a reset undoes, so the sheet is re-read with
        # every column again. Without this the graph would keep the samples the user had
        # left out while the preview showed them all back in the graph. The re-read is asked
        # for explicitly because resetting the selection is a display change, not a click.
        if self.state.dataset.samples:
            self.sheet.select_all_columns()
            self._apply_column_selection()
            self.dirty = False
    def _mark_dirty(self) -> None:
        """Record that the graph was adjusted, so a new file asks before discarding it."""
        if not self.syncing and (self.state.dataset.samples or self.state.dataset.series):
            self.dirty = True
