from __future__ import annotations

import math
import random
from typing import Optional

from constants import OPTIONELE_WEDSTRIJDEN, VERPLICHTE_WEDSTRIJDEN
from models import Match, Team


class TournamentScheduler:
    """Generates tournament schedules using greedy and backtracking strategies."""

    def __init__(self, seed: Optional[int] = 42) -> None:
        self.seed = seed
        self.random = random.Random(seed)

    @staticmethod
    def naam_index(teams: list[Team]) -> dict[str, Team]:
        index: dict[str, Team] = {}
        for team in teams:
            if team.naam in index:
                raise ValueError(
                    f"Teamnaam '{team.naam}' komt dubbel voor; namen moeten uniek zijn."
                )
            index[team.naam] = team
        return index

    @staticmethod
    def consecutieve_rondes_toegestaan(vorige: Optional[int], huidige: int) -> bool:
        if vorige is None:
            return True
        return not (huidige == vorige + 1 and not (vorige == 5 and huidige == 6))

    @staticmethod
    def geslacht_compatibel(team_a: Team, team_b: Team) -> bool:
        return team_a.geslacht == team_b.geslacht

    @staticmethod
    def compatibiliteit_score(team_a: Team, team_b: Team) -> int:
        score = 100
        score -= abs(team_a.niveau - team_b.niveau) * 20
        return score

    def pareer_gretig(
        self,
        beschikbaar: list[Team],
        al_gespeeld: set[frozenset[str]],
    ) -> list[tuple[Team, Team]]:
        paren: list[tuple[Team, Team]] = []
        pool = sorted(beschikbaar, key=lambda team: (team.niveau, team.geslacht != "Mixed", team.naam))
        gebruikt: set[Team] = set()
        for index, team in enumerate(pool):
            if team in gebruikt:
                continue
            kandidaten = [
                other
                for other in pool[index + 1 :]
                if other not in gebruikt
                and self.geslacht_compatibel(team, other)
                and frozenset((team.naam, other.naam)) not in al_gespeeld
            ]
            kandidaten.sort(
                key=lambda other: (
                    frozenset((team.naam, other.naam)) in al_gespeeld,
                    -self.compatibiliteit_score(team, other),
                    other.naam,
                )
            )
            if not kandidaten:
                continue
            opponent = kandidaten[0]
            paren.append((team, opponent))
            gebruikt.update({team, opponent})
        return paren

    def pareer_gretig_randomized(
        self,
        beschikbaar: list[Team],
        al_gespeeld: set[frozenset[str]],
        top_k: int = 3,
    ) -> list[tuple[Team, Team]]:
        paren: list[tuple[Team, Team]] = []
        pool = beschikbaar[:]
        self.random.shuffle(pool)
        gebruikt: set[Team] = set()
        for index, team in enumerate(pool):
            if team in gebruikt:
                continue
            kandidaten = [
                other
                for other in pool[index + 1 :]
                if other not in gebruikt
                and self.geslacht_compatibel(team, other)
                and frozenset((team.naam, other.naam)) not in al_gespeeld
            ]
            kandidaten.sort(
                key=lambda other: (
                    frozenset((team.naam, other.naam)) in al_gespeeld,
                    -self.compatibiliteit_score(team, other),
                    other.naam,
                )
            )
            if not kandidaten:
                continue
            pick_from = kandidaten[: min(top_k, len(kandidaten))]
            opponent = self.random.choice(pick_from)
            paren.append((team, opponent))
            gebruikt.update({team, opponent})
        return paren

    def available_rounds_for_team(
        self,
        team: Team,
        ronde_now: int,
        n_rondes: int,
        laatste_ronde: dict[Team, Optional[int]],
    ) -> int:
        previous = laatste_ronde.get(team)
        count = 0
        for ronde in range(ronde_now, n_rondes + 1):
            if self.consecutieve_rondes_toegestaan(previous, ronde):
                count += 1
        return count

    def feasible_lower_bound(
        self,
        teams: list[Team],
        ronde_now: int,
        n_rondes: int,
        resterend_verplicht: dict[Team, int],
        laatste_ronde: dict[Team, Optional[int]],
    ) -> bool:
        for team in teams:
            need = resterend_verplicht[team]
            if need <= 0:
                continue
            available = self.available_rounds_for_team(team, ronde_now, n_rondes, laatste_ronde)
            if need > available:
                return False
        return True

    def genereer_schema(
        self,
        teams: list[Team],
        voorkeuren: list[tuple[str, str]],
        n_rondes: int = 7,
        n_velden: int = 12,
    ) -> tuple[list[Match], dict[str, int], dict[str, int]]:
        naam2team = self.naam_index(teams)
        resterend_verplicht: dict[Team, int] = {
            team: VERPLICHTE_WEDSTRIJDEN.get(team.niveau, 0) for team in teams
        }
        resterend_opt: dict[Team, int] = {
            team: OPTIONELE_WEDSTRIJDEN.get(team.niveau, 0) for team in teams
        }
        laatste_ronde: dict[Team, Optional[int]] = {team: None for team in teams}

        voorkeur_set: set[frozenset[str]] = set()
        for team_a, team_b in voorkeuren:
            if team_a in naam2team and team_b in naam2team and team_a != team_b:
                voorkeur_set.add(frozenset((team_a, team_b)))

        ongeplande_voorkeuren = set(voorkeur_set)
        voorkeur_lijst = list(voorkeur_set)
        self.random.shuffle(voorkeur_lijst)
        voorkeur_doelronde: dict[frozenset[str], int] = {
            pair: (index % n_rondes) + 1 for index, pair in enumerate(voorkeur_lijst)
        }

        al_gespeeld: set[frozenset[str]] = set()
        wedstrijden: list[Match] = []

        def beschikbare_teams(ronde: int, alleen_verplicht: bool) -> list[Team]:
            result: list[Team] = []
            for team in teams:
                if not self.consecutieve_rondes_toegestaan(laatste_ronde[team], ronde):
                    continue
                if any(
                    match.ronde == ronde and (match.team_a == team or match.team_b == team)
                    for match in wedstrijden
                ):
                    continue
                if alleen_verplicht:
                    if resterend_verplicht[team] > 0:
                        result.append(team)
                elif resterend_verplicht[team] > 0 or resterend_opt[team] > 0:
                    result.append(team)
            return result

        for ronde in range(1, n_rondes + 1):
            veld_teller = 1
            geplande_deze_ronde: set[Team] = set()
            resterende_rondes = n_rondes - ronde + 1
            resterende_voorkeuren = len(ongeplande_voorkeuren)
            voorkeur_quota = min(
                n_velden,
                math.ceil(resterende_voorkeuren / resterende_rondes) if resterende_voorkeuren > 0 else 0,
            )
            geplande_voorkeuren_deze_ronde = 0

            def urgentie_key(pair: frozenset[str]) -> tuple[int, int, int, int, str]:
                team_a_name, team_b_name = sorted(pair)
                team_a = naam2team[team_a_name]
                team_b = naam2team[team_b_name]
                doelronde = voorkeur_doelronde.get(pair, ronde)
                overdue_flag = 0 if doelronde <= ronde else 1
                return (
                    overdue_flag,
                    abs(doelronde - ronde),
                    -(resterend_verplicht[team_a] + resterend_verplicht[team_b]),
                    -self.compatibiliteit_score(team_a, team_b),
                    f"{team_a_name}-{team_b_name}",
                )

            for pair in sorted(ongeplande_voorkeuren, key=urgentie_key):
                if veld_teller > n_velden or geplande_voorkeuren_deze_ronde >= voorkeur_quota:
                    break
                team_a_name, team_b_name = list(pair)
                team_a = naam2team[team_a_name]
                team_b = naam2team[team_b_name]
                if team_a in geplande_deze_ronde or team_b in geplande_deze_ronde:
                    continue
                if not self.consecutieve_rondes_toegestaan(laatste_ronde[team_a], ronde):
                    continue
                if not self.consecutieve_rondes_toegestaan(laatste_ronde[team_b], ronde):
                    continue
                if resterend_verplicht[team_a] == 0 and resterend_opt[team_a] == 0:
                    continue
                if resterend_verplicht[team_b] == 0 and resterend_opt[team_b] == 0:
                    continue
                if not self.geslacht_compatibel(team_a, team_b):
                    continue

                wedstrijden.append(Match(ronde, veld_teller, team_a, team_b))
                veld_teller += 1
                geplande_voorkeuren_deze_ronde += 1
                geplande_deze_ronde.update({team_a, team_b})
                laatste_ronde[team_a] = ronde
                laatste_ronde[team_b] = ronde
                al_gespeeld.add(frozenset((team_a.naam, team_b.naam)))
                for team in (team_a, team_b):
                    if resterend_verplicht[team] > 0:
                        resterend_verplicht[team] -= 1
                    elif resterend_opt[team] > 0:
                        resterend_opt[team] -= 1
                ongeplande_voorkeuren.discard(pair)

            for fase in ("verplicht", "opt"):
                if veld_teller > n_velden:
                    break
                alleen_verplicht = fase == "verplicht"
                beschikbaar = [
                    team
                    for team in beschikbare_teams(ronde, alleen_verplicht)
                    if team not in geplande_deze_ronde
                ]
                for team_a, team_b in self.pareer_gretig(beschikbaar, al_gespeeld):
                    if veld_teller > n_velden:
                        break
                    if alleen_verplicht and (
                        resterend_verplicht[team_a] == 0 or resterend_verplicht[team_b] == 0
                    ):
                        continue
                    if not alleen_verplicht and (
                        (resterend_verplicht[team_a] == 0 and resterend_opt[team_a] == 0)
                        or (resterend_verplicht[team_b] == 0 and resterend_opt[team_b] == 0)
                    ):
                        continue
                    wedstrijden.append(Match(ronde, veld_teller, team_a, team_b))
                    veld_teller += 1
                    geplande_deze_ronde.update({team_a, team_b})
                    laatste_ronde[team_a] = ronde
                    laatste_ronde[team_b] = ronde
                    al_gespeeld.add(frozenset((team_a.naam, team_b.naam)))
                    for team in (team_a, team_b):
                        if resterend_verplicht[team] > 0:
                            resterend_verplicht[team] -= 1
                        elif resterend_opt[team] > 0:
                            resterend_opt[team] -= 1

        rest_verplicht_by_name = {team.naam: resterend_verplicht[team] for team in teams}
        rest_opt_by_name = {team.naam: resterend_opt[team] for team in teams}
        return wedstrijden, rest_verplicht_by_name, rest_opt_by_name

    def genereer_schema_backtracking(
        self,
        teams: list[Team],
        voorkeuren: list[tuple[str, str]],
        n_rondes: int = 7,
        n_velden: int = 12,
        time_limit_nodes: int = 20_000,
        top_k_random: int = 3,
    ) -> tuple[list[Match], dict[str, int], dict[str, int]]:
        naam2team = self.naam_index(teams)
        resterend_verplicht: dict[Team, int] = {
            team: VERPLICHTE_WEDSTRIJDEN.get(team.niveau, 0) for team in teams
        }
        resterend_opt: dict[Team, int] = {
            team: OPTIONELE_WEDSTRIJDEN.get(team.niveau, 0) for team in teams
        }
        laatste_ronde: dict[Team, Optional[int]] = {team: None for team in teams}

        voorkeur_set: set[frozenset[str]] = set()
        for team_a, team_b in voorkeuren:
            if team_a in naam2team and team_b in naam2team and team_a != team_b:
                voorkeur_set.add(frozenset((team_a, team_b)))
        ongeplande_voorkeuren = set(voorkeur_set)
        al_gespeeld: set[frozenset[str]] = set()
        wedstrijden: list[Match] = []
        nodes = 0

        if not self.feasible_lower_bound(
            teams, 1, n_rondes, resterend_verplicht, laatste_ronde
        ):
            return [], {team.naam: resterend_verplicht[team] for team in teams}, {
                team.naam: resterend_opt[team] for team in teams
            }

        def candidates_for_round(
            ronde: int,
            geplande_deze_ronde: set[Team],
            geplande_pref_cnt: int,
            pref_quota: int,
        ) -> list[tuple[Team, Team, bool, int]]:
            beschikbaar = [
                team
                for team in teams
                if team not in geplande_deze_ronde
                and self.consecutieve_rondes_toegestaan(laatste_ronde[team], ronde)
                and (resterend_verplicht[team] > 0 or resterend_opt[team] > 0)
            ]
            base_pairs = self.pareer_gretig_randomized(
                beschikbaar, al_gespeeld, top_k=top_k_random
            )
            seen = {frozenset((a.naam, b.naam)) for a, b in base_pairs}
            for index, team_a in enumerate(beschikbaar):
                for team_b in beschikbaar[index + 1 :]:
                    pair = frozenset((team_a.naam, team_b.naam))
                    if pair in seen or pair in al_gespeeld:
                        continue
                    if not self.geslacht_compatibel(team_a, team_b):
                        continue
                    base_pairs.append((team_a, team_b))
                    seen.add(pair)

            candidates: list[tuple[Team, Team, bool, int]] = []
            for team_a, team_b in base_pairs:
                is_pref = frozenset((team_a.naam, team_b.naam)) in voorkeur_set
                if is_pref and geplande_pref_cnt >= pref_quota:
                    continue
                priority = (
                    (1 if is_pref else 0) * 1_000_000
                    + (resterend_verplicht[team_a] + resterend_verplicht[team_b]) * 10_000
                    + self.compatibiliteit_score(team_a, team_b)
                )
                candidates.append((team_a, team_b, is_pref, priority))
            candidates.sort(key=lambda item: (-item[3], item[0].naam, item[1].naam))
            return candidates

        def recurse(
            ronde: int,
            veld_idx: int,
            geplande_deze_ronde: set[Team],
            geplande_pref_cnt: int,
        ) -> bool:
            nonlocal nodes
            nodes += 1
            if nodes > time_limit_nodes:
                return False
            if all(resterend_verplicht[team] == 0 for team in teams):
                return True
            if ronde > n_rondes:
                return False

            resterende_rondes = n_rondes - ronde + 1
            resterende_voorkeuren = len(ongeplande_voorkeuren)
            pref_quota = min(
                n_velden,
                math.ceil(resterende_voorkeuren / resterende_rondes) if resterende_voorkeuren > 0 else 0,
            )

            if veld_idx <= n_velden:
                for team_a, team_b, is_pref, _priority in candidates_for_round(
                    ronde,
                    geplande_deze_ronde,
                    geplande_pref_cnt,
                    pref_quota,
                ):
                    wedstrijden.append(Match(ronde, veld_idx, team_a, team_b))
                    prev_a = laatste_ronde[team_a]
                    prev_b = laatste_ronde[team_b]
                    laatste_ronde[team_a] = ronde
                    laatste_ronde[team_b] = ronde
                    pair = frozenset((team_a.naam, team_b.naam))
                    was_pref_unplanned = pair in ongeplande_voorkeuren and is_pref
                    if was_pref_unplanned:
                        ongeplande_voorkeuren.remove(pair)

                    required_a = resterend_verplicht[team_a]
                    required_b = resterend_verplicht[team_b]
                    optional_a = resterend_opt[team_a]
                    optional_b = resterend_opt[team_b]
                    if resterend_verplicht[team_a] > 0:
                        resterend_verplicht[team_a] -= 1
                    elif resterend_opt[team_a] > 0:
                        resterend_opt[team_a] -= 1
                    if resterend_verplicht[team_b] > 0:
                        resterend_verplicht[team_b] -= 1
                    elif resterend_opt[team_b] > 0:
                        resterend_opt[team_b] -= 1
                    al_gespeeld.add(pair)
                    geplande_deze_ronde.update({team_a, team_b})

                    feasible = self.feasible_lower_bound(
                        teams,
                        ronde,
                        n_rondes,
                        resterend_verplicht,
                        laatste_ronde,
                    )
                    if feasible and recurse(
                        ronde,
                        veld_idx + 1,
                        geplande_deze_ronde,
                        geplande_pref_cnt + (1 if is_pref else 0),
                    ):
                        return True

                    if was_pref_unplanned:
                        ongeplande_voorkeuren.add(pair)
                    wedstrijden.pop()
                    laatste_ronde[team_a] = prev_a
                    laatste_ronde[team_b] = prev_b
                    resterend_verplicht[team_a] = required_a
                    resterend_verplicht[team_b] = required_b
                    resterend_opt[team_a] = optional_a
                    resterend_opt[team_b] = optional_b
                    al_gespeeld.discard(pair)
                    geplande_deze_ronde.discard(team_a)
                    geplande_deze_ronde.discard(team_b)

            if self.feasible_lower_bound(
                teams,
                ronde + 1,
                n_rondes,
                resterend_verplicht,
                laatste_ronde,
            ):
                if recurse(ronde + 1, 1, set(), 0):
                    return True
            return False

        recurse(1, 1, set(), 0)
        return wedstrijden, {
            team.naam: resterend_verplicht[team] for team in teams
        }, {team.naam: resterend_opt[team] for team in teams}

    def try_generate_with_retries(
        self,
        teams: list[Team],
        prefs: list[tuple[str, str]],
        n_rondes: int,
        n_velden: int,
        max_tries: int = 100,
        prefer_seed: Optional[int] = None,
    ) -> tuple[bool, list[Match], dict[str, int], dict[str, int], Optional[int]]:
        def single_try(attempt_seed: Optional[int]):
            scheduler = TournamentScheduler(seed=attempt_seed)
            wedstrijden, rest_verplicht, rest_opt = scheduler.genereer_schema(
                teams=teams,
                voorkeuren=prefs,
                n_rondes=n_rondes,
                n_velden=n_velden,
            )
            return not any(rest_verplicht.values()), wedstrijden, rest_verplicht, rest_opt

        if prefer_seed is not None:
            ok, wedstrijden, rest_verplicht, rest_opt = single_try(prefer_seed)
            if ok:
                return True, wedstrijden, rest_verplicht, rest_opt, prefer_seed
            tries_left = max(0, max_tries - 1)
        else:
            tries_left = max_tries

        current_seed = self.seed
        last_wedstrijden: list[Match] = []
        last_rest_verplicht: dict[str, int] = {}
        last_rest_opt: dict[str, int] = {}
        for _ in range(tries_left):
            ok, wedstrijden, rest_verplicht, rest_opt = single_try(current_seed)
            last_wedstrijden = wedstrijden
            last_rest_verplicht = rest_verplicht
            last_rest_opt = rest_opt
            if ok:
                return True, wedstrijden, rest_verplicht, rest_opt, current_seed
            current_seed = random.randint(1, 1000)
        return False, last_wedstrijden, last_rest_verplicht, last_rest_opt, current_seed


class CapacityAnalyzer:
    """Calculates remaining tournament capacity."""

    def __init__(self, scheduler: TournamentScheduler) -> None:
        self.scheduler = scheduler

    @staticmethod
    def clone_team_like(name_suffix: int, base_team: Team) -> Team:
        return Team(
            niveau=base_team.niveau,
            geslacht=base_team.geslacht,
            naam=f"{base_team.naam} (nieuw {name_suffix})",
            leeftijd=base_team.leeftijd,
        )

    @staticmethod
    def group_prototypes(teams: list[Team]) -> list[Team]:
        seen: dict[tuple[int, str, str], Team] = {}
        for team in teams:
            key = (team.niveau, team.geslacht, team.leeftijd)
            if key not in seen:
                seen[key] = team
        return list(seen.values())

    def max_extra_for_profile(
        self,
        base_teams: list[Team],
        prefs: list[tuple[str, str]],
        n_rondes: int,
        n_velden: int,
        seed: Optional[int],
        prototype_team: Team,
    ) -> int:
        def feasible(extra_count: int) -> bool:
            extra = [
                self.clone_team_like(index + 1, prototype_team)
                for index in range(extra_count)
            ]
            ok, *_ = TournamentScheduler(seed=seed).try_generate_with_retries(
                base_teams + extra,
                prefs,
                n_rondes,
                n_velden,
                max_tries=100,
            )
            return ok

        if not feasible(1):
            return 0
        low = high = 1
        while feasible(high):
            high *= 2
            if high > 256:
                break
        while low + 1 < high:
            middle = (low + high) // 2
            if feasible(middle):
                low = middle
            else:
                high = middle
        return low
