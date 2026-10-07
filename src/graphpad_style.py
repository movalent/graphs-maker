"""GraphPad Prism look and feel expressed as matplotlib ``rcParams``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal

import matplotlib as mpl
from cycler import cycler
from matplotlib import font_manager
from matplotlib.colors import to_hex
from matplotlib.figure import Figure

PRISM_COLORS: Final[tuple[str, ...]] = (
    '#0000ff',
    '#ff0000',
    '#000000',
    '#008000',
    '#ff00ff',
    '#00ffff',
    '#996633',
    '#800000',
    '#808080',
    '#000080',
)
FALLBACK_FONTS: Final[tuple[str, ...]] = ('Arial', 'Helvetica', 'Liberation Sans', 'DejaVu Sans')

# The sizes and thicknesses Prism draws with. They are held as data and fed to
# :func:`rc_params`, so the renderer and the window, which shows the automatic value in a field
# so the user can read it off, take the same number rather than two copies that can drift.
DEFAULT_TICK_FONT: Final[int] = 11
DEFAULT_LEGEND_FONT: Final[int] = 8
DEFAULT_LINE_WIDTH: Final[float] = 0.8

# A sequential map that is dark at the low end is sampled across this window. Taking the top
# of a 256 step map by a fixed increment would hand a small graph several indistinguishable
# purples, and the darkest end sits almost on black, which is the colour of the bar outline.
DARK_LOW: Final[float] = 0.15
DARK_HIGH: Final[float] = 0.90
# A map that is pale at the low end, such as Blues or Reds, has to start further along or the
# first bar is almost white and vanishes against the page. These bounds keep every bar of
# those maps clearly visible.
PALE_LOW: Final[float] = 0.35
PALE_HIGH: Final[float] = 0.95
# The published Okabe-Ito colours, in their designed order. They are read from the front so
# that a small graph uses the most separable part of the palette rather than a slice of it.
OKABE_ITO: Final[tuple[str, ...]] = (
    '#000000',
    '#e69f00',
    '#56b4e9',
    '#009e73',
    '#f0e442',
    '#0072b2',
    '#d55e00',
    '#cc79a7',
)

# Which section of the palette menu a palette is listed under. Categorical palettes give
# unrelated bars clearly different colours, which is what an unordered set of conditions
# needs. Sequential palettes run dark to light, so colour carries a meaning: the order.
PaletteKind = Literal['categorical', 'sequential']


@dataclass(frozen=True, slots=True)
class Palette:
    """One selectable set of bar colours.

    Attributes:
        key: Stable name used in the saved settings and by :func:`palette_colors`.
        label: Text shown in the window.
        kind: Section of the menu the palette is listed under.
        colors: The colours themselves, for a categorical palette.
        colormap: Name of a matplotlib colormap, used by a sequential palette.
        colorblind: Whether the colours stay distinguishable for a reader with a colour
            vision deficiency. Kept as data rather than written into the label, so the label
            cannot claim a guarantee the palette does not carry.
        low: Where a sequential palette starts, as a fraction of the colormap.
        high: Where a sequential palette ends.

    """

    key: str
    label: str
    kind: PaletteKind = 'categorical'
    colors: tuple[str, ...] = ()
    colormap: str = ''
    colorblind: bool = False
    low: float = DARK_LOW
    high: float = DARK_HIGH

    @property
    def is_sequential(self) -> bool:
        """Return whether this palette is sampled from a continuous colormap.

        Okabe-Ito is registered as a colormap but is a fixed list of eight colours, so it is
        read from the front like any other categorical palette.
        """
        return self.kind == 'sequential'


def _fixed(key: str, label: str, colormap: str, size: int) -> tuple[str, ...]:
    """Return the fixed colours of a discrete matplotlib colormap, in their designed order.

    Args:
        key: Palette key, used only in a failure message.
        label: Human readable name, used only in a failure message.
        colormap: Name of the matplotlib colormap to read.
        size: How many colours the colormap holds.

    Returns:
        The colours as hex, read from the front of the map.

    """
    return tuple(to_hex(mpl.colormaps[colormap](index)) for index in range(size))


def _categorical(key: str, label: str, colors: tuple[str, ...], colorblind: bool = False) -> Palette:
    """Return a palette of fixed colours, read from the front.

    Args:
        key: Palette key.
        label: Text shown in the window.
        colors: The colours in their designed order.
        colorblind: Whether the colours stay separable under a colour vision deficiency.

    Returns:
        The palette description.

    """
    return Palette(key=key, label=label, kind='categorical', colors=colors, colorblind=colorblind)


def _sequential(key: str, colormap: str, pale_start: bool = False, colorblind: bool = False) -> Palette:
    """Return a palette sampled from a continuous colormap.

    Args:
        key: Palette key.
        colormap: Name of the matplotlib colormap to sample.
        pale_start: Whether the map is pale at its low end, in which case sampling starts
            further along so the first bar is not almost white.
        colorblind: Whether the colours stay separable under a colour vision deficiency.

    Returns:
        The palette description.

    """
    return Palette(
        key=key,
        label=f'{key} (colorblind)' if colorblind else key,
        kind='sequential',
        colormap=colormap,
        colorblind=colorblind,
        low=PALE_LOW if pale_start else DARK_LOW,
        high=PALE_HIGH if pale_start else DARK_HIGH,
    )


PALETTES: Final[dict[str, Palette]] = {
    palette.key: palette
    for palette in (
        # Categorical first, so the palettes that suit unrelated conditions are the ones
        # reached without scrolling.
        _categorical('tab10', 'tab10', _fixed('tab10', 'tab10', 'tab10', 10)),
        # Okabe-Ito is built to stay separable under all three common forms of colour vision
        # deficiency. Its first colour is black, so a leading bar is solid black; that is the
        # published order, and any single bar can still be recoloured afterwards.
        _categorical('okabe_ito', 'Okabe-Ito (colorblind)', OKABE_ITO, colorblind=True),
        _categorical('tab20', 'tab20', _fixed('tab20', 'tab20', 'tab20', 20)),
        _categorical('Dark2', 'Dark2', _fixed('Dark2', 'Dark2', 'Dark2', 8)),
        _categorical('Paired', 'Paired', _fixed('Paired', 'Paired', 'Paired', 12)),
        _categorical('Set1', 'Set1', _fixed('Set1', 'Set1', 'Set1', 9)),
        _categorical('Pastel1', 'Pastel1', _fixed('Pastel1', 'Pastel1', 'Pastel1', 9)),
        _sequential('viridis', 'viridis', colorblind=True),
        _sequential('magma', 'magma'),
        _sequential('inferno', 'inferno'),
        _sequential('plasma', 'plasma'),
        _sequential('cividis', 'cividis', colorblind=True),
        _sequential('Blues', 'Blues', pale_start=True),
        _sequential('Greens', 'Greens', pale_start=True),
        _sequential('Reds', 'Reds', pale_start=True),
        _sequential('YlOrRd', 'YlOrRd', pale_start=True),
        _sequential('PuBuGn', 'PuBuGn', pale_start=True),
        # The original GraphPad colours stay available below a divider, but they are no
        # longer the default: saturated blue on pure red and black is hard to read.
        _categorical('prism', 'GraphPad', PRISM_COLORS),
    )
}
# Tab10 is the default because it is a well established categorical scheme whose colours stay
# apart, which is what a set of unrelated conditions needs.
DEFAULT_PALETTE: Final[str] = 'tab10'
# The original GraphPad colours are listed under a heading of their own and last, so that the
# two grouped sections stay contiguous and the headings cannot mislead.
LEGACY_PALETTE: Final[str] = 'prism'
# The menu is shown in this order, each heading introducing the palettes that follow it.
PALETTE_KINDS: Final[tuple[PaletteKind, ...]] = ('categorical', 'sequential')


def resolve_font() -> str:
    """Return the first available font from the GraphPad preference list."""
    available = {font.name for font in font_manager.fontManager.ttflist}
    return next((name for name in FALLBACK_FONTS if name in available), 'sans-serif')


def _palette(palette: str) -> Palette:
    """Return a known palette, falling back to the GraphPad default.

    Args:
        palette: Palette key, as stored in the settings.

    Returns:
        The matching palette, or the default one for an unknown or empty name.

    """
    return PALETTES.get(palette, PALETTES[DEFAULT_PALETTE])


def palette_colors(palette: str, count: int) -> list[str]:
    """Return ``count`` colours spread across the chosen palette.

    A categorical palette is read from the front, which is the order it was designed in, and
    cycles once the bars outnumber its colours. A sequential palette is spread evenly across
    that palette's own window, because stepping a fixed increment along a 256 step map would
    hand a small graph several near identical purples, and because a map that is pale at its
    low end has to start further along or the first bar would be almost white.

    Args:
        palette: Palette key, as stored in the settings.
        count: How many colours are needed, one per bar.

    Returns:
        Exactly ``count`` colours in ``#rrggbb`` form.

    """
    chosen = _palette(palette)
    if count <= 0:
        return []
    if not chosen.is_sequential:
        return [chosen.colors[index % len(chosen.colors)] for index in range(count)]
    colormap = mpl.colormaps[chosen.colormap]
    steps = min(count, max(colormap.N, 1))
    spread = [chosen.low + (chosen.high - chosen.low) * index / max(steps - 1, 1) for index in range(steps)]
    first = [to_hex(colormap(step)) for step in spread]
    return [first[index % len(first)] for index in range(count)]


def default_color(index: int, palette: str = DEFAULT_PALETTE, count: int = 0) -> str:
    """Return one colour from the chosen palette.

    Args:
        index: Position of the sample in the drawing order, counted from zero.
        palette: Palette key, as stored in the settings.
        count: Total number of samples being coloured, needed so a continuous palette can be
            spread across the whole range. Treated as one when omitted.

    Returns:
        A colour in ``#rrggbb`` form.

    """
    return palette_colors(palette, max(count, index + 1))[index]


def rc_params() -> dict[str, Any]:
    """Return the matplotlib settings that reproduce the Prism default graph.

    Returns:
        A mapping of matplotlib ``rcParams`` keys to Prism like values.

    """
    return {
        'font.family': resolve_font(),
        'font.size': DEFAULT_TICK_FONT,
        'font.weight': 'normal',
        'axes.titlesize': 12,
        'axes.labelsize': DEFAULT_TICK_FONT,
        'axes.linewidth': DEFAULT_LINE_WIDTH,
        'axes.edgecolor': '#000000',
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.grid': False,
        'axes.axisbelow': True,
        'axes.prop_cycle': cycler(color=list(PRISM_COLORS)),
        'xtick.direction': 'out',
        'ytick.direction': 'out',
        'xtick.major.size': 3.5,
        'ytick.major.size': 3.5,
        'xtick.minor.size': 0.0,
        'ytick.minor.size': 0.0,
        'xtick.major.width': DEFAULT_LINE_WIDTH,
        'ytick.major.width': DEFAULT_LINE_WIDTH,
        'xtick.major.pad': 3.0,
        'ytick.major.pad': 3.0,
        'legend.frameon': False,
        'legend.fontsize': DEFAULT_LEGEND_FONT,
        'lines.linewidth': 1.0,
        'patch.linewidth': DEFAULT_LINE_WIDTH,
        'figure.figsize': (6.4, 4.8),
        'figure.dpi': 100,
        'figure.facecolor': '#ffffff',
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'savefig.facecolor': '#ffffff',
        'mathtext.default': 'regular',
    }


def apply_graphpad_style() -> None:
    """Push the Prism defaults into the global matplotlib configuration.

    Keys are set one at a time through ``rcParams``, which is typed against a fixed set
    of literal names and therefore rejects a bulk update from a plain dictionary.
    """
    for key, value in rc_params().items():
        mpl.rcParams[key] = value  # type: ignore[index]


def new_figure(width: float = 6.4, height: float = 4.8) -> Figure:
    """Create a figure pre-styled with the GraphPad defaults.

    Args:
        width: Figure width in inches.
        height: Figure height in inches.

    Returns:
        A blank Prism style figure.

    """
    apply_graphpad_style()
    return Figure(
        figsize=(width, height),
        dpi=100,
        facecolor='#ffffff',
        edgecolor='#000000',
        linewidth=DEFAULT_LINE_WIDTH,
    )
