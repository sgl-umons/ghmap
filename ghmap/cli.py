"""Command-line interface for the GitHub Event Mapping Tool."""

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from importlib.resources import files
from typing import Dict, List, Tuple
from .preprocess.event_processor import EventProcessor
from .mapping.action_mapper import ActionMapper
from .mapping.activity_mapper import ActivityMapper
from .utils import load_json_file, save_to_jsonl_file


def extract_version_info(filename: str) -> Tuple[str, datetime]:
    """Extract platform and version date from mapping filename.

    Expected format: {platform}_{type}_{date}.json
    Example: github_action_2025-10-08T16:59:23Z.json
    """
    # Remove .json extension and split
    base_name = filename.replace('.json', '')
    parts = base_name.split('_')

    if len(parts) < 3:
        raise ValueError(f"Invalid mapping filename format: {filename}")

    # Platform is first part
    platform = parts[0]

    # Version date is last part (after last underscore)
    version_str = parts[-1]

    # Parse ISO format date
    try:
        # Try with Z suffix
        version_date = datetime.fromisoformat(version_str.replace('Z', '+00:00'))
    except ValueError:
        # Try without timezone info
        version_date = datetime.fromisoformat(version_str)

    return platform, version_date


def find_valid_mappings(platform: str, event_date: datetime) -> Dict[str, Path]:
    """Find the valid mapping files for a given platform and event date."""
    config_dir = Path(files("ghmap").joinpath("config"))

    # Group mapping files by type and version date
    action_mappings = {}
    activity_mappings = {}

    for mapping_file in config_dir.glob(f"{platform}_*.json"):
        try:
            file_platform, version_date = extract_version_info(mapping_file.name)

            if file_platform != platform:
                continue

            # Determine mapping type
            if "action" in mapping_file.name.lower():
                action_mappings[version_date] = mapping_file
            elif "activity" in mapping_file.name.lower():
                activity_mappings[version_date] = mapping_file

        except (ValueError, KeyError):
            continue

    # Find the latest mapping that's valid for the event date
    # (mapping version date <= event date)
    valid_action_mapping = None
    valid_activity_mapping = None

    # Sort versions descending to find latest valid one
    sorted_action_versions = sorted(
        [v for v in action_mappings if v <= event_date],
        reverse=True
    )

    sorted_activity_versions = sorted(
        [v for v in activity_mappings if v <= event_date],
        reverse=True
    )

    if sorted_action_versions:
        valid_action_mapping = action_mappings[sorted_action_versions[0]]
    if sorted_activity_versions:
        valid_activity_mapping = activity_mappings[sorted_activity_versions[0]]

    return {
        'action': valid_action_mapping,
        'activity': valid_activity_mapping
    }


def split_events_by_mapping_versions(
    events: List[Dict], platform: str
) -> Dict[Tuple[datetime, datetime], List[Dict]]:
    """Split events into time periods based on available mapping versions."""

    config_dir = Path(files("ghmap").joinpath("config"))

    version_dates = _get_version_dates(config_dir, platform)
    if not version_dates:
        return {(datetime.min.replace(tzinfo=timezone.utc),
                 datetime.max.replace(tzinfo=timezone.utc)): events}

    time_periods = _create_time_periods(sorted(version_dates))
    events_by_period = _assign_events_to_periods(events, time_periods)

    # Remove empty periods
    return {k: v for k, v in events_by_period.items() if v}


def _get_version_dates(config_dir: Path, platform: str) -> set:
    """Retrieve all unique mapping version dates for a platform."""
    version_dates = set()
    for mapping_file in config_dir.glob(f"{platform}_*.json"):
        try:
            file_platform, version_date = extract_version_info(mapping_file.name)
            if file_platform == platform:
                version_dates.add(version_date)
        except (ValueError, KeyError):
            continue
    return version_dates


def _create_time_periods(sorted_versions: List[datetime]) -> List[Tuple[datetime, datetime]]:
    """Create time periods from sorted version dates."""
    periods = []
    for i, start_date in enumerate(sorted_versions):
        end_date = (
            sorted_versions[i + 1]
            if i + 1 < len(sorted_versions)
            else datetime.max.replace(tzinfo=timezone.utc)
        )
        periods.append((start_date, end_date))
    return periods


def _assign_events_to_periods(
        events: List[Dict],
        time_periods: List[Tuple[datetime, datetime]]
) -> Dict[Tuple[datetime, datetime], List[Dict]]:
    """Assign each event to its corresponding time period."""
    events_by_period = {period: [] for period in time_periods}

    for event in events:
        event_date = _parse_event_date(event.get('created_at'))
        if not event_date:
            continue

        for period_start, period_end in time_periods:
            if period_start <= event_date < period_end:
                events_by_period[(period_start, period_end)].append(event)
                break

    return events_by_period


def _parse_event_date(date_str: str) -> datetime | None:
    """Parse the event date string into a datetime object."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        try:
            return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S%z')
        except ValueError:
            return None

def main():
    """Parse arguments and run the event-to-activity mapping pipeline."""
    args = _parse_args()

    try:
        all_actions, all_activities = _process_events(args)
        _save_results(all_actions, all_activities, args.output_actions, args.output_activities)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"An error occurred: {e}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process GitHub events into structured activities."
    )
    parser.add_argument(
        '--raw-events',
        required=True,
        help="Path to the folder containing raw events."
    )
    parser.add_argument(
        '--output-actions',
        required=True,
        help="Path to the output file for mapped actions."
    )
    parser.add_argument(
        '--output-activities',
        required=True,
        help="Path to the output file for mapped activities."
    )
    parser.add_argument(
        '--actors-to-remove',
        nargs='*',
        default=[],
        help="List of actors to remove from the raw events."
    )
    parser.add_argument(
        '--repos-to-remove',
        nargs='*',
        default=[],
        help="List of repositories to remove from the raw events."
    )
    parser.add_argument(
        '--orgs-to-remove',
        nargs='*',
        default=[],
        help="List of organizations to remove from the raw events."
    )
    parser.add_argument(
        '--platform',
        default='github',
        help="Platform to use for mapping (default: github)."
    )
    parser.add_argument(
        '--disable-progress-bar',
        action='store_false',
        dest='progress_bar',
        help="Disable the progress bar display."
    )
    parser.add_argument(
        '--custom-action-mapping',
        default=None,
        help='Path to a custom event to action mapping JSON file.'
    )
    parser.add_argument(
        '--custom-activity-mapping',
        default=None,
        help='Path to a custom action to activity mapping JSON file.'
    )
    return parser.parse_args()


def _process_events(args: argparse.Namespace) -> (List[Dict], List[Dict]):
    """Process raw events into actions and activities."""
    print("Step 0: Preprocessing events...")
    processor = EventProcessor(args.platform, progress_bar=args.progress_bar)
    events = processor.process(
        args.raw_events,
        args.actors_to_remove,
        args.repos_to_remove,
        args.orgs_to_remove
    )

    # If custom mappings provided, skip automatic mapping
    if args.custom_action_mapping and args.custom_activity_mapping:
        return _apply_custom_mappings(events, args)

    # Automatic mapping
    all_actions = []
    all_activities = []

    events_by_period = split_events_by_mapping_versions(events, args.platform)
    if not events_by_period:
        print("No events to process after filtering.")
        return all_actions, all_activities

    print(f"Found {len(events_by_period)} time period(s) based on mapping versions.")
    for (period_start, period_end), period_events in events_by_period.items():
        if not period_events:
            continue
        _process_period(period_events, period_start, period_end, args, all_actions, all_activities)

    return all_actions, all_activities


def _apply_custom_mappings(
        events: List[Dict],
        args: argparse.Namespace
) -> (List[Dict], List[Dict]):
    """Apply custom action and activity mappings if provided."""
    print("Using custom mappings, skipping automatic mapping detection...")
    all_actions, all_activities = [], []

    if args.custom_action_mapping:
        action_mapping = load_json_file(args.custom_action_mapping)
        action_mapper = ActionMapper(action_mapping, progress_bar=args.progress_bar)
        all_actions = action_mapper.map(events)

    if args.custom_activity_mapping:
        activity_mapping = load_json_file(args.custom_activity_mapping)
        activity_mapper = ActivityMapper(activity_mapping, progress_bar=args.progress_bar)
        all_activities = activity_mapper.map(all_actions)

    if all_actions:
        save_to_jsonl_file(all_actions, args.output_actions)
        print(f"Total {len(all_actions)} actions saved to: {args.output_actions}")

    if all_activities:
        save_to_jsonl_file(all_activities, args.output_activities)
        print(f"Total {len(all_activities)} activities saved to: {args.output_activities}")

    return all_actions, all_activities


def _process_period(
        period_events: List[Dict],
        period_start: datetime,
        period_end: datetime,
        args: argparse.Namespace,
        all_actions: List[Dict],
        all_activities: List[Dict]
):
    """Process events for a single time period."""
    print(f"\nProcessing period: {period_start} to {period_end}")
    print(f"  Events in period: {len(period_events)}")

    period_mid = period_start + (period_end - period_start) / 2
    valid_mappings = find_valid_mappings(args.platform, period_mid)

    if not valid_mappings['action'] or not valid_mappings['activity']:
        print(f"  Warning: No valid mappings found for this period. Skipping.")
        return

    print(f"  Using action mapping: {valid_mappings['action'].name}")
    print(f"  Using activity mapping: {valid_mappings['activity'].name}")

    # Step 1: Event to Action Mapping
    action_mapping = load_json_file(valid_mappings['action'])
    action_mapper = ActionMapper(action_mapping, progress_bar=args.progress_bar)
    actions = action_mapper.map(period_events)
    all_actions.extend(actions)

    # Step 2: Action to Activity Mapping
    activity_mapping = load_json_file(valid_mappings['activity'])
    activity_mapper = ActivityMapper(activity_mapping, progress_bar=args.progress_bar)
    activities = activity_mapper.map(actions)
    all_activities.extend(activities)


def _save_results(
        all_actions: List[Dict],
        all_activities: List[Dict],
        output_actions: str,
        output_activities: str
):
    if all_actions:
        save_to_jsonl_file(all_actions, output_actions)
        print(f"\nTotal {len(all_actions)} actions saved to: {output_actions}")
    if all_activities:
        save_to_jsonl_file(all_activities, output_activities)
        print(f"Total {len(all_activities)} activities saved to: {output_activities}")


if __name__ == '__main__':
    main()
