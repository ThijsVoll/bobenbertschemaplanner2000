from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from models import Match, Team

import random


# ------------------------------------------------------------
# Internal team wrapper
# ------------------------------------------------------------

@dataclass
class InternalTeam:
    name: str
    gender: str
    level: str
    age: str
    matches_needed: int
    last_round: Optional[int] = None


# ------------------------------------------------------------
# Simplified Scheduler
# ------------------------------------------------------------

class TournamentScheduler:
    """
    Simplified, readable tournament scheduler.
    - Respects: same gender, same level, no consecutive matches
    - Supports preference matches
    - Returns the *same types* as the original version
    - No nested functions
    """

    def __init__(self, teams: List[Team], preferences: List[Tuple[str, str]], seed: Optional[int] = 42):
        self.teams: Dict[str, InternalTeam] = {
            self._team_name(t): InternalTeam(
                name=self._team_name(t),
                gender=self._team_gender(t),
                level=self._team_level(t),
                age=t.age,
                matches_needed=self._team_match_target(t),
            )
            for t in teams
        }

        preferences = [frozenset((a, b)) for a, b in preferences if a in self.teams and b in self.teams]
        if preferences:
            self.preferences = preferences

        else:
            self.preferences = set()

        # Output metrics mimicking original class
        self.last_node_visits = 0
        self.node_cap_reached = False
        self.soft_constraint_used = False

    # ------------------------------------------------------------
    # Attribute helpers (same as original)
    # ------------------------------------------------------------

    @classmethod
    def _team_name(cls, team: Team) -> str:
        return team.name

    @classmethod
    def _team_gender(cls, team: Team) -> str:
        return team.gender

    @classmethod
    def _team_level(cls, team: Team):
        return team.level

    @classmethod
    def _team_match_target(cls, team: Team) -> int:
        return team.matches

    # ------------------------------------------------------------
    # Constraint checks
    # ------------------------------------------------------------

    @staticmethod
    def consecutive_rounds_allowed(last_round: Optional[int], current_round: int) -> bool:
        if last_round is None:
            return True
        return last_round + 1 != current_round

    @staticmethod
    def _can_pair_same_group(a: InternalTeam, b: InternalTeam) -> bool:
        """Same gender + same level."""
        return a.gender == b.gender and a.level == b.level

    def _eligible(self) -> List[InternalTeam]:
        return [t for t in self.teams.values() if t.matches_needed > 0]


    # ------------------------------------------------------------
    # Preference scheduling
    # ------------------------------------------------------------

    def _find_preference_pairings(
        self,
        round_number: int,
        used: set,
    ) -> List[Tuple[str, str]]:
        result = []

        # Order preference pairs alphabetically for determinism
        for pair in self.preferences:
            a, b = tuple(sorted(pair))
            if a in used or b in used:
                continue

            if self.teams[a].matches_needed <= 0 or self.teams[b].matches_needed <= 0:
                continue
            if not self.consecutive_rounds_allowed(self.teams[a].last_round, round_number):
                continue
            if not self.consecutive_rounds_allowed(self.teams[b].last_round, round_number):
                continue

            used.add(a)
            used.add(b)
            result.append((a, b))
        return result

    # ------------------------------------------------------------
    # Regular match scheduling
    # ------------------------------------------------------------

    def _find_regular_pairings(
        self,
        round_number: int,
        used: set,
        max_pairs: int,
        used_pairs: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        result = []
        teams = self._eligible()

        for i, ta in enumerate(teams):
            if ta.name in used or ta.matches_needed <= 0:
                continue

            for tb in teams[i + 1:]:
                if tb.name in used or tb.matches_needed <= 0:
                    continue

                if not self._can_pair_same_group(ta, tb):
                    continue
                if not self.consecutive_rounds_allowed(ta.last_round, round_number):
                    continue
                if not self.consecutive_rounds_allowed(tb.last_round, round_number):
                    continue
                if (ta.name, tb.name) in used_pairs:
                    continue

                used.add(ta.name)
                used.add(tb.name)
                result.append((ta.name, tb.name))
                break

            if len(result) >= max_pairs:
                break

        return result

    # ------------------------------------------------------------
    # Apply a round to internal state
    # ------------------------------------------------------------

    def _apply_round(
        self,
        round_number: int,
        pairs: List[Tuple[str, str]]
    ) -> List[Match]:
        matches = []
        for field, (a, b) in enumerate(pairs, start=1):
            ta = self.teams[a]
            tb = self.teams[b]

            ta.matches_needed -= 1
            tb.matches_needed -= 1

            ta.last_round = round_number
            tb.last_round = round_number

            matches.append(Match(round_number, field, ta, tb))
        return matches

    # ------------------------------------------------------------
    # MAIN ENTRY: required API
    # ------------------------------------------------------------

    def generate_schedule(
        self,
        num_rounds: int = 7,
        num_fields: int = 12
    ) -> Tuple[List[Match], Dict[str, int]]:
        """
        Returns:
        - list[Match]
        - remaining_matches_by_team: dict[str, int]
        """
        all_matches: List[Match] = []
        used_pairings: List[Tuple] = []

        for round_number in range(1, num_rounds + 1):
            print(used_pairings)
            used = set()

            # (1) Preference matches first
            pref_pairs = self._find_preference_pairings(round_number, used)

            # (2) Fill remaining fields with regular matches
            remaining_slots = num_fields - len(pref_pairs)
            reg_pairs = self._find_regular_pairings(round_number, used, remaining_slots, used_pairings)

            # Final pair list for this round
            round_pairs = pref_pairs + reg_pairs

            # Apply matches
            matches = self._apply_round(round_number, round_pairs)
            all_matches.extend(matches)

            for match in matches:
                used_pairings.append((match.team_a.name, match.team_b.name))

            # Stop early if everything satisfied
            if all(t.matches_needed <= 0 for t in self.teams.values()):
                break

        remaining = {name: t.matches_needed for name, t in self.teams.items()}
        return all_matches, remaining
    
class CapacityAnalyzer:
    """Estimate how many additional teams of a profile still fit in the schedule."""

    def __init__(self, scheduler: TournamentScheduler) -> None:
        self.scheduler = scheduler

    @staticmethod
    def clone_team_like(name_suffix: int, base_team: Team) -> Team:
        team_name = TournamentScheduler._team_name(base_team)
        team_level = TournamentScheduler._team_level(base_team)
        team_gender = TournamentScheduler._team_gender(base_team)
        team_age_group = TournamentScheduler._team_age_group(base_team)
        team_match_target = TournamentScheduler._team_match_target(base_team)

        try:
            return Team(
                level=team_level,
                gender=team_gender,
                name=f"{team_name} (new {name_suffix})",
                age_group=team_age_group,
                matches=team_match_target,
            )
        except TypeError:
            return Team(
                level=team_level,
                gender=team_gender,
                name=f"{team_name} (new {name_suffix})",
                age=team_age_group,
                wedstrijden=team_match_target,
            )

    @staticmethod
    def group_prototypes(teams: list[Team]) -> list[Team]:
        seen: dict[tuple[object, str, object], Team] = {}
        for team in teams:
            key = (
                TournamentScheduler._team_level(team),
                TournamentScheduler._team_gender(team),
                TournamentScheduler._team_age_group(team),
            )
            if key not in seen:
                seen[key] = team
        return list(seen.values())

    def max_extra_for_profile(
        self,
        base_teams: list[Team],
        prefs: list[tuple[str, str]],
        num_rounds: int,
        num_fields: int,
        seed: Optional[int],
        prototype_team: Team,
    ) -> int:
        def feasible(extra_count: int) -> bool:
            extra_teams = [
                self.clone_team_like(index + 1, prototype_team)
                for index in range(extra_count)
            ]
            scheduler = TournamentScheduler(
                base_teams + extra_teams,
                prefs,
                seed=seed,
            )
            ok, _, _ = scheduler.try_generate_with_retries(
                num_rounds=num_rounds,
                num_fields=num_fields,
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
