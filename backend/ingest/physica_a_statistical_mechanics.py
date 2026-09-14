"""Private source wrapper for Physica A: Statistical Mechanics.

Access note: reach out to Elsevier or your institutional library.
URL: https://www.sciencedirect.com/journal/physica-a-statistical-mechanics-and-its-applications
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["physica_a_statistical_mechanics"])
