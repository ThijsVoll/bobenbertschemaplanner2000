from __future__ import annotations

import html
from collections import defaultdict
from typing import Callable

from browser import create_proxy, document, get_element
from data_access import InputRepository
from state import AppState


class TeamsRenderer:
    """Renders and wires the editable teams table."""

    def __init__(
        self,
        state: AppState,
        sync_preferences_ui: Callable[[], None],
        set_status: Callable[[str, str], None],
    ) -> None:
        self.state = state
        self.sync_preferences_ui = sync_preferences_ui
        self.set_status = set_status

    def apply_team_name_filter(self) -> None:
        query = self.state.team_name_filter.strip().lower()
        rows = document.querySelectorAll("#teams-list tbody tr")
        for row in rows:
            team_name = (row.getAttribute("data-team-name") or "").lower()
            row.style.display = "" if query in team_name else "none"

    def on_toggle_team_name_filter(self, event=None) -> None:
        self.state.team_name_filter_open = not self.state.team_name_filter_open
        self.render()
        if self.state.team_name_filter_open:
            input_element = get_element("team-name-filter-input")
            if input_element is not None:
                input_element.focus()
                try:
                    length = len(self.state.team_name_filter)
                    input_element.setSelectionRange(length, length)
                except Exception:
                    pass

    def on_team_name_filter_input(self, event=None) -> None:
        input_element = get_element("team-name-filter-input")
        if input_element is None:
            return
        self.state.team_name_filter = str(input_element.value or "")
        self.apply_team_name_filter()

    def render(self) -> None:
        self.state.remove_team_proxies = []
        self.state.team_filter_proxies = []
        container = get_element("teams-list")
        if container is None:
            return
        try:
            teams = InputRepository.get_team_dicts()
        except Exception as exc:
            container.innerHTML = (
                f'<div class="status status-error">Teams UI unavailable: '
                f'{html.escape(str(exc))}</div>'
            )
            return
        if not teams:
            container.innerHTML = (
                '<div class="muted small">Nog geen teams toegevoegd. '
                'Importeer een CSV of voeg teams toe via het formulier hierboven.</div>'
            )
            return

        teams_sorted = sorted(
            teams,
            key=lambda team: (
                int(team.get("niveau", 0)),
                str(team.get("geslacht", "")),
                str(team.get("naam", "")),
            ),
        )
        filter_value = html.escape(self.state.team_name_filter, quote=True)
        input_class = (
            "teams-filter-input"
            if self.state.team_name_filter_open
            else "teams-filter-input hidden"
        )

        html_parts = [
            '<table class="teams-table">',
            '<thead><tr>',
            (
                '<th class="teams-filter-header">'
                '<button type="button" class="teams-filter-trigger" '
                'id="team-name-filter-toggle">Naam</button>'
                f'<input id="team-name-filter-input" class="{input_class}" '
                f'type="text" placeholder="Filter op naam..." value="{filter_value}" />'
                '</th>'
            ),
            '<th>Geslacht</th>',
            '<th>Leeftijd</th>',
            '<th>Niveau</th>',
            '<th></th>',
            '</tr></thead><tbody>',
        ]
        for index, team in enumerate(teams_sorted):
            naam = html.escape(str(team.get("naam", "")))
            geslacht = html.escape(str(team.get("geslacht", "")))
            leeftijd = html.escape(str(team.get("leeftijd", "")))
            niveau = int(team.get("niveau", 0))
            html_parts.append(
                f'<tr id="team-row-{index}" data-team-name="{naam.lower()}">'
                f'<td>{naam}</td>'
                f'<td>{geslacht}</td>'
                f'<td>{leeftijd}</td>'
                f'<td>{niveau}</td>'
                f'<td><button type="button" class="secondary" id="del-team-{index}">'
                'Verwijderen</button></td>'
                '</tr>'
            )
        html_parts.append('</tbody></table>')
        container.innerHTML = ''.join(html_parts)

        for index, team_name in enumerate(str(team.get("naam", "")) for team in teams_sorted):
            def make_delete_handler(name: str):
                def handler(event=None):
                    try:
                        current = InputRepository.get_team_dicts()
                        new_list = [
                            item for item in current if str(item.get("naam", "")) != name
                        ]
                        if len(new_list) == len(current):
                            self.set_status(f"Team '{name}' niet gevonden.", "error")
                            return
                        InputRepository.set_teams_json(new_list)
                        self.sync_preferences_ui()
                        self.render()
                        self.set_status(f"Team '{name}' verwijderd.", "success")
                    except Exception as exc:
                        self.set_status(f"Error: {exc}", "error")
                return handler

            proxy = create_proxy(make_delete_handler(team_name))
            self.state.remove_team_proxies.append(proxy)
            button = get_element(f"del-team-{index}")
            if button is not None:
                button.addEventListener("click", proxy)

        toggle_button = get_element("team-name-filter-toggle")
        if toggle_button is not None:
            toggle_proxy = create_proxy(self.on_toggle_team_name_filter)
            self.state.team_filter_proxies.append(toggle_proxy)
            toggle_button.addEventListener("click", toggle_proxy)

        input_element = get_element("team-name-filter-input")
        if input_element is not None:
            input_proxy = create_proxy(self.on_team_name_filter_input)
            self.state.team_filter_proxies.append(input_proxy)
            input_element.addEventListener("input", input_proxy)
        self.apply_team_name_filter()


class PreferencesRenderer:
    """Renders preferences controls and list."""

    def __init__(self, state: AppState, set_status: Callable[[str, str], None]) -> None:
        self.state = state
        self.set_status = set_status

    def populate_dropdowns(self) -> None:
        team_names = sorted(set(InputRepository.get_team_names()))
        select_a = get_element("pref-team-a")
        select_b = get_element("pref-team-b")
        empty_hint = get_element("prefs-editor-empty")
        select_a.innerHTML = ""
        select_b.innerHTML = ""
        if not team_names:
            for select in (select_a, select_b):
                placeholder = document.createElement("option")
                placeholder.value = ""
                placeholder.textContent = "Eerst teams importeren"
                select.appendChild(placeholder)
                select.disabled = True
            empty_hint.style.display = "block"
            return
        select_a.disabled = False
        select_b.disabled = False
        empty_hint.style.display = "none"
        for name in team_names:
            for select in (select_a, select_b):
                option = document.createElement("option")
                option.value = name
                option.textContent = name
                select.appendChild(option)
        select_b.selectedIndex = 1 if len(team_names) > 1 else 0

    def render(self) -> None:
        self.state.remove_pref_proxies = []
        container = get_element("prefs-list")
        container.innerHTML = ""
        try:
            prefs = InputRepository.get_preferences()
            valid_teams = set(InputRepository.get_team_names())
        except Exception as exc:
            row = document.createElement("div")
            row.className = "status status-error"
            row.textContent = f"Preferences UI unavailable: {exc}"
            container.appendChild(row)
            return
        if not prefs:
            row = document.createElement("div")
            row.className = "muted small"
            row.textContent = "Nog geen voorkeuren toegevoegd."
            container.appendChild(row)
            return
        for index, pair in enumerate(prefs):
            team_a_name, team_b_name = pair
            row = document.createElement("div")
            row.style.display = "flex"
            row.style.justifyContent = "space-between"
            row.style.alignItems = "center"
            row.style.gap = "12px"
            row.style.padding = "10px 12px"
            row.style.border = "1px solid rgba(255,255,255,0.12)"
            row.style.borderRadius = "10px"
            label = document.createElement("div")
            label_text = f"{team_a_name} ↔ {team_b_name}"
            if team_a_name not in valid_teams or team_b_name not in valid_teams:
                label_text += " (team missing from current import)"
            label.textContent = label_text
            row.appendChild(label)
            button = document.createElement("button")
            button.type = "button"
            button.className = "secondary"
            button.textContent = "Remove"

            def make_remove_handler(pref_index: int):
                def handler(event=None):
                    prefs_now = InputRepository.get_preferences()
                    if 0 <= pref_index < len(prefs_now):
                        del prefs_now[pref_index]
                        InputRepository.set_preferences(prefs_now)
                        self.render()
                        self.set_status("Preference removed.", "success")
                return handler

            proxy = create_proxy(make_remove_handler(index))
            self.state.remove_pref_proxies.append(proxy)
            button.addEventListener("click", proxy)
            row.appendChild(button)
            container.appendChild(row)

    def sync(self) -> None:
        self.populate_dropdowns()
        self.render()


class ResultsRenderer:
    """Renders the schedule, team timeline and summary output."""

    def __init__(self, state: AppState) -> None:
        self.state = state

    def set_output_view(self, view: str) -> None:
        self.state.output_view = view
        table_button = get_element("view-table-btn")
        timeline_button = get_element("view-timeline-btn")
        table_element = get_element("schedule-output")
        timeline_element = get_element("timeline-output")
        if view == "timeline":
            table_element.classList.add("hidden")
            timeline_element.classList.remove("hidden")
            table_button.classList.remove("is-active")
            timeline_button.classList.add("is-active")
        else:
            timeline_element.classList.add("hidden")
            table_element.classList.remove("hidden")
            timeline_button.classList.remove("is-active")
            table_button.classList.add("is-active")

    @staticmethod
    def clear_output_sections() -> None:
        get_element("schedule-output").innerHTML = ""
        get_element("timeline-output").innerHTML = ""
        get_element("remaining-output").innerHTML = ""

    @staticmethod
    def show_primary_summary(html_content: str) -> None:
        summary = get_element("summary")
        capacity = get_element("capacity-summary")
        summary.innerHTML = html_content
        summary.classList.remove("hidden")
        capacity.innerHTML = ""
        capacity.classList.add("hidden")

    @staticmethod
    def clear_primary_summary() -> None:
        summary = get_element("summary")
        summary.innerHTML = ""
        summary.classList.add("hidden")

    def render_table_schedule(self, results: dict) -> None:
        output_element = get_element("schedule-output")
        matches = results["matches"]
        grouped: dict[int, list[dict]] = defaultdict(list)
        for match in sorted(matches, key=lambda item: (item["ronde"], item["veld"])):
            grouped[match["ronde"]].append(match)
        sections: list[str] = []
        for ronde in sorted(grouped):
            rows: list[str] = []
            for match in grouped[ronde]:
                rows.append(
                    f"""
                    <tr>
                      <td>{match['veld']:02d}</td>
                      <td><strong>{html.escape(match['team_a']['naam'])}</strong><br>
                          <span class="muted small">{html.escape(match['team_a']['geslacht'])} ·
                          {html.escape(match['team_a']['leeftijd'])} · Niveau {match['team_a']['niveau']}</span>
                      </td>
                      <td><strong>{html.escape(match['team_b']['naam'])}</strong><br>
                          <span class="muted small">{html.escape(match['team_b']['geslacht'])} ·
                          {html.escape(match['team_b']['leeftijd'])} · Niveau {match['team_b']['niveau']}</span>
                      </td>
                    </tr>
                    """
                )
            sections.append(
                f"""
                <section class="round-block">
                  <div class="round-header">Ronde {ronde}</div>
                  <table class="match-table">
                    <thead><tr><th>Veld</th><th>Team A</th><th>Team B</th></tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                  </table>
                </section>
                """
            )
        output_element.innerHTML = ''.join(sections) or '<p class="muted">Geen wedstrijden gepland.</p>'

    def render_team_timeline(self, results: dict) -> None:
        timeline_element = get_element("timeline-output")
        teams = results.get("teams", [])
        matches = results.get("matches", [])
        n_rondes = int(results.get("n_rondes", 0) or 0)
        timeline_lookup: dict[str, dict[int, dict]] = defaultdict(dict)
        for match in matches:
            ronde = int(match["ronde"])
            veld = int(match["veld"])
            team_a = match["team_a"]
            team_b = match["team_b"]
            timeline_lookup[team_a["naam"]][ronde] = {
                "opponent": team_b["naam"],
                "veld": veld,
                "opponent_geslacht": team_b["geslacht"],
                "opponent_leeftijd": team_b["leeftijd"],
                "opponent_niveau": team_b["niveau"],
            }
            timeline_lookup[team_b["naam"]][ronde] = {
                "opponent": team_a["naam"],
                "veld": veld,
                "opponent_geslacht": team_a["geslacht"],
                "opponent_leeftijd": team_a["leeftijd"],
                "opponent_niveau": team_a["niveau"],
            }
        if not teams:
            timeline_element.innerHTML = '<p class="muted">Geen teamdata beschikbaar.</p>'
            return
        header_cells = ['<th class="timeline-team-col">Team</th>']
        header_cells.extend(
            f'<th class="timeline-round-col">Ronde {ronde}</th>'
            for ronde in range(1, n_rondes + 1)
        )
        body_rows: list[str] = []
        sorted_teams = sorted(
            teams,
            key=lambda team: (
                int(team.get("niveau", 0)),
                str(team.get("geslacht", "")),
                str(team.get("naam", "")),
            ),
        )
        for team in sorted_teams:
            team_name = str(team["naam"])
            team_niveau = int(team["niveau"])
            team_geslacht = str(team["geslacht"])
            team_leeftijd = str(team["leeftijd"])
            cells: list[str] = []
            for ronde in range(1, n_rondes + 1):
                slot = timeline_lookup.get(team_name, {}).get(ronde)
                if slot:
                    cells.append(
                        f"""
                        <td class="timeline-slot">
                          <div class="timeline-match level-{team_niveau}">
                            <div class="timeline-opponent">{html.escape(slot['opponent'])}</div>
                            <span class="timeline-subline">Veld {slot['veld']:02d}</span>
                            <span class="timeline-subline">{html.escape(slot['opponent_geslacht'])} ·
                            {html.escape(slot['opponent_leeftijd'])} · Niveau {slot['opponent_niveau']}</span>
                          </div>
                        </td>
                        """
                    )
                else:
                    cells.append('<td class="timeline-slot"><span class="timeline-empty">—</span></td>')
            body_rows.append(
                f"""
                <tr>
                  <td class="timeline-team-cell">
                    <div class="timeline-team-name">{html.escape(team_name)}</div>
                    <span class="timeline-team-meta">{html.escape(team_geslacht)} ·
                    {html.escape(team_leeftijd)} · Niveau {team_niveau}</span>
                  </td>
                  {''.join(cells)}
                </tr>
                """
            )
        timeline_element.innerHTML = f"""
        <section class="timeline-shell">
          <div class="round-header">Team timeline</div>
          <div class="timeline-scroll">
            <table class="timeline-table">
              <thead><tr>{''.join(header_cells)}</tr></thead>
              <tbody>{''.join(body_rows)}</tbody>
            </table>
          </div>
        </section>
        """

    def render_results(self, results: dict) -> None:
        remaining_element = get_element("remaining-output")
        matches = results["matches"]
        rounds = sorted({match["ronde"] for match in matches})
        self.show_primary_summary(
            f"""
            <div class="summary-list">
              <div class="summary-item"><span class="muted">Aantal wedstrijden</span>
                <strong>{len(matches)}</strong></div>
              <div class="summary-item"><span class="muted">Rondes gebruikt</span>
                <strong>{len(rounds)}</strong></div>
              <div class="summary-item"><span class="muted">Niet ingedeelde wedstrijden (Verplicht/optioneel)</span>
                <strong>{sum(results['remaining_required'].values())}/{sum(results['remaining_optional'].values())}</strong>
              </div>
            </div>
            """
        )
        self.render_table_schedule(results)
        self.render_team_timeline(results)
        rows = []
        for name in sorted(results["remaining_required"]):
            rows.append(
                f"<tr><td>{html.escape(name)}</td>"
                f"<td>{results['remaining_required'][name]}</td>"
                f"<td>{results['remaining_optional'][name]}</td></tr>"
            )
        remaining_element.innerHTML = f"""
        <section class="panel" style="padding:0; margin-top: 16px;">
          <div class="round-header">Remaining capacity</div>
          <table class="remaining-table">
            <thead><tr><th>Team</th><th>Required left</th><th>Optional left</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </section>
        """
        self.set_output_view(self.state.output_view)
