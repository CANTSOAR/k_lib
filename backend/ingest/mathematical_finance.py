"""Private source wrapper for Mathematical Finance.

Access note: reach out to Wiley or your institutional library.
URL: https://onlinelibrary.wiley.com/journal/14679965
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["mathematical_finance"])
