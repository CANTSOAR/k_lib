"""Private source wrapper for Stochastic Processes and their Applications.

Access note: reach out to Elsevier or your institutional library.
URL: https://www.sciencedirect.com/journal/stochastic-processes-and-their-applications
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["stochastic_processes_and_their_applications"])
