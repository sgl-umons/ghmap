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
        [v for v in action_mappings.keys() if v <= event_date],
        reverse=True
    )
    
    sorted_activity_versions = sorted(
        [v for v in activity_mappings.keys() if v <= event_date],
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


def split_events_by_mapping_versions(events: List[Dict], platform: str) -> Dict[Tuple[datetime, datetime], List[Dict]]:
    """Split events into time periods based on available mapping versions."""
    config_dir = Path(files("ghmap").joinpath("config"))
    
    # Get all unique version dates for this platform
    version_dates = set()
    
    for mapping_file in config_dir.glob(f"{platform}_*.json"):
        try:
            file_platform, version_date = extract_version_info(mapping_file.name)
            if file_platform == platform:
                version_dates.add(version_date)
        except (ValueError, KeyError):
            continue
    
    if not version_dates:
        # No versioned mappings found, use all events in one batch
        return {(datetime.min.replace(tzinfo=timezone.utc), 
                datetime.max.replace(tzinfo=timezone.utc)): events}
    
    # Sort version dates
    sorted_versions = sorted(version_dates)
    
    # Create time periods
    time_periods = []
    for i, version_date in enumerate(sorted_versions):
        start_date = version_date
        end_date = sorted_versions[i + 1] if i + 1 < len(sorted_versions) else datetime.max.replace(tzinfo=timezone.utc)
        time_periods.append((start_date, end_date))
    
    # Split events into periods
    events_by_period = {}
    for period in time_periods:
        events_by_period[period] = []
    
    for event in events:
        # Extract event date (assuming standard GitHub event structure)
        event_date_str = event.get('created_at', '')
        if not event_date_str:
            # Skip events without date
            continue
            
        try:
            event_date = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
        except ValueError:
            # Try alternative format
            event_date = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M:%S%z')
        
        # Find which period this event belongs to
        for period_start, period_end in time_periods:
            if period_start <= event_date < period_end:
                events_by_period[(period_start, period_end)].append(event)
                break
    
    # Remove empty periods
    events_by_period = {k: v for k, v in events_by_period.items() if v}
    
    return events_by_period


def main():
    """Parse arguments and run the event-to-activity mapping pipeline."""
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
    args = parser.parse_args()

    try:
        all_actions = []
        all_activities = []
        
        # Step 0: Event Preprocessing
        print("Step 0: Preprocessing events...")
        # We need platform to pass to EventProcessor, but we'll auto-detect
        processor = EventProcessor(args.platform, progress_bar=args.progress_bar)
        events = processor.process(
            args.raw_events,
            args.actors_to_remove,
            args.repos_to_remove,
            args.orgs_to_remove
        )
        
        # Split events by mapping versions
        print(f"Splitting events by {args.platform} mapping versions...")
        events_by_period = split_events_by_mapping_versions(events, args.platform)
        
        if not events_by_period:
            print("No events to process after filtering.")
            return
            
        print(f"Found {len(events_by_period)} time period(s) based on mapping versions.")
        
        # Process each time period with its appropriate mappings
        for (period_start, period_end), period_events in events_by_period.items():
            if not period_events:
                continue
                
            print(f"\nProcessing period: {period_start} to {period_end}")
            print(f"  Events in period: {len(period_events)}")
            
            # Find valid mappings for this period (use middle point of period)
            period_mid = period_start + (period_end - period_start) / 2
            valid_mappings = find_valid_mappings(args.platform, period_mid)
            
            if not valid_mappings['action'] or not valid_mappings['activity']:
                print(f"  Warning: No valid mappings found for this period. Skipping.")
                continue
                
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
        
        # Save all results
        if all_actions:
            save_to_jsonl_file(all_actions, args.output_actions)
            print(f"\nTotal {len(all_actions)} actions saved to: {args.output_actions}")
            
        if all_activities:
            save_to_jsonl_file(all_activities, args.output_activities)
            print(f"Total {len(all_activities)} activities saved to: {args.output_activities}")
            
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"An error occurred: {e}")


if __name__ == '__main__':
    main()