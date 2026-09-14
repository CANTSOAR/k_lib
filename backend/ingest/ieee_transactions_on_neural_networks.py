"""Private source wrapper for IEEE Transactions on Neural Networks.

Access note: reach out to IEEE Xplore account admins or your institutional library.
URL: https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=5962385
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import main_for_source
from backend.ingest.registry import SOURCE_REGISTRY


if __name__ == "__main__":
    main_for_source(SOURCE_REGISTRY["ieee_transactions_on_neural_networks"])
