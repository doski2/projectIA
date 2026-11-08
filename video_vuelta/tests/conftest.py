import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "PCARS2-AI" / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
