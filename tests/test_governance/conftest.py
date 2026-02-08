"""Test configuration for governance tests."""

import sys
from pathlib import Path

# Ensure root project directory is first in path
root = Path(__file__).parent.parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
