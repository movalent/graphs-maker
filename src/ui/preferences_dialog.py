"""The modal dialog for persistent application preferences."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.graphpad_style import PALETTES
from src.models import CHART_LABELS, ORIENTATION_LABELS, SAMPLE_CHARTS
from src.preferences import EXPORT_FORMATS, Preferences

PreferenceApplier = Callable[[Preferences], bool]


class PreferencesDialog:
    """Edit application defaults without changing the graph currently being edited."""

    def __init__(self, parent: tk.Tk, preferences: Preferences, apply: PreferenceApplier) -> None:
        """Build and display the preferences window.

        Args:
            parent: Main application window.
            preferences: Current preference values.
            apply: Saves and activates preferences, returning whether that succeeded.

        """
        self.window = tk.Toplevel(parent)
        self.window.title('Preferences')
        self.window.transient(parent)
        self.window.resizable(False, False)
        self._apply = apply
        self._strings: dict[str, tk.StringVar] = {}
        self._booleans: dict[str, tk.BooleanVar] = {}
        self._build(preferences)
        self.window.protocol('WM_DELETE_WINDOW', self.window.destroy)
        self.window.grab_set()
        self.window.focus_set()

    def _build(self, preferences: Preferences) -> None:
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        graph = ttk.Frame(notebook, padding=12)
        export = ttk.Frame(notebook, padding=12)
        interface = ttk.Frame(notebook, padding=12)
        behavior = ttk.Frame(notebook, padding=12)
        notebook.add(graph, text='Graph Defaults')
        notebook.add(export, text='Export')
        notebook.add(interface, text='Interface')
        notebook.add(behavior, text='Behavior')

        self._choice(
            graph,
            'Default chart',
            'default_chart',
            tuple(CHART_LABELS[kind] for kind in SAMPLE_CHARTS),
            {CHART_LABELS[kind]: kind for kind in SAMPLE_CHARTS},
            preferences.default_chart,
        )
        self._choice(
            graph,
            'Orientation',
            'default_orientation',
            tuple(ORIENTATION_LABELS.values()),
            {label: value for value, label in ORIENTATION_LABELS.items()},
            preferences.default_orientation,
        )
        self._choice(
            graph,
            'Error bars',
            'default_error_kind',
            ('SD', 'SEM', 'None'),
            {'SD': 'sd', 'SEM': 'sem', 'None': 'none'},
            preferences.default_error_kind,
        )
        self._choice(
            graph,
            'Color by',
            'default_color_by',
            ('Sample', 'Group'),
            {'Sample': 'sample', 'Group': 'group'},
            preferences.default_color_by,
        )
        self._choice(
            graph,
            'Palette',
            'default_palette',
            tuple(palette.label for palette in PALETTES.values()),
            {palette.label: palette.key for palette in PALETTES.values()},
            preferences.default_palette,
        )
        self._choice(
            graph,
            'Legend position',
            'default_legend_position',
            ('Above graph', 'Right of graph', 'Top right (inside graph)'),
            {'Above graph': 'above', 'Right of graph': 'right', 'Top right (inside graph)': 'inside'},
            preferences.default_legend_position,
        )
        self._check(graph, 'Show individual points', 'default_show_points', preferences.default_show_points)
        self._number(graph, 'Point jitter (0 to 1)', 'default_jitter', preferences.default_jitter)
        self._check(graph, 'Connect points', 'default_connect_points', preferences.default_connect_points)

        self._choice(
            export,
            'Default image format',
            'default_export_format',
            tuple(format_.upper() for format_ in EXPORT_FORMATS),
            {format_.upper(): format_ for format_ in EXPORT_FORMATS},
            preferences.default_export_format,
        )
        self._number(export, 'Resolution (DPI)', 'default_export_dpi', preferences.default_export_dpi)
        self._check(
            export,
            'Transparent background by default',
            'default_transparent_background',
            preferences.default_transparent_background,
        )

        self._number(interface, 'Control panel width (pixels)', 'panel_width', preferences.panel_width)
        ttk.Label(interface, text='Panel width changes take effect immediately.').pack(anchor=tk.W, pady=(4, 8))
        self._text(interface, 'UI font family', 'ui_font_family', preferences.ui_font_family)
        self._number(interface, 'UI font size', 'ui_font_size', preferences.ui_font_size)

        self._check(
            behavior, 'Automatically refresh graph preview', 'auto_refresh_preview', preferences.auto_refresh_preview
        )
        self._number(behavior, 'Undo history limit', 'undo_history_limit', preferences.undo_history_limit)
        self._check(behavior, 'Show confirmation dialogs', 'show_confirmations', preferences.show_confirmations)
        file_handling = ttk.LabelFrame(behavior, text='File handling', padding=8)
        file_handling.pack(fill=tk.X, pady=(12, 0))
        self._directory(file_handling, 'Default input directory', 'default_input_dir', preferences.default_input_dir)
        self._directory(file_handling, 'Default output directory', 'default_output_dir', preferences.default_output_dir)
        self._check(
            file_handling,
            'Remember last used input/output directories',
            'remember_last_directories',
            preferences.remember_last_directories,
        )
        ttk.Label(
            behavior,
            text='Automatic project saving is unavailable until editable project files are supported.',
            wraplength=400,
        ).pack(anchor=tk.W, pady=(12, 0))

        buttons = ttk.Frame(self.window, padding=(10, 0, 10, 10))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text='Reset to Defaults', command=self._reset).pack(side=tk.LEFT)
        ttk.Button(buttons, text='Cancel', command=self.window.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text='Apply', command=self._apply_changes).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(buttons, text='OK', command=self._accept).pack(side=tk.RIGHT, padx=(0, 6))

    def _choice(
        self,
        parent: ttk.Frame,
        label: str,
        name: str,
        options: tuple[str, ...],
        mapping: dict[str, str],
        current: str,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=25).pack(side=tk.LEFT)
        variable = tk.StringVar(value=next((caption for caption, value in mapping.items() if value == current), ''))
        self._strings[name] = variable
        combo = ttk.Combobox(row, textvariable=variable, values=options, state='readonly', width=28)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _number(self, parent: ttk.Frame, label: str, name: str, current: int | float) -> None:
        self._text(parent, label, name, str(current))

    def _text(self, parent: ttk.Frame, label: str, name: str, current: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=25).pack(side=tk.LEFT)
        variable = tk.StringVar(value=current)
        self._strings[name] = variable
        ttk.Entry(row, textvariable=variable, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _check(self, parent: tk.Widget, label: str, name: str, current: bool) -> None:
        variable = tk.BooleanVar(value=current)
        self._booleans[name] = variable
        ttk.Checkbutton(parent, text=label, variable=variable).pack(anchor=tk.W, pady=4)

    def _directory(self, parent: tk.Widget, label: str, name: str, current: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=25).pack(side=tk.LEFT)
        variable = tk.StringVar(value=current)
        self._strings[name] = variable
        ttk.Entry(row, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text='Browse…', command=lambda: self._browse_directory(variable)).pack(
            side=tk.LEFT,
            padx=(5, 0),
        )

    def _browse_directory(self, variable: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(
            parent=self.window,
            initialdir=variable.get() or str(Path.home()),
        )
        if chosen:
            variable.set(chosen)

    def _reset(self) -> None:
        self._load_values(Preferences())

    def _load_values(self, preferences: Preferences) -> None:
        for name, variable in self._strings.items():
            value = getattr(preferences, name)
            if name == 'default_chart':
                value = CHART_LABELS[value]
            elif name == 'default_orientation':
                value = ORIENTATION_LABELS[value]
            elif name == 'default_error_kind':
                value = {'sd': 'SD', 'sem': 'SEM', 'none': 'None'}[value]
            elif name == 'default_color_by':
                value = {'sample': 'Sample', 'group': 'Group'}[value]
            elif name == 'default_palette':
                value = PALETTES[value].label
            elif name == 'default_legend_position':
                value = {'above': 'Above graph', 'right': 'Right of graph', 'inside': 'Top right (inside graph)'}[value]
            elif name == 'default_export_format':
                value = value.upper()
            variable.set(str(value))
        for name, boolean_variable in self._booleans.items():
            boolean_variable.set(getattr(preferences, name))

    def _read_preferences(self) -> Preferences:
        mappings: dict[str, dict[str, str]] = {
            'default_chart': {CHART_LABELS[kind]: kind for kind in SAMPLE_CHARTS},
            'default_orientation': {label: value for value, label in ORIENTATION_LABELS.items()},
            'default_error_kind': {'SD': 'sd', 'SEM': 'sem', 'None': 'none'},
            'default_color_by': {'Sample': 'sample', 'Group': 'group'},
            'default_palette': {palette.label: palette.key for palette in PALETTES.values()},
            'default_legend_position': {
                'Above graph': 'above',
                'Right of graph': 'right',
                'Top right (inside graph)': 'inside',
            },
            'default_export_format': {format_.upper(): format_ for format_ in EXPORT_FORMATS},
        }
        values: dict[str, object] = {name: variable.get() for name, variable in self._strings.items()}
        for name, mapping in mappings.items():
            caption = str(values[name])
            if caption not in mapping:
                raise ValueError(f'Choose a valid value for {name.replace("_", " ")}.')
            values[name] = mapping[caption]
        for name in ('default_jitter',):
            values[name] = float(str(values[name]))
        for name in ('default_export_dpi', 'panel_width', 'ui_font_size', 'undo_history_limit'):
            values[name] = int(str(values[name]))
        values.update({name: variable.get() for name, variable in self._booleans.items()})
        if not 0 <= float(str(values['default_jitter'])) <= 1:
            raise ValueError('Point jitter must be between 0 and 1.')
        for name, low, high in (
            ('default_export_dpi', 72, 1200),
            ('panel_width', 240, 600),
            ('ui_font_size', 6, 24),
            ('undo_history_limit', 1, 1000),
        ):
            number = int(str(values[name]))
            if not low <= number <= high:
                raise ValueError(f'{name.replace("_", " ").capitalize()} must be between {low} and {high}.')
        if not str(values['ui_font_family']).strip():
            raise ValueError('UI font family cannot be empty.')
        values['ui_font_family'] = str(values['ui_font_family']).strip()
        return Preferences.from_dict(values)

    def _apply_changes(self) -> bool:
        try:
            preferences = self._read_preferences()
        except (ValueError, tk.TclError) as error:
            messagebox.showerror('Invalid preferences', str(error), parent=self.window)
            return False
        return self._apply(preferences)

    def _accept(self) -> None:
        if self._apply_changes():
            self.window.destroy()
