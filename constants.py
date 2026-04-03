from __future__ import annotations

from typing import Dict, List, Tuple

VERPLICHTE_WEDSTRIJDEN = {1: 3, 2: 3, 3: 2}
OPTIONELE_WEDSTRIJDEN = {1: 0, 2: 0, 3: 1}

CAPACITY_SEED_CACHE: Dict[Tuple[int, str, str], int] = {}
EXAMPLE_TEAMS: List[dict] = [
  {
    "level": 2,
    "gender": "Dames",
    "name": "Birthe",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Dames",
    "name": "Christianne Schroder",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Dames",
    "name": "Evie Buitink",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Dames",
    "name": "Nora Bauer",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Dames",
    "name": "Sabrina",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Dames",
    "name": "Nina Zeilstra",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Dames",
    "name": "Nanette Wielenga",
    "age": "Oud",
    "wedstrijden": 2
  },
  {
    "level": 2,
    "gender": "Dames",
    "name": "Eva Kernkamp",
    "age": "Oud",
    "wedstrijden": 2
  },
  {
    "level": 1,
    "gender": "Heren",
    "name": "Pieter Groenewoud",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 1,
    "gender": "Heren",
    "name": "Thijs Parlevliet",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Heren",
    "name": "bas Vietor",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Heren",
    "name": "Guus Vos",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Heren",
    "name": "Sebas",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Heren",
    "name": "Yaniek Buitink",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 3,
    "gender": "Heren",
    "name": "Harm Schut",
    "age": "Oud",
    "wedstrijden": 2
  },
  {
    "level": 3,
    "gender": "Heren",
    "name": "Jan Lodewijk Smit",
    "age": "Oud",
    "wedstrijden": 2
  },
  {
    "level": 1,
    "gender": "Heren",
    "name": "Cappie de Muralt",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 1,
    "gender": "Heren",
    "name": "Pieter van Aken",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Heren",
    "name": "Arno van der Kooij",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Heren",
    "name": "Hessel de Jong",
    "age": "Oud",
    "wedstrijden": 2
  },
  {
    "level": 2,
    "gender": "Heren",
    "name": "Jan Geert Buitink",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Heren",
    "name": "Robert van Well",
    "age": "Oud",
    "wedstrijden": 2
  },
  {
    "level": 3,
    "gender": "Mixed",
    "name": "Caroliene Mellema",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 3,
    "gender": "Mixed",
    "name": "Isa Noordover",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 3,
    "gender": "Mixed",
    "name": "Kai",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 3,
    "gender": "Mixed",
    "name": "Puck van de Velde",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 3,
    "gender": "Mixed",
    "name": "Wiegert Schut",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 3,
    "gender": "Mixed",
    "name": "Emma van Ginkel",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 1,
    "gender": "Mixed",
    "name": "Lieke Beckers",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Mixed",
    "name": "Annemijn Maan",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Mixed",
    "name": "Femke van Renesse",
    "age": "Jong",
    "wedstrijden": 3
  },
  {
    "level": 1,
    "gender": "Mixed",
    "name": "Sascha Zwenk",
    "age": "Oud",
    "wedstrijden": 2
  },
  {
    "level": 1,
    "gender": "Mixed",
    "name": "Irene van Dijk",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Mixed",
    "name": "Annemarie",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Mixed",
    "name": "Michelle Rietbergen",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Mixed",
    "name": "Ninah Rikken",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Mixed",
    "name": "Maran",
    "age": "Oud",
    "wedstrijden": 3
  },
  {
    "level": 2,
    "gender": "Mixed",
    "name": "Ludy Holst",
    "age": "Oud",
    "wedstrijden": 2
  },
  {
    "level": 1,
    "gender": "Heren",
    "name": "Olivier Vis",
    "age": "Oud",
    "wedstrijden": 3
  },
]
EXAMPLE_PREFS: List[list[str]] = [
  [
    "Wiegert Schut",
    "Sebas"
  ],
  [
    "Wiegert Schut",
    "Harm Schut"
  ],
  [
    "Jan Lodewijk Smit",
    "Harm Schut"
  ],
  [
    "Sebas",
    "Jan Lodewijk Smit"
  ],
  [
    "Christianne Schroder",
    "Nanette Wielenga"
  ],
  [
    "Eva Kernkamp",
    "Nanette Wielenga"
  ],
  [
    "Arno van der Kooij",
    "Sebas"
  ],
  [
    "Arno van der Kooij",
    "bas Vietor"
  ],
  [
    "Arno van der Kooij",
    "Isa Noordover"
  ],
  [
    "Wiegert Schut",
    "Sascha Zwenk"
  ],
  [
    "Nanette Wielenga",
    "Sascha Zwenk"
  ]
]
