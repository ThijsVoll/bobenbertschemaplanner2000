from __future__ import annotations

import asyncio
import csv
import html
import io
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from js import console, document, navigator, XLSX  # type: ignore
from pyodide.ffi import create_proxy, to_js # type: ignore

@dataclass(frozen=True)
class Team:
    niveau: int
    geslacht: str
    naam: str
    leeftijd: str


@dataclass
class Match:
    ronde: int
    veld: int
    team_a: Team
    team_b: Team


VERPLICHTE_WEDSTRIJDEN = {1: 3, 2: 3, 3: 2}
OPTIONELE_WEDSTRIJDEN = {1: 0, 2: 0, 3: 1}

EXAMPLE_TEAMS = [
    {"niveau": 1, "geslacht": "Heren", "naam": "Falcons", "leeftijd": "Jong"},
    {"niveau": 1, "geslacht": "Heren", "naam": "Wolves", "leeftijd": "Midden"},
    {"niveau": 1, "geslacht": "Heren", "naam": "Raptors", "leeftijd": "Oud"},
    {"niveau": 1, "geslacht": "Heren", "naam": "Lions", "leeftijd": "Jong"},
    {"niveau": 2, "geslacht": "Dames", "naam": "Orcas", "leeftijd": "Midden"},
    {"niveau": 2, "geslacht": "Dames", "naam": "Sharks", "leeftijd": "Jong"},
    {"niveau": 2, "geslacht": "Dames", "naam": "Otters", "leeftijd": "Oud"},
    {"niveau": 2, "geslacht": "Dames", "naam": "Seals", "leeftijd": "Midden"},
    {"niveau": 3, "geslacht": "Mixed", "naam": "Comets", "leeftijd": "Jong"},
    {"niveau": 3, "geslacht": "Mixed", "naam": "Nebula", "leeftijd": "Midden"},
    {"niveau": 3, "geslacht": "Mixed", "naam": "Meteors", "leeftijd": "Oud"},
    {"niveau": 3, "geslacht": "Mixed", "naam": "Aurora", "leeftijd": "Midden"},
]

EXAMPLE_PREFS = [
    ["Falcons", "Wolves"],
    ["Orcas", "Sharks"],
    ["Comets", "Aurora"],
    ["Raptors", "Lions"],
]

LAST_RESULT = None
REMOVE_PREF_PROXIES = []
EVENT_PROXIES = []
OUTPUT_VIEW = "table"


def _naam_index(teams: List[Team]) -> Dict[str, Team]:
    ix = {}
    for t in teams:
        if t.naam in ix:
            raise ValueError(f"Teamnaam '{t.naam}' komt dubbel voor; namen moeten uniek zijn.")
        ix[t.naam] = t
    return ix


def _leeftijd_map(niveau: str) -> int:
    data = {"Jong": 1, "Midden": 2, "Oud": 3}
    val = data.get(niveau)
    if val is None:
        raise ValueError(f"Onbekende leeftijd: {niveau}")
    return val


def _consecutieve_rondes_toegestaan(vorige: Optional[int], huidige: int) -> bool:
    if vorige is None:
        return True
    if huidige == vorige + 1 and not (vorige == 5 and huidige == 6):
        return False
    return True


def _geslacht_compatibel(a: Team, b: Team) -> bool:
    if a.geslacht == "Mixed" or b.geslacht == "Mixed":
        return True
    return a.geslacht == b.geslacht


def _compatibiliteit_score(a: Team, b: Team) -> int:
    score = 100
    score -= abs(a.niveau - b.niveau) * 20
    score -= abs(_leeftijd_map(a.leeftijd) - _leeftijd_map(b.leeftijd)) * 10
    return score


def _pareer_gretig(
    beschikbaar: List[Team],
    al_gespeeld: Set[frozenset],
    ronde: int,
) -> List[Tuple[Team, Team]]:
    paren: List[Tuple[Team, Team]] = []
    pool = beschikbaar[:]
    pool.sort(key=lambda t: (t.niveau, t.geslacht != "Mixed", t.naam))
    gebruikt: Set[Team] = set()

    for i, t in enumerate(pool):
        if t in gebruikt:
            continue

        kandidaten = [
            k for k in pool[i + 1:] if k not in gebruikt and _geslacht_compatibel(t, k)
        ]

        kandidaten.sort(
            key=lambda k: (
                (frozenset((t.naam, k.naam)) in al_gespeeld),
                -_compatibiliteit_score(t, k),
                k.naam,
            )
        )

        if not kandidaten:
            continue

        k = kandidaten[0]
        paren.append((t, k))
        gebruikt.add(t)
        gebruikt.add(k)

    return paren


def genereer_schema(
    teams: List[Team],
    voorkeuren: List[Tuple[str, str]],
    n_rondes: int = 7,
    n_velden: int = 12,
    seed: Optional[int] = 42,
) -> Tuple[List[Match], Dict[str, int], Dict[str, int]]:
    if seed is not None:
        random.seed(seed)

    naam2team = _naam_index(teams)

    resterend_verplicht: Dict[Team, int] = {
        t: VERPLICHTE_WEDSTRIJDEN.get(t.niveau, 0) for t in teams
    }
    resterend_opt: Dict[Team, int] = {
        t: OPTIONELE_WEDSTRIJDEN.get(t.niveau, 0) for t in teams
    }
    laatste_ronde: Dict[Team, Optional[int]] = {t: None for t in teams}

    voorkeur_set: Set[frozenset] = set()
    for a, b in voorkeuren:
        if a in naam2team and b in naam2team and a != b:
            voorkeur_set.add(frozenset((a, b)))

    ongeplande_voorkeuren = set(voorkeur_set)
    voorkeur_lijst = list(voorkeur_set)
    random.shuffle(voorkeur_lijst)

    voorkeur_doelronde: Dict[frozenset, int] = {}
    for i, pair in enumerate(voorkeur_lijst):
        voorkeur_doelronde[pair] = (i % n_rondes) + 1

    al_gespeeld: Set[frozenset] = set()
    wedstrijden: List[Match] = []

    def _beschikbare_teams(ronde: int, alleen_verplicht: bool) -> List[Team]:
        res = []
        for t in teams:
            if not _consecutieve_rondes_toegestaan(laatste_ronde[t], ronde):
                continue
            if any(m.ronde == ronde and (m.team_a == t or m.team_b == t) for m in wedstrijden):
                continue
            if alleen_verplicht:
                if resterend_verplicht[t] > 0:
                    res.append(t)
            else:
                if resterend_verplicht[t] > 0 or resterend_opt[t] > 0:
                    res.append(t)
        return res

    for ronde in range(1, n_rondes + 1):
        veld_teller = 1
        geplande_deze_ronde: Set[Team] = set()

        resterende_rondes = n_rondes - ronde + 1
        resterende_voorkeuren = len(ongeplande_voorkeuren)
        voorkeur_quota = min(
            n_velden,
            math.ceil(resterende_voorkeuren / resterende_rondes) if resterende_voorkeuren > 0 else 0,
        )
        geplande_voorkeuren_deze_ronde = 0

        def _dringendheidskey(fs: frozenset) -> Tuple[int, int, int, int, str]:
            a_name, b_name = sorted(list(fs))
            a, b = naam2team[a_name], naam2team[b_name]
            doelronde = voorkeur_doelronde.get(fs, ronde)
            overdue_flag = 0 if doelronde <= ronde else 1
            return (
                overdue_flag,
                abs(doelronde - ronde),
                -(resterend_verplicht[a] + resterend_verplicht[b]),
                -_compatibiliteit_score(a, b),
                f"{a_name}-{b_name}",
            )

        for pair in sorted(list(ongeplande_voorkeuren), key=_dringendheidskey):
            if veld_teller > n_velden or geplande_voorkeuren_deze_ronde >= voorkeur_quota:
                break

            a_name, b_name = list(pair)
            a, b = naam2team[a_name], naam2team[b_name]

            if a in geplande_deze_ronde or b in geplande_deze_ronde:
                continue
            if not _consecutieve_rondes_toegestaan(laatste_ronde[a], ronde):
                continue
            if not _consecutieve_rondes_toegestaan(laatste_ronde[b], ronde):
                continue
            if resterend_verplicht[a] == 0 and resterend_opt[a] == 0:
                continue
            if resterend_verplicht[b] == 0 and resterend_opt[b] == 0:
                continue
            if not _geslacht_compatibel(a, b):
                continue

            wedstrijden.append(Match(ronde, veld_teller, a, b))
            veld_teller += 1
            geplande_voorkeuren_deze_ronde += 1
            geplande_deze_ronde.update([a, b])
            laatste_ronde[a] = ronde
            laatste_ronde[b] = ronde
            al_gespeeld.add(frozenset((a.naam, b.naam)))

            for t in (a, b):
                if resterend_verplicht[t] > 0:
                    resterend_verplicht[t] -= 1
                elif resterend_opt[t] > 0:
                    resterend_opt[t] -= 1

            ongeplande_voorkeuren.discard(pair)

        for fase in ("verplicht", "opt"):
            if veld_teller > n_velden:
                break

            alleen_verplicht = fase == "verplicht"
            beschikbaar = [
                t for t in _beschikbare_teams(ronde, alleen_verplicht) if t not in geplande_deze_ronde
            ]
            paren = _pareer_gretig(beschikbaar, al_gespeeld, ronde)

            for a, b in paren:
                if veld_teller > n_velden:
                    break

                if alleen_verplicht:
                    if resterend_verplicht[a] == 0 or resterend_verplicht[b] == 0:
                        continue
                else:
                    if resterend_verplicht[a] == 0 and resterend_opt[a] == 0:
                        continue
                    if resterend_verplicht[b] == 0 and resterend_opt[b] == 0:
                        continue

                wedstrijden.append(Match(ronde, veld_teller, a, b))
                veld_teller += 1
                geplande_deze_ronde.update([a, b])
                laatste_ronde[a] = ronde
                laatste_ronde[b] = ronde
                al_gespeeld.add(frozenset((a.naam, b.naam)))

                for t in (a, b):
                    if resterend_verplicht[t] > 0:
                        resterend_verplicht[t] -= 1
                    elif resterend_opt[t] > 0:
                        resterend_opt[t] -= 1

    rest_verplicht_by_name = {t.naam: resterend_verplicht[t] for t in teams}
    rest_opt_by_name = {t.naam: resterend_opt[t] for t in teams}
    return wedstrijden, rest_verplicht_by_name, rest_opt_by_name


def serialize_results(
    teams: List[Team],
    wedstrijden: List[Match],
    rest_verplicht: Dict[str, int],
    rest_opt: Dict[str, int],
    n_rondes: int,
) -> dict:
    return {
        "n_rondes": n_rondes,
        "teams": [
            {
                "naam": t.naam,
                "geslacht": t.geslacht,
                "leeftijd": t.leeftijd,
                "niveau": t.niveau,
            }
            for t in teams
        ],
        "matches": [
            {
                "ronde": m.ronde,
                "veld": m.veld,
                "team_a": {
                    "naam": m.team_a.naam,
                    "geslacht": m.team_a.geslacht,
                    "leeftijd": m.team_a.leeftijd,
                    "niveau": m.team_a.niveau,
                },
                "team_b": {
                    "naam": m.team_b.naam,
                    "geslacht": m.team_b.geslacht,
                    "leeftijd": m.team_b.leeftijd,
                    "niveau": m.team_b.niveau,
                },
            }
            for m in wedstrijden
        ],
        "remaining_required": rest_verplicht,
        "remaining_optional": rest_opt,
    }


def set_status(message: str, kind: str = "info") -> None:
    el = document.getElementById("status")
    el.className = f"status status-{kind}"
    el.textContent = message


def _normalize_header(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _pick_column(field_map: Dict[str, str], *aliases: str) -> str:
    for alias in aliases:
        key = _normalize_header(alias)
        if key in field_map:
            return field_map[key]
    raise ValueError("Missing required CSV column. Expected one of: " + ", ".join(aliases))


def parse_teams_csv_text(csv_text: str) -> List[dict]:
    if not csv_text or not csv_text.strip():
        raise ValueError("The selected CSV file is empty.")

    sample = csv_text[:4096]

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        class _Default(csv.excel):
            delimiter = ","
        dialect = _Default

    reader = csv.DictReader(io.StringIO(csv_text), dialect=dialect)

    if not reader.fieldnames:
        raise ValueError("Could not read CSV headers.")

    field_map = {_normalize_header(name): name for name in reader.fieldnames if name is not None}

    naam_col = _pick_column(field_map, "naam", "team", "teamnaam", "name")
    niveau_col = _pick_column(field_map, "niveau", "level")
    geslacht_col = _pick_column(field_map, "geslacht", "gender")
    leeftijd_col = _pick_column(field_map, "leeftijd", "age", "leeftijdscategorie")

    teams = []
    for row_number, row in enumerate(reader, start=2):
        if not row:
            continue

        naam = str(row.get(naam_col, "") or "").strip()
        niveau_text = str(row.get(niveau_col, "") or "").strip()
        geslacht = str(row.get(geslacht_col, "") or "").strip()
        leeftijd = str(row.get(leeftijd_col, "") or "").strip()

        if not any([naam, niveau_text, geslacht, leeftijd]):
            continue

        if not naam:
            raise ValueError(f"CSV row {row_number}: column '{naam_col}' is empty.")
        if not niveau_text:
            raise ValueError(f"CSV row {row_number}: column '{niveau_col}' is empty.")
        if not geslacht:
            raise ValueError(f"CSV row {row_number}: column '{geslacht_col}' is empty.")
        if not leeftijd:
            raise ValueError(f"CSV row {row_number}: column '{leeftijd_col}' is empty.")

        try:
            niveau = int(niveau_text)
        except ValueError as exc:
            raise ValueError(
                f"CSV row {row_number}: niveau must be an integer, got '{niveau_text}'."
            ) from exc

        teams.append(
            {
                "niveau": niveau,
                "geslacht": geslacht,
                "naam": naam,
                "leeftijd": leeftijd,
            }
        )

    if not teams:
        raise ValueError("No team rows were found in the CSV file.")

    return teams


def _safe_load_json_array(element_id: str) -> list:
    raw = document.getElementById(element_id).value.strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError(f"{element_id} must contain a JSON array.")
    return parsed


def get_team_dicts() -> List[dict]:
    data = _safe_load_json_array("teams-json")
    teams = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each team must be a JSON object.")
        teams.append(item)
    return teams


def get_team_names() -> List[str]:
    teams = get_team_dicts()
    names = []
    for item in teams:
        name = str(item.get("naam", "") or "").strip()
        if name:
            names.append(name)
    return names


def get_preferences() -> List[List[str]]:
    data = _safe_load_json_array("prefs-json")
    prefs = []
    for pair in data:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("Each preference must be a 2-item array, e.g. ['Team A', 'Team B']")
        prefs.append([str(pair[0]), str(pair[1])])
    return prefs


def set_preferences(prefs: List[List[str]]) -> None:
    document.getElementById("prefs-json").value = json.dumps(prefs, indent=2, ensure_ascii=False)


def populate_preference_dropdowns() -> None:
    team_names = sorted(set(get_team_names()))
    select_a = document.getElementById("pref-team-a")
    select_b = document.getElementById("pref-team-b")
    empty_hint = document.getElementById("prefs-editor-empty")

    select_a.innerHTML = ""
    select_b.innerHTML = ""

    if not team_names:
        placeholder_a = document.createElement("option")
        placeholder_a.value = ""
        placeholder_a.textContent = "Eerst teams importeren"
        select_a.appendChild(placeholder_a)

        placeholder_b = document.createElement("option")
        placeholder_b.value = ""
        placeholder_b.textContent = "Eerst teams importeren"
        select_b.appendChild(placeholder_b)

        select_a.disabled = True
        select_b.disabled = True
        empty_hint.style.display = "block"
        return

    select_a.disabled = False
    select_b.disabled = False
    empty_hint.style.display = "none"

    for name in team_names:
        opt_a = document.createElement("option")
        opt_a.value = name
        opt_a.textContent = name
        select_a.appendChild(opt_a)

        opt_b = document.createElement("option")
        opt_b.value = name
        opt_b.textContent = name
        select_b.appendChild(opt_b)

    if len(team_names) > 1:
        select_b.selectedIndex = 1
    else:
        select_b.selectedIndex = 0


def render_preferences_editor() -> None:
    global REMOVE_PREF_PROXIES

    prefs_container = document.getElementById("prefs-list")
    prefs_container.innerHTML = ""
    REMOVE_PREF_PROXIES = []

    try:
        prefs = get_preferences()
        valid_teams = set(get_team_names())
    except Exception as exc:
        row = document.createElement("div")
        row.className = "status status-error"
        row.textContent = f"Preferences UI unavailable: {exc}"
        prefs_container.appendChild(row)
        return

    if not prefs:
        row = document.createElement("div")
        row.className = "muted small"
        row.textContent = "Nog geen voorkeuren toegevoegd."
        prefs_container.appendChild(row)
        return

    for idx, pair in enumerate(prefs):
        a_name, b_name = pair

        row = document.createElement("div")
        row.style.display = "flex"
        row.style.justifyContent = "space-between"
        row.style.alignItems = "center"
        row.style.gap = "12px"
        row.style.padding = "10px 12px"
        row.style.border = "1px solid rgba(255,255,255,0.12)"
        row.style.borderRadius = "10px"

        label = document.createElement("div")
        label_text = f"{a_name} ↔ {b_name}"
        if a_name not in valid_teams or b_name not in valid_teams:
            label_text += " (team missing from current import)"
        label.textContent = label_text
        row.appendChild(label)

        button = document.createElement("button")
        button.type = "button"
        button.className = "secondary"
        button.textContent = "Remove"

        def _make_remove_handler(index: int):
            def _handler(event=None):
                prefs_now = get_preferences()
                if 0 <= index < len(prefs_now):
                    del prefs_now[index]
                    set_preferences(prefs_now)
                    render_preferences_editor()
                    set_status("Preference removed.", "success")
            return _handler

        proxy = create_proxy(_make_remove_handler(idx))
        REMOVE_PREF_PROXIES.append(proxy)
        button.addEventListener("click", proxy)

        row.appendChild(button)
        prefs_container.appendChild(row)


def sync_preferences_ui() -> None:
    populate_preference_dropdowns()
    render_preferences_editor()


async def import_csv_async() -> None:
    file_input = document.getElementById("teams-csv-file")
    files = file_input.files
    if not files or files.length == 0:
        return

    file = files.item(0)
    set_status(f"Reading {file.name}...", "info")

    try:
        csv_text = await file.text()
        teams = parse_teams_csv_text(str(csv_text))
        document.getElementById("teams-json").value = json.dumps(
            teams, indent=2, ensure_ascii=False
        )
        sync_preferences_ui()
        set_status(f"{len(teams)} teams geimporteerd van {file.name}.", "success")
    except Exception as exc:
        console.error(str(exc))
        set_status(f"CSV import error: {exc}", "error")


def on_teams_csv_selected(*args):
    asyncio.create_task(import_csv_async())


def load_example_data(*args):
    document.getElementById("teams-json").value = json.dumps(
        EXAMPLE_TEAMS, indent=2, ensure_ascii=False
    )
    document.getElementById("prefs-json").value = json.dumps(
        EXAMPLE_PREFS, indent=2, ensure_ascii=False
    )
    sync_preferences_ui()
    set_status("Loaded example dataset.", "success")


def on_add_preference(*args):
    try:
        team_a = document.getElementById("pref-team-a").value.strip()
        team_b = document.getElementById("pref-team-b").value.strip()

        if not team_a or not team_b:
            raise ValueError("Select two teams first.")
        if team_a == team_b:
            raise ValueError("A preference must contain two different teams.")

        prefs = get_preferences()
        pair = [team_a, team_b]
        reverse_pair = [team_b, team_a]

        if pair in prefs or reverse_pair in prefs:
            raise ValueError("This preference already exists.")

        prefs.append(pair)
        set_preferences(prefs)
        render_preferences_editor()
        set_status(f"Added preference: {team_a} ↔ {team_b}", "success")
    except Exception as exc:
        console.error(str(exc))
        set_status(f"Preference error: {exc}", "error")


def on_teams_json_changed(*args):
    try:
        populate_preference_dropdowns()
        render_preferences_editor()
    except Exception:
        populate_preference_dropdowns()


def on_prefs_json_changed(*args):
    render_preferences_editor()


def bereken_minimaal_aantal_velden(teams, voorkeuren, n_rondes, seed):
    for i in range(1, 15):
        schema, rest_verplicht, rest_optioneel = genereer_schema(
            teams,
            voorkeuren,
            n_rondes=n_rondes,
            n_velden=i,
            seed=seed,
        )
        if not any(rest_verplicht.values()):
            return schema, rest_verplicht, rest_optioneel, i

    return [], {}, {}, -1


def read_inputs() -> tuple[list[Team], list[tuple[str, str]], int, int, Optional[int]]:
    teams_raw = _safe_load_json_array("teams-json")
    prefs_raw = _safe_load_json_array("prefs-json")

    n_rondes = int(document.getElementById("n-rondes").value)
    n_velden = int(document.getElementById("n-velden").value)

    seed_text = document.getElementById("seed").value.strip()
    seed = int(seed_text) if seed_text else None

    teams = []
    for item in teams_raw:
        if not isinstance(item, dict):
            raise ValueError("Each team must be a JSON object.")

        teams.append(
            Team(
                niveau=int(item["niveau"]),
                geslacht=str(item["geslacht"]),
                naam=str(item["naam"]),
                leeftijd=str(item["leeftijd"]),
            )
        )

    prefs = []
    for pair in prefs_raw:
        if not isinstance(pair, (list, tuple)):
            raise ValueError("Each preference must be a 2-item array, e.g. ['Team A', 'Team B']")
        if len(pair) != 2:
            raise ValueError("Each preference must contain exactly 2 team names.")

        prefs.append((str(pair[0]), str(pair[1])))

    return teams, prefs, n_rondes, n_velden, seed


def set_output_view(view: str) -> None:
    global OUTPUT_VIEW
    OUTPUT_VIEW = view

    table_btn = document.getElementById("view-table-btn")
    timeline_btn = document.getElementById("view-timeline-btn")
    table_el = document.getElementById("schedule-output")
    timeline_el = document.getElementById("timeline-output")

    if view == "timeline":
        table_el.classList.add("hidden")
        timeline_el.classList.remove("hidden")
        table_btn.classList.remove("is-active")
        timeline_btn.classList.add("is-active")
    else:
        timeline_el.classList.add("hidden")
        table_el.classList.remove("hidden")
        timeline_btn.classList.remove("is-active")
        table_btn.classList.add("is-active")


def render_table_schedule(results: dict) -> None:
    output_el = document.getElementById("schedule-output")
    matches = results["matches"]

    grouped = defaultdict(list)
    for m in sorted(matches, key=lambda x: (x["ronde"], x["veld"])):
        grouped[m["ronde"]].append(m)

    schedule_parts = []

    for ronde in sorted(grouped):
        rows = []
        for m in grouped[ronde]:
            rows.append(
                f"""
                <tr>
                  <td>{m['veld']:02d}</td>
                  <td>
                    <strong>{html.escape(m['team_a']['naam'])}</strong><br>
                    <span class="muted small">
                      {html.escape(m['team_a']['geslacht'])} · {html.escape(m['team_a']['leeftijd'])} · Niveau {m['team_a']['niveau']}
                    </span>
                  </td>
                  <td>
                    <strong>{html.escape(m['team_b']['naam'])}</strong><br>
                    <span class="muted small">
                      {html.escape(m['team_b']['geslacht'])} · {html.escape(m['team_b']['leeftijd'])} · Niveau {m['team_b']['niveau']}
                    </span>
                  </td>
                </tr>
                """
            )

        schedule_parts.append(
            f"""
            <section class="round-block">
              <div class="round-header">Ronde {ronde}</div>
              <table class="match-table">
                <thead>
                  <tr><th>Veld</th><th>Team A</th><th>Team B</th></tr>
                </thead>
                <tbody>
                  {''.join(rows)}
                </tbody>
              </table>
            </section>
            """
        )

    output_el.innerHTML = (
        "".join(schedule_parts)
        if schedule_parts
        else '<p class="muted">Geen wedstrijden gepland.</p>'
    )


def render_team_timeline(results: dict) -> None:
    timeline_el = document.getElementById("timeline-output")
    teams = results.get("teams", [])
    matches = results.get("matches", [])
    n_rondes = int(results.get("n_rondes", 0) or 0)

    timeline_lookup: Dict[str, Dict[int, dict]] = defaultdict(dict)

    for m in matches:
        ronde = int(m["ronde"])
        veld = int(m["veld"])

        a = m["team_a"]
        b = m["team_b"]

        timeline_lookup[a["naam"]][ronde] = {
            "opponent": b["naam"],
            "veld": veld,
            "opponent_geslacht": b["geslacht"],
            "opponent_leeftijd": b["leeftijd"],
            "opponent_niveau": b["niveau"],
            "own_niveau": a["niveau"],
        }

        timeline_lookup[b["naam"]][ronde] = {
            "opponent": a["naam"],
            "veld": veld,
            "opponent_geslacht": a["geslacht"],
            "opponent_leeftijd": a["leeftijd"],
            "opponent_niveau": a["niveau"],
            "own_niveau": b["niveau"],
        }

    if not teams:
        timeline_el.innerHTML = '<p class="muted">Geen teamdata beschikbaar.</p>'
        return

    header_cells = ['<th class="timeline-team-col">Team</th>']
    for ronde in range(1, n_rondes + 1):
        header_cells.append(f'<th class="timeline-round-col">Ronde {ronde}</th>')

    body_rows = []
    sorted_teams = sorted(
        teams,
        key=lambda t: (int(t.get("niveau", 0)), str(t.get("geslacht", "")), str(t.get("naam", ""))),
    )

    for team in sorted_teams:
        team_name = str(team["naam"])
        team_niveau = int(team["niveau"])
        team_geslacht = str(team["geslacht"])
        team_leeftijd = str(team["leeftijd"])

        cells = []
        for ronde in range(1, n_rondes + 1):
            slot = timeline_lookup.get(team_name, {}).get(ronde)
            if slot:
                level_class = f"level-{team_niveau}"
                cells.append(
                    f"""
                    <td class="timeline-slot">
                      <div class="timeline-match {level_class}">
                        <div class="timeline-opponent">{html.escape(slot['opponent'])}</div>
                        <span class="timeline-subline">Veld {slot['veld']:02d}</span>
                        <span class="timeline-subline">
                          {html.escape(slot['opponent_geslacht'])} · {html.escape(slot['opponent_leeftijd'])} · Niveau {slot['opponent_niveau']}
                        </span>
                      </div>
                    </td>
                    """
                )
            else:
                cells.append(
                    """
                    <td class="timeline-slot">
                      <span class="timeline-empty">—</span>
                    </td>
                    """
                )

        body_rows.append(
            f"""
            <tr>
              <td class="timeline-team-cell">
                <div class="timeline-team-name">{html.escape(team_name)}</div>
                <span class="timeline-team-meta">
                  {html.escape(team_geslacht)} · {html.escape(team_leeftijd)} · Niveau {team_niveau}
                </span>
              </td>
              {''.join(cells)}
            </tr>
            """
        )

    timeline_el.innerHTML = f"""
    <section class="timeline-shell">
      <div class="round-header">Team timeline</div>
      <div class="timeline-scroll">
        <table class="timeline-table">
          <thead>
            <tr>
              {''.join(header_cells)}
            </tr>
          </thead>
          <tbody>
            {''.join(body_rows)}
          </tbody>
        </table>
      </div>
    </section>
    """


def render_results(results: dict) -> None:
    summary_el = document.getElementById("summary")
    remaining_el = document.getElementById("remaining-output")

    matches = results["matches"]
    rounds = sorted({m["ronde"] for m in matches})

    summary_el.innerHTML = f"""
    <div class="summary-list">
      <div class="summary-item">
        <span class="muted">Aantal wedstrijden</span>
        <strong>{len(matches)}</strong>
      </div>
      <div class="summary-item">
        <span class="muted">Rondes gebruikt</span>
        <strong>{len(rounds)}</strong>
      </div>
      <div class="summary-item">
        <span class="muted">Ongebruikte slots</span>
        <strong>{sum(results['remaining_required'].values())}</strong>
      </div>
    </div>
    """

    render_table_schedule(results)
    render_team_timeline(results)

    remaining_rows = []
    for name in sorted(results["remaining_required"].keys()):
        remaining_rows.append(
            f"""
            <tr>
              <td>{html.escape(name)}</td>
              <td>{results['remaining_required'][name]}</td>
              <td>{results['remaining_optional'][name]}</td>
            </tr>
            """
        )

    remaining_el.innerHTML = f"""
    <section class="panel" style="padding:0; margin-top: 16px;">
      <div class="round-header">Remaining capacity</div>
      <table class="remaining-table">
        <thead>
          <tr><th>Team</th><th>Required left</th><th>Optional left</th></tr>
        </thead>
        <tbody>
          {''.join(remaining_rows)}
        </tbody>
      </table>
    </section>
    """

    set_output_view(OUTPUT_VIEW)

def _build_excel_overview_rows(results: dict) -> list[list]:
    matches = results.get("matches", [])
    teams = results.get("teams", [])
    rounds_used = sorted({int(m["ronde"]) for m in matches})

    return [
        ["Metric", "Value"],
        ["Aantal teams", len(teams)],
        ["Aantal wedstrijden", len(matches)],
        ["Rondes gebruikt", len(rounds_used)],
        ["Geconfigureerde rondes", int(results.get("n_rondes", 0) or 0)],
        ["Open verplichte slots", sum(results.get("remaining_required", {}).values())],
    ]


def _build_excel_matches_rows(results: dict) -> list[list]:
    rows = [
        [
            "Ronde",
            "Veld",
            "Team A",
            "Team A Geslacht",
            "Team A Leeftijd",
            "Team A Niveau",
            "Team B",
            "Team B Geslacht",
            "Team B Leeftijd",
            "Team B Niveau",
        ]
    ]

    for m in sorted(results.get("matches", []), key=lambda x: (x["ronde"], x["veld"])):
        rows.append(
            [
                int(m["ronde"]),
                int(m["veld"]),
                str(m["team_a"]["naam"]),
                str(m["team_a"]["geslacht"]),
                str(m["team_a"]["leeftijd"]),
                int(m["team_a"]["niveau"]),
                str(m["team_b"]["naam"]),
                str(m["team_b"]["geslacht"]),
                str(m["team_b"]["leeftijd"]),
                int(m["team_b"]["niveau"]),
            ]
        )

    return rows


def _build_excel_timeline_rows(results: dict) -> list[list]:
    teams = results.get("teams", [])
    matches = results.get("matches", [])
    n_rondes = int(results.get("n_rondes", 0) or 0)

    timeline_lookup: Dict[str, Dict[int, str]] = defaultdict(dict)

    for m in matches:
        ronde = int(m["ronde"])
        veld = int(m["veld"])

        a = m["team_a"]
        b = m["team_b"]

        timeline_lookup[str(a["naam"])][ronde] = f"{b['naam']} (Veld {veld:02d})"
        timeline_lookup[str(b["naam"])][ronde] = f"{a['naam']} (Veld {veld:02d})"

    header = ["Team", "Geslacht", "Leeftijd", "Niveau"]
    header.extend([f"Ronde {ronde}" for ronde in range(1, n_rondes + 1)])

    rows = [header]

    sorted_teams = sorted(
        teams,
        key=lambda t: (
            int(t.get("niveau", 0)),
            str(t.get("geslacht", "")),
            str(t.get("naam", "")),
        ),
    )

    for team in sorted_teams:
        team_name = str(team["naam"])
        row = [
            team_name,
            str(team["geslacht"]),
            str(team["leeftijd"]),
            int(team["niveau"]),
        ]

        for ronde in range(1, n_rondes + 1):
            row.append(timeline_lookup.get(team_name, {}).get(ronde, ""))

        rows.append(row)

    return rows


def _build_excel_remaining_rows(results: dict) -> list[list]:
    rows = [["Team", "Required left", "Optional left"]]

    required = results.get("remaining_required", {})
    optional = results.get("remaining_optional", {})

    for name in sorted(required.keys()):
        rows.append(
            [
                str(name),
                int(required.get(name, 0)),
                int(optional.get(name, 0)),
            ]
        )

    return rows


def _build_excel_preferences_rows() -> list[list]:
    rows = [["Team A", "Team B"]]

    try:
        prefs = get_preferences()
    except Exception:
        prefs = []

    for pair in prefs:
        if len(pair) == 2:
            rows.append([str(pair[0]), str(pair[1])])

    return rows


def on_export_excel(*args):
    if LAST_RESULT is None:
        set_status("Genereer eerst een schema voordat je exporteert.", "error")
        return

    try:
        wb = XLSX.utils.book_new()
        overview_ws = XLSX.utils.aoa_to_sheet(to_js(_build_excel_overview_rows(LAST_RESULT)))
        matches_ws = XLSX.utils.aoa_to_sheet(to_js(_build_excel_matches_rows(LAST_RESULT)))
        timeline_ws = XLSX.utils.aoa_to_sheet(to_js(_build_excel_timeline_rows(LAST_RESULT)))
        remaining_ws = XLSX.utils.aoa_to_sheet(to_js(_build_excel_remaining_rows(LAST_RESULT)))
        prefs_ws = XLSX.utils.aoa_to_sheet(to_js(_build_excel_preferences_rows()))

        XLSX.utils.book_append_sheet(wb, overview_ws, "Overzicht")
        XLSX.utils.book_append_sheet(wb, matches_ws, "Wedstrijden")
        XLSX.utils.book_append_sheet(wb, timeline_ws, "TeamTimeline")
        XLSX.utils.book_append_sheet(wb, remaining_ws, "Capaciteit")
        XLSX.utils.book_append_sheet(wb, prefs_ws, "Voorkeuren")

        XLSX.writeFile(wb, "tournament_schedule.xlsx")

        set_status("Excel-bestand succesvol gedownload.", "success")

    except Exception as exc:
        console.error(str(exc))
        set_status(f"Excel export error: {exc}", "error")


def on_generate(*args):
    global LAST_RESULT
    try:
        teams, prefs, n_rondes, n_velden, seed = read_inputs()

        success = False
        wedstrijden = []
        rest_verplicht = {}
        rest_opt = {}

        for _ in range(1000):
            wedstrijden, rest_verplicht, rest_opt = genereer_schema(
                teams=teams,
                voorkeuren=prefs,
                n_rondes=n_rondes,
                n_velden=n_velden,
                seed=seed,
            )
            if not any(rest_verplicht.values()):
                success = True
                break
            seed = random.randint(1, 1000)
            document.getElementById("seed").value = str(seed)

        LAST_RESULT = serialize_results(teams, wedstrijden, rest_verplicht, rest_opt, n_rondes)
        render_results(LAST_RESULT)

        if success:
            set_status(f"Succesvol {len(wedstrijden)} wedstrijden gegenereerd.", "success")
        else:
            set_status("Combinatie niet mogelijk.", "error")
    except Exception as exc:
        console.error(str(exc))
        set_status(f"Error: {exc}", "error")


def on_calculate(*args):
    global LAST_RESULT
    try:
        teams, prefs, n_rondes, n_velden, seed = read_inputs()

        succes = False
        wedstrijden = []
        rest_verplicht = {}
        rest_opt = {}
        result_n_velden = n_velden

        for _ in range(1000):
            wedstrijden, rest_verplicht, rest_opt, result_n_velden = bereken_minimaal_aantal_velden(
                teams=teams,
                voorkeuren=prefs,
                n_rondes=n_rondes,
                seed=seed,
            )
            if not any(rest_verplicht.values()):
                succes = True
                document.getElementById("n-velden").value = str(result_n_velden)
                break
            seed = random.randint(1, 1000)
            document.getElementById("seed").value = str(seed)

        LAST_RESULT = serialize_results(teams, wedstrijden, rest_verplicht, rest_opt, n_rondes)
        render_results(LAST_RESULT)

        if succes:
            set_status(f"Succesvol {len(wedstrijden)} wedstrijden gegenereerd.", "success")
        else:
            set_status("Combinatie niet mogelijk.", "error")
    except Exception as exc:
        console.error(str(exc))
        set_status(f"Error: {exc}", "error")


def init_fields() -> None:
    teams_el = document.getElementById("teams-json")
    prefs_el = document.getElementById("prefs-json")

    if not teams_el.value.strip():
        teams_el.value = "[]"

    if not prefs_el.value.strip():
        prefs_el.value = "[]"


def on_view_table(*args):
    set_output_view("table")


def on_view_timeline(*args):
    set_output_view("timeline")


def wire_events() -> None:
    global EVENT_PROXIES

    EVENT_PROXIES = [
        create_proxy(on_generate),
        create_proxy(on_teams_csv_selected),
        create_proxy(on_add_preference),
        create_proxy(on_teams_json_changed),
        create_proxy(on_prefs_json_changed),
        create_proxy(on_calculate),
        create_proxy(on_view_table),
        create_proxy(on_view_timeline),
        create_proxy(on_export_excel),
    ]

    document.getElementById("generate-btn").addEventListener("click", EVENT_PROXIES[0])
    document.getElementById("teams-csv-file").addEventListener("change", EVENT_PROXIES[1])
    document.getElementById("add-pref-btn").addEventListener("click", EVENT_PROXIES[2])
    document.getElementById("teams-json").addEventListener("change", EVENT_PROXIES[3])
    document.getElementById("prefs-json").addEventListener("change", EVENT_PROXIES[4])
    document.getElementById("min-fields-calc-button").addEventListener("click", EVENT_PROXIES[5])
    document.getElementById("view-table-btn").addEventListener("click", EVENT_PROXIES[6])
    document.getElementById("view-timeline-btn").addEventListener("click", EVENT_PROXIES[7])
    document.getElementById("export-excel").addEventListener("click", EVENT_PROXIES[8])



init_fields()
wire_events()
sync_preferences_ui()
set_output_view("table")