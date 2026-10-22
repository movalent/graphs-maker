from src.excel_reader import read_dataset, detect_layout, read_table
from pathlib import Path

path = Path('c:/Users/Klaudia/Desktop/GraphPad prism/input/Conc_bar_26-09-27.xlsx')
table = read_table(path)
layout = detect_layout(table, path)
print('layout:', layout)
ds = read_dataset(table, layout, path)
print('samples:', len(ds.samples))
for s in ds.samples:
    print(f'  {s.name} group={s.group}')