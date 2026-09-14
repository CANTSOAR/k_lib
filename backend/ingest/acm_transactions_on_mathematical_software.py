"""Private source wrapper for ACM Transactions on Mathematical Software.

Access note: reach out to ACM Digital Library or your institutional library.
URL: https://dl.acm.org/journal/toms
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["acm_transactions_on_mathematical_software"])
