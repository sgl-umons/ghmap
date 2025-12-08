"""Action Mapper: maps GitHub events to structured high-level actions."""

import json
import re
from datetime import datetime
from typing import List, Dict, Any
from tqdm import tqdm


class ActionMapper: # pylint: disable=too-few-public-methods
    """
    A class to map events to high-level actions based on predefined event types and conditions.

    Attributes:
        action_mapping (Dict): Predefined mapping of actions and event rules.
        event_type_key (str): Key to identify the event type in the event record.
        created_at_key (str): Key to identify the creation date in the event record.
        progress_bar (bool): Flag to enable or disable progress bar (tqdm).
    """

    def __init__(self, action_mapping: Dict, progress_bar: bool = True):
        self.action_mapping = action_mapping
        parameters = action_mapping.get('parameters', {})
        self.event_type_key = parameters.get('event_type_key', 'type')
        self.created_at_key = parameters.get('created_at_key', 'created_at')
        self.progress_bar = progress_bar

    @staticmethod
    def _deserialize_payload(event_record: Dict) -> Dict:
        """Deserializes the 'payload' field of the event record if it's a string."""
        if isinstance(event_record['payload'], str):
            event_record['payload'] = json.loads(event_record['payload'])
        return event_record

    def _convert_date_to_iso(self, event_record: Dict) -> Dict:
        """Converts 'created_at' to ISO 8601 format if it's a Unix timestamp or string."""
        created_at = event_record.get(self.created_at_key)
        if isinstance(created_at, str):
            # If the date has milliseconds, remove them
            if '.' in created_at:
                created_at = created_at.split('.')[0] + "Z"
            event_record[self.created_at_key] = datetime.strptime(
                created_at, '%Y-%m-%dT%H:%M:%SZ'
            ).strftime('%Y-%m-%dT%H:%M:%SZ')
        elif isinstance(created_at, int):
            event_record[self.created_at_key] = datetime.utcfromtimestamp(
                created_at / 1000
            ).strftime('%Y-%m-%dT%H:%M:%SZ')
        return event_record

    @staticmethod
    def _match_condition(event_value: Any, mapping_value: Any) -> bool:
        """Matches an event value against a mapping value."""
        if isinstance(mapping_value, dict):
            return all(
                ActionMapper._match_condition(event_value.get(k), v)
                for k, v in mapping_value.items() if k in event_value
            )

        if isinstance(mapping_value, list):
            return all(
                ActionMapper._match_condition(ev, mv)
                for ev, mv in zip(event_value, mapping_value)
            ) if event_value else False

        if (
            isinstance(mapping_value, str)
            and mapping_value.startswith('^')
            and mapping_value.endswith('$')
        ):
            return bool(re.match(mapping_value, event_value))

        return event_value == mapping_value

    def _extract_attributes(
        self, event_record: Dict, action_details: Dict, action_name: str
    ) -> Dict:
        """Extracts attributes and common fields from the event record."""
        mapped_action = {'action': action_name}

        if action_details['attributes'].get('include_common_fields'):
            mapped_action.update(
                self._extract_fields(
                    event_record, self.action_mapping['common_fields']
                )
            )

        mapped_action['details'] = self._extract_fields(
            event_record, action_details['attributes'].get('details', {})
        )

        return mapped_action

    def _extract_fields(self, event_record: Dict, field_mapping: Dict) -> Dict:
        """Extracts values from the event record using provided mappings."""
        extracted_data = {}
        for field_key, mapping_value in field_mapping.items():
            if isinstance(mapping_value, dict):
                extracted_data[field_key] = self._extract_fields(
                    event_record, mapping_value
                )
            elif isinstance(mapping_value, list):
                extracted_data[field_key] = self._extract_list(
                    event_record, mapping_value
                )
            else:
                extracted_data[field_key] = self._extract_field(
                    event_record, mapping_value
                )
        return extracted_data

    def _extract_list(self, event_record: Dict, list_mapping: list) -> list:
        """Extracts a list of values from the event record."""
        base_path = list_mapping[0][list(list_mapping[0].keys())[0]].split('.')[:-1]
        base_list = self._extract_field(event_record, base_path)
        if not isinstance(base_list, list):
            return []
        return [
            {
                key: item.get(path.split('.')[-1])
                for key, path in list_mapping[0].items()
            }
            for item in base_list
        ]

    @staticmethod
    def _extract_field(event_record: Dict, field_path: str) -> Any:
        """Extracts a value from the event record using a dotted field path."""
        keys = field_path.split('.') if isinstance(field_path, str) else field_path
        value = event_record
        for key in keys:
            if isinstance(value, list):
                return value
            value = value.get(key)
            if value is None:
                return None
        return value

    def map(self, events: List[Dict], mapping_strategy: str = "flexible") -> List[Dict]:
        """
        Maps events to high-level actions using mapping configuration.

        mapping_strategy: "strict" or "flexible"
        - strict: raise an error on UnknownAction
        - flexible: tolerate UnknownAction and issue a warning once
        """
        all_mapped_actions = []
        unknown_warning_issued = False  # only warn once in flexible mode

        for event_record in tqdm(
            events, desc="Mapping events to actions", unit="event", disable=not self.progress_bar
        ):
            if 'payload' in event_record:
                event_record = self._deserialize_payload(event_record)
            event_record = self._convert_date_to_iso(event_record)
            event_type = self._extract_field(event_record, self.event_type_key)

            for action_name, action_details in self.action_mapping['actions'].items():
                if (
                    event_type == action_details['event'].get('type', None)
                    and all(
                        self._match_condition(
                            self._extract_field(event_record, k), v
                        )
                        for k, v in action_details['event'].items() if k != 'type'
                    )
                ):
                    mapped_action = self._extract_attributes(
                        event_record, action_details, action_name
                    )
                    all_mapped_actions.append(mapped_action)
                    break
            else:
                # Handle UnknownAction based on strategy
                if mapping_strategy == "strict":
                    raise ValueError(
                        f"UnknownAction encountered for event: {event_record}"
                    )
                if mapping_strategy == "flexible":
                    if not unknown_warning_issued:
                        print("Warning: Some actions not identified and mapped as UnknownAction.")
                        unknown_warning_issued = True

                    mapped_action = self._extract_attributes(
                        event_record,
                        self.action_mapping['actions']['UnknownAction'],
                        'UnknownAction'
                    )
                    all_mapped_actions.append(mapped_action)
                else:
                    raise ValueError(f"Invalid mapping_strategy: {mapping_strategy}")

        return all_mapped_actions
