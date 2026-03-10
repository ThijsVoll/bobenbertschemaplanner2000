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

from js import console, document, navigator # type: ignore
from pyodide.ffi import create_proxy # type: ignore


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
            k for k in pool[i + 1 :] if k not in gebruikt and _geslacht_compatibel(t, k)
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
    resterend_opt: Dict[Team, int] = {t: OPTIONELE_WEDSTRIJDEN.get(t.niveau, 0) for t in teams}
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
    wedstrijden: List[Match], rest_verplicht: Dict[str, int], rest_opt: Dict[str, int]
) -> dict:
    return {
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


def render_results(results: dict) -> None:
    summary_el = document.getElementById("summary")
    output_el = document.getElementById("schedule-output")
    remaining_el = document.getElementById("remaining-output")

    matches = results["matches"]
    rounds = sorted({m["ronde"] for m in matches})

    summary_el.innerHTML = f"""
      <div class="summary-list">
        <div class="summary-item"><span class="muted">Total matches</span><strong>{len(matches)}</strong></div>
        <div class="summary-item"><span class="muted">Rounds used</span><strong>{len(rounds)}</strong></div>
        <div class="summary-item"><span class="muted">Unmet required slots</span><strong>{sum(results['remaining_required'].values())}</strong></div>
      </div>
    """

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
                  <td><strong>{html.escape(m['team_a']['naam'])}</strong><br><span class="muted small">{html.escape(m['team_a']['geslacht'])} · {html.escape(m['team_a']['leeftijd'])} · Niveau {m['team_a']['niveau']}</span></td>
                  <td><strong>{html.escape(m['team_b']['naam'])}</strong><br><span class="muted small">{html.escape(m['team_b']['geslacht'])} · {html.escape(m['team_b']['leeftijd'])} · Niveau {m['team_b']['niveau']}</span></td>
                </tr>
                """
            )
        schedule_parts.append(
            f"""
            <section class="round-block">
              <div class="round-header">Round {ronde}</div>
              <table class="match-table">
                <thead>
                  <tr><th>Field</th><th>Team A</th><th>Team B</th></tr>
                </thead>
                <tbody>
                  {''.join(rows)}
                </tbody>
              </table>
            </section>
            """
        )

    output_el.innerHTML = ''.join(schedule_parts) if schedule_parts else '<p class="muted">No matches scheduled.</p>'

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
    raise ValueError(
        "Missing required CSV column. Expected one of: " + ", ".join(aliases)
    )


def parse_teams_csv_text(csv_text: str) -> List[dict]:
    if not csv_text or not csv_text.strip():
        raise ValueError("The selected CSV file is empty.")

    sample = csv_text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;	")
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
        placeholder_a.textContent = "Import teams first"
        select_a.appendChild(placeholder_a)

        placeholder_b = document.createElement("option")
        placeholder_b.value = ""
        placeholder_b.textContent = "Import teams first"
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
        row.textContent = "No preferences added yet."
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
        set_status(f"Imported {len(teams)} teams from {file.name}.", "success")
    except Exception as exc:
        console.error(str(exc))
        set_status(f"CSV import error: {exc}", "error")


def on_teams_csv_selected(*args):
    asyncio.create_task(import_csv_async())

def load_example_data(*args):
    document.getElementById("teams-json").value = json.dumps(EXAMPLE_TEAMS, indent=2, ensure_ascii=False)
    document.getElementById("prefs-json").value = json.dumps(EXAMPLE_PREFS, indent=2, ensure_ascii=False)
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
        
        schema, rest_verplicht, rest_optioneel = genereer_schema(teams, voorkeuren, n_rondes=n_rondes, n_velden=i, seed=7)
        if not any(rest_verplicht.values()):
            return schema, rest_verplicht, rest_optioneel, i
    
    return [], {}, (), -1


def read_inputs() -> tuple[list[Team], list[tuple[str, str]], int, int, Optional[int]]:
    teams_raw = json.loads(document.getElementById("teams-json").value)
    prefs_raw = json.loads(document.getElementById("prefs-json").value)
    n_rondes = int(document.getElementById("n-rondes").value)
    n_velden = int(document.getElementById("n-velden").value)
    seed_text = document.getElementById("seed").value.strip()
    seed = int(seed_text) if seed_text else None

    teams = []
    for item in teams_raw:
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
        if not isinstance(pair, list) and not isinstance(pair, tuple):
            raise ValueError("Each preference must be a 2-item array, e.g. ['Team A', 'Team B']")
        if len(pair) != 2:
            raise ValueError("Each preference must contain exactly 2 team names.")
        prefs.append((str(pair[0]), str(pair[1])))

    return teams, prefs, n_rondes, n_velden, seed


def on_generate(*args):
    global LAST_RESULT
    try:

        teams, prefs, n_rondes, n_velden, seed = read_inputs()
        for _ in range(10000):
            
            wedstrijden, rest_verplicht, rest_opt = genereer_schema(
                teams=teams,
                voorkeuren=prefs,
                n_rondes=n_rondes,
                n_velden=n_velden,
                seed=seed,
            )

            if not any(rest_verplicht.values()):
                break
            else:
                seed = random.randint(1, 1000)
                document.getElementById("seed").value = seed

        LAST_RESULT = serialize_results(wedstrijden, rest_verplicht, rest_opt)
        render_results(LAST_RESULT)
        set_status(f"Generated {len(wedstrijden)} matches successfully.", "success")
    except Exception as exc:
        console.error(str(exc))
        set_status(f"Error: {exc}", "error")

def on_calculate(*args):
    global LAST_RESULT
    try:

        teams, prefs, n_rondes, n_velden, seed = read_inputs()
        succes = False
        for _ in range(10000):

            
            wedstrijden, rest_verplicht, rest_opt, n_velden = bereken_minimaal_aantal_velden(
                teams=teams,
                voorkeuren=prefs,
                n_rondes=n_rondes,
                seed=seed,
            )

            if not any(rest_verplicht.values()):
                succes = True
                document.getElementById("n-velden").value = n_velden
                break
            else:
                seed = random.randint(1, 1000)
                document.getElementById("seed").value = seed

        LAST_RESULT = serialize_results(wedstrijden, rest_verplicht, rest_opt)
        render_results(LAST_RESULT)

        if succes:
            set_status(f"Generated {len(wedstrijden)} matches successfully.", "success")
        else:
            set_status(f"Combinatie niet mogelijk.", "error")
    except Exception as exc:
        console.error(str(exc))
        set_status(f"Error: {exc}", "error")


def on_copy_json(*args):
    if LAST_RESULT is None:
        set_status("Generate a schedule first, then copy the JSON.", "error")
        return

    payload = json.dumps(LAST_RESULT, indent=2, ensure_ascii=False)
    try:
        promise = navigator.clipboard.writeText(payload)
        set_status("Copied results JSON to clipboard.", "success")
        return promise
    except Exception:
        set_status("Clipboard copy failed. Open DevTools and copy window.LAST_RESULT if needed.", "error")


def wire_events() -> None:
    global EVENT_PROXIES
    EVENT_PROXIES = [
        create_proxy(on_generate),
        create_proxy(on_copy_json),
        create_proxy(on_teams_csv_selected),
        create_proxy(on_add_preference),
        create_proxy(on_teams_json_changed),
        create_proxy(on_prefs_json_changed),
        create_proxy(on_calculate),
    ]

    document.getElementById("generate-btn").addEventListener("click", EVENT_PROXIES[0])
    document.getElementById("copy-json").addEventListener("click", EVENT_PROXIES[1])
    document.getElementById("teams-csv-file").addEventListener("change", EVENT_PROXIES[2])
    document.getElementById("add-pref-btn").addEventListener("click", EVENT_PROXIES[3])
    document.getElementById("teams-json").addEventListener("change", EVENT_PROXIES[4])
    document.getElementById("prefs-json").addEventListener("change", EVENT_PROXIES[5])
    document.getElementById("min-fields-calc-button").addEventListener("click", EVENT_PROXIES[6])

wire_events()
load_example_data()