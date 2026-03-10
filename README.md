# Tournament Scheduler (GitHub Pages + PyScript)

A static tournament scheduler you can deploy directly to **GitHub Pages**.

This scaffold keeps the scheduling logic in **Python** and runs it **in the browser** using **PyScript / Pyodide**, so there is **no backend** to host.

## Features

- paste teams as JSON
- paste preferred matchups as JSON
- configure rounds, fields, and random seed
- generate a schedule entirely client-side
- copy the resulting schedule as JSON
- deploy automatically to GitHub Pages with GitHub Actions

## Repo structure

```text
.
├── .github/
│   └── workflows/
│       └── pages.yml
├── app.py
├── index.html
├── style.css
└── README.md
```

## Local preview

Because the page loads browser assets and Python modules, use a tiny local web server instead of opening `index.html` directly.

### Python

```bash
python -m http.server 8000
```

Then open <http://localhost:8000>.

## Deploy to GitHub Pages

1. Create a new GitHub repository.
2. Copy these files into the repo.
3. Push to `main`.
4. In GitHub:
   - go to **Settings → Pages**
   - set **Source** to **GitHub Actions**
5. The included workflow will publish the site automatically.

## Input format

### Teams

```json
[
  {
    "niveau": 1,
    "geslacht": "Heren",
    "naam": "Falcons",
    "leeftijd": "Jong"
  },
  {
    "niveau": 2,
    "geslacht": "Dames",
    "naam": "Orcas",
    "leeftijd": "Midden"
  }
]
```

### Preferences

```json
[
  ["Falcons", "Wolves"],
  ["Orcas", "Sharks"]
]
```

## Notes / limitations

- this is a **static** site: there is no database, login, or server-side processing
- inputs are currently **JSON**, not Excel
- repeated opponents are **discouraged but not strictly forbidden** by the greedy pairing logic
- the scheduler spreads preference matches over rounds using a **target-round + quota** strategy

## Suggested next improvements

- add CSV / Excel import
- add strict “no repeat opponents” mode
- export to CSV / JSON download file
- add richer validation and schedule diagnostics
