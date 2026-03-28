from __future__ import annotations

from typing import Dict, List, Tuple

VERPLICHTE_WEDSTRIJDEN = {1: 3, 2: 3, 3: 2}
OPTIONELE_WEDSTRIJDEN = {1: 0, 2: 0, 3: 1}

CAPACITY_SEED_CACHE: Dict[Tuple[int, str, str], int] = {}
EXAMPLE_TEAMS: List[dict] = []
EXAMPLE_PREFS: List[list[str]] = []
