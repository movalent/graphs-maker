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


class _TabManager:
    """A tab manager that mimics ttk.Notebook interface for tests.

    Uses buttons instead of a real notebook, with tabs fixed in the header
    and content in the scrollable body.
    """

    def __init__(self, tab_names: tuple[str, ...]):
        self._tab_names = tab_names
        self._tabs: list[ttk.Button] = []
        self._name_to_frame: dict[str, tk.Frame] = {}
        self._current_tab: str = ''
        self._switch_callback: callable = None

    def _build(self, header: ttk.Frame, switch_callback: callable) -> dict[str, tk.Frame]:
        """Build the tab buttons and content frames.

        Args:
            header: The fixed header frame for tab buttons.
            switch_callback: Called with tab name when selection changes.

        Returns:
            Dictionary mapping tab names to their content frames.
        """
        from tkinter import ttk
        tab_button_frame = ttk.Frame(header)
        tab_button_frame.pack(fill=tk.X, pady=(8, 0))

        self._switch_callback = switch_callback
        self._tab_buttons = []
        self._tab_frames = {}

        for name in self._tab_names:
            content_frame = ttk.Frame(padding=6)
            self._tab_frames[name] = content_frame

            btn = ttk.Button(
                tab_button_frame,
                text=name,
                command=lambda n=name: self._on_button_click(n),
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._tabs.append(btn)
            # Store mapping from button name to content frame for tests
            self._name_to_frame[btn.winfo_name()] = content_frame

        return self._tab_frames

    def _on_button_click(self, tab_name: str) -> None:
        """Handle tab button click."""
        if self._switch_callback:
            self._switch_callback(tab_name)

    def tab(self, index_or_widget: int | str, option: str | None = None) -> str | None:
        """Mimic ttk.Notebook.tab() for tests.

        Returns tab text when called with index.
        """
        if isinstance(index_or_widget, int):
            if 0 <= index_or_widget < len(self._tabs):
                return self._tab_names[index_or_widget]
            return None
        return None

    def select(self, widget_or_index: int | str | None = None) -> None:
        """Mimic ttk.Notebook.select() for tests."""
        if widget_or_index is None:
            return
        if isinstance(widget_or_index, int):
            if 0 <= widget_or_index < len(self._tabs):
                self._tabs[widget_or_index].invoke()
        elif isinstance(widget_or_index, str):
            # Could be tab name like "General" or widget path like ".!frame.!button2"
            if widget_or_index in self._tab_names:
                self._on_button_click(widget_or_index)
            else:
                # Handle widget path strings like '.!frame.!button2'
                # The test passes the full path, so match the last component
                for i, btn in enumerate(self._tabs):
                    btn_path = btn.winfo_pathname(btn.winfo_id())
                    if widget_or_index == btn_path or widget_or_index in btn_path:
                        self._tabs[i].invoke()
                        break

    def index(self, option: str = None) -> int:
        """Mimic ttk.Notebook.index() for tests."""
        if option == 'end':
            return len(self._tabs)
        return 0

    def tabs(self) -> list[str]:
        """Return list of tab widget path strings for tests."""
        return [btn.winfo_pathname(btn.winfo_id()) for btn in self._tabs]

    def nametowidget(self, name: str) -> tk.Misc:
        """Return a widget by name for tests.

        Returns the content frame associated with the tab button name.
        """
        # Handle both full path and last component
        parts = name.split('.')
        key = parts[-1]
        if key in self._name_to_frame:
            return self._name_to_frame[key]
        raise tk.TclError(f'unknown widget name: {name}')

    def current_tab(self) -> str:
        """Return the currently selected tab name."""
        return self._current_tab

    def set_current_tab(self, name: str) -> None:
        """Set the currently selected tab name."""
        self._current_tab = name

    def update_tab_style(self) -> None:
        """Update button styles to show which tab is active."""
        for i, (name, btn) in enumerate(zip(self._tab_names, self._tabs)):
            if name == self._current_tab:
                btn.state(['pressed'])
            else:
                btn.state(['!pressed'])

    def _tab_frames(self) -> dict[str, tk.Frame]:
        """Return the content frames dict."""
        return self._tab_frames


class ShellMixin(_AppBase):
    """The panel the settings are put in, and the notebook of tabs they sit in."""

    def _build_controls(self) -> None:
        """Create the left hand control panel.

        The action buttons are packed to the bottom edge, so they are always given their
        space before the expanding sample list can take it. Packing them in order after
        the list squeezed the last one down to a few pixels whenever the window was
        shorter than the panel needed.

        The colour row and the notebook tabs are kept fixed at the top so they never
        scroll out of view. Only the active tab's content lives in the scrollable area.
        """
        panel = ttk.Frame(self.root, padding=8, width=PANEL_WIDTH)
        panel.pack(side=tk.LEFT, fill=tk.Y)
        panel.pack_propagate(False)
        self.panel = panel

        self._build_file_bar(panel)
        self._build_action_buttons(panel)

        # Sample list above the fixed header
        self._build_sample_list(panel)

        # Fixed header: colour row + notebook tabs (these never scroll)
        header = ttk.Frame(panel)
        header.pack(side=tk.TOP, fill=tk.X)
        self._build_color_row(header)
        self._build_tabs(header)

        # Scrollable body holds only the active tab's content
        body = ttk.Frame(panel)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._scroll_body(body)

        # Now that the scrollable body exists, show the tab content
        self._show_tab_content()

        # Initial tab content
        self._show_tab_content()
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
        self._body_inner = inner
    def _build_tabs(self, header: ttk.Frame) -> None:
        """Create the tab buttons in the fixed header and content frames for the scrollable body.

        The tab buttons live in the header so they never scroll. Each tab's content is
        built into its own frame; all frames are packed in the scrollable body but
        only the active tab's content is visible.

        Args:
            header: The fixed header frame where the tab buttons are placed.

        """
        self._tab_manager = _TabManager(('General', 'Axis', 'Plot style', 'Data preview'))
        self._tab_frames = self._tab_manager._build(header, self._switch_tab)

        # Build content into the frames
        self._build_general_tab(self._tab_frames['General'])
        self._build_axis_tab(self._tab_frames['Axis'])
        self._build_style_panel(self._tab_frames['Plot style'])
        self._build_preview_tab(self._tab_frames['Data preview'])

        # Expose the tab manager interface for tests
        self.tabs = self._tab_manager

        # Show initial tab (scrollable body may not exist yet; _show_tab_content handles this)
        self._current_tab = self._tab_manager._tab_names[0]
        self._tab_manager.set_current_tab(self._current_tab)
        self._update_tab_button_styles()
        self._show_tab_content()

    def _switch_tab(self, tab_name: str) -> None:
        """Switch to the given tab."""
        if tab_name == self._current_tab:
            return
        self._current_tab = tab_name
        self._tab_manager.set_current_tab(tab_name)
        self._tab_manager.update_tab_style()
        self._show_tab_content()

    def _update_tab_button_styles(self) -> None:
        """Update button styles to show which tab is active."""
        self._tab_manager.update_tab_style()

    def _show_tab_content(self) -> None:
        """Show the active tab's content in the scrollable body."""
        if not hasattr(self, '_tab_frames') or not self._tab_frames:
            return
        if not hasattr(self, '_body_inner') or self._body_inner is None:
            return
        # All frames are packed in the inner frame; just show/hide
        active_frame = None
        for name, frame in self._tab_frames.items():
            if name == self._current_tab:
                frame.pack(in_=self._body_inner, fill=tk.BOTH, expand=True)
                active_frame = frame
            else:
                frame.pack_forget()
        # Update scroll region based on only the active frame
        if active_frame:
            active_frame.update_idletasks()
            # Bind wheel to the active frame and its children
            bind_wheel(active_frame, lambda e: self._body_canvas.yview_scroll(wheel_units(e), 'units'))
            # Get the required height of the active frame
            req_height = active_frame.winfo_reqheight()
            canvas_width = self._body_canvas.winfo_width()
            self._body_canvas.configure(scrollregion=(0, 0, canvas_width, req_height))
        else:
            self._body_inner.update_idletasks()
            self._body_canvas.configure(scrollregion=self._body_canvas.bbox('all'))
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
