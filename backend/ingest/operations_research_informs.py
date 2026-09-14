"""Private source wrapper for Operations Research (INFORMS).

Access note: reach out to INFORMS subscriptions or your institutional library.
URL: https://pubsonline.informs.org/journal/opre
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["operations_research_informs"])
