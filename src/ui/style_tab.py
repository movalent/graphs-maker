"""The Plot style tab: how the drawing itself is dressed.

This is the longest tab, because it holds every choice about the marks rather than about
what they say: joining points, showing replicates, turning the graph, the error bars, the
outline and fill of a bar, and the colours. Grouping sits at the bottom of it in a block of
its own, because it acts on the samples highlighted in the list rather than on the drawing.

The colour row above the tabs and the palette picker live here too, since both decide how
the marks are filled.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from src.app_state import FALLBACK_COLOR, HATCH_LABELS, HATCH_PATTERNS, normalize_hex
from src.graphpad_style import (
    DEFAULT_PALETTE,
    LEGACY_PALETTE,
    PALETTE_KINDS,
    PALETTES,
    palette_colors,
)
from src.models import (
    DEFAULT_POINT_TYPE,
    ORIENTATION_LABELS,
    ORIENTATIONS,
    POINT_LABELS,
    POINT_TYPES,
    ErrorKind,
    Orientation,
)
from src.ui.base import _SYNTHETIC_EVENT, PANEL_WIDTH, _AppBase
from src.ui.fields import label_to
from src.ui.widgets import SWATCH_HEIGHT, draw_swatch, dropdown_row, option_row, pair_row, section, swatch

JITTER_MAX = 0.6
# The orientations offered in the window. The ``inverted`` layout is still drawn by the
# renderer and still reachable from a saved file or the command line, but it is not one of
# the two a reader picks between here, so it is left out of this list rather than removed
# from the settings.
ORIENTATION_CHOICES: tuple[str, ...] = tuple(
    ORIENTATION_LABELS[one] for one in ORIENTATIONS if one != 'inverted'
)
# The graph a sheet is drawn as until the user says otherwise.
DEFAULT_ORIENTATION: Orientation = 'vertical'
# The error bars a bar graph can carry, and the caption each is offered under.
ERROR_CHOICES: dict[str, ErrorKind] = {'SD': 'sd', 'SEM': 'sem', 'None': 'none'}
ERROR_LABELS: dict[ErrorKind, str] = {'sd': 'SD', 'sem': 'SEM', 'none': 'None'}
# The shape a point is drawn as. The choices themselves are held in ``src.models``, beside the
# markers they stand for, so the caption in the window and the mark drawn cannot drift apart.
POINT_TYPE_CHOICES: tuple[str, ...] = tuple(POINT_LABELS[one] for one in POINT_TYPES)
# A palette swatch is a short strip of the palette's own colours, drawn the way a reference
# menu shows them: several blocks side by side rather than a single blended bar.
SWATCH_BLOCKS = 6
SWATCH_WIDTH = 84
# The palette picker is drawn as a combobox rather than a ttk.Button, because a button
# cannot be made the same height as the comboboxes beside it: the vista theme takes a
# button's height from its font and padding, and the smallest it will go is two pixels
# taller than a combobox. A button also centres its label, which reads as right aligned
# once a swatch is packed beside the text. These are the theme's own field colours, so the
# picker matches the other dropdowns instead of inventing a shade of its own.
FIELD_FACE = '#f0f0f0'
FIELD_BORDER = '#9a9a9a'


class StyleTabMixin(_AppBase):
    """How the marks are drawn: their shape, their fill and the colours they carry."""

    def _sync_style(self) -> None:
        """Put the Plot style tab's fields back, showing what is really in use."""
        self._refresh_groups()
        config = self.state.config
        self.error_var.set(ERROR_LABELS[config.error_kind])
        self.color_by_var.set(config.color_by.title())
        self.palette_key_var.set(config.palette)
        self._show_palette_swatch(config.palette)
        self.orientation_var.set(ORIENTATION_LABELS[config.orientation])
        self.grouped_var.set(config.grouped_layout)
        self.points_var.set(config.show_points)
        # The shape is put back here rather than through the style panel, because that panel
        # packs itself into view and this has to leave it hidden until a sample is chosen.
        # A highlighted series is filled in by the panel when the highlight moves.
        names = self._selected_samples()
        first = names[0] if names else ''
        self.point_type_var.set(POINT_LABELS[self.state.point_type_of(first) if first else config.point_type])
        self.jitter_var.set(config.jitter)
        # The thickness field shows the value in use, so an untouched field is never read as
        # a request to fix the line at the default the graph already uses.
        self.bar_width_var.set(f'{self.state.line_width_of("bar"):g}')

    def _build_style_panel(self, panel: ttk.Frame) -> None:
        """Create the tab holding how the bars themselves are drawn.

        The order is the order a graph is dressed in: the marks are joined, the replicates
        are shown and spread out, the bars are turned and given their error bars, their
        outline and their fill, and the colours are chosen last because they are the part
        most often left as they are.

        Args:
            panel: The Plot style tab frame.

        """
        # How the marks themselves are drawn belongs with the style of the drawing rather
        # than with what the graph as a whole says, so these live here.
        self.connect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            panel,
            text='Join the points with a line',
            variable=self.connect_var,
            command=self._update_connect,
        ).pack(anchor=tk.W)

        self.points_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            panel,
            text='Replicate points',
            variable=self.points_var,
            command=self._update_points,
        ).pack(anchor=tk.W, pady=(8, 0))

        self.jitter_var = tk.DoubleVar(value=0.0)
        ttk.Label(panel, text='Replicate spread', font=('Segoe UI', 8)).pack(anchor=tk.W, pady=(10, 0))
        ttk.Scale(panel, from_=0.0, to=JITTER_MAX, variable=self.jitter_var, command=self._update_jitter).pack(
            fill=tk.X
        )

        # The legend and the series names are separate choices, so neither is switched off
        # by turning the other on.
        self.point_labels_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            panel,
            text='Name each series at its rightmost point',
            variable=self.point_labels_var,
            command=self._update_point_labels,
        ).pack(anchor=tk.W, pady=(8, 0))

        self.orientation_var = tk.StringVar(value=ORIENTATION_LABELS[DEFAULT_ORIENTATION])
        option_row(
            panel,
            ('Graph orientation', self.orientation_var, ORIENTATION_CHOICES, self._update_orientation),
            (None, None, (), None),
        )

        self.error_var = tk.StringVar(value='SD')
        option_row(
            panel,
            ('Error bars', self.error_var, ('SD', 'SEM', 'None'), self._update_error),
            (None, None, (), None),
        )

        # The bar thickness is one setting for the whole graph rather than a per sample one,
        # because it describes the weight of the drawing rather than how a bar is coloured.
        # The hatch beside it is a placeholder: a bar's fill is really set per sample from
        # the block below, which is where a hatch has to be chosen from, because two bars
        # may carry different ones.
        self.bar_width_var = tk.StringVar()
        self.bar_hatch_var = tk.StringVar(value=HATCH_LABELS[0])
        pair_row(
            panel,
            ('Bar outline width', self.bar_width_var, (), self._update_line_width),
            ('Bar hatch', self.bar_hatch_var, HATCH_LABELS, None),
        )

        # The palette sits next to "Colour by" because both decide how the bars are coloured.
        # It is a custom menu rather than a combobox because a combobox dropdown is a plain
        # listbox, which can show an icon or a label per row but never both, so it cannot
        # show a colour swatch beside each palette name.
        self.palette_key_var = tk.StringVar(value=DEFAULT_PALETTE)
        self.palette_var = tk.StringVar(value=PALETTES[DEFAULT_PALETTE].label)
        self._build_palette_picker(panel)

        self.color_by_var = tk.StringVar(value='Sample')
        option_row(
            panel,
            ('Colour by', self.color_by_var, ('Sample', 'Group'), self._update_color_by),
            (None, None, (), None),
        )

        # The layout is a statement about how the samples sit next to one another rather
        # than about any one of them, so it belongs with the drawing rather than on General.
        self.grouped_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            panel,
            text='Group bars (Prism)',
            variable=self.grouped_var,
            command=self._update_grouped,
        ).pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(
            panel,
            text='Leaves the wider Prism gap between groups and names each group once.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 40,
        ).pack(anchor=tk.W)

        self.style_frame = ttk.Labelframe(panel, text='Bar style')
        # Created but deliberately not packed, so the panel only takes up room once a
        # sample has actually been selected and the controls mean something.
        self.style_name = ttk.Label(self.style_frame, text='', font=('Segoe UI', 9, 'bold'))
        self.style_name.pack(anchor=tk.W)

        self.edge_var = tk.StringVar()
        self.hatch_var = tk.StringVar(value=HATCH_LABELS[0])
        row = ttk.Frame(self.style_frame)
        row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(row, text='Outline', font=('Segoe UI', 8), width=9).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=self.edge_var, width=9)
        entry.pack(side=tk.LEFT, padx=(0, 4))
        entry.bind('<Return>', lambda _e: self._apply_edge())
        entry.bind('<FocusOut>', lambda _e: self._apply_edge())
        ttk.Button(row, text='Pick', width=6, command=self._pick_edge).pack(side=tk.LEFT)

        row = ttk.Frame(self.style_frame)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text='Hatch', font=('Segoe UI', 8), width=9).pack(side=tk.LEFT)
        combo = ttk.Combobox(row, textvariable=self.hatch_var, values=HATCH_LABELS, state='readonly', width=10)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        combo.bind('<<ComboboxSelected>>', lambda _e: self._apply_hatch())

        # A scatter series is drawn as points, so connecting them and naming them are
        # per series decisions that a bar never has to make. They are packed only for a
        # scatter plot, where the list holds series rather than samples.
        self.series_style_frame = ttk.Frame(self.style_frame)
        ttk.Label(
            self.series_style_frame,
            text='For the series highlighted in the list above.',
            font=('Segoe UI', 8),
        ).pack(anchor=tk.W, pady=(8, 0))
        self.connect_series_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.series_style_frame,
            text='Connect the points with a line',
            variable=self.connect_series_var,
            command=self._apply_series_style,
        ).pack(anchor=tk.W)
        self.label_series_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.series_style_frame,
            text='Name it at its rightmost point',
            variable=self.label_series_var,
            command=self._apply_series_style,
        ).pack(anchor=tk.W)
        ttk.Label(
            self.series_style_frame,
            text='Naming one series switches the labels on. The Scatter tab names them all.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 40,
        ).pack(anchor=tk.W, pady=(2, 0))

        # The shape of a point belongs here rather than in the drawing above, because a graph
        # often wants its series told apart by shape as well as by colour, and one shape for
        # the whole plot cannot do that.
        self.point_type_var = tk.StringVar(value=POINT_LABELS[DEFAULT_POINT_TYPE])
        # The dropdown is kept rather than packed into a local, so the window can offer the
        # shapes the settings know about without this module repeating that list.
        self.point_type_combo = dropdown_row(
            self.series_style_frame, 'Point type', self.point_type_var, POINT_TYPE_CHOICES, self._update_point_type
        )
        ttk.Label(
            self.series_style_frame,
            text='Leave on Round for every point unless a series is picked out.',
            font=('Segoe UI', 8),
            wraplength=PANEL_WIDTH - 40,
        ).pack(anchor=tk.W, pady=(2, 0))

        buttons = ttk.Frame(self.style_frame)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text='Clear style', command=self._clear_style).pack(side=tk.LEFT)

        # Grouping goes last: it acts on the samples highlighted in the list above rather than
        # on the drawing, so it reads as the last thing done rather than one of the settings.
        self._build_group_controls(panel)
    def _build_group_controls(self, panel: tk.Widget) -> None:
        """Create the block that moves samples into and out of a named group.

        This used to have a tab of its own. It is the act of grouping rather than a look at
        the graph, and it acts on the samples highlighted in the list above, so it sits at
        the bottom of the tab where the rest of the drawing is set rather than beside it.

        Args:
            panel: The Plot style tab frame.

        """
        box = section(panel, 'Groups')

        self.merge_name_var = tk.StringVar()
        ttk.Label(box, text='Group samples as', font=('Segoe UI', 8)).pack(anchor=tk.W)
        row = ttk.Frame(box)
        row.pack(fill=tk.X)
        entry = ttk.Entry(row, textvariable=self.merge_name_var, width=14)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind('<Return>', lambda _e: self._group_selection())
        ttk.Button(row, text='Apply', width=6, command=self._group_selection).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text='Ungroup', width=8, command=self._ungroup_selection).pack(side=tk.LEFT)

        ttk.Label(box, text='Tick the groups to combine', font=('Segoe UI', 8)).pack(anchor=tk.W, pady=(6, 0))
        self.group_vars: dict[str, tk.BooleanVar] = {}
        self.group_checks: list[ttk.Checkbutton] = []
        self.group_list = ttk.Frame(box)
        self.group_list.pack(fill=tk.X)
    def _group_selection(self, _event: object = None) -> None:
        """Move every sample highlighted in the list into the group named in the field.

        A blank field falls back to the first highlighted name, so grouping a single sample
        always does something rather than silently doing nothing.

        Args:
            _event: Unused; the button applies the grouping itself.

        """
        if self.syncing:
            return
        names = self._selected_samples()
        # One sample is not a grouping, and a blank name would name nothing, so in both cases
        # the click is ignored rather than half applied.
        name = self.merge_name_var.get().strip()
        if len(names) < 2 or not name:
            return
        for sample in names:
            self.state.set_group(sample, name)
        self._after_grouping_changed()
    def _ungroup_selection(self, _event: object = None) -> None:
        """Drop the group override of every highlighted sample, restoring the worksheet group.

        Args:
            _event: Unused; the button applies the grouping itself.

        """
        if self.syncing:
            return
        for sample in self._selected_samples():
            self.state.set_group(sample, '')
        self._after_grouping_changed()
    def _after_grouping_changed(self) -> None:
        """Refresh everything that shows the grouping after it has been edited.

        The selection is deliberately left alone: a grouping change moves where a bar is
        drawn, so the samples the user picked are still the ones they picked.
        """
        self._refresh_list()
        self._refresh_groups()
        self._on_row_selected(_SYNTHETIC_EVENT)
        self.redraw()
    def _refresh_groups(self) -> None:
        """Rebuild the group checkboxes to match the groups currently drawn.

        A group of one is not a grouping, so it is left off the list rather than offered as
        something that could be merged.
        """
        for check in self.group_checks:
            check.destroy()
        self.group_checks.clear()
        self.group_vars = {}
        for group in self.state.multi_groups():
            variable = tk.BooleanVar(value=False)
            check = ttk.Checkbutton(self.group_list, text=group, variable=variable)
            check.pack(anchor=tk.W)
            self.group_vars[group] = variable
            self.group_checks.append(check)
        if not self.group_vars:
            ttk.Label(self.group_list, text='No groups of more than one', font=('Segoe UI', 8)).pack(anchor=tk.W)
    def _ticked_groups(self) -> tuple[str, ...]:
        """Return the groups whose checkbox is ticked."""
        return tuple(group for group, variable in self.group_vars.items() if variable.get())
    def _merge_groups(self, _event: object = None) -> None:
        """Combine the ticked groups into the group named in the field.

        Args:
            _event: Unused; the button applies the merge itself.

        """
        ticked = self._ticked_groups()
        # Combining one group with itself changes nothing, so it takes at least two.
        name = self.merge_name_var.get().strip()
        if len(ticked) < 2 or not name:
            return
        self.state.merge_groups(ticked, name)
        self.merge_name_var.set('')
        self._after_grouping_changed()
    def _split_group(self, _event: object = None) -> None:
        """Move every highlighted sample out into a group of its own.

        Args:
            _event: Unused; the button applies the split itself.

        """
        ticked = self._ticked_groups()
        if not ticked:
            return
        for sample in self.state.samples:
            if sample.group in ticked:
                self.state.split_sample(sample.name)
        self._after_grouping_changed()
    def _apply_hex(self) -> None:
        """Apply the hex colour in the field to every selected sample."""
        if self.syncing:
            return
        names = self._selected_samples()
        value = normalize_hex(self.hex_var.get())
        if value is None:
            messagebox.showerror(
                'Invalid colour',
                f'Use a hex colour such as #ff0000.\n\nGot: {self.hex_var.get()!r}',
                parent=self.root,
            )
            self._show_selected_color()
            return
        for name in names:
            self.state.set_color(name, value)
        self._refresh_list()
        self._show_selected_color()
        self.redraw()
    def _reset_colors(self) -> None:
        """Return every sample to the GraphPad palette colour."""
        self.state.reset_colors()
        self._refresh_list()
        self._on_row_selected(_SYNTHETIC_EVENT)
        self.redraw()
    def _apply_edge(self) -> None:
        """Apply the outline colour in the field to every selected sample."""
        if self.syncing:
            return
        value = normalize_hex(self.edge_var.get())
        if value is None:
            return
        for name in self._selected_samples():
            self.state.set_edge_color(name, value)
        self.redraw()
    def _pick_edge(self) -> None:
        """Open the colour chooser for the bar outline of the selected samples."""
        names = self._selected_samples()
        if not names:
            return
        current = self.state.edge_of(names[0])
        chosen = colorchooser.askcolor(color=current, parent=self.root)
        if chosen[1] is None:
            return
        value = chosen[1].lower()
        for name in names:
            self.state.set_edge_color(name, value)
        self._show_selected_style()
        self.redraw()
    def _apply_hatch(self) -> None:
        """Apply the hatch chosen in the list to every selected sample."""
        if self.syncing:
            return
        pattern = HATCH_PATTERNS[HATCH_LABELS.index(self.hatch_var.get())]
        for name in self._selected_samples():
            self.state.set_hatch(name, pattern)
        self.redraw()
    def _apply_series_style(self, _event: object = None) -> None:
        """Connect or name the highlighted scatter series.

        Both are per series, because a graph often wants one line traced through its own
        points while the others stay as separate marks, and only some names legible when
        every one of them is written out beside the plot.

        Args:
            _event: Unused; the checkboxes apply the choice themselves.

        """
        if self.syncing:
            return
        names = set(self._selected_samples())
        if not names:
            # There is nothing to apply this to. The boxes are put back so that a click
            # with an empty selection cannot leave a tick showing for no reason.
            self.connect_series_var.set(False)
            self.label_series_var.set(False)
            return
        config = self.state.config
        connect = set(config.connect_series)
        labelled = set(config.label_series)
        if self.connect_series_var.get():
            connect |= names
        else:
            connect -= names
        if self.label_series_var.get():
            labelled |= names
            # Naming a series has to switch the master on as well. The renderer only draws
            # a name when it is, so a tick on its own would record the choice and change
            # nothing, which reads as a broken control rather than as a hidden prerequisite
            # the user is left to discover on another tab.
            config.point_labels = True
            self.point_labels_var.set(True)
        else:
            labelled -= names
        config.connect_series = tuple(sorted(connect))
        config.label_series = tuple(sorted(labelled))
        self.redraw()
    def _clear_style(self) -> None:
        """Return every selected sample to the default outline and no hatch."""
        for name in self._selected_samples():
            # An empty colour is refused by the state, so the entry is dropped instead, which
            # is what puts the bar back to the shared default outline.
            self.state.config.hatches.pop(name, None)
            self.state.config.edge_colors.pop(name, None)
            # The shape is dropped with them, so clearing a series' style returns its points to
            # the shape the whole graph is drawn with rather than leaving them apart from it.
            self.state.clear_point_type(name)
        self._show_selected_style()
        self.redraw()
    def _build_color_row(self, panel: tk.Widget) -> None:
        """Create the row that types a colour as a hex code.

        Args:
            panel: The control panel the row is added to.

        """
        box = ttk.Frame(panel)
        box.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(box, text='Colour').pack(side=tk.LEFT)
        self.hex_var = tk.StringVar()
        entry = ttk.Entry(box, textvariable=self.hex_var, width=11)
        entry.pack(side=tk.LEFT, padx=6)
        # Kept so the layout can be checked against the control below the sample list.
        self.hex_entry = entry
        entry.bind('<Return>', lambda _e: self._apply_hex())
        entry.bind('<FocusOut>', lambda _e: self._apply_hex())
        # The chooser sits beside the value it changes, and doubles as a preview of the
        # colour that is actually in use.
        self.swatch = tk.Button(box, text='  ', width=3, command=self._pick_color, relief=tk.RAISED, borderwidth=2)
        self.swatch.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(box, text='Apply', width=6, command=self._apply_hex).pack(side=tk.LEFT)
        ttk.Button(box, text='Reset', width=6, command=self._reset_colors).pack(side=tk.LEFT, padx=4)
    def _build_palette_picker(self, panel: ttk.Frame) -> None:
        """Create the control that opens the palette menu.

        The control carries the current palette's name and a swatch of it, so the choice in
        force is visible without opening the menu.

        It is a frame drawn like a combobox rather than a ttk.Button, for two reasons. A ttk
        widget is not a container, so a swatch packed inside a button fights the theme's own
        element layout, which both collapsed the button and centred its text over the swatch.
        And a button cannot be given the height of a combobox: the vista theme derives a
        button's height from its font and padding, and the smallest it goes is still two
        pixels taller than the dropdowns beside it. The frame is sized to a real combobox
        measured from the theme instead, so the two line up.

        Args:
            panel: The Groups tab frame the picker is added to.

        """
        ttk.Label(panel, text='Colour palette', font=('Segoe UI', 8)).pack(anchor=tk.W, pady=(10, 0))
        self.palette_button = tk.Frame(
            panel,
            bg=FIELD_FACE,
            highlightthickness=1,
            highlightbackground=FIELD_BORDER,
            takefocus=True,
        )
        self.palette_button.pack(fill=tk.X)
        # A readonly combobox is the control the picker is imitating, so its own height is
        # the measurement taken rather than a number guessed here.
        probe = ttk.Combobox(self.palette_button, state='readonly', width=1)
        self.palette_button.configure(height=max(probe.winfo_reqheight(), SWATCH_HEIGHT + 4))
        probe.destroy()
        self.palette_swatch = swatch(self.palette_button, SWATCH_BLOCKS, SWATCH_WIDTH)
        self.palette_swatch.pack(side=tk.RIGHT, padx=4)
        # The name is a label rather than button text so it can be aligned to the left edge,
        # which is how a combobox presents its value and how a button does not.
        self.palette_name = ttk.Label(
            self.palette_button,
            textvariable=self.palette_var,
            font=('Segoe UI', 9),
            background=FIELD_FACE,
            anchor=tk.W,
        )
        self.palette_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        # The frame does not own the click, so the label and the swatch each need it, or
        # clicking them would do nothing while the rest of the row worked.
        for widget in (self.palette_button, self.palette_name, self.palette_swatch):
            widget.bind('<Button-1>', self._open_palette_menu)
        self.palette_button.bind('<Return>', self._open_palette_menu)
        self._show_palette_swatch(self.palette_key_var.get())
    def _show_palette_swatch(self, key: str) -> None:
        """Redraw the button's swatch from the palette currently in use.

        The colours come from the same helper the graph uses, so the swatch cannot show
        something the graph will not actually use.

        Args:
            key: Palette key, as stored in the settings.

        """
        self.palette_var.set(PALETTES.get(key, PALETTES[DEFAULT_PALETTE]).label)
        draw_swatch(self.palette_swatch, palette_colors(key, SWATCH_BLOCKS))
    def _open_palette_menu(self, _event: object = None) -> None:
        """Open the palette menu under the control, or close it if it is already open.

        Args:
            _event: Unused; the control is bound directly rather than through a wrapper.

        """
        if self.palette_popup is not None and self.palette_popup.winfo_exists():
            self._close_palette_menu()
            return
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        frame = ttk.Frame(popup, relief=tk.RAISED, borderwidth=1)
        frame.pack(fill=tk.BOTH, expand=True)
        current = self.state.config.palette
        # The legacy palette is categorical but is listed under a heading of its own, so it is
        # left out of the grouped sections and drawn last. Without the exclusion it would
        # appear twice, once under Categorical and once on its own.
        sections: list[tuple[str, list[str]]] = [
            (
                kind.title(),
                [key for key, palette in PALETTES.items() if palette.kind == kind and key != LEGACY_PALETTE],
            )
            for kind in PALETTE_KINDS
        ]
        sections.append(('GraphPad', [LEGACY_PALETTE]))
        for heading, keys in sections:
            if not keys:
                continue
            ttk.Label(frame, text=heading, font=('Segoe UI', 8, 'bold')).pack(anchor=tk.W, padx=8, pady=(8, 2))
            for key in keys:
                self._palette_row(frame, key, PALETTES[key].label, current == key)
        # The window is placed after it is built, because its height is only known once every
        # row has been packed.
        self.palette_popup = popup
        self._place_palette_menu()
        popup.bind('<Escape>', lambda _e: self._close_palette_menu())
        popup.bind('<FocusOut>', lambda _e: self.root.after(80, self._close_if_clicked_elsewhere))
        popup.focus_force()
    def _palette_row(self, parent: ttk.Frame, key: str, label: str, current: bool) -> None:
        """Add one clickable palette row, with its swatch, to the menu.

        Args:
            parent: The menu frame the row is added to.
            key: Palette key this row selects.
            label: Text shown for the palette.
            current: Whether this palette is already in use, which is marked.

        """
        row = ttk.Frame(parent)
        row.pack(fill=tk.X)
        text = ttk.Label(row, text=label, font=('Segoe UI', 9, 'bold' if current else 'normal'))
        text.pack(side=tk.LEFT, padx=(8, 4), pady=1)
        # Named apart from the builder, so that painting it is not read as calling the local.
        strip = swatch(row, SWATCH_BLOCKS, SWATCH_WIDTH)
        strip.pack(side=tk.RIGHT, padx=6)
        draw_swatch(strip, palette_colors(key, SWATCH_BLOCKS))
        def choose(event: tk.Event[tk.Misc], chosen: str = key) -> None:
            self._choose_palette(chosen)

        def raise_row(event: tk.Event[tk.Misc], host: ttk.Frame = row) -> None:
            host.configure(relief=tk.RAISED)

        def lower_row(event: tk.Event[tk.Misc], host: ttk.Frame = row) -> None:
            host.configure(relief=tk.FLAT)

        for widget in (row, text, strip):
            widget.bind('<Button-1>', choose)
            # Only the row itself is raised, so a highlight does not jitter between the
            # label and the swatch as the pointer crosses them.
            widget.bind('<Enter>', raise_row)
            widget.bind('<Leave>', lower_row)
        # A canvas takes no focus, so the label beside it carries the keyboard selection.
        text.configure(takefocus=True)
        text.bind('<Return>', choose)
    def _place_palette_menu(self) -> None:
        """Move the menu so that it opens just under the button and inside the screen."""
        if self.palette_popup is None:
            return
        self.palette_popup.update_idletasks()
        left = self.palette_button.winfo_rootx()
        below = self.palette_button.winfo_rooty() + self.palette_button.winfo_height()
        height = self.palette_popup.winfo_reqheight()
        screen_h = self.root.winfo_screenheight()
        # A menu taller than the space below the button opens upwards rather than running off
        # the bottom of the screen.
        top = below if below + height <= screen_h else max(self.palette_button.winfo_rooty() - height, 0)
        self.palette_popup.geometry(f'+{left}+{top}')
    def _close_if_clicked_elsewhere(self) -> None:
        """Close the menu once focus has genuinely moved off it.

        Focus is given back to the window as soon as the menu opens, so the first FocusOut
        is not by itself a reason to close and a click inside would be ignored.
        """
        if self.palette_popup is None or not self.palette_popup.winfo_exists():
            return
        if self.root.focus_get() is not None and str(self.root.focus_get()).startswith(str(self.palette_popup)):
            return
        self._close_palette_menu()
    def _close_palette_menu(self) -> None:
        """Destroy the palette menu if it is open."""
        if self.palette_popup is not None:
            if self.palette_popup.winfo_exists():
                self.palette_popup.destroy()
            self.palette_popup = None
    def _choose_palette(self, key: str) -> None:
        """Apply a palette chosen from the menu and close it.

        Args:
            key: Palette key the user picked.

        """
        self.palette_key_var.set(key)
        self._close_palette_menu()
        self._update_palette()
    def _update_palette(self) -> None:
        """Apply the chosen colour palette to every sample that has no colour of its own.

        Choosing a palette is a statement about the whole graph, so any colour the user had
        set by hand is dropped. Otherwise a single overridden bar would keep an old colour
        that no longer belongs to the chosen palette. Per bar colours can be set again
        afterwards, which is the way to pull one bar out of the scheme.

        Args:
            _event: Unused; the menu applies the palette itself.

        """
        if self.syncing:
            return
        chosen = self.palette_key_var.get()
        if chosen not in PALETTES:
            chosen = DEFAULT_PALETTE
        if chosen == self.state.config.palette:
            self._show_palette_swatch(chosen)
            return
        self.state.config.palette = chosen
        self.state.config.colors.clear()
        # The list rows are tinted with the same palette, so they are rebuilt too.
        self._refresh_list()
        self._show_selected_color()
        self._show_palette_swatch(chosen)
        self.redraw()
    def _update_color_by(self, _event: object = None) -> None:
        """Apply whether colours follow samples or whole groups.

        Switching between the two changes which palette entry a sample takes, so the
        fields showing the highlighted sample's colour are refreshed as well. Leaving them
        would keep the previous mode's colour on screen and make the change look as though
        it had not been applied.
        """
        self.state.config.color_by = 'group' if self.color_by_var.get() == 'Group' else 'sample'
        self._refresh_list()
        self._show_selected_color()
        self.redraw()
    def _update_point_type(self, _event: object = None) -> None:
        """Give the highlighted series its own point shape, or every point one shape.

        A shape chosen with a series highlighted belongs to that series alone, which is how
        series are told apart when one shape for the whole plot cannot do it. With nothing
        highlighted there is no series to give it to, so it becomes the shape every point
        follows, and the series that had one of their own go back to following it.

        A caption the window does not know falls back to the default rather than being stored,
        so a stale field cannot leave the renderer with a shape it has no marker for.

        Args:
            _event: Unused; the dropdown applies the choice itself.

        """
        if self.syncing:
            return
        chosen = label_to(POINT_TYPES, POINT_LABELS, self.point_type_var.get(), DEFAULT_POINT_TYPE)
        names = self._selected_samples()
        if not names:
            self.state.config.point_type = chosen
            # The graph is about to be drawn with one shape, so a series that was picked out of
            # it has to stop claiming one of its own.
            self.state.config.point_types.clear()
            self.redraw()
            return
        for name in names:
            if chosen == DEFAULT_POINT_TYPE:
                # The default is stored as no choice at all, so the series follows the graph
                # rather than being pinned to a shape that happens to match it today.
                self.state.clear_point_type(name)
            else:
                self.state.set_point_type(name, chosen)
        self.redraw()
    def _update_grouped(self) -> None:
        """Apply the Prism grouped layout, which spaces the groups apart.

        Grouping with a single group, or with every sample in one, would add no boundary at
        all, so the layout is left alone in that case rather than redrawing a graph that
        already looks the same.
        """
        self.state.config.grouped_layout = bool(self.grouped_var.get()) and len(self.state.groups()) > 1
        self.redraw()
    def _update_points(self) -> None:
        """Show or hide the individual replicate points."""
        self.state.config.show_points = bool(self.points_var.get())
        self.redraw()
    def _update_jitter(self, value: str) -> None:
        """Apply the replicate spread chosen on the slider."""
        self.state.config.jitter = float(value)
        self.redraw()
    def _update_orientation(self, _event: object = None) -> None:
        """Turn the graph so the values run across rather than up."""
        if self.syncing:
            return
        self.state.config.orientation = label_to(
            ORIENTATIONS, ORIENTATION_LABELS, self.orientation_var.get(), DEFAULT_ORIENTATION
        )
        self.redraw()
    def _update_error(self, _event: object = None) -> None:
        """Apply the chosen error bar statistic."""
        self.state.config.error_kind = ERROR_CHOICES[self.error_var.get()]
        self.redraw()
    def _pick_color(self) -> None:
        """Open the colour chooser for the selected sample.

        The current colour is passed to the chooser only when Tk can parse it, because the
        chooser calls ``winfo_rgb`` on that value and raises a bare Tcl error window for
        anything it does not recognise.
        """
        names = self._selected_samples()
        if not names:
            return
        current = normalize_hex(self.state.color_of(names[0])) or FALLBACK_COLOR
        try:
            chosen = colorchooser.askcolor(color=current, parent=self.root)
        except tk.TclError:
            chosen = colorchooser.askcolor(parent=self.root)
        if chosen[1]:
            for name in names:
                self.state.set_color(name, chosen[1])
            self._refresh_list()
            self.redraw()


