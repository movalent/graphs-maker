"""Creating, editing and moving text annotations on the graph."""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from tkinter import colorchooser, messagebox, ttk

from matplotlib.backend_bases import MouseEvent
from matplotlib.text import Text

from src.app_state import MAX_ANNOTATION_FONT_SIZE, MIN_ANNOTATION_FONT_SIZE
from src.models import DEFAULT_FONT_TYPE, TextAnnotation
from src.ui.base import _AppBase
from src.ui.general_tab import FONT_CHOICES

ANNOTATION_GID_PREFIX = 'graph-annotation-'


def _editor_origin(
    anchor_x: int,
    anchor_y: int,
    editor_width: int,
    editor_height: int,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    """Place an editor above its anchor when possible, keeping it on-screen."""
    x = min(max(anchor_x - editor_width // 2, 0), max(0, screen_width - editor_width))
    y = anchor_y - editor_height - 8
    if y < 0:
        y = anchor_y + 8
    y = min(max(y, 0), max(0, screen_height - editor_height))
    return x, y


class AnnotationMixin(_AppBase):
    """Manage text annotations and their mouse and keyboard interactions."""

    def _build_annotation_controls(self, panel: tk.Widget) -> None:
        """Add the button that starts graph annotation placement.

        Args:
            panel: The General tab panel that receives the control.

        """
        self._annotation_placing = False
        self._selected_annotation_index = None
        self._annotation_drag_index = None
        self._annotation_clipboard = None
        self.add_annotation_button = ttk.Button(
            panel,
            text='Add text annotation',
            command=self._start_annotation_placement,
        )
        self.add_annotation_button.pack(fill=tk.X, pady=(8, 0))

    def _start_annotation_placement(self) -> None:
        """Wait for a click in the plot before opening the text and style editor."""
        if not self.canvas.figure.axes:
            messagebox.showinfo('No graph', 'Open an Excel file before adding an annotation.', parent=self.root)
            return
        self._annotation_placing = True
        self.add_annotation_button.configure(text='Click graph to place text…')

    def _connect_annotation_events(self) -> None:
        """Connect annotation interactions to the current figure canvas."""
        self.canvas.mpl_connect('button_press_event', self._on_annotation_press)
        self.canvas.mpl_connect('motion_notify_event', self._on_annotation_motion)
        self.canvas.mpl_connect('button_release_event', self._on_annotation_release)
        self.canvas.get_tk_widget().bind('<Delete>', self._delete_selected_annotation)
        self.canvas.get_tk_widget().bind('<Control-c>', self._copy_selected_annotation)
        self.canvas.get_tk_widget().bind('<Control-C>', self._copy_selected_annotation)
        self.canvas.get_tk_widget().bind('<Control-v>', self._paste_annotation)
        self.canvas.get_tk_widget().bind('<Control-V>', self._paste_annotation)

    def _annotation_artists(self) -> tuple[Text, ...]:
        """Return the text artists belonging to graph annotations."""
        if not self.canvas.figure.axes:
            return ()
        return tuple(
            artist
            for artist in self.canvas.figure.axes[0].texts
            if (artist.get_gid() or '').startswith(ANNOTATION_GID_PREFIX)
        )

    def _sync_annotation_selection(self) -> None:
        """Show a thin dashed outline around the selected annotation only."""
        artists = self._annotation_artists()
        if self._selected_annotation_index is not None and self._selected_annotation_index >= len(artists):
            self._selected_annotation_index = None
        for index, artist in enumerate(artists):
            if index == self._selected_annotation_index:
                artist.set_bbox(
                    {
                        'boxstyle': 'square,pad=0.2',
                        'facecolor': 'none',
                        'edgecolor': 'black',
                        'linestyle': '--',
                        'linewidth': 0.8,
                    }
                )
            else:
                artist.set_bbox(None)

    def _on_annotation_press(self, event: MouseEvent) -> None:
        """Place, select, edit or begin dragging an annotation.

        Args:
            event: The matplotlib mouse event.

        """
        if not self.canvas.figure.axes:
            return
        widget = self.canvas.get_tk_widget()
        widget.focus_set()
        axes = self.canvas.figure.axes[0]
        if event.inaxes not in self.canvas.figure.axes:
            self._selected_annotation_index = None
            self._sync_annotation_selection()
            self.canvas.draw_idle()
            return
        x, y = axes.transAxes.inverted().transform((event.x, event.y))
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            return
        if self._annotation_placing:
            self._annotation_placing = False
            self.add_annotation_button.configure(text='Add text annotation')
            initial = TextAnnotation(text='Text', x=float(x), y=float(y))
            annotation = self._annotation_editor(initial, 'Add text annotation')
            if annotation is not None:
                if self.state.add_text_annotation(annotation):
                    self._selected_annotation_index = len(self.state.config.annotations) - 1
                    self.redraw()
                else:
                    messagebox.showerror('Invalid annotation', 'Enter text with a valid font, size, and color.',
                                         parent=self.root)
            return

        for index, artist in enumerate(self._annotation_artists()):
            contains, _details = artist.contains(event)
            if not contains:
                continue
            self._selected_annotation_index = index
            self._sync_annotation_selection()
            if event.dblclick:
                self._edit_text_annotation(index)
            else:
                self._annotation_drag_index = index
            self.canvas.draw_idle()
            return
        self._selected_annotation_index = None
        self._sync_annotation_selection()
        self.canvas.draw_idle()

    def _copy_selected_annotation(self, _event: tk.Event[tk.Misc]) -> str | None:
        """Copy the selected annotation, including its styling, to the app clipboard.

        Args:
            _event: The Tk keyboard event.

        Returns:
            ``'break'`` when an annotation was copied, otherwise ``None``.

        """
        index = self._selected_annotation_index
        if index is None or not 0 <= index < len(self.state.config.annotations):
            return None
        self._annotation_clipboard = self.state.config.annotations[index]
        return 'break'

    def _paste_annotation(self, _event: tk.Event[tk.Misc]) -> str | None:
        """Paste a styled copy near the selected annotation and select the copy.

        Args:
            _event: The Tk keyboard event.

        Returns:
            ``'break'`` when an annotation was pasted, otherwise ``None``.

        """
        annotation = self._annotation_clipboard
        if annotation is None:
            return None
        x = annotation.x + (0.05 if annotation.x <= 0.95 else -0.05)
        y = annotation.y + (0.05 if annotation.y <= 0.95 else -0.05)
        pasted = replace(annotation, x=x, y=y)
        if not self.state.add_text_annotation(pasted):
            return None
        self._selected_annotation_index = len(self.state.config.annotations) - 1
        self.redraw()
        return 'break'

    def _on_annotation_motion(self, event: MouseEvent) -> None:
        """Move the active annotation visually while the mouse is held down.

        Args:
            event: The matplotlib mouse event.

        """
        index = self._annotation_drag_index
        if index is None or not self.canvas.figure.axes:
            return
        x, y = self.canvas.figure.axes[0].transAxes.inverted().transform((event.x, event.y))
        x = min(1.0, max(0.0, float(x)))
        y = min(1.0, max(0.0, float(y)))
        artists = self._annotation_artists()
        if index < len(artists):
            artists[index].set_position((x, y))
            self.canvas.draw_idle()

    def _on_annotation_release(self, _event: MouseEvent) -> None:
        """Commit the final dragged position as one undoable graph edit.

        Args:
            _event: The matplotlib mouse event.

        """
        index = self._annotation_drag_index
        self._annotation_drag_index = None
        if index is None:
            return
        artists = self._annotation_artists()
        if index >= len(artists) or index >= len(self.state.config.annotations):
            return
        x, y = artists[index].get_position()
        previous = self.state.config.annotations[index]
        if (x, y) == (previous.x, previous.y):
            return
        if self.state.update_text_annotation(index, replace(previous, x=x, y=y)):
            self.redraw()

    def _edit_text_annotation(self, index: int) -> None:
        """Edit one annotation's text and style.

        Args:
            index: Position of the annotation in the current state.

        """
        if not 0 <= index < len(self.state.config.annotations):
            return
        updated = self._annotation_editor(self.state.config.annotations[index], 'Edit text annotation')
        if updated is not None and self.state.update_text_annotation(index, updated):
            self._selected_annotation_index = index
            self.redraw()

    def _delete_selected_annotation(self, _event: tk.Event[tk.Misc]) -> str | None:
        """Remove the selected annotation when Delete is pressed in the graph.

        Args:
            _event: The Tk keyboard event.

        Returns:
            ``'break'`` when an annotation was deleted, otherwise ``None``.

        """
        index = self._selected_annotation_index
        if index is None or self._text_widget_focused():
            return None
        if self.state.remove_text_annotation(index):
            self._selected_annotation_index = None
            self.redraw()
            return 'break'
        return None

    def _annotation_editor(self, annotation: TextAnnotation, title: str) -> TextAnnotation | None:
        """Show a modal editor for annotation text and its font, size, and color.

        Args:
            annotation: Initial values to show in the editor.
            title: Window title distinguishing creation from editing.

        Returns:
            The edited annotation, or ``None`` if the dialog was cancelled.

        """
        window = tk.Toplevel(self.root)
        window.title(title)
        window.transient(self.root)
        window.resizable(False, False)
        body = ttk.Frame(window, padding=12)
        body.pack(fill=tk.BOTH, expand=True)

        text_var = tk.StringVar(value=annotation.text)
        font_var = tk.StringVar(value=annotation.font or DEFAULT_FONT_TYPE)
        size_var = tk.StringVar(value=str(annotation.size))
        color_var = tk.StringVar(value=annotation.color)
        ttk.Label(body, text='Text').grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        text_entry = ttk.Entry(body, textvariable=text_var, width=36)
        text_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=(0, 6))
        ttk.Label(body, text='Font').grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(body, textvariable=font_var, values=FONT_CHOICES, state='readonly').grid(
            row=1, column=1, columnspan=2, sticky=tk.EW, pady=3
        )
        ttk.Label(body, text='Size').grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(
            body,
            textvariable=size_var,
            from_=MIN_ANNOTATION_FONT_SIZE,
            to=MAX_ANNOTATION_FONT_SIZE,
            width=8,
        ).grid(row=2, column=1, sticky=tk.W, pady=3)

        def choose_color() -> None:
            chosen = colorchooser.askcolor(color=color_var.get(), parent=window)
            if chosen[1] is not None:
                color_var.set(chosen[1])
                color_button.configure(background=chosen[1])

        color_button = tk.Button(body, text='Text color', command=choose_color, background=annotation.color)
        color_button.grid(row=2, column=2, sticky=tk.E, padx=(8, 0), pady=3)

        result: list[TextAnnotation] = []

        def accept() -> None:
            text = text_var.get().strip()
            try:
                size = int(size_var.get())
            except ValueError:
                messagebox.showerror('Invalid size', 'Enter a whole-number font size.', parent=window)
                return
            if not text or not MIN_ANNOTATION_FONT_SIZE <= size <= MAX_ANNOTATION_FONT_SIZE:
                messagebox.showerror(
                    'Invalid annotation',
                    f'Enter text and a font size from {MIN_ANNOTATION_FONT_SIZE} to {MAX_ANNOTATION_FONT_SIZE}.',
                    parent=window,
                )
                return
            result.append(
                replace(
                    annotation,
                    text=text,
                    font=font_var.get(),
                    size=size,
                    color=color_var.get(),
                )
            )
            window.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=3, sticky=tk.E, pady=(10, 0))
        ttk.Button(buttons, text='Cancel', command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text='OK', command=accept).pack(side=tk.RIGHT)
        body.columnconfigure(1, weight=1)
        window.bind('<Return>', lambda _event: accept())
        window.bind('<Escape>', lambda _event: window.destroy())
        window.protocol('WM_DELETE_WINDOW', window.destroy)
        window.update_idletasks()
        x, y = self._annotation_editor_origin(annotation, window.winfo_reqwidth(), window.winfo_reqheight())
        window.geometry(f'+{x}+{y}')
        window.grab_set()
        text_entry.focus_set()
        window.wait_window()
        return result[0] if result else None

    def _annotation_editor_origin(
        self,
        annotation: TextAnnotation,
        editor_width: int,
        editor_height: int,
    ) -> tuple[int, int]:
        """Return a screen position for the editor, centered just above its annotation.

        Args:
            annotation: Annotation whose position anchors the editor.
            editor_width: Requested editor width in pixels.
            editor_height: Requested editor height in pixels.

        Returns:
            The editor's top-left screen coordinates, clamped to the display.

        """
        widget = self.canvas.get_tk_widget()
        axes = self.canvas.figure.axes[0]
        display_x, display_y = axes.transAxes.transform((annotation.x, annotation.y))
        anchor_x = widget.winfo_rootx() + round(display_x)
        anchor_y = widget.winfo_rooty() + widget.winfo_height() - round(display_y)
        return _editor_origin(
            anchor_x,
            anchor_y,
            editor_width,
            editor_height,
            widget.winfo_screenwidth(),
            widget.winfo_screenheight(),
        )
