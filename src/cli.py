"""Command line front end that turns an Excel file into a Prism style graph."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

# The batch entry point must never try to open a window, so the headless backend is
# selected here rather than in the package, which the interactive window shares.
os.environ.setdefault('MPLBACKEND', 'Agg')

from src.excel_reader import parse_columns, read_dataset, read_table, read_xy
from src.models import ORIENTATIONS, Dataset, PlotConfig
from src.plotting import plot_dataset

DEFAULT_OUTPUT = Path('output')
SUPPORTED_FORMATS = ('png', 'pdf', 'svg', 'jpg', 'tif')


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the command line interface.

    Returns:
        The configured parser.

    """
    parser = argparse.ArgumentParser(
        prog='graphpad',
        description='Create a GraphPad Prism style graph from an Excel data sheet.',
    )
    parser.add_argument('--input', type=Path, required=True, help='Path to the input .xlsx file.')
    parser.add_argument('--output', type=Path, help='Output image path; defaults to output/<input name>.<fmt>.')
    parser.add_argument('--format', choices=SUPPORTED_FORMATS, default='png', help='Output image format.')
    parser.add_argument('--dpi', type=int, default=300, help='Resolution of raster output.')
    parser.add_argument('--title', default=None, help='Optional figure title.')
    parser.add_argument('--log-axis', action='store_true', help='Use a logarithmic value axis.')
    parser.add_argument(
        '--error',
        choices=('sd', 'sem', 'none'),
        default='sd',
        help='Statistic drawn as error bars.',
    )
    parser.add_argument(
        '--color-by',
        choices=('sample', 'group'),
        default='sample',
        help='Whether palette colours follow each sample or each group.',
    )
    parser.add_argument('--order', nargs='*', default=[], help='Sample names in the desired left to right order.')
    parser.add_argument('--no-points', action='store_true', help='Hide the individual replicate points.')
    parser.add_argument('--jitter', type=float, default=0.0, help='Spread of replicates inside a bar, in bar widths.')
    parser.add_argument(
        '--gui',
        action='store_true',
        help='Open the interactive window instead of writing a file straight away.',
    )
    parser.add_argument(
        '--orientation',
        choices=ORIENTATIONS,
        default='vertical',
        help='Which way round the bars are drawn.',
    )
    parser.add_argument(
        '--scatter',
        action='store_true',
        help='Plot paired x and y values as points instead of drawing bars.',
    )
    parser.add_argument('--x-row', type=int, default=None, help='Row holding the scatter x values, 1 based.')
    parser.add_argument('--x-column', type=int, default=None, help='Column holding the scatter x values, 1 based.')
    parser.add_argument(
        '--y-columns',
        default='',
        help='Columns holding the scatter y values, 1 based, separated by commas or given as a range.',
    )
    return parser


def resolve_output(input_path: Path, output: Path | None, image_format: str) -> Path:
    """Work out where the image should be written.

    Args:
        input_path: The source workbook, used to derive a default file name.
        output: Explicit output path given on the command line, if any.
        image_format: Image format used when a suffix has to be added.

    Returns:
        The resolved output path.

    """
    if output is not None:
        return output if output.suffix else output.with_suffix(f'.{image_format}')
    return DEFAULT_OUTPUT / f'{input_path.stem}.{image_format}'


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Command line arguments, or ``None`` to read them from the process.

    Returns:
        A process exit code, ``0`` on success.

    """
    args = build_parser().parse_args(argv)
    # A scatter sheet has no Group header row, so it cannot be read as a bar sheet at all.
    # It is read from the rows and columns the caller named instead.
    dataset = _scatter_from_args(args) if args.scatter else read_dataset(args.input)
    config = _config_from_args(args)
    if args.gui:
        from src.app import GraphPadApp  # imported late so batch mode never needs a display
        from src.app_state import AppState

        GraphPadApp(AppState(dataset, config), args.input).run()
        return 0
    figure = plot_dataset(dataset, config)
    target = resolve_output(args.input, args.output, args.format)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(target, dpi=args.dpi)
    if dataset.series:
        print(f'Saved {target} with {len(dataset.series)} series and {dataset.points} points.')
        return 0
    print(f'Saved {target} with {len(dataset.samples)} samples in {len(dataset.groups)} groups.')
    return 0


def _scatter_from_args(args: argparse.Namespace) -> Dataset:
    """Read the sheet as a scatter plot from the rows and columns named on the command line.

    Args:
        args: The parsed command line arguments.

    Returns:
        A dataset holding the named points and nothing else, because a scatter sheet has no
        sample columns to summarise.

    Raises:
        SystemExit: When the x or y values were not named, since a scatter plot cannot be
            drawn without them and guessing which column was meant would be worse.

    """
    if args.x_row is None and args.x_column is None:
        message = 'A scatter plot needs --x-row or --x-column to say where the x values are.'
        raise SystemExit(message)
    if not args.y_columns:
        message = 'A scatter plot needs --y-columns to say which columns hold the y values.'
        raise SystemExit(message)
    table = read_table(args.input)
    series, x_label = read_xy(
        table,
        x_row=None if args.x_row is None else args.x_row - 1,
        x_column=None if args.x_column is None else args.x_column - 1,
        y_columns=tuple(column - 1 for column in parse_columns(args.y_columns)),
        path=args.input,
    )
    return Dataset(samples=(), series=series, x_label=x_label)


def _config_from_args(args: argparse.Namespace) -> PlotConfig:
    """Build the presentation settings described by the parsed arguments.

    Args:
        args: The parsed command line arguments.

    Returns:
        The settings to plot with.

    """
    return PlotConfig(
        sample_order=tuple(args.order),
        log_axis=args.log_axis,
        title=args.title,
        error_kind=args.error,
        color_by=args.color_by,
        jitter=args.jitter,
        show_points=not args.no_points,
        chart='scatter' if args.scatter else 'bar',
        orientation=args.orientation,
    )
