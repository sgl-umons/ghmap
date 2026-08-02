"""Module to map GitHub actions to higher-level activities based on rules."""

from datetime import datetime, timedelta
from typing import Any

from tqdm import tqdm


class ActivityMapper: # pylint: disable=too-few-public-methods
    """
    A class to map GitHub actions to high-level activities based on predefined mapping rules.

    Attributes:
        activity_mapping (Dict): Predefined mapping of activities and rules.
        used_ids (set): Set of action IDs that have been processed.
        progress_bar (bool): Flag to enable or disable progress bar (tqdm).
    """

    def __init__(self, activity_mapping: dict, progress_bar: bool = True):
        self.activity_mapping = self._preprocess_activities(activity_mapping)
        self.used_ids = set()
        self.progress_bar = progress_bar

    @staticmethod
    def _preprocess_activities(activity_mapping: dict) -> dict:
        for activity in activity_mapping["activities"]:
            activity["time_window"] = timedelta(
                seconds=int(activity["time_window"].replace("s", ""))
            )
        return activity_mapping

    @staticmethod
    def _within_time_limit(start_time: str, end_time: str, time_window: timedelta) -> bool:
        diff = abs(
            datetime.fromisoformat(end_time.replace("Z", "")) -
            datetime.fromisoformat(start_time.replace("Z", ""))
        )
        return diff <= time_window

    @staticmethod
    def _get_nested_value(data: dict, field: str) -> Any:
        for key in field.split('.'):
            data = data.get(key)
            if data is None:
                return None
        return data

    @staticmethod
    def _group_actions(actions: list[dict]) -> dict[tuple[int, int], list[dict]]:
        grouped = {}
        for action in actions:
            key = (action["actor"]["id"], action["repository"]["id"])
            grouped.setdefault(key, []).append(action)
        for group in grouped.values():
            group.sort(key=lambda x: x["date"])
        return grouped

    def _validate_gathered_actions(self, gathered: list[dict], activity: dict) -> tuple[list[dict], list[dict]]: # pylint: disable=line-too-long
        if len(gathered) == 1:
            return gathered, []

        validated, invalid = [], []
        for action in gathered:
            config = next(
                (a for a in activity["actions"] if a["action"] == action["action"]),
                {}
            )
            if not config.get("validate_with"):
                validated.append(action)
                continue

            is_valid = all(
                not any(target["action"] == rule["target_action"] for target in gathered) or
                all(
                    all(
                        self._get_nested_value(action["details"], field["field"]) ==
                        self._get_nested_value(target["details"], field["target_field"])
                        for field in rule["fields"]
                    )
                    for target in gathered
                    if target["action"] == rule["target_action"] and target["event_id"] != action["event_id"] # pylint: disable=line-too-long
                )
                for rule in config["validate_with"]
            )

            (validated if is_valid else invalid).append(action)

        return validated, invalid

    def _gather_actions(self, actions: list[dict], start_idx: int, activity: dict) -> tuple[list[dict], int, list[dict]]: # pylint: disable=line-too-long
        gathered, preserved = [], []
        found_required = set()
        time_window = activity["time_window"]

        rules = {
            "required": {a["action"] for a in activity["actions"] if not a.get("optional", False)},
            "optional": {a["action"] for a in activity["actions"] if a.get("optional", True)},
            "repeatable": {a["action"] for a in activity["actions"] if a.get("repeat", False)}
        }

        for i, action in enumerate(actions[start_idx:], start_idx):
            if gathered and not self._within_time_limit(gathered[-1]["date"], action["date"], time_window): # pylint: disable=line-too-long
                preserved.extend(actions[i:])
                break

            if action["action"] not in rules["required"] | rules["optional"]:
                preserved.extend(actions[i:])
                break

            if action["action"] in rules["repeatable"] or action["action"] not in {a["action"] for a in gathered}: # pylint: disable=line-too-long
                gathered.append(action)
                if action["action"] in rules["required"]:
                    found_required.add(action["action"])
            else:
                preserved.extend(actions[i:])
                break

        if not rules["required"].issubset(found_required):
            preserved.extend(gathered)
            return [], start_idx, preserved

        validated, invalid = self._validate_gathered_actions(gathered, activity)
        preserved.extend(invalid)
        return validated, start_idx + len(validated), preserved

    def map(self, actions: list[dict]) -> list[dict]:
        """Map actions to activities based on activity mapping configuration."""
        grouped = self._group_actions(actions)
        all_mapped_activities = []

        for actions_group in tqdm(grouped.values(), desc="Mapping actions to activities", unit="group", disable=not self.progress_bar): # pylint: disable=line-too-long
            i = 0
            while i < len(actions_group):
                if actions_group[i]["event_id"] in self.used_ids:
                    i += 1
                    continue

                for activity in self.activity_mapping["activities"]:
                    gathered, _, _ = self._gather_actions(actions_group, i, activity)
                    if gathered:
                        all_mapped_activities.append({
                            "activity": activity["name"],
                            "start_date": gathered[0]["date"],
                            "end_date": gathered[-1]["date"],
                            "actor": gathered[0]["actor"],
                            "repository": gathered[0]["repository"],
                            "actions": [
                                {k: a[k] for k in ("action", "event_id", "date", "details")}
                                for a in gathered
                            ]
                        })
                        self.used_ids.update(a["event_id"] for a in gathered)
                        actions_group = [
                            a for a in actions_group if a["event_id"] not in self.used_ids
                        ]
                        i = 0
                        break
                else:
                    i += 1

        unused_ids = {
            a["event_id"] for group in grouped.values() for a in group
        } - self.used_ids

        if unused_ids:
            print(f"Warning: Unused actions: {unused_ids}")

        all_mapped_activities.sort(key=lambda x: x["start_date"])
        return all_mapped_activities
