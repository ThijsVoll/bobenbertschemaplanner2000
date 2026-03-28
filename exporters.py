from __future__ import annotations

from browser import XLSX, to_js
from data_access import InputRepository
from serializers import (
    build_excel_matches_rows,
    build_excel_overview_rows,
    build_excel_remaining_rows,
    build_excel_timeline_rows,
)


class ExcelExporter:
    """Exports the current schedule state to an XLSX workbook."""

    @staticmethod
    def build_excel_preferences_rows() -> list[list]:
        rows = [["Team A", "Team B"]]
        try:
            prefs = InputRepository.get_preferences()
        except Exception:
            prefs = []
        for pair in prefs:
            if len(pair) == 2:
                rows.append([str(pair[0]), str(pair[1])])
        return rows

    def export(self, results: dict) -> None:
        workbook = XLSX.utils.book_new()
        overview_sheet = XLSX.utils.aoa_to_sheet(to_js(build_excel_overview_rows(results)))
        matches_sheet = XLSX.utils.aoa_to_sheet(to_js(build_excel_matches_rows(results)))
        timeline_sheet = XLSX.utils.aoa_to_sheet(to_js(build_excel_timeline_rows(results)))
        remaining_sheet = XLSX.utils.aoa_to_sheet(to_js(build_excel_remaining_rows(results)))
        prefs_sheet = XLSX.utils.aoa_to_sheet(to_js(self.build_excel_preferences_rows()))
        XLSX.utils.book_append_sheet(workbook, overview_sheet, "Overzicht")
        XLSX.utils.book_append_sheet(workbook, matches_sheet, "Wedstrijden")
        XLSX.utils.book_append_sheet(workbook, timeline_sheet, "TeamTimeline")
        XLSX.utils.book_append_sheet(workbook, remaining_sheet, "Capaciteit")
        XLSX.utils.book_append_sheet(workbook, prefs_sheet, "Voorkeuren")
        XLSX.writeFile(workbook, "tournament_schedule.xlsx")
