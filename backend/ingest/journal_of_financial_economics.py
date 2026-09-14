"""Private source wrapper for Journal of Financial Economics.

Access note: reach out to Elsevier or your institutional library.
URL: https://www.journals.elsevier.com/journal-of-financial-economics
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["journal_of_financial_economics"])
