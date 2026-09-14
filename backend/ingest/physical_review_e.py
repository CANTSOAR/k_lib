"""Private source wrapper for Physical Review E.

Access note: reach out to APS or your institutional library.
URL: https://journals.aps.org/pre
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["physical_review_e"])
