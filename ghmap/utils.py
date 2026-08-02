"""Utility functions for loading and saving JSON/JSONL files."""

import json


def load_jsonl_file(file_path):
    """Load actions from a JSON Lines file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        return [json.loads(line) for line in file]

def load_json_file(file_path):
    """Load a JSON file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

def save_to_jsonl_file(data, file_path):
    """Save a list of data to a JSON Lines file."""
    with open(file_path, 'w', encoding='utf-8') as file:
        for item in data:
            json.dump(item, file)
            file.write('\n')
