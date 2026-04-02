from __future__ import annotations

import asyncio
import json
import random
from typing import Optional

from browser import console, create_proxy, document, get_element, set_status
from constants import  EXAMPLE_PREFS, EXAMPLE_TEAMS
from data_access import InputRepository
from exporters import ExcelExporter
from renderers import PreferencesRenderer, ResultsRenderer, TeamsRenderer
from schedulerv2 import CapacityAnalyzer
from sat import TournamentSchedulerSAT as TournamentScheduler
from serializers import serialize_results
from state import AppState


class AppController:
    """Coordinates data access, scheduling logic and UI updates."""

    def __init__(self) -> None:
        self.state = AppState()
        self.preferences_renderer = PreferencesRenderer(self.state, set_status)
        self.results_renderer = ResultsRenderer(self.state)
        self.teams_renderer = TeamsRenderer(
            self.state,
            self.sync_preferences_ui,
            set_status,
        )
        self.excel_exporter = ExcelExporter()

    def init_fields(self) -> None:
        teams_element = get_element("teams-json")
        prefs_element = get_element("prefs-json")
        if not teams_element.value.strip():
            teams_element.value = "[]"
        if not prefs_element.value.strip():
            prefs_element.value = "[]"

    def sync_preferences_ui(self) -> None:
        self.preferences_renderer.sync()

    def on_add_team(self, *args) -> None:
        try:
            name = get_element("new-team-name").value.strip()
            gender = get_element("new-team-gender").value.strip()
            age = get_element("new-team-age").value.strip()
            level_text = get_element("new-team-level").value.strip()
            wedstrijden_text = get_element("new-team-matches").value.strip()
            if not name:
                raise ValueError("Naam is verplicht.")
            if not gender:
                raise ValueError("Geslacht is verplicht.")
            if not age:
                raise ValueError("Leeftijd is verplicht.")
            try:
                level = int(level_text)
            except Exception as exc:
                raise ValueError("Niveau moet een geheel getal zijn.") from exc
            try:
                wedstrijden = int(wedstrijden_text)
            except Exception as exc:
                raise ValueError("wedstijden moet een geheel getal zijn.") from exc
            
            if name in set(InputRepository.get_team_names()):
                raise ValueError(f"Teamname '{name}' bestaat al. Kies een unieke name.")
            current = InputRepository.get_team_dicts()
            current.append(
                {
                    "level": level,
                    "gender": gender,
                    "name": name,
                    "age": age,
                    "wedstrijden": wedstrijden
                }
            )
            InputRepository.set_teams_json(current)
            get_element("new-team-name").value = ""
            get_element("new-team-level").value = "1"
            get_element("new-team-level").value = "3"
            get_element("new-team-gender").value = "Mixed"
            get_element("new-team-age").value = "Jong"
            self.sync_preferences_ui()
            self.teams_renderer.render()
            set_status(f"Team '{name}' toegevoegd.", "success")
        except Exception as exc:
            console.error(str(exc))
            set_status(f"Error: {exc}", "error")

    async def import_teams_csv_async(self) -> None:
        file_input = get_element("teams-csv-file")
        files = file_input.files
        if not files or files.length == 0:
            return
        file = files.item(0)
        set_status(f"Reading {file.name}...", "info")
        try:
            csv_text = await file.text()
            teams = InputRepository.parse_teams_csv_text(str(csv_text))
            get_element("teams-json").value = json.dumps(teams, indent=2, ensure_ascii=False)
            self.sync_preferences_ui()
            self.teams_renderer.render()
            set_status(f"{len(teams)} teams geimporteerd van {file.name}.", "success")
        except Exception as exc:
            console.error(str(exc))
            set_status(f"CSV import error: {exc}", "error")

    async def import_prefs_csv_async(self) -> None:
        file_input = get_element("prefs-csv-file")
        files = file_input.files
        if not files or files.length == 0:
            return
        file = files.item(0)
        set_status(f"Reading {file.name}...", "info")
        try:
            csv_text = await file.text()
            prefs = InputRepository.parse_prefs_csv_text(str(csv_text))
            get_element("prefs-json").value = json.dumps(prefs, indent=2, ensure_ascii=False)
            self.sync_preferences_ui()
            self.teams_renderer.render()
            set_status(f"{len(prefs)} teams geimporteerd van {file.name}.", "success")
        except Exception as exc:
            console.error(str(exc))
            set_status(f"CSV import error: {exc}", "error")

    def on_teams_csv_selected(self, *args) -> None:
        asyncio.create_task(self.import_teams_csv_async())

    def on_prefs_csv_selected(self, *args) -> None:
        asyncio.create_task(self.import_prefs_csv_async())

    def load_example_data(self, *args) -> None:
        get_element("teams-json").value = json.dumps(EXAMPLE_TEAMS, indent=2, ensure_ascii=False)
        get_element("prefs-json").value = json.dumps(EXAMPLE_PREFS, indent=2, ensure_ascii=False)
        self.sync_preferences_ui()
        set_status("Loaded example dataset.", "success")

    def on_add_preference(self, *args) -> None:
        try:
            team_a = get_element("pref-team-a").value.strip()
            team_b = get_element("pref-team-b").value.strip()
            if not team_a or not team_b:
                raise ValueError("Select two teams first.")
            if team_a == team_b:
                raise ValueError("A preference must contain two different teams.")
            prefs = InputRepository.get_preferences()
            pair = [team_a, team_b]
            reverse_pair = [team_b, team_a]
            if pair in prefs or reverse_pair in prefs:
                raise ValueError("This preference already exists.")
            prefs.append(pair)
            InputRepository.set_preferences(prefs)
            self.preferences_renderer.render()
            set_status(f"Added preference: {team_a} ↔ {team_b}", "success")
        except Exception as exc:
            console.error(str(exc))
            set_status(f"Preference error: {exc}", "error")

    def on_teams_json_changed(self, *args) -> None:
        try:
            self.sync_preferences_ui()
            self.teams_renderer.render()
        except Exception:
            self.preferences_renderer.populate_dropdowns()
            self.teams_renderer.render()

    def on_prefs_json_changed(self, *args) -> None:
        self.preferences_renderer.render()

    def on_generate(self, *args) -> None:
        try:
            teams, prefs, n_rondes, n_velden= InputRepository.read_inputs()
            scheduler = TournamentScheduler(teams=teams, preferences=prefs)

            ok = True
            wedstrijden, rest_verplicht = scheduler.generate_schedule(
                n_rondes,
                n_velden
            )
 
            self.state.last_result = serialize_results(
                teams,
                wedstrijden,
                rest_verplicht,
                n_rondes,
            )
            self.results_renderer.render_results(self.state.last_result)

            if ok:
                set_status(f"Succesvol {len(wedstrijden)} wedstrijden gegenereerd.", "success")
            else:
                set_status("Combinatie niet mogelijk (node-/tijdlimiet bereikt).", "error")

        except Exception as exc:
            console.error(str(exc))
            set_status(f"Error: {exc}", "error")

    def on_export_excel(self, *args) -> None:
        if self.state.last_result is None:
            set_status("Genereer eerst een schema voordat je exporteert.", "error")
            return
        try:
            self.excel_exporter.export(self.state.last_result)
            set_status("Excel-bestand succesvol gedownload.", "success")
        except Exception as exc:
            console.error(str(exc))
            set_status(f"Excel export error: {exc}", "error")

    def on_view_table(self, *args) -> None:
        self.results_renderer.set_output_view("table")

    def on_view_timeline(self, *args) -> None:
        self.results_renderer.set_output_view("timeline")

    def wire_events(self) -> None:
        self.state.event_proxies = [
            create_proxy(self.on_generate),
            create_proxy(self.on_teams_csv_selected),
            create_proxy(self.on_add_preference),
            create_proxy(self.on_teams_json_changed),
            create_proxy(self.on_prefs_json_changed),
            create_proxy(self.on_view_table),
            create_proxy(self.on_view_timeline),
            create_proxy(self.on_export_excel),
            create_proxy(self.on_add_team),
            create_proxy(self.on_prefs_csv_selected)
        ]
        get_element("generate-btn").addEventListener("click", self.state.event_proxies[0])
        get_element("teams-csv-file").addEventListener("change", self.state.event_proxies[1])
        get_element("add-pref-btn").addEventListener("click", self.state.event_proxies[2])
        get_element("teams-json").addEventListener("change", self.state.event_proxies[3])
        get_element("prefs-json").addEventListener("change", self.state.event_proxies[4])
        get_element("view-table-btn").addEventListener("click", self.state.event_proxies[5])
        get_element("view-timeline-btn").addEventListener("click", self.state.event_proxies[6])
        get_element("export-excel").addEventListener("click", self.state.event_proxies[7])
        get_element("add-team-btn").addEventListener("click", self.state.event_proxies[8])
        get_element("prefs-csv-file").addEventListener("change", self.state.event_proxies[9])

    def initialize(self) -> None:
        self.init_fields()
        self.wire_events()
        self.sync_preferences_ui()
        self.results_renderer.set_output_view("table")
        self.teams_renderer.render()
