from __future__ import annotations

import math
import random
from typing import Optional

from models import Match, Team


class TournamentScheduler:
    """Balanced backtracking tournament scheduler.

    Design goals:
    - Same-gender only.
    - Same-level only.
    - Keep the existing preference target-round + quota logic intact.
    - Search with backtracking, optionally bounded by depth / node limits.
    - Prefer schedules that distribute matches evenly across rounds.
    - Prefer schedules that minimise the peak number of simultaneously used fields.
    - Optionally relax the consecutive-round rule with a bounded soft budget.
    """

    def __init__(
        self,
        teams: list[Team],
        preferences: list[tuple[str, str]],
        seed: Optional[int] = 42,
    ) -> None:
        self.seed = seed
        self.random = random.Random(seed)
        self.teams = teams
        self.preferences = preferences
        self.team_by_name = self._build_team_index(teams)

        # Diagnostics after a run.
        self.last_node_visits = 0
        self.node_cap_reached = False
        self.soft_constraint_used = False

    # ------------------------------------------------------------------
    # Team attribute compatibility helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _get_attr(obj: object, *names: str):
        for name in names:
            if hasattr(obj, name):
                return getattr(obj, name)
        joined = ", ".join(names)
        raise AttributeError(f"Expected one of these attributes to exist: {joined}")

    @classmethod
    def _team_name(cls, team: Team) -> str:
        return str(cls._get_attr(team, "name", "name"))

    @classmethod
    def _team_gender(cls, team: Team) -> str:
        return str(cls._get_attr(team, "gender", "gender"))

    @classmethod
    def _team_level(cls, team: Team):
        return cls._get_attr(team, "level", "level")

    @classmethod
    def _team_match_target(cls, team: Team) -> int:
        value = cls._get_attr(team, "matches", "wedstrijden", "matches")
        return int(value)

    @classmethod
    def _build_team_index(cls, teams: list[Team]) -> dict[str, Team]:
        index: dict[str, Team] = {}
        for team in teams:
            team_name = cls._team_name(team)
            if team_name in index:
                raise ValueError(
                    f"Duplicate team name '{team_name}'; team names must be unique."
                )
            index[team_name] = team
        return index

    # ------------------------------------------------------------------
    # Core constraints and priorities
    # ------------------------------------------------------------------
    @staticmethod
    def consecutive_rounds_allowed(previous_round: Optional[int], current_round: int) -> bool:
        if previous_round is None:
            return True
        return not (
            current_round == previous_round + 1
            and not (previous_round == 5 and current_round == 6)
        )

    def _can_pair(self, team_a_name: str, team_b_name: str) -> bool:
        team_a = self.team_by_name[team_a_name]
        team_b = self.team_by_name[team_b_name]
        return (
            self._team_gender(team_a) == self._team_gender(team_b)
            and self._team_level(team_a) == self._team_level(team_b)
        )

    def _team_sort_key(self, team_name: str) -> tuple[object, str, str]:
        team = self.team_by_name[team_name]
        return (
            self._team_level(team),
            self._team_gender(team),
            team_name,
        )

    def _preference_priority(
        self,
        pair: frozenset[str],
        round_number: int,
        preference_target_round: dict[frozenset[str], int],
        remaining_matches_by_team: dict[str, int],
    ) -> tuple[int, int, int, str]:
        team_a_name, team_b_name = sorted(pair)
        target_round = preference_target_round.get(pair, round_number)
        overdue_flag = 0 if target_round <= round_number else 1
        return (
            overdue_flag,
            abs(target_round - round_number),
            -(
                remaining_matches_by_team[team_a_name]
                + remaining_matches_by_team[team_b_name]
            ),
            f"{team_a_name}-{team_b_name}",
        )

    def _eligible_teams(
        self,
        remaining_matches_by_team: dict[str, int],
    ) -> list[str]:
        eligible: list[str] = []
        for team in self.teams:
            team_name = self._team_name(team)
            if remaining_matches_by_team[team_name] > 0:
                eligible.append(team_name)
        eligible.sort(key=self._team_sort_key)
        return eligible

    @staticmethod
    def _normalise_ratio(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))

    def _soft_mode_active(
        self,
        node_visit_count: int,
        max_node_visits: Optional[int],
        relax_on_node_ratio: Optional[float],
    ) -> bool:
        ratio = self._normalise_ratio(relax_on_node_ratio)
        if max_node_visits is None or ratio is None:
            return False
        return node_visit_count >= math.ceil(max_node_visits * ratio)

    def _pair_exception_info(
        self,
        team_a_name: str,
        team_b_name: str,
        round_number: int,
        last_round_by_team: dict[str, Optional[int]],
    ) -> tuple[bool, tuple[str, ...]]:
        exception_teams: list[str] = []
        for team_name in (team_a_name, team_b_name):
            if not self.consecutive_rounds_allowed(last_round_by_team[team_name], round_number):
                exception_teams.append(team_name)
        return (len(exception_teams) > 0, tuple(sorted(exception_teams)))

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def generate_schedule(
        self,
        num_rounds: int = 7,
        num_fields: int = 12,
        max_search_depth: Optional[int] = 10,
        max_node_visits: Optional[int] = 2000,
        max_consecutive_exception_matches_total: int = 0,
        max_consecutive_exceptions_per_team: int = 0,
        relax_on_node_ratio: Optional[float] = 0.75,
        allow_relaxed_greedy_completion: bool = True,
    ) -> tuple[list[Match], dict[str, int]]:
        remaining_matches_by_team: dict[str, int] = {
            self._team_name(team): self._team_match_target(team)
            for team in self.teams
        }
        last_round_by_team: dict[str, Optional[int]] = {
            self._team_name(team): None for team in self.teams
        }

        preference_pairs: set[frozenset[str]] = set()
        for team_a_name, team_b_name in self.preferences:
            if (
                team_a_name in self.team_by_name
                and team_b_name in self.team_by_name
                and team_a_name != team_b_name
            ):
                preference_pairs.add(frozenset((team_a_name, team_b_name)))

        unscheduled_preferences = set(preference_pairs)
        shuffled_preferences = list(preference_pairs)
        self.random.shuffle(shuffled_preferences)
        preference_target_round: dict[frozenset[str], int] = {
            pair: (index % num_rounds) + 1
            for index, pair in enumerate(shuffled_preferences)
        }

        effective_max_depth = num_rounds if max_search_depth is None else max(0, min(max_search_depth, num_rounds))
        effective_max_node_visits = None if max_node_visits is None else max(0, int(max_node_visits))
        effective_max_consecutive_exception_matches_total = max(0, int(max_consecutive_exception_matches_total))
        effective_max_consecutive_exceptions_per_team = max(0, int(max_consecutive_exceptions_per_team))

        played_pairs: set[frozenset[str]] = set()
        current_matches: list[Match] = []
        current_preference_count = 0
        current_exception_match_count = 0
        current_exception_team_use_count = 0
        round_match_counts = [0 for _ in range(num_rounds)]
        exception_match_count_by_team: dict[str, int] = {
            self._team_name(team): 0 for team in self.teams
        }

        node_visit_count = 0
        search_stopped = False

        self.last_node_visits = 0
        self.node_cap_reached = False
        self.soft_constraint_used = False

        best_matches: list[Match] = []
        best_remaining: dict[str, int] = dict(remaining_matches_by_team)
        best_score: tuple[int, int, int, int, int, int] | None = None
        best_signature: tuple[tuple[int, int, str, str], ...] | None = None

        # --------------------------------------------------------------
        # Scoring and round targets
        # --------------------------------------------------------------
        def schedule_signature(matches: list[Match]) -> tuple[tuple[int, int, str, str], ...]:
            sig: list[tuple[int, int, str, str]] = []
            for match in matches:
                team_a_name = self._team_name(match.team_a)
                team_b_name = self._team_name(match.team_b)
                a, b = sorted((team_a_name, team_b_name))
                sig.append((match.ronde, match.veld, a, b))
            return tuple(sig)

        def balance_penalty() -> tuple[int, int]:
            peak_fields_used = max(round_match_counts) if round_match_counts else 0
            sum_of_squares = sum(count * count for count in round_match_counts)
            return peak_fields_used, sum_of_squares

        def candidate_score() -> tuple[int, int, int, int, int, int]:
            peak_fields_used, sum_of_squares = balance_penalty()
            return (
                len(current_matches),
                current_preference_count,
                -peak_fields_used,
                -sum_of_squares,
                -current_exception_match_count,
                -current_exception_team_use_count,
            )

        def is_better_solution(signature: tuple[tuple[int, int, str, str], ...]) -> bool:
            nonlocal best_score, best_signature
            score = candidate_score()
            if best_score is None:
                return True
            if score > best_score:
                return True
            if score < best_score:
                return False
            if best_signature is None:
                return True
            return signature < best_signature

        def evaluate_current_solution() -> None:
            nonlocal best_matches, best_remaining, best_score, best_signature
            signature = schedule_signature(current_matches)
            if is_better_solution(signature):
                best_matches = list(current_matches)
                best_remaining = dict(remaining_matches_by_team)
                best_score = candidate_score()
                best_signature = signature
                if current_exception_match_count > 0:
                    self.soft_constraint_used = True

        def max_possible_additional_matches(from_round: int) -> int:
            remaining_rounds = num_rounds - from_round + 1
            remaining_field_capacity = remaining_rounds * num_fields
            remaining_demand_capacity = sum(remaining_matches_by_team.values()) // 2
            return min(remaining_field_capacity, remaining_demand_capacity)

        def max_possible_additional_preferences(from_round: int) -> int:
            remaining_rounds = num_rounds - from_round + 1
            return min(len(unscheduled_preferences), remaining_rounds * num_fields)

        def target_pairs_for_round(round_number: int) -> int:
            remaining_rounds = num_rounds - round_number + 1
            remaining_possible_matches = max_possible_additional_matches(round_number)
            if remaining_rounds <= 0:
                return 0
            target = math.ceil(remaining_possible_matches / remaining_rounds)
            return max(0, min(target, num_fields))

        def goal_order_for_round(round_number: int) -> list[int]:
            target = target_pairs_for_round(round_number)
            max_pairs_this_round = min(
                num_fields,
                len(self._eligible_teams(remaining_matches_by_team)) // 2,
            )
            goals: list[int] = []
            for offset in range(0, max_pairs_this_round + 1):
                for value in ({target - offset, target + offset} if offset else {target}):
                    if 0 <= value <= max_pairs_this_round and value not in goals:
                        goals.append(value)
            return goals

        # --------------------------------------------------------------
        # Pair metadata and state mutation
        # --------------------------------------------------------------
        def build_pair_metadata(
            team_a_name: str,
            team_b_name: str,
            round_number: int,
            soft_mode_active: bool,
        ) -> Optional[dict[str, object]]:
            if not self._can_pair(team_a_name, team_b_name):
                return None
            pair_fs = frozenset((team_a_name, team_b_name))
            if pair_fs in played_pairs:
                return None
            uses_exception_match, exception_teams = self._pair_exception_info(
                team_a_name,
                team_b_name,
                round_number,
                last_round_by_team,
            )
            if uses_exception_match:
                if not soft_mode_active:
                    return None
                if current_exception_match_count >= effective_max_consecutive_exception_matches_total:
                    return None
                for team_name in exception_teams:
                    if exception_match_count_by_team[team_name] >= effective_max_consecutive_exceptions_per_team:
                        return None
            return {
                "pair": (team_a_name, team_b_name),
                "pair_fs": pair_fs,
                "uses_exception_match": uses_exception_match,
                "exception_teams": exception_teams,
                "is_preference": pair_fs in unscheduled_preferences,
            }

        def apply_round_matches(
            round_number: int,
            pair_entries: list[dict[str, object]],
        ) -> tuple[
            list[tuple[str, Optional[int]]],
            list[frozenset[str]],
            int,
            int,
            list[str],
        ]:
            nonlocal current_exception_match_count, current_exception_team_use_count
            previous_round_entries: list[tuple[str, Optional[int]]] = []
            removed_preferences: list[frozenset[str]] = []
            preference_delta = 0
            exception_match_delta = 0
            exception_team_delta_names: list[str] = []
            seen_teams: set[str] = set()

            for field_number, entry in enumerate(pair_entries, start=1):
                team_a_name, team_b_name = entry["pair"]
                if team_a_name in seen_teams or team_b_name in seen_teams:
                    raise ValueError("Internal scheduler error: team scheduled twice in the same round.")
                seen_teams.update({team_a_name, team_b_name})

                pair_fs = entry["pair_fs"]
                current_matches.append(
                    Match(
                        round_number,
                        field_number,
                        self.team_by_name[team_a_name],
                        self.team_by_name[team_b_name],
                    )
                )
                round_match_counts[round_number - 1] += 1
                played_pairs.add(pair_fs)

                if entry["is_preference"]:
                    unscheduled_preferences.remove(pair_fs)
                    removed_preferences.append(pair_fs)
                    preference_delta += 1

                previous_round_entries.append((team_a_name, last_round_by_team[team_a_name]))
                previous_round_entries.append((team_b_name, last_round_by_team[team_b_name]))
                last_round_by_team[team_a_name] = round_number
                last_round_by_team[team_b_name] = round_number

                remaining_matches_by_team[team_a_name] -= 1
                remaining_matches_by_team[team_b_name] -= 1

                if entry["uses_exception_match"]:
                    current_exception_match_count += 1
                    exception_match_delta += 1
                    for team_name in entry["exception_teams"]:
                        exception_match_count_by_team[team_name] += 1
                        current_exception_team_use_count += 1
                        exception_team_delta_names.append(team_name)

            return previous_round_entries, removed_preferences, preference_delta, exception_match_delta, exception_team_delta_names

        def undo_round_matches(
            round_number: int,
            pair_entries: list[dict[str, object]],
            previous_round_entries: list[tuple[str, Optional[int]]],
            removed_preferences: list[frozenset[str]],
            exception_match_delta: int,
            exception_team_delta_names: list[str],
        ) -> None:
            nonlocal current_exception_match_count, current_exception_team_use_count

            for team_name in reversed(exception_team_delta_names):
                exception_match_count_by_team[team_name] -= 1
                current_exception_team_use_count -= 1
            current_exception_match_count -= exception_match_delta

            for team_name, previous_round in reversed(previous_round_entries):
                last_round_by_team[team_name] = previous_round

            for entry in reversed(pair_entries):
                team_a_name, team_b_name = entry["pair"]
                remaining_matches_by_team[team_a_name] += 1
                remaining_matches_by_team[team_b_name] += 1
                played_pairs.remove(entry["pair_fs"])
                current_matches.pop()
                round_match_counts[round_number - 1] -= 1

            for pair_fs in removed_preferences:
                unscheduled_preferences.add(pair_fs)

        # --------------------------------------------------------------
        # Enumerators
        # --------------------------------------------------------------
        def enumerate_preference_subsets(
            candidates: list[dict[str, object]],
            quota: int,
            preferred_count: int,
        ):
            chosen: list[dict[str, object]] = []
            used_teams: set[str] = set()
            selected_exception_matches = 0

            def dfs(index: int):
                nonlocal selected_exception_matches
                if len(chosen) == quota:
                    yield list(chosen), set(used_teams)
                    return
                if index >= len(candidates):
                    yield list(chosen), set(used_teams)
                    return

                entry = candidates[index]
                team_a_name, team_b_name = entry["pair"]
                can_take = team_a_name not in used_teams and team_b_name not in used_teams
                extra_exception = 1 if entry["uses_exception_match"] else 0
                if (
                    current_exception_match_count + selected_exception_matches + extra_exception
                    > effective_max_consecutive_exception_matches_total
                ):
                    can_take = False

                take_first = len(chosen) < preferred_count
                if take_first and can_take:
                    used_teams.update({team_a_name, team_b_name})
                    chosen.append(entry)
                    selected_exception_matches += extra_exception
                    yield from dfs(index + 1)
                    selected_exception_matches -= extra_exception
                    chosen.pop()
                    used_teams.remove(team_a_name)
                    used_teams.remove(team_b_name)
                    yield from dfs(index + 1)
                else:
                    yield from dfs(index + 1)
                    if can_take:
                        used_teams.update({team_a_name, team_b_name})
                        chosen.append(entry)
                        selected_exception_matches += extra_exception
                        yield from dfs(index + 1)
                        selected_exception_matches -= extra_exception
                        chosen.pop()
                        used_teams.remove(team_a_name)
                        used_teams.remove(team_b_name)

            yield from dfs(0)

        def enumerate_regular_matchings(
            available_team_names: list[str],
            max_pairs: int,
            round_number: int,
            soft_mode_active: bool,
            preferred_pair_count: int,
        ):
            available = sorted(available_team_names, key=self._team_sort_key)
            chosen: list[dict[str, object]] = []
            selected_exception_matches = 0

            def dfs(remaining: list[str]):
                nonlocal selected_exception_matches
                if max_pairs == 0:
                    yield []
                    return
                if not remaining or len(chosen) == max_pairs:
                    yield list(chosen)
                    return

                first = remaining[0]
                rest = remaining[1:]

                def pair_branches():
                    nonlocal selected_exception_matches
                    for idx, other in enumerate(rest):
                        entry = build_pair_metadata(first, other, round_number, soft_mode_active)
                        if entry is None:
                            continue
                        extra_exception = 1 if entry["uses_exception_match"] else 0
                        if (
                            current_exception_match_count + selected_exception_matches + extra_exception
                            > effective_max_consecutive_exception_matches_total
                        ):
                            continue
                        chosen.append(entry)
                        selected_exception_matches += extra_exception
                        next_remaining = rest[:idx] + rest[idx + 1 :]
                        yield from dfs(next_remaining)
                        selected_exception_matches -= extra_exception
                        chosen.pop()

                pair_first = len(chosen) < preferred_pair_count
                if pair_first:
                    yield from pair_branches()
                    yield from dfs(rest)
                else:
                    yield from dfs(rest)
                    yield from pair_branches()

            yield from dfs(available)

        # --------------------------------------------------------------
        # Greedy fallback
        # --------------------------------------------------------------
        def build_greedy_round(round_number: int, soft_mode_active: bool) -> list[dict[str, object]]:
            remaining_rounds = num_rounds - round_number + 1
            remaining_preferences = len(unscheduled_preferences)
            preference_quota = min(
                num_fields,
                math.ceil(remaining_preferences / remaining_rounds) if remaining_preferences > 0 else 0,
            )
            target_pairs = target_pairs_for_round(round_number)

            eligible_teams = [
                team_name
                for team_name in self._eligible_teams(remaining_matches_by_team)
            ]
            eligible_set = set(eligible_teams)
            scheduled_teams: set[str] = set()
            round_entries: list[dict[str, object]] = []
            scheduled_preferences = 0
            round_exception_matches = 0
            round_limit = min(num_fields, target_pairs)

            preference_candidates: list[dict[str, object]] = []
            for pair in sorted(
                unscheduled_preferences,
                key=lambda p: self._preference_priority(
                    p,
                    round_number,
                    preference_target_round,
                    remaining_matches_by_team,
                ),
            ):
                team_a_name, team_b_name = tuple(sorted(pair))
                if team_a_name not in eligible_set or team_b_name not in eligible_set:
                    continue
                entry = build_pair_metadata(team_a_name, team_b_name, round_number, soft_mode_active)
                if entry is not None:
                    preference_candidates.append(entry)

            for entry in preference_candidates:
                if len(round_entries) >= round_limit or scheduled_preferences >= preference_quota:
                    break
                team_a_name, team_b_name = entry["pair"]
                if team_a_name in scheduled_teams or team_b_name in scheduled_teams:
                    continue
                extra_exception = 1 if entry["uses_exception_match"] else 0
                if current_exception_match_count + round_exception_matches + extra_exception > effective_max_consecutive_exception_matches_total:
                    continue
                round_entries.append(entry)
                scheduled_teams.update({team_a_name, team_b_name})
                scheduled_preferences += 1
                round_exception_matches += extra_exception

            regular_candidates = [name for name in eligible_teams if name not in scheduled_teams]
            for team_name in regular_candidates:
                if len(round_entries) >= round_limit or team_name in scheduled_teams:
                    continue
                for other_name in regular_candidates:
                    if other_name <= team_name or other_name in scheduled_teams:
                        continue
                    entry = build_pair_metadata(team_name, other_name, round_number, soft_mode_active)
                    if entry is None:
                        continue
                    extra_exception = 1 if entry["uses_exception_match"] else 0
                    if current_exception_match_count + round_exception_matches + extra_exception > effective_max_consecutive_exception_matches_total:
                        continue
                    round_entries.append(entry)
                    scheduled_teams.update({team_name, other_name})
                    round_exception_matches += extra_exception
                    break

            return round_entries

        def apply_greedy_completion(start_round: int, soft_mode_active: bool):
            states = []
            preference_total = 0
            for round_number in range(start_round, num_rounds + 1):
                round_entries = build_greedy_round(round_number, soft_mode_active)
                prev_entries, removed_preferences, preference_delta, exception_match_delta, exception_team_delta_names = apply_round_matches(
                    round_number,
                    round_entries,
                )
                states.append(
                    (
                        round_number,
                        round_entries,
                        prev_entries,
                        removed_preferences,
                        preference_delta,
                        exception_match_delta,
                        exception_team_delta_names,
                    )
                )
                preference_total += preference_delta
            return states, preference_total

        def undo_greedy_completion(states) -> None:
            for (
                round_number,
                round_entries,
                prev_entries,
                removed_preferences,
                _,
                exception_match_delta,
                exception_team_delta_names,
            ) in reversed(states):
                undo_round_matches(
                    round_number,
                    round_entries,
                    prev_entries,
                    removed_preferences,
                    exception_match_delta,
                    exception_team_delta_names,
                )

        def finish_current_branch_greedily(round_number: int, soft_mode_active: bool) -> None:
            nonlocal current_preference_count
            states, preference_total = apply_greedy_completion(round_number, soft_mode_active)
            current_preference_count += preference_total
            evaluate_current_solution()
            current_preference_count -= preference_total
            undo_greedy_completion(states)

        # --------------------------------------------------------------
        # DFS
        # --------------------------------------------------------------
        def search(round_number: int) -> None:
            nonlocal node_visit_count, search_stopped, current_preference_count

            if search_stopped:
                return

            if effective_max_node_visits is not None and node_visit_count >= effective_max_node_visits:
                self.node_cap_reached = True
                finish_current_branch_greedily(round_number, allow_relaxed_greedy_completion)
                search_stopped = True
                return

            node_visit_count += 1
            self.last_node_visits = node_visit_count

            # Branch-and-bound pruning using the primary objectives only.
            if best_score is not None:
                optimistic_matches = len(current_matches) + max_possible_additional_matches(round_number)
                if optimistic_matches < best_score[0]:
                    return
                if optimistic_matches == best_score[0]:
                    optimistic_preferences = current_preference_count + max_possible_additional_preferences(round_number)
                    if optimistic_preferences < best_score[1]:
                        return

            if round_number > num_rounds:
                evaluate_current_solution()
                return

            if round_number > effective_max_depth:
                finish_current_branch_greedily(round_number, allow_relaxed_greedy_completion)
                return

            soft_mode_active = (
                effective_max_consecutive_exception_matches_total > 0
                and effective_max_consecutive_exceptions_per_team > 0
                and self._soft_mode_active(
                    node_visit_count,
                    effective_max_node_visits,
                    relax_on_node_ratio,
                )
            )

            remaining_rounds = num_rounds - round_number + 1
            remaining_preferences = len(unscheduled_preferences)
            preference_quota = min(
                num_fields,
                math.ceil(remaining_preferences / remaining_rounds) if remaining_preferences > 0 else 0,
            )

            all_eligible = self._eligible_teams(remaining_matches_by_team)
            eligible_teams = set(all_eligible)

            preference_candidates: list[dict[str, object]] = []
            for pair in sorted(
                unscheduled_preferences,
                key=lambda p: self._preference_priority(
                    p,
                    round_number,
                    preference_target_round,
                    remaining_matches_by_team,
                ),
            ):
                team_a_name, team_b_name = tuple(sorted(pair))
                if team_a_name not in eligible_teams or team_b_name not in eligible_teams:
                    continue
                entry = build_pair_metadata(team_a_name, team_b_name, round_number, soft_mode_active)
                if entry is not None:
                    preference_candidates.append(entry)

            for goal_pairs in goal_order_for_round(round_number):
                preferred_preference_count = min(preference_quota, goal_pairs)
                for selected_preferences, used_teams in enumerate_preference_subsets(
                    preference_candidates,
                    preference_quota,
                    preferred_preference_count,
                ):
                    if search_stopped:
                        break
                    if len(selected_preferences) > goal_pairs:
                        continue

                    remaining_field_slots = min(num_fields - len(selected_preferences), goal_pairs - len(selected_preferences))
                    if remaining_field_slots < 0:
                        continue

                    regular_candidates = [
                        team_name for team_name in all_eligible if team_name not in used_teams
                    ]
                    preferred_regular_count = max(0, goal_pairs - len(selected_preferences))

                    for selected_regulars in enumerate_regular_matchings(
                        regular_candidates,
                        remaining_field_slots,
                        round_number,
                        soft_mode_active,
                        preferred_regular_count,
                    ):
                        if search_stopped:
                            break

                        round_entries = list(selected_preferences) + list(selected_regulars)
                        if len(round_entries) != goal_pairs:
                            # For balanced scheduling we strongly bias toward the current
                            # round goal. If it cannot be reached, lower goals are tried later.
                            continue

                        prev_entries, removed_preferences, preference_delta, exception_match_delta, exception_team_delta_names = apply_round_matches(
                            round_number,
                            round_entries,
                        )
                        current_preference_count += preference_delta
                        search(round_number + 1)
                        current_preference_count -= preference_delta
                        undo_round_matches(
                            round_number,
                            round_entries,
                            prev_entries,
                            removed_preferences,
                            exception_match_delta,
                            exception_team_delta_names,
                        )

                if search_stopped:
                    break

        search(1)
        self.last_node_visits = node_visit_count
        return best_matches, best_remaining

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
