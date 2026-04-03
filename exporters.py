from __future__ import annotations

from browser import XLSX, to_js
from js import XLSX, Object, Reflect
from js import XLSX, Object, Reflect
from pyodide.ffi import to_js




def _js(obj):
    """Convert Python dict/list -> plain JS objects/arrays"""
    return to_js(obj, dict_converter=Object.fromEntries)


def _cell_addr(r: int, c: int) -> str:
    """Zero-based row/col -> A1 address"""
    return XLSX.utils.encode_cell(_js({"r": r, "c": c}))


def _get_cell(sheet, addr: str):
    """Read a JS worksheet cell"""
    return Reflect.get(sheet, addr)


def _set_prop(obj, key: str, value):
    """Set any JS property safely from Pyodide"""
    Reflect.set(obj, key, value)


def _set_cell_style(sheet, addr: str, style: dict):
    cell = _get_cell(sheet, addr)
    if cell is None:
        return
    _set_prop(cell, "s", _js(style))

class ExcelExporter:
    """Exports the schedule to a single XLSX sheet grouped by ronde."""

    @staticmethod
    def _build_rows_and_merges(results: dict) -> tuple[list[list], list[dict]]:
        rows = [["Veld", "Team A", "Team B"]]
        merges = []

        matches = results["matches"]
        n_rondes = results["n_rondes"]

        current_row_index = 1  # zero-based row index in Excel, after header row

        for ronde in range(1, n_rondes + 1):
            # Add merged round title row
            rows.append([f"Ronde {ronde}", "", ""])
            merges.append(
                {
                    "s": {"r": current_row_index, "c": 0},
                    "e": {"r": current_row_index, "c": 2},
                }
            )
            current_row_index += 1

            # Add matches for this round, sorted by veld
            ronde_matches = sorted(
                [match for match in matches if match["ronde"] == ronde],
                key=lambda match: match["veld"],
            )

            for match in ronde_matches:
                rows.append(
                    [
                        f"Veld {match['veld']}",
                        match["team_a"]["name"],
                        match["team_b"]["name"],
                    ]
                )
                current_row_index += 1

        return rows, merges



    def export(self, results: dict) -> None:
        workbook = XLSX.utils.book_new()

        rows, merges = self._build_rows_and_merges(results)
        sheet = XLSX.utils.aoa_to_sheet(to_js(rows))

        # worksheet metadata
        _set_prop(sheet, "!merges", _js(merges))
        _set_prop(
            sheet,
            "!cols",
            _js(
                [
                    {"wch": 12},  # Veld
                    {"wch": 28},  # Team A
                    {"wch": 28},  # Team B
                ]
            ),
        )

        # ---- styles ----
        merged_title_style = {
            "alignment": {
                "horizontal": "center",
                "vertical": "center",
                "wrapText": True,
            },
            "fill": {
                "patternType": "solid",
                "fgColor": {"rgb": "FF1F4E78"},  # dark blue
            },
            "font": {
                "bold": True,
                "color": {"rgb": "FFFFFFFF"},
                "sz": 13,
                "name": "Calibri",
            },
            "border": {
                "top": {"style": "thin", "color": {"rgb": "FF1F1F1F"}},
                "bottom": {"style": "thin", "color": {"rgb": "FF1F1F1F"}},
                "left": {"style": "thin", "color": {"rgb": "FF1F1F1F"}},
                "right": {"style": "thin", "color": {"rgb": "FF1F1F1F"}},
            },
        }

        header_style = {
            "alignment": {
                "horizontal": "center",
                "vertical": "center",
                "wrapText": True,
            },
            "fill": {
                "patternType": "solid",
                "fgColor": {"rgb": "FFD9E2F3"},  # light blue
            },
            "font": {
                "bold": True,
                "color": {"rgb": "FF000000"},
                "sz": 11,
                "name": "Calibri",
            },
            "border": {
                "top": {"style": "thin", "color": {"rgb": "FF808080"}},
                "bottom": {"style": "thin", "color": {"rgb": "FF808080"}},
                "left": {"style": "thin", "color": {"rgb": "FF808080"}},
                "right": {"style": "thin", "color": {"rgb": "FF808080"}},
            },
        }

        data_style = {
            "alignment": {
                "vertical": "center",
                "horizontal": "left",
                "wrapText": True,
            },
            "border": {
                "top": {"style": "thin", "color": {"rgb": "FFD9D9D9"}},
                "bottom": {"style": "thin", "color": {"rgb": "FFD9D9D9"}},
                "left": {"style": "thin", "color": {"rgb": "FFD9D9D9"}},
                "right": {"style": "thin", "color": {"rgb": "FFD9D9D9"}},
            },
            "font": {
                "name": "Calibri",
                "sz": 11,
                "color": {"rgb": "FF000000"},
            },
        }

        # ---- apply style to merged rows (top-left cell of each merge) ----
        for merge in merges:
            top_left = merge["s"]
            addr = _cell_addr(top_left["r"], top_left["c"])
            _set_cell_style(sheet, addr, merged_title_style)

        # ---- apply header style to first non-title row (adjust row index if needed) ----
        # Example assumes row 1 is header: [Veld, Team A, Team B]
        for c in range(3):
            _set_cell_style(sheet, _cell_addr(1, c), header_style)

        # ---- apply data style to remaining rows ----
        for r in range(2, len(rows)):
            for c in range(3):
                _set_cell_style(sheet, _cell_addr(r, c), data_style)

        XLSX.utils.book_append_sheet(workbook, sheet, "Schema")
        XLSX.writeFile(workbook, "tournament_schedule.xlsx")
