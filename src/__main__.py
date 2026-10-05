"""Allow the package to be executed with ``python -m src``."""

import os
import sys
from pathlib import Path

# ``python src/__main__.py`` puts src/ on sys.path rather than the project root, so the
# ``src`` package would not be importable. Adding the parent directory makes that form work
# alongside ``python -m src``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault('MKL_THREADING_LAYER', 'SEQUENTIAL')
os.environ.setdefault('MPLBACKEND', 'Agg')

from src.cli import main  # noqa: E402

raise SystemExit(main())
