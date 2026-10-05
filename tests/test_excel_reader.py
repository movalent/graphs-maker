"""Tests for the Excel reader against the real input file and synthetic workbooks."""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest
from src.excel_reader import (
    ExcelLayoutError,
    ExcelLayoutWarning,
    ScatterLayout,
    SheetLayout,
    cell_number,
    detect_scatter_layout,
    read_dataset,
    read_table,
    read_xy,
    xy_column_labels,
    xy_row_labels,
)
from src.models import Dataset

INPUT_FILE = Path(__file__).resolve().parents[1] / 'input' / 'Conc_bar_26-09-27.xlsx'


def write_book(tmp_path: Path, rows: list[list[object]], name: str = 'book.xlsx') -> Path:
    """Write a header-less worksheet so the reader sees the same layout as Excel."""
    path = tmp_path / name
    pd.DataFrame(rows).to_excel(path, index=False, header=False)
    return path


@pytest.fixture
def real_dataset() -> Dataset:
    return read_dataset(INPUT_FILE)


def test_reads_every_measured_column(real_dataset: Dataset) -> None:
    assert len(real_dataset.samples) == 8


def test_detects_replicate_rows_and_value_label(real_dataset: Dataset) -> None:
    assert real_dataset.y_label == 'Conc.1, ng/uL'
    # The second replicate label has deliberate trailing 'l' padding to stress the preview
    # column layout. We only assert the meaningful prefix here.
    assert real_dataset.replicate_labels[0] == 'Conc.1, ng/uL'
    assert real_dataset.replicate_labels[1].startswith('Conc.2, ng/uL')


def test_forward_fills_group_labels_across_columns(real_dataset: Dataset) -> None:
    assert real_dataset.groups == ('WT Phi29', 'Phi29-XT', 'EquiPhi29', 'Saiyan 1', 'Saitan 2')
    assert len(real_dataset.group_of('WT Phi29')) == 4
    assert len(real_dataset.group_of('Phi29-XT')) == 1


def test_sample_names_prefer_condition_then_group(real_dataset: Dataset) -> None:
    assert [sample.name for sample in real_dataset.samples[:4]] == ['Control', '42C', 'Low Mg', 'Low pDNA']
    assert [sample.name for sample in real_dataset.samples[4:]] == [
        'Phi29-XT',
        'EquiPhi29',
        'Saiyan 1',
        'Saitan 2',
    ]


def test_statistics_match_the_sheet(real_dataset: Dataset) -> None:
    means = [sample.mean for sample in real_dataset.samples]
    # Low pDNA: (120.224 + 111) / 2 = 115.612. The 120.224 is a deliberate text-typed
    # high-precision value in the fixture (also tested in test_app.py and test_excel_reader.py).
    assert means == pytest.approx([205.0, 95.0, 107.5, 115.612, 565.0, 605.0, 802.5, 497.5])
    assert all(sample.n == 2 for sample in real_dataset.samples)
    assert real_dataset.samples[0].sd == pytest.approx(7.0710678, rel=1e-6)
    assert real_dataset.samples[0].sem == pytest.approx(5.0, rel=1e-6)


def test_skips_leading_empty_rows(tmp_path: Path) -> None:
    book = write_book(
        tmp_path,
        [
            [None, None, None],
            ['Group', 'A', 'B'],
            ['Condition', 'only', 'only'],
            ['Value', 1.0, 2.0],
            ['Value', 3.0, 4.0],
        ],
    )
    dataset = read_dataset(book)
    assert [sample.name for sample in dataset.samples] == ['A', 'B']
    assert dataset.y_label == 'Value'
    assert dataset.samples[0].values == (1.0, 3.0)


def test_replicates_without_condition_row(tmp_path: Path) -> None:
    book = write_book(tmp_path, [['Group', 'A', 'B'], ['Value', 1.0, 2.0], ['Value', 3.0, 4.0]])
    dataset = read_dataset(book)
    assert [sample.name for sample in dataset.samples] == ['A', 'B']
    assert dataset.samples[0].values == (1.0, 3.0)


def test_non_numeric_replicate_is_skipped_with_warning(tmp_path: Path) -> None:
    book = write_book(tmp_path, [['Group', 'A'], ['Value', 1.0], ['Value', 'bad']])
    with pytest.warns(ExcelLayoutWarning):
        dataset = read_dataset(book)
    assert dataset.samples[0].values == (1.0,)


def test_single_replicate_warns(tmp_path: Path) -> None:
    book = write_book(tmp_path, [['Group', 'A'], ['Value', 1.0]])
    with pytest.warns(ExcelLayoutWarning, match='single replicate'):
        dataset = read_dataset(book)
    assert dataset.samples[0].sd == 0.0


def test_missing_group_row_raises(tmp_path: Path) -> None:
    book = write_book(tmp_path, [['Something', 'A'], ['Value', 1.0]])
    with pytest.raises(ExcelLayoutError, match='Group'):
        read_dataset(book)


def test_detects_the_rows_of_the_real_sheet() -> None:
    """The window previews what the reader worked out, so it has to be the real answer."""
    from src.excel_reader import detect_layout, read_table

    layout = detect_layout(read_table(INPUT_FILE), INPUT_FILE)
    assert layout.group_row == 0
    assert layout.condition_row == 1
    assert layout.first_data_row == 2


def test_an_explicit_layout_reads_the_same_sheet(real_dataset: Dataset) -> None:
    """Pointing at the detected rows must give exactly the dataset the reader found itself."""
    assert read_dataset(INPUT_FILE, SheetLayout(0, 1, 2)) == real_dataset


def test_rows_can_be_chosen_where_there_are_no_markers(tmp_path: Path) -> None:
    """A sheet with no Group or Condition marker is the case the window is really for."""
    book = write_book(
        tmp_path,
        [
            ['Batch', 'one', 'two'],
            [None, 1.0, 2.0],
            [None, 3.0, 4.0],
        ],
    )
    dataset = read_dataset(book, SheetLayout(group_row=0, condition_row=None, first_data_row=1))
    # With no sample name row the group name is used for both, which is what the reader has
    # always done when a sheet carries no Condition marker.
    assert [sample.name for sample in dataset.samples] == ['one', 'two']
    assert dataset.samples[0].values == (1.0, 3.0)
    assert dataset.groups == ('one', 'two')


def test_a_chosen_condition_row_names_the_samples(tmp_path: Path) -> None:
    """The sample name row is the one the user pointed at, whatever it is called."""
    book = write_book(
        tmp_path,
        [
            ['Group', 'A', 'B'],
            ['not a marker', 'left', 'right'],
            ['Value', 1.0, 2.0],
            ['Value', 3.0, 4.0],
        ],
    )
    dataset = read_dataset(book, SheetLayout(group_row=0, condition_row=1, first_data_row=2))
    assert [sample.name for sample in dataset.samples] == ['left', 'right']


def test_a_row_outside_the_sheet_is_refused(tmp_path: Path) -> None:
    book = write_book(tmp_path, [['Group', 'A'], ['Value', 1.0]])
    with pytest.raises(ExcelLayoutError, match='outside the sheet'):
        read_dataset(book, SheetLayout(group_row=0, condition_row=None, first_data_row=9))


def test_x_values_read_down_a_column(tmp_path: Path) -> None:
    """The tidy layout: one x per data row, so every y column shares the same x values."""
    book = write_book(
        tmp_path,
        [
            ['Dose', 'Resp A', 'Resp B'],
            [1.0, 10.0, 5.0],
            [2.0, 12.0, 6.5],
            [4.0, 15.0, 7.1],
        ],
    )
    table = read_table(book)
    series, x_label = read_xy(table, x_column=0, y_columns=(1, 2), first_data_row=1, path=book)
    assert x_label == 'Dose'
    assert [one.name for one in series] == ['Resp A', 'Resp B']
    assert [(p.x, p.y) for p in series[0].points] == [(1.0, 10.0), (2.0, 12.0), (4.0, 15.0)]
    assert [(p.x, p.y) for p in series[1].points] == [(1.0, 5.0), (2.0, 6.5), (4.0, 7.1)]


def test_x_values_read_across_a_row(tmp_path: Path) -> None:
    """The GraphPad layout: one x per plotted column, paired with the values below it."""
    book = write_book(
        tmp_path,
        [
            ['X values', 1.0, 4.0],
            ['Batch', 'Dose A', 'Dose B'],
            [None, 2.0, 8.0],
            [None, 3.0, 12.0],
        ],
    )
    table = read_table(book)
    series, x_label = read_xy(table, x_row=0, y_columns=(1, 2), series_row=1, first_data_row=2, path=book)
    assert x_label == 'X values'
    assert [(p.x, p.y) for p in series[0].points] == [(1.0, 2.0), (1.0, 3.0)]
    assert [(p.x, p.y) for p in series[1].points] == [(4.0, 8.0), (4.0, 12.0)]


def test_a_row_without_a_y_value_drops_the_point(tmp_path: Path) -> None:
    """Half a point cannot be drawn, so the pair is dropped and reported."""
    book = write_book(
        tmp_path,
        [
            ['Dose', 'Resp A'],
            [1.0, 10.0],
            [2.0, None],
            [4.0, 15.0],
        ],
    )
    table = read_table(book)
    with pytest.warns(ExcelLayoutWarning, match='without both'):
        series, _ = read_xy(table, x_column=0, y_columns=(1,), first_data_row=1, path=book)
    assert [(p.x, p.y) for p in series[0].points] == [(1.0, 10.0), (4.0, 15.0)]


def test_x_must_be_either_a_row_or_a_column(tmp_path: Path) -> None:
    """Saying both at once is ambiguous, and saying neither leaves nothing to plot against."""
    book = write_book(tmp_path, [['Dose', 'Resp A'], [1.0, 10.0]])
    table = read_table(book)
    with pytest.raises(ExcelLayoutError, match='not both'):
        read_xy(table, x_row=0, x_column=0, y_columns=(1,))
    with pytest.raises(ExcelLayoutError, match='not both'):
        read_xy(table, y_columns=(1,))


def test_a_scatter_import_needs_a_y_column(tmp_path: Path) -> None:
    book = write_book(tmp_path, [['Dose', 'Resp A'], [1.0, 10.0]])
    with pytest.raises(ExcelLayoutError, match='at least one column'):
        read_xy(read_table(book), x_column=0, y_columns=())


def test_row_and_column_labels_name_the_dropdowns(tmp_path: Path) -> None:
    """The dialog offers the sheet's own words, so the choice can be read rather than counted."""
    book = write_book(tmp_path, [['Dose', 'Resp A', 'Resp B'], [1.0, 10.0, 5.0], [2.0, 12.0, 6.5]])
    table = read_table(book)
    assert xy_row_labels(table) == ('Dose', '1', '2')
    assert xy_column_labels(table) == ('Dose', 'Resp A', 'Resp B')


def test_ordered_keeps_unknown_names_out_and_appends_rest(real_dataset: Dataset) -> None:
    reordered = real_dataset.ordered(('Saitan 2', 'Control', 'missing'))
    assert [sample.name for sample in reordered][:2] == ['Saitan 2', 'Control']
    assert len(reordered) == len(real_dataset.samples)


def test_reader_emits_no_warning_for_the_real_file(real_dataset: Dataset) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter('error', ExcelLayoutWarning)
        assert read_dataset(INPUT_FILE).samples


def test_reading_every_column_is_the_default(real_dataset: Dataset) -> None:
    """Naming every column must give exactly the same dataset as naming none."""
    every = read_dataset(INPUT_FILE, columns=tuple(range(1, 9)))
    assert [sample.name for sample in every.samples] == [sample.name for sample in real_dataset.samples]
    assert [sample.values for sample in every.samples] == [sample.values for sample in real_dataset.samples]


def test_a_left_out_column_produces_no_sample(real_dataset: Dataset) -> None:
    """One column ticked off in the data preview must leave the graph one bar shorter."""
    fewer = read_dataset(INPUT_FILE, columns=(1, 2, 3, 4, 5, 6, 7))
    assert len(fewer.samples) == len(real_dataset.samples) - 1
    assert 'Saitan 2' not in {sample.name for sample in fewer.samples}


def test_the_columns_chosen_do_not_rename_the_ones_kept(real_dataset: Dataset) -> None:
    """Names come from the sheet, so removing a column must not shuffle the others."""
    fewer = read_dataset(INPUT_FILE, columns=(1, 2, 3))
    assert [sample.name for sample in fewer.samples] == ['Control', '42C', 'Low Mg']


def test_a_column_outside_the_sheet_is_refused() -> None:
    """Silently dropping a bad column would hide which one went missing."""
    with pytest.raises(ExcelLayoutError, match='outside the sheet'):
        read_dataset(INPUT_FILE, columns=(1, 99))


def test_the_label_column_cannot_be_plotted() -> None:
    """Column one holds the row names, so offering it as a measurement would read nothing."""
    with pytest.raises(ExcelLayoutError, match='outside the sheet'):
        read_dataset(INPUT_FILE, columns=(0, 1))



SCATTER_FILE = Path(__file__).resolve().parents[1] / 'input' / 'Conc_scatter_26-09-27.xlsx'


def test_a_tidy_sheet_is_recognised_as_a_scatter_layout() -> None:
    """The common shape draws itself, so the user is not asked to name its parts."""
    found = detect_scatter_layout(read_table(SCATTER_FILE))
    assert found == ScatterLayout(
        x_direction='column',
        x_index=0,
        y_columns=(1, 2, 3, 4, 5, 6, 7, 8),
        series_row=1,
        first_data_row=2,
    )


def test_a_sheet_of_names_alone_is_not_mistaken_for_a_scatter_layout() -> None:
    """A guess drawn as a graph is worse than no guess, so nothing is returned."""
    assert detect_scatter_layout(pd.DataFrame([['alpha', 'beta'], ['gamma', 'delta']])) is None


def test_the_real_bar_sheet_offers_no_scatter_layout() -> None:
    """The bar sheet measures down its rows, not along a line of x values."""
    assert detect_scatter_layout(read_table(INPUT_FILE)) is None


def test_a_detected_layout_reads_the_points_it_names(tmp_path: Path) -> None:
    """The names taken from the series row are the ones the legend has to show."""
    found = detect_scatter_layout(read_table(SCATTER_FILE))
    assert found is not None
    series, x_label = read_xy(
        read_table(SCATTER_FILE),
        x_column=found.x_index,
        y_columns=found.y_columns,
        series_row=found.series_row,
        first_data_row=found.first_data_row,
        path=SCATTER_FILE,
    )
    assert x_label == 'X'
    assert [one.name for one in series][:4] == ['Control', '42C', 'Low Mg', 'Low pDNA']
    assert all(one.n == 3 for one in series)


def test_the_series_row_saves_a_repeated_name_from_the_header() -> None:
    """Naming from the header row would call five columns Standard five times."""
    table = pd.DataFrame(
        [
            ['Dose', 'WT', 'WT'],
            ['Group', 'Control', 'Standard'],
            [1.0, 10.0, 20.0],
            [2.0, 11.0, 21.0],
        ]
    )
    found = detect_scatter_layout(table)
    assert found is not None
    assert found.series_row == 1
    series, _ = read_xy(
        table,
        x_column=found.x_index,
        y_columns=found.y_columns,
        series_row=found.series_row,
        first_data_row=found.first_data_row,
    )
    assert [one.name for one in series] == ['Control', 'Standard']


def test_a_number_typed_as_text_is_read_as_that_number() -> None:
    """One such cell must not become a gap in an otherwise numeric column.

    The data preview rounds its values, so it has to reach the same conclusion about what
    a cell holds as the reader does, or a column would show one value left behind.
    """
    assert cell_number('120.224') == pytest.approx(120.224)
    assert cell_number('200') == pytest.approx(200.0)
    assert cell_number('Control') is None
    assert cell_number('') is None
    assert cell_number(None) is None
    assert cell_number(True) is None
