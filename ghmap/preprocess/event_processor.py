"""Preprocess module for filtering and cleaning GitHub events."""
import json
import os
from datetime import datetime
from typing import List, Dict
from tqdm import tqdm


class EventProcessor:  # pylint: disable=too-few-public-methods
    """
    A class to process events, removing unwanted events and filtering redundant review events.
    """

    def __init__(self, platform: str = 'github', progress_bar: bool = True):
        self.platform = platform
        self.progress_bar = progress_bar
        self.processed_ids = set()
        self.pending_events = []

    @staticmethod
    def _parse_time(timestamp: str | int) -> datetime:
        """Converts a Unix timestamp (in milliseconds) or ISO 8601 string to a datetime object."""
        if isinstance(timestamp, str):
            return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
        return datetime.utcfromtimestamp(timestamp / 1000)

    @staticmethod
    def _calculate_time_diff(start: datetime, end: datetime) -> float:
        """Calculates the difference in seconds between two datetime objects."""
        return (end - start).total_seconds()

    @staticmethod
    def _is_within_time_window(event1: Dict, event2: Dict, window: int = 2) -> bool:
        """Checks if event2 is within a specified time window (in seconds) of event1."""
        time_diff = abs(EventProcessor._calculate_time_diff(
            EventProcessor._parse_time(event1['created_at']),
            EventProcessor._parse_time(event2['created_at'])
        ))
        return time_diff <= window

    def _should_keep_event(self, current_event: Dict, events: List[Dict], index: int) -> bool:
        """Determines whether the current event should be kept based on redundant review checks."""
        actor_id = current_event['actor']['id']
        repo_id = current_event['repo']['id']

        for j in range(index - 1, -1, -1):
            if not self._is_within_time_window(current_event, events[j]):
                break
            if events[j]['type'] == "PullRequestReviewCommentEvent" and \
                    events[j]['actor']['id'] == actor_id and \
                    events[j]['repo']['id'] == repo_id:
                return False

        for j in range(index + 1, len(events)):
            if not self._is_within_time_window(current_event, events[j]):
                break
            if events[j]['type'] == "PullRequestReviewCommentEvent" and \
                    events[j]['actor']['id'] == actor_id and \
                    events[j]['repo']['id'] == repo_id:
                return False

        return True

    def _filter_redundant_review_events(self, events: List[Dict]) -> List[Dict]:
        """Filters out redundant PullRequestReviewEvent events."""
        filtered_events = []
        combined_events = self.pending_events + events
        self.pending_events = combined_events[-3:]

        for i, event in enumerate(combined_events):
            if event['type'] == "PullRequestReviewEvent" and event['id'] not in self.processed_ids:
                if self._should_keep_event(event, combined_events, i):
                    if not (
                            filtered_events and
                            filtered_events[-1]['type'] == "PullRequestReviewEvent" and
                            filtered_events[-1]['actor']['id'] == event['actor']['id'] and
                            filtered_events[-1]['repo']['id'] == event['repo']['id'] and
                            self._is_within_time_window(filtered_events[-1], event)
                    ):
                        filtered_events.append(event)
                        self.processed_ids.add(event['id'])
            elif event['id'] not in self.processed_ids:
                filtered_events.append(event)
                self.processed_ids.add(event['id'])

        return filtered_events

    @staticmethod
    def _remove_unwanted_actors(events: List[Dict], actors_to_remove: List[str]) -> List[Dict]:
        """Filters out events belonging to unwanted actors."""
        return [e for e in events if e.get('actor', {}).get('login') not in actors_to_remove]

    @staticmethod
    def _remove_unwanted_repos(events: List[Dict], repos_to_remove: List[str]) -> List[Dict]:
        """Filters out events belonging to unwanted repositories."""
        return [e for e in events if e.get('repo', {}).get('name') not in repos_to_remove]

    @staticmethod
    def _remove_unwanted_orgs(events: List[Dict], orgs_to_remove: List[str]) -> List[Dict]:
        """Filters out events belonging to unwanted organizations."""
        return [e for e in events if e.get('org', {}).get('login') not in orgs_to_remove]

    def process(
        self,
        input_path: str,
        actors_to_remove: List[str],
        repos_to_remove: List[str],
        orgs_to_remove: List[str]
    ) -> List[Dict]:
        """
        Processes an input file or directory of files.
        Supports:
            - JSON list     → [ {}, {}, ... ]
            - JSON object   → { ... }
            - JSON lines    → {} \n {} \n {}
            - directory containing .json files
        """

        all_events = []

        if os.path.isdir(input_path):
            # Process every .json file in the directory
            files = sorted(f for f in os.listdir(input_path) if f.endswith(".json"))
            for filename in tqdm(files, desc="Processing event files", disable=not self.progress_bar):
                path = os.path.join(input_path, filename)
                events = self._load_events(path)
                all_events.extend(self._apply_filters(events, actors_to_remove, repos_to_remove, orgs_to_remove))

        elif os.path.isfile(input_path):
            # Process single file
            events = self._load_events(input_path)
            all_events.extend(self._apply_filters(events, actors_to_remove, repos_to_remove, orgs_to_remove))

        return all_events

    def _load_events(self, path: str) -> List[Dict]:
        """Loads events from JSON, JSON list, or JSON lines."""
        with open(path, 'r', encoding='utf-8') as file:
            first_char = file.read(1)
            file.seek(0)
            if first_char == '[':
                return json.load(file)
            else:
                return [json.loads(line) for line in file]
            
        raise ValueError(f"Unsupported JSON structure in: {path}")
    
    def _apply_filters(self, events, actors, repos, orgs):
        events = self._remove_unwanted_actors(events, actors)
        events = self._remove_unwanted_repos(events, repos)
        events = self._remove_unwanted_orgs(events, orgs)

        if self.platform == "github":
            events = self._filter_redundant_review_events(events)

        return events