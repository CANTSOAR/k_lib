"""Private source wrapper for European Physical Journal B.

Access note: reach out to Springer or your institutional library.
URL: https://www.springer.com/journal/10051
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["european_physical_journal_b"])
