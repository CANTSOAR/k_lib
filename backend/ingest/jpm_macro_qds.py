"""Private source wrapper for J.P. Morgan Macro QDS.

Access note: reach out to your J.P. Morgan sales representative or institutional account team.
URL: https://www.jpmm.com/
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["jpm_macro_qds"])
