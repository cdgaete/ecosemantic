"""Import paths for the scripts the tests of the database sources load by name."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

sys.path.insert(0, str(SCRIPTS / "uslci"))
sys.path.insert(0, str(SCRIPTS / "ecoinvent"))
