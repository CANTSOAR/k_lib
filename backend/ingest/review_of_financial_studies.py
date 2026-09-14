"""Private source wrapper for Review of Financial Studies.

Access note: reach out to Oxford University Press or your institutional library.
URL: https://academic.oup.com/rfs
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["review_of_financial_studies"])
