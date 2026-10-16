"""The Axis tab: the name, scale, range and fonts of each axis.

The two axes are separated into blocks because they are set the same way but mean different
things. The settings that belong to the frame rather than to either axis sit above the two
blocks, unsectioned, because putting them inside one of them would imply that axis owns them.

The fields a bar graph has no use for are greyed out rather than hidden, so the block keeps
one shape as the kind of graph changes and a value already typed into one is not lost.
"""

from __future__ import annotations

import math
import tkinter as tk
from functools import partial
from tkinter import colorchooser, ttk

from matplotlib.ticker import AutoLocator

from src.app_state import FALLBACK_COLOR, LineTarget, normalize_hex
from src.graphpad_style import DEFAULT_LEGEND_FONT, DEFAULT_TICK_FONT
from src.models import (
    DEFAULT_FONT_TYPE,
    REFERENCE_LINE_STYLE_LABELS,
    REFERENCE_LINE_STYLES,
    ReferenceLine,
    ReferenceLineOrientation,
)
from src.ui.base import PANEL_WIDTH, _AppBase
from src.ui.fields import chosen_size, chosen_value, optional_number, optional_size, shown_number
from src.ui.general_tab import FONT_CHOICES
from src.ui.widgets import bind_wheel, dropdown_row, number_row, option_row, pair_row, section

# How an axis may be scaled. A log axis cannot start at or cross zero, so it is offered on
# both axes the same way rather than being restricted to the value axis.
AXIS_TYPES: tuple[str, ...] = ('Linear', 'Logarithmic')
# How far a label may be turned, in degrees. The whole turn is allowed because a label
# reading up the side of the graph is turned ninety degrees, and a value outside this range
# would draw text upside down or mirrored, which is never what anyone means.
MIN_ROTATION = -180
MAX_ROTATION = 180
DEFAULT_ROTATION = 0


def _positive_length(text: str, previous: float) -> float:
    """Return a finite positive length, keeping the previous value for unfinished input."""
    value = optional_number(text)
    return value if value is not None and math.isfinite(value) and value > 0 else previous


class AxisTabMixin(_AppBase):
    """The name, scale, range and fonts of each of the two axes."""

    def _sync_axis(self) -> None:
        """Put the two axis blocks back, showing the settings that are really in use."""
        config = self.state.config
        self.log_var.set('Log' if config.log_axis else 'Linear')
        # The field shows the title in use, which is the override when there is one and the
        # sheet's own title otherwise, so the user can see and edit what is drawn.
        self.y_title_var.set(config.y_label or self.state.dataset.y_label)
        self.x_title_var.set(config.x_label_override or self.state.dataset.x_label)
        self.rotation_var.set(f'{config.label_rotation:g}')
        self.y_max_var.set(shown_number(config.y_max, self.state.automatic_y_max()))
        self.y_step_var.set(shown_number(config.y_major_step, self._automatic_step()))
        # A range that was never chosen is left blank rather than filled with the automatic
        # value, so a field left alone is never read as a request to fix the axis there.
        self.x_max_var.set('' if config.x_max is None else f'{config.x_max:g}')
        self.x_step_var.set('' if config.x_major_step is None else f'{config.x_major_step:g}')
        self.x_axis_length_var.set(f'{config.x_axis_length_cm:g}')
        self.y_axis_length_var.set(f'{config.y_axis_length_cm:g}')
        # Each axis shows the size it will actually draw with, which is its own where it has
        # one and the shared size otherwise, so a field never reads as a choice that is
        # quietly not in effect.
        self.x_tick_font_var.set(str(config.x_font_size or config.font_size or DEFAULT_TICK_FONT))
        self.y_tick_font_var.set(str(config.y_font_size or config.font_size or DEFAULT_TICK_FONT))
        # The thickness field shows the value in use, so an untouched field is never read as
        # a request to fix the line at the default the graph already uses.
        self.axis_width_var.set(f'{self.state.line_width_of("axis"):g}')
        self._sync_reference_lines()

    def _build_axis_tab(self, tab: ttk.Frame) -> None:
        """Create the tab holding the name, scale, range and fonts of each axis.

        The two axes are separated into blocks of their own because they are set the same
        way but mean different things. The settings that genuinely belong to the frame
        rather than to either axis sit above the blocks, unsectioned, because putting them
        inside one of the blocks would imply that axis owns them.

        Args:
            tab: The Axis tab frame.

        """
        # The line width and the label family each draw both axes, so neither belongs to
        # one block. The size of the tick labels is the one font setting that is not
        # shared, so each block carries its own.
        self.axis_width_var = tk.StringVar()
        self.axis_font_type_var = tk.StringVar(value=DEFAULT_FONT_TYPE)
        pair_row(
            tab,
            ('Axis line width', self.axis_width_var, (), self._update_line_width),
            ('Axis font type', self.axis_font_type_var, FONT_CHOICES, None),
        )

        self._build_x_axis(section(tab, 'X axis'))
        self._build_y_axis(section(tab, 'Y axis'))
        self.reference_lines_frame = section(tab, 'Reference lines')
        ttk.Button(
            self.reference_lines_frame,
            text='Add horizontal line',
            command=lambda: self._add_reference_line('horizontal'),
        ).pack(fill=tk.X)
        ttk.Button(
            self.reference_lines_frame,
            text='Add vertical line',
            command=lambda: self._add_reference_line('vertical'),
        ).pack(fill=tk.X, pady=(4, 0))

    def _build_x_axis(self, box: tk.Widget) -> None:
        """Create the block of settings that describe the x axis.

        Args:
            box: The X axis block.

        """
        ttk.Label(box, text='Title', font=('Segoe UI', 8)).pack(anchor=tk.W)
        self.x_title_var = tk.StringVar()
        self.x_title_entry = ttk.Entry(box, textvariable=self.x_title_var)
        self.x_title_entry.pack(fill=tk.X)
        self.x_title_entry.bind('<Return>', lambda _e: self._update_x_title())
        self.x_title_entry.bind('<FocusOut>', lambda _e: self._update_x_title())
        # The entry is kept rather than packed into a local, because the panel has to be
        # able to grey it out for a bar graph, which has no x axis to name.
        ttk.Label(
            box,
            text='Leave empty to name the x axis after the sheet.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 60,
        ).pack(anchor=tk.W, pady=(2, 0))

        # A bar graph has no x values to scale, so the range is meaningless for one. The
        # fields are still shown rather than hidden, and greyed out, so the block does not
        # change shape as the graph type changes and the user can see what would apply.
        self.x_max_var = tk.StringVar()
        self.x_step_var = tk.StringVar()
        self.x_max_entry, self.x_step_entry = pair_row(
            box,
            ('X max', self.x_max_var, (), self._update_x_axis),
            ('X step', self.x_step_var, (), self._update_x_axis),
        )

        # The font type is shared and sits above the two blocks, so this one carries only
        # the size, which is set per axis because the two sets of labels are not the same
        # kind of text: a row of sample names against a column of numbers.
        self.x_tick_font_var = tk.StringVar()
        number_row(box, 'X tick text size', self.x_tick_font_var, self._update_fonts)

        self.x_axis_type_var = tk.StringVar(value=AXIS_TYPES[0])
        self.x_axis_type_combo = dropdown_row(box, 'X axis type', self.x_axis_type_var, AXIS_TYPES, None)

        self.x_axis_length_var = tk.StringVar()
        number_row(box, 'X axis length (cm)', self.x_axis_length_var, self._update_axis_lengths)

        # The rotation belongs to the x axis because that is where a label long enough to
        # need turning sits: the sample names along the bottom. The value axis carries a
        # single number, which stays readable upright however long the name above it is.
        ttk.Label(box, text='Label rotation', font=('Segoe UI', 8)).pack(anchor=tk.W, pady=(6, 0))
        self.rotation_var = tk.StringVar(value=str(DEFAULT_ROTATION))
        self.rotation_entry = ttk.Spinbox(
            box,
            from_=MIN_ROTATION,
            to=MAX_ROTATION,
            textvariable=self.rotation_var,
            width=8,
        )
        self.rotation_entry.pack(fill=tk.X)
        self.rotation_entry.bind('<Return>', lambda _e: self._update_rotation())
        self.rotation_entry.bind('<FocusOut>', lambda _e: self._update_rotation())
        ttk.Label(
            box,
            text=f'Degrees, {MIN_ROTATION} to {MAX_ROTATION}.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 60,
        ).pack(anchor=tk.W, pady=(2, 0))

    def _build_y_axis(self, box: tk.Widget) -> None:
        """Create the block of settings that describe the y axis.

        Args:
            box: The Y axis block.

        """
        ttk.Label(box, text='Title', font=('Segoe UI', 8)).pack(anchor=tk.W)
        self.y_title_var = tk.StringVar()
        title_entry = ttk.Entry(box, textvariable=self.y_title_var)
        title_entry.pack(fill=tk.X)
        title_entry.bind('<Return>', lambda _e: self._update_y_title())
        title_entry.bind('<FocusOut>', lambda _e: self._update_y_title())

        self.y_max_var = tk.StringVar()
        self.y_step_var = tk.StringVar()
        pair_row(
            box,
            ('Y max', self.y_max_var, (), self._update_axis),
            ('Y step', self.y_step_var, (), self._update_axis),
        )

        # The value axis title size is the size of the axis name, which is a different piece
        # of text from the tick labels, so it keeps a field of its own.
        self.y_label_size_var = tk.StringVar()
        number_row(box, 'Y title text size', self.y_label_size_var, self._update_fonts)

        self.y_axis_length_var = tk.StringVar()
        number_row(box, 'Y axis length (cm)', self.y_axis_length_var, self._update_axis_lengths)

        self.y_tick_font_var = tk.StringVar()
        number_row(box, 'Y tick text size', self.y_tick_font_var, self._update_fonts)

        self.log_var = tk.StringVar(value=AXIS_TYPES[0])
        option_row(
            box,
            ('Y axis type', self.log_var, ('Linear', 'Log'), self._update_log),
            (None, None, (), None),
        )

    def _update_y_title(self, _event: object = None) -> None:
        """Apply the value axis title, treating the sheet's own title as no override.

        Args:
            _event: Unused; the field applies the title itself.

        """
        if self.syncing:
            return
        text = self.y_title_var.get().strip()
        # The sheet's own title is what the graph already says, so typing it back is not an
        # override. Storing it as one would make a later change to the sheet invisible.
        self.state.config.y_label = None if text == self.state.dataset.y_label else text or None
        self.redraw()

    def _update_axis(self, _event: object = None) -> None:
        """Apply the value axis range and tick spacing.

        A field left on the automatic value stores nothing, so the graph goes on deciding for
        itself and a later change to the data is still reflected.

        Args:
            _event: Unused; the field applies the value itself.

        """
        if self.syncing:
            return
        self.state.config.y_max = chosen_value(self.y_max_var.get(), self.state.automatic_y_max())
        self.state.config.y_major_step = chosen_value(self.y_step_var.get(), self._automatic_step())
        self.redraw()

    def _sync_reference_lines(self) -> None:
        """Rebuild the reference-line controls to show the current line settings."""
        scroll_position = self._body_canvas.yview()[0]
        for child in self.reference_lines_frame.winfo_children()[2:]:
            child.destroy()
        self.reference_color_buttons = {}
        for index, line in enumerate(self.state.config.reference_lines):
            box = ttk.LabelFrame(
                self.reference_lines_frame,
                text=f'{line.orientation.capitalize()} line {index + 1}',
                padding=5,
            )
            box.pack(fill=tk.X, pady=(6, 0))
            position_var = tk.StringVar(value=f'{line.position:g}')
            style_var = tk.StringVar(value=REFERENCE_LINE_STYLE_LABELS[line.linestyle])
            _position_entry, _style_combo = pair_row(
                box,
                (
                    'Position',
                    position_var,
                    (),
                    partial(self._update_reference_position, index, position_var),
                ),
                (
                    'Line type',
                    style_var,
                    tuple(REFERENCE_LINE_STYLE_LABELS[style] for style in REFERENCE_LINE_STYLES),
                    partial(self._update_reference_style, index, style_var),
                ),
            )
            row = ttk.Frame(box)
            row.pack(fill=tk.X, pady=(4, 0))
            ttk.Label(row, text='Thickness', font=('Segoe UI', 8), width=9).pack(side=tk.LEFT)
            width_var = tk.StringVar(value=f'{line.linewidth:g}')
            width_entry = ttk.Entry(row, textvariable=width_var, width=8)
            width_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            width_entry.bind(
                '<Return>',
                partial(self._update_reference_width, index, width_var),
            )
            width_entry.bind(
                '<FocusOut>',
                partial(self._update_reference_width, index, width_var),
            )
            ttk.Button(
                row,
                text='Remove',
                command=partial(self._remove_reference_line, index),
            ).pack(side=tk.LEFT, padx=(5, 0))
            self._reference_color_button(box, index, line.color)
        bind_wheel(self.reference_lines_frame, self._on_body_wheel)
        self.reference_lines_frame.update_idletasks()
        self._body_inner.update_idletasks()
        self._body_canvas.configure(scrollregion=self._body_canvas.bbox('all'))
        self._body_canvas.yview_moveto(scroll_position)

    def _reference_color_button(self, parent: tk.Widget, index: int, color: str) -> tk.Button:
        """Add a color swatch button for one reference line."""
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(row, text='Color', font=('Segoe UI', 8), width=9).pack(side=tk.LEFT)
        button = tk.Button(
            row,
            text=color,
            bg=color,
            fg='white' if sum(int(color[offset : offset + 2], 16) for offset in (1, 3, 5)) < 360 else 'black',
            command=partial(self._choose_reference_color, index),
            relief=tk.RAISED,
        )
        button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.reference_color_buttons[index] = button
        return button

    def _add_reference_line(self, orientation: ReferenceLineOrientation) -> None:
        """Add a reference line in the requested direction and redraw the graph."""
        if self.state.add_reference_line(orientation):
            self._sync_reference_lines()
            self.redraw()

    def _remove_reference_line(self, index: int) -> None:
        """Remove one reference line and redraw the graph."""
        if self.state.remove_reference_line(index):
            self._sync_reference_lines()
            self.redraw()

    def _update_reference_line(self, index: int, line: ReferenceLine) -> bool:
        """Apply a validated line edit without rebuilding the controls.

        Returns:
            ``True`` when the line was accepted.

        """
        if self.state.update_reference_line(index, line):
            self.redraw()
            return True
        return False

    def _update_reference_position(self, index: int, variable: tk.StringVar, _event: object = None) -> None:
        """Apply a finite data coordinate to one reference line."""
        if self.syncing:
            return
        position = optional_number(variable.get())
        if position is None or not math.isfinite(position):
            variable.set(f'{self.state.config.reference_lines[index].position:g}')
            return
        line = self.state.config.reference_lines[index]
        if not self._update_reference_line(
            index, ReferenceLine(line.orientation, position, line.linestyle, line.color, line.linewidth)
        ):
            variable.set(f'{line.position:g}')

    def _update_reference_style(self, index: int, variable: tk.StringVar, _event: object = None) -> None:
        """Apply a chosen line style to one reference line."""
        if self.syncing:
            return
        style = next(
            (key for key, label in REFERENCE_LINE_STYLE_LABELS.items() if label == variable.get()),
            None,
        )
        if style is None:
            variable.set(REFERENCE_LINE_STYLE_LABELS[self.state.config.reference_lines[index].linestyle])
            return
        line = self.state.config.reference_lines[index]
        if not self._update_reference_line(
            index, ReferenceLine(line.orientation, line.position, style, line.color, line.linewidth)
        ):
            variable.set(REFERENCE_LINE_STYLE_LABELS[line.linestyle])

    def _update_reference_width(self, index: int, variable: tk.StringVar, _event: object = None) -> None:
        """Apply a usable thickness to one reference line."""
        if self.syncing:
            return
        width = optional_number(variable.get())
        if width is None or not math.isfinite(width):
            variable.set(f'{self.state.config.reference_lines[index].linewidth:g}')
            return
        line = self.state.config.reference_lines[index]
        if not self._update_reference_line(
            index, ReferenceLine(line.orientation, line.position, line.linestyle, line.color, width)
        ):
            variable.set(f'{line.linewidth:g}')

    def _choose_reference_color(self, index: int) -> None:
        """Open the color chooser for one reference line."""
        line = self.state.config.reference_lines[index]
        chosen = colorchooser.askcolor(color=line.color, parent=self.root)
        if chosen[1] is None:
            return
        color = normalize_hex(chosen[1]) or FALLBACK_COLOR
        if self._update_reference_line(
            index,
            ReferenceLine(line.orientation, line.position, line.linestyle, color, line.linewidth),
        ):
            button = self.reference_color_buttons[index]
            button.configure(
                text=color,
                bg=color,
                fg='white' if sum(int(color[offset : offset + 2], 16) for offset in (1, 3, 5)) < 360 else 'black',
            )

    def _update_x_axis(self, _event: object = None) -> None:
        """Apply the x axis top and tick spacing of a scatter plot.

        A field left on the automatic value stores nothing, so the graph goes on framing
        the points itself and a later change to the sheet is still reflected.

        Args:
            _event: Unused; the field applies the value itself.

        """
        if self.syncing:
            return
        self.state.config.x_max = optional_number(self.x_max_var.get())
        self.state.config.x_major_step = optional_number(self.x_step_var.get())
        self.redraw()

    def _update_axis_lengths(self, _event: object = None) -> None:
        """Apply positive finite physical lengths to the two plotting axes.

        An invalid or unfinished value leaves that axis at its last accepted length and is
        put back in its field, so a blank or half-typed number cannot collapse the plot.

        Args:
            _event: Unused; either length field applies its own value.

        """
        if self.syncing:
            return
        self.state.config.x_axis_length_cm = _positive_length(
            self.x_axis_length_var.get(),
            self.state.config.x_axis_length_cm,
        )
        self.state.config.y_axis_length_cm = _positive_length(
            self.y_axis_length_var.get(),
            self.state.config.y_axis_length_cm,
        )
        self.x_axis_length_var.set(f'{self.state.config.x_axis_length_cm:g}')
        self.y_axis_length_var.set(f'{self.state.config.y_axis_length_cm:g}')
        self.redraw()

    def _automatic_step(self) -> float | None:
        """Return the value axis tick spacing matplotlib would choose on its own.

        The window shows the automatic value in the field so it can be read off, and reads it
        back through the same helper, which stores nothing when it still matches.

        Returns:
            The spacing matplotlib picked, or ``None`` when the graph has no axis yet.

        """
        axes = self.canvas.figure.axes
        if not axes:
            return None
        low, high = axes[0].get_ylim()
        ticks = AutoLocator().tick_values(low, high)
        return max(ticks) if len(ticks) else None

    def _update_line_width(self, _event: object = None) -> None:
        """Apply the axis and bar line thicknesses typed into the two fields.

        Args:
            _event: Unused; the field applies the value itself.

        """
        if self.syncing:
            return
        # Text that is not a number yet is left alone rather than applied, so a half typed
        # value such as ``tbc`` cannot quietly reset the thickness already chosen.
        widths: tuple[tuple[LineTarget, tk.StringVar], ...] = (
            ('axis', self.axis_width_var),
            ('bar', self.bar_width_var),
        )
        for target, variable in widths:
            text = variable.get().strip()
            # An emptied field is a request for the default. A half typed one is not a
            # request for anything, so it is left alone rather than applied, which would
            # quietly undo the thickness that was already chosen.
            if not text:
                self.state.set_line_width(target, None)
                continue
            chosen = optional_number(text)
            if chosen is not None:
                self.state.set_line_width(target, chosen)
        # A thickness the state refuses, because it is not a number or falls outside the
        # range it will draw, is put back in the field. Leaving it there would show a number
        # that did nothing, as though the change had been applied.
        self.axis_width_var.set(f'{self.state.line_width_of("axis"):g}')
        self.bar_width_var.set(f'{self.state.line_width_of("bar"):g}')
        self.redraw()

    def _update_x_title(self, _event: object = None) -> None:
        """Apply the x axis title, treating the sheet's own title as no override.

        Args:
            _event: Unused; the field applies the title itself.

        """
        if self.syncing:
            return
        text = self.x_title_var.get().strip()
        # The sheet's own title is what the graph already says, so typing it back is not an
        # override. Storing it as one would make a later change to the sheet invisible.
        self.state.config.x_label_override = None if text == self.state.dataset.x_label else text or None
        self.redraw()

    def _update_rotation(self, _event: object = None) -> None:
        """Turn the x axis labels, and keep the field inside the range they may turn through.

        The field is corrected rather than left as typed, so a number outside the range is
        never left sitting there looking as though it had been accepted. Half typed text is
        left alone rather than applied, which would quietly undo the turn already chosen.

        Args:
            _event: Unused; the field applies and corrects the value itself.

        """
        if self.syncing:
            return
        chosen = optional_number(self.rotation_var.get())
        if chosen is None:
            return
        bounded = max(MIN_ROTATION, min(round(chosen), MAX_ROTATION))
        self.rotation_var.set(str(bounded))
        self.state.config.label_rotation = float(bounded)
        self.redraw()

    def _update_fonts(self, _event: object = None) -> None:
        """Apply the requested tick, legend, axis title and figure title font sizes.

        Args:
            _event: Unused; the fields apply the sizes themselves.

        """
        if self.syncing:
            return
        # The two axes are sized apart, and each stores nothing while its field holds the
        # Prism default, so an untouched axis keeps following the shared size.
        self.state.config.x_font_size = chosen_size(self.x_tick_font_var.get(), DEFAULT_TICK_FONT)
        self.state.config.y_font_size = chosen_size(self.y_tick_font_var.get(), DEFAULT_TICK_FONT)
        self.state.config.legend_size = chosen_size(self.legend_font_var.get(), DEFAULT_LEGEND_FONT)
        self.state.config.y_label_size = optional_size(self.y_label_size_var.get())
        self.state.config.title_size = optional_size(self.title_size_var.get())
        self.redraw()

    def _update_log(self, _event: object = None) -> None:
        """Apply the chosen value axis scale."""
        self.state.config.log_axis = self.log_var.get() == 'Log'
        self.redraw()
