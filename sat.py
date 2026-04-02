from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import threading
from models import Match, Team


from pysat.card import CardEnc
from pysat.formula import CNF, IDPool
from pysat.solvers import Solver



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


# ------------------------------------------------------------
# SAT optimizer helper
# ------------------------------------------------------------
class _IncrementalCountOptimizer:
    """
    Small helper around a SAT solver that lets us test lower bounds of the form:
        sum(lits) >= k
    incrementally via activation literals.

    Each distinct bound is encoded once and can then be enabled via assumptions.
    """

    def __init__(self, solver: Solver, pool: IDPool) -> None:
        self.solver = solver
        self.pool = pool
        self._cache: Dict[Tuple[str, int], int] = {}

    def stop_solver_after(self, seconds):
        """Interrupt solver after given seconds."""
        timer = threading.Timer(seconds, self.solver.interrupt)
        timer.start()
        return timer

    def bound_selector(self, label: str, lits: List[int], k: int) -> Optional[int]:
        """
        Return an activation literal for constraint sum(lits) >= k.
        If k <= 0, no selector is needed.
        If k > len(lits), the bound is impossible; returns a selector that forces UNSAT when assumed.
        """
        if k <= 0:
            return None

        key = (label, k)
        if key in self._cache:
            return self._cache[key]

        act = self.pool.id(("activate-atleast", label, k))
        self._cache[key] = act

        if k > len(lits):
            # Assuming 'act' immediately makes the formula UNSAT.
            self.solver.add_clause([-act])
            return act

        enc = CardEnc.atleast(lits=lits, bound=k, vpool=self.pool)
        for clause in enc.clauses:
            # Activate the constraint only when act is assumed true.
            self.solver.add_clause([-act] + clause)

        return act

    def maximize(
        self,
        label: str,
        lits: List[int],
        upper_bound: int,
        fixed_assumptions: Optional[List[int]] = None,
    ) -> Tuple[int, Optional[List[int]]]:
        """
        Exact maximization of sum(lits), using binary search on k with SAT checks.
        Returns (best_value, best_model).
        """
        assumptions = list(fixed_assumptions or [])

        # First check that the base assumptions are feasible at all.
        if not self.solver.solve(assumptions=assumptions):
            return -1, None

        best_model = self.solver.get_model()
        low, high = 0, upper_bound

        while low < high:
            print(f'low: {low}')
            print(f'high: {high}')

            mid = (low + high + 1) // 2
            print(f'low: {low}')
            print(f'high: {high}')
            print(f'mid: {mid}')
            sel = self.bound_selector(label, lits, mid)
            trial = assumptions + ([] if sel is None else [sel])
            if self.solver.solve(assumptions=trial):
                print('solver said true!')
                low = mid
                best_model = self.solver.get_model()
                if mid == high:
                    return low, best_model
            else:
                print('its false, restarting')
                high = mid - 1

        return low, best_model


# ------------------------------------------------------------
# SAT-based scheduler with two-phase optimization
# ------------------------------------------------------------
class TournamentSchedulerSAT:
    """
    Exact two-phase SAT scheduler.

    Hard constraints:
    - a team plays at most once per round
    - a team may not play in consecutive rounds, except between rounds 5 and 6
    - the same pairing is used at most once overall
    - a team is scheduled for at most its requested number of matches
    - each round uses at most `num_fields` matches
    - regular matches require same gender and same level
    - preference pairs are allowed even when they cross groups

    Optimization:
    Phase 1: maximize number of unique preference pairs scheduled
    Phase 2: subject to phase 1 optimum, maximize total matches
    """

    def __init__(
        self,
        teams: List[Team],
        preferences: List[Tuple[str, str]]
    ) -> None:

        self.teams: Dict[str, InternalTeam] = {
            self._team_name(t): InternalTeam(
                name=self._team_name(t),
                gender=self._team_gender(t),
                level=self._team_level(t),
                age=self._team_age_group(t),
                matches_needed=self._team_match_target(t),
            )
            for t in teams
        }

        self.preferences = {
            frozenset((a, b))
            for a, b in preferences
            if a in self.teams and b in self.teams and a != b
        }

        # Output metrics mirroring the previous scheduler as closely as possible.
        self.last_node_visits = 0
        self.node_cap_reached = False
        self.soft_constraint_used = bool(self.preferences)

    # ------------------------------------------------------------
    # Attribute helpers (compatible with mixed Team definitions)
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
    def _team_age_group(cls, team: Team):
        return getattr(team, "age_group", getattr(team, "age", None))

    @classmethod
    def _team_match_target(cls, team: Team) -> int:
        if hasattr(team, "matches"):
            return int(team.matches)
        if hasattr(team, "wedstrijden"):
            return int(team.wedstrijden)
        raise AttributeError("Team must have either `matches` or `wedstrijden`.")

    # ------------------------------------------------------------
    # Pair feasibility helpers
    # ------------------------------------------------------------
    @staticmethod
    def _can_pair_same_group(a: InternalTeam, b: InternalTeam) -> bool:
        return a.gender == b.gender and a.level == b.level

    def _is_preference(self, a: str, b: str) -> bool:
        return frozenset((a, b)) in self.preferences

    def _allowed_pairs(self) -> List[Tuple[str, str]]:
        names = sorted(self.teams)
        pairs: List[Tuple[str, str]] = []

        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                ta = self.teams[a]
                tb = self.teams[b]
                if self._can_pair_same_group(ta, tb) or self._is_preference(a, b):
                    pairs.append((a, b))

        return pairs

    @staticmethod
    def _allows_consecutive_between(round_a: int, round_b: int) -> bool:
        """Return True when a team may play in both consecutive rounds."""
        lo, hi = sorted((round_a, round_b))
        return lo == 5 and hi == 6

    @classmethod
    def _max_matches_with_consecutive_exceptions(cls, num_rounds: int) -> int:
        """
        Maximum number of rounds a single team can play under the no-consecutive
        rule, with the explicit exception that rounds 5 and 6 may both be used.
        """
        if num_rounds <= 0:
            return 0

        base = (num_rounds + 1) // 2
        return base + (1 if num_rounds >= 6 else 0)

    # ------------------------------------------------------------
    # Build hard CNF only
    # ------------------------------------------------------------
    def _build_cnf(self, num_rounds: int, num_fields: int):
        pool = IDPool()
        cnf = CNF()

        allowed_pairs = self._allowed_pairs()
        team_names = sorted(self.teams)

        def match_var(round_number: int, a: str, b: str) -> int:
            x, y = sorted((a, b))
            return pool.id(("match", round_number, x, y))

        def play_var(round_number: int, team_name: str) -> int:
            return pool.id(("plays", round_number, team_name))

        def pref_used_var(a: str, b: str) -> int:
            x, y = sorted((a, b))
            return pool.id(("pref-used", x, y))

        by_round_team_matches: Dict[Tuple[int, str], List[int]] = {
            (r, name): []
            for r in range(1, num_rounds + 1)
            for name in team_names
        }
        by_pair: Dict[frozenset[str], List[int]] = {
            frozenset((a, b)): [] for a, b in allowed_pairs
        }
        by_round_matches: Dict[int, List[int]] = {
            r: [] for r in range(1, num_rounds + 1)
        }

        team_degrees: Dict[str, int] = {name: 0 for name in team_names}
        non_pref_team_degrees: Dict[str, int] = {name: 0 for name in team_names}

        preference_pair_vars: List[int] = []
        regular_match_vars: List[int] = []
        all_match_vars: List[int] = []

        all_play_vars: Dict[Tuple[int, str], int] = {
            (r, name): play_var(r, name)
            for r in range(1, num_rounds + 1)
            for name in team_names
        }

        for a, b in allowed_pairs:
            team_degrees[a] += 1
            team_degrees[b] += 1
            if not self._is_preference(a,b):
                non_pref_team_degrees[a] += 1
                non_pref_team_degrees[b] += 1
             

        for r in range(1, num_rounds + 1):
            for a, b in allowed_pairs:
                mv = match_var(r, a, b)
                all_match_vars.append(mv)

                by_round_team_matches[(r, a)].append(mv)
                by_round_team_matches[(r, b)].append(mv)
                by_pair[frozenset((a, b))].append(mv)
                by_round_matches[r].append(mv)

                if self._is_preference(a, b):
                    pass
                else:
                    regular_match_vars.append(mv)

        # Preference objective vars: one literal per preference pair, regardless of round.
        for a, b in allowed_pairs:
            if not self._is_preference(a, b):
                continue

            pu = pref_used_var(a, b)
            preference_pair_vars.append(pu)
            pair_lits = by_pair[frozenset((a, b))]

            # Any round-level match implies the preference pair is used.
            for mv in pair_lits:
                cnf.append([-mv, pu])

            # If the pair is marked used, it must occur in some round.
            cnf.append([-pu] + pair_lits)

        # (1) Team-round linking: p[r,t] <-> exactly one incident match in round r
        for (r, team_name), match_lits in by_round_team_matches.items():
            pv = all_play_vars[(r, team_name)]

            if not match_lits:
                cnf.append([-pv])
                continue

            # x -> p
            for mv in match_lits:
                cnf.append([-mv, pv])

            # p -> OR(incident matches)
            cnf.append([-pv] + match_lits)

            # at most one incident match for a team in a round
            if len(match_lits) > 1:
                enc = CardEnc.atmost(lits=match_lits, bound=1, vpool=pool)
                cnf.extend(enc.clauses)

        # (2) No consecutive rounds for any team, except rounds 5 and 6 may both be used.
        for team_name in team_names:
            for r in range(1, num_rounds):
                if self._allows_consecutive_between(r, r + 1):
                    continue
                cnf.append([-all_play_vars[(r, team_name)], -all_play_vars[(r + 1, team_name)]])

        # (3) Same pairing used at most once overall
        for lits in by_pair.values():
            if len(lits) > 1:
                enc = CardEnc.atmost(lits=lits, bound=1, vpool=pool)
                cnf.extend(enc.clauses)

        # (4) Round capacity
        for r, lits in by_round_matches.items():
            if num_fields <= 0:
                for lit in lits:
                    cnf.append([-lit])
            elif len(lits) > num_fields:
                enc = CardEnc.atmost(lits=lits, bound=num_fields, vpool=pool)
                cnf.extend(enc.clauses)

        # (5) Team total match limits, using play vars and accounting for the 5-6 exception
        max_nonconsecutive_slots = self._max_matches_with_consecutive_exceptions(num_rounds)
        effective_caps: Dict[str, int] = {}
        non_pref_caps: Dict[str, int] = {}

        for team_name in team_names:
            requested = max(0, self.teams[team_name].matches_needed)
            cap = min(requested, max_nonconsecutive_slots, team_degrees[team_name])
            effective_caps[team_name] = cap
            non_pref_caps[team_name] = min(requested, max_nonconsecutive_slots, non_pref_team_degrees[team_name])

            play_lits = [all_play_vars[(r, team_name)] for r in range(1, num_rounds + 1)]

            if cap == 0:
                for lit in play_lits:
                    cnf.append([-lit])
            elif len(play_lits) > cap:
                enc = CardEnc.atmost(lits=play_lits, bound=cap, vpool=pool)
                cnf.extend(enc.clauses)

        metadata = {
            "allowed_pairs": allowed_pairs,
            "match_var": match_var,
            "play_var": play_var,
            "effective_caps": effective_caps,
            "non_pref_caps": non_pref_caps,
            "all_play_vars": all_play_vars,
            "all_match_vars": all_match_vars,
            "preference_pair_vars": preference_pair_vars,
            "regular_match_vars": regular_match_vars,
        }

        return cnf, pool, metadata

    # ------------------------------------------------------------
    # Solve with 2-phase exact SAT optimization
    # ------------------------------------------------------------
    def _solve(self, num_rounds: int, num_fields: int):
        print("building hard cnf")
        cnf, pool, metadata = self._build_cnf(num_rounds, num_fields)

        print("running two-phase SAT optimization")
        with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
            opt = _IncrementalCountOptimizer(solver=solver, pool=pool)

            pref_lits: List[int] = metadata["preference_pair_vars"]
            all_match_lits: List[int] = metadata["all_match_vars"]

            # Tight upper bounds help the binary search a lot.
            
            max_possible_matches = min(
                num_rounds * num_fields,
                sum(metadata["non_pref_caps"].values()) // 2,
                len(metadata["allowed_pairs"]),
            )

            print(f'max possible matches: {max_possible_matches}')
            max_possible_pref = min(len(pref_lits), max_possible_matches)
            
            print('starting to maximize prefs')
            # Phase 1: maximize number of preference matches.
            best_pref, pref_model = opt.maximize(
                label="pref-count",
                lits=pref_lits,
                upper_bound=max_possible_pref,
                fixed_assumptions=[],
            )
            print('done!')
            print(f'best_pref: {best_pref}')
            if pref_model is None:
                return [], {name: t.matches_needed for name, t in self.teams.items()}

            pref_fix_sel = opt.bound_selector("pref-count", pref_lits, best_pref)
            phase2_assumptions = [] if pref_fix_sel is None else [pref_fix_sel]
            print('starting to maximize matches')
            # Phase 2: subject to best preference count, maximize total matches.
            best_total, final_model = opt.maximize(
                label="total-count",
                lits=all_match_lits,
                upper_bound=max_possible_matches,
                fixed_assumptions=phase2_assumptions,
            )

            print('done!')
            self.last_node_visits = 0  # SAT solve count could be tracked separately if wanted.

            if final_model is None:
                final_model = pref_model

        print(f"done! best_pref={best_pref}, best_total={best_total}")

        model_set = {lit for lit in final_model if lit > 0}

        matches: List[Match] = []
        scheduled_by_team = {name: 0 for name in self.teams}
        by_round_pairs: Dict[int, List[Tuple[str, str]]] = {
            r: [] for r in range(1, num_rounds + 1)
        }

        for r in range(1, num_rounds + 1):
            for a, b in metadata["allowed_pairs"]:
                mv = metadata["match_var"](r, a, b)
                if mv in model_set:
                    by_round_pairs[r].append((a, b))
                    scheduled_by_team[a] += 1
                    scheduled_by_team[b] += 1

        # Stable ordering inside each round: preference pairs first, then alphabetical.
        for r in range(1, num_rounds + 1):
            ordered_pairs = sorted(
                by_round_pairs[r],
                key=lambda p: (0 if self._is_preference(*p) else 1, p[0], p[1]),
            )

            for field, (a, b) in enumerate(ordered_pairs, start=1):
                ta = self.teams[a]
                tb = self.teams[b]
                matches.append(Match(r, field, ta, tb))

        remaining = {
            name: max(0, self.teams[name].matches_needed - scheduled_by_team[name])
            for name in self.teams
        }

        return matches, remaining

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------
    def _generate(
        self,
        num_rounds: int = 7,
        num_fields: int = 12,
    ) -> Tuple[List[Match], Dict[str, int]]:
        return self._solve(num_rounds=num_rounds, num_fields=num_fields)

    def generate_schedule(
        self,
        num_rounds: int = 7,
        num_fields: int = 12,
    ) -> Tuple[List[Match], Dict[str, int]]:
        return self._generate(num_rounds=num_rounds, num_fields=num_fields)

    def try_generate_with_retries(
        self,
        num_rounds: int = 7,
        num_fields: int = 12,
        max_tries: int = 1,
    ) -> Tuple[bool, List[Match], Dict[str, int]]:
        del max_tries  # deterministic SAT solve; no randomized retries needed
        matches, remaining = self.generate_schedule(
            num_rounds=num_rounds,
            num_fields=num_fields,
        )
        ok = all(value <= 0 for value in remaining.values())
        return ok, matches, remaining


class CapacityAnalyzerSAT:
    """Estimate how many additional teams of a profile still fit in the SAT schedule."""

    def __init__(self, scheduler_cls=TournamentSchedulerSAT) -> None:
        self.scheduler_cls = scheduler_cls

    @staticmethod
    def clone_team_like(name_suffix: int, base_team: Team) -> Team:
        team_name = TournamentSchedulerSAT._team_name(base_team)
        team_level = TournamentSchedulerSAT._team_level(base_team)
        team_gender = TournamentSchedulerSAT._team_gender(base_team)
        team_age_group = TournamentSchedulerSAT._team_age_group(base_team)
        team_match_target = TournamentSchedulerSAT._team_match_target(base_team)

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
    def group_prototypes(teams: List[Team]) -> List[Team]:
        seen: Dict[Tuple[object, str, object], Team] = {}
        for team in teams:
            key = (
                TournamentSchedulerSAT._team_level(team),
                TournamentSchedulerSAT._team_gender(team),
                TournamentSchedulerSAT._team_age_group(team),
            )
            if key not in seen:
                seen[key] = team
        return list(seen.values())

    def max_extra_for_profile(
        self,
        base_teams: List[Team],
        prefs: List[Tuple[str, str]],
        num_rounds: int,
        num_fields: int,
        seed: Optional[int],
        prototype_team: Team,
    ) -> int:
        del seed  # deterministic for SAT solver

        def feasible(extra_count: int) -> bool:
            extra_teams = [
                self.clone_team_like(index + 1, prototype_team)
                for index in range(extra_count)
            ]
            scheduler = self.scheduler_cls(base_teams + extra_teams, prefs)
            ok, _, _ = scheduler.try_generate_with_retries(
                num_rounds=num_rounds,
                num_fields=num_fields,
                max_tries=1,
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

