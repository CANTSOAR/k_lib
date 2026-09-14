"""Private source wrapper for SIAM Journal on Financial Mathematics.

Access note: reach out to SIAM or your institutional library.
URL: https://www.siam.org/publications/journals/siam-journal-on-financial-mathematics-sifin
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["siam_journal_on_financial_mathematics"])
