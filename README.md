# ghmap: GitHub Event Mapping Tool

<!-- CI & QA -->
[![Tests](https://github.com/uhourri/ghmap/actions/workflows/python-package.yml/badge.svg?branch=main)](https://github.com/uhourri/ghmap/actions/workflows/python-package.yml)
[![Linting](https://github.com/uhourri/ghmap/actions/workflows/pylint.yml/badge.svg?branch=main)](https://github.com/uhourri/ghmap/actions/workflows/pylint.yml)
[![CodeQL](https://github.com/uhourri/ghmap/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/uhourri/ghmap/actions/workflows/codeql.yml)

<!-- Dependencies & Security -->
[![Dependencies](https://github.com/uhourri/ghmap/actions/workflows/dependabot/dependabot-updates/badge.svg?branch=main)](https://github.com/uhourri/ghmap/actions/workflows/dependabot/dependabot-updates)
[![codecov](https://codecov.io/gh/uhourri/ghmap/branch/main/graph/badge.svg)](https://codecov.io/gh/uhourri/ghmap)

<!-- Meta -->
[![PyPI](https://badgen.net/pypi/v/ghmap?cachebuster=1)](https://pypi.org/project/ghmap)
[![Commits](https://badgen.net/github/last-commit/uhourri/ghmap)](https://github.com/uhourri/ghmap/commits/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![SWH](https://archive.softwareheritage.org/badge/origin/https://github.com/uhourri/ghmap/)](https://archive.softwareheritage.org/browse/origin/?origin_url=https://github.com/uhourri/ghmap)

ghmap is a Python tool that transforms raw event data from software development platforms (GitHub, GitLab, etc.) into structured **actions** and **activities** reflecting contributors' real intent. By abstracting low‑level events like `PullRequestEvent`, `IssuesEvent` and `DeleteEvent` into meaningful operations, ghmap facilitates large‑scale analysis of contributor behavior, with main features:

- **Multi‑platform support** works with GitHub and GitLab; easily extensible to other platforms.
- **Versioned mappings** automatically selects the correct mapping version based on event timestamps, accommodating platform API changes over time.
- **Custom mappings** use your own JSON mapping files for platform‑specific or custom event structures.

The **NumFocus Contributor Activities dataset** (available on [Zenodo](https://zenodo.org/records/14914741)) was built using ghmap. It contains over 2 million activities from 180,000+ contributors across 2,800 repositories and 58 projects over three years.

---

## Repository Structure

```
.
├── LICENSE
├── README.md
├── ghmap/
│   ├── __init__.py
│   ├── cli.py                     # Command‑line interface
│   ├── config/                    # JSON mapping files
│   │   ├── github_action_20150101T000000Z.json
│   │   ├── github_action_20251008T165923Z.json
│   │   ├── github_activity_20150101T000000Z.json
│   │   └── github_activity_20251008T165923Z.json
│   ├── mapping/
│   │   ├── __init__.py
│   │   ├── action_mapper.py       # Maps raw events → actions
│   │   └── activity_mapper.py     # Groups actions → activities
│   ├── preprocess/
│   │   ├── __init__.py
│   │   └── event_processor.py     # Platform‑aware preprocessing
│   └── utils.py
├── pyproject.toml
├── requirements.txt
├── setup.py
└── tests/
    ├── test_cli.py
    └── data/                      # Test fixtures
        ├── custom-*.json
        └── sample-events.json
```

---

## Installation

ghmap requires **Python 3.10 or later**. For best practices, install it in an isolated environment to keep your system clean.

### Option A: Using [uv](https://docs.astral.sh/uv/)

```bash
# Find more details on how to install uv in its official documentation.
uv tool install ghmap
```

### Option B: Using [venv](https://docs.python.org/3/library/venv.html)

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# or
.\.venv\Scripts\activate         # Windows

# Install ghmap from PyPI
pip install ghmap
```

---

## Usage

```bash
ghmap --raw-events /path/to/events-folder \
      --output-actions /path/to/actions.jsonl \
      --output-activities /path/to/activities.jsonl \
      [--platform github] \
      [--custom-action-mapping custom_event_to_action.json] \
      [--custom-activity-mapping custom_action_to_activity.json] \
      [--mapping-strategy flexible] \
      [--disable-progress-bar]
```

| Argument | Description |
|----------|-------------|
| `--raw-events` | Path to a folder or file containing raw event data (JSON format). |
| `--output-actions` | Path where mapped actions will be saved (JSON Lines format). |
| `--output-activities` | Path where mapped activities will be saved (JSON Lines format). |
| `--platform` | Platform identifier (e.g., `github`, `gitlab`). Default: `github`. |
| `--custom-action-mapping` | Path to a custom event‑to‑action mapping JSON file. |
| `--custom-activity-mapping` | Path to a custom action‑to‑activity mapping JSON file. |
| `--mapping-strategy` | How to handle unknown actions: `strict` (raise error) or `flexible` (warn once). Default: `flexible`. |
| `--disable-progress-bar` | Disable the progress bar display. |

**Note:** When custom mappings are provided, the automatic version‑based mapping is bypassed. This is useful for processing events from platforms other than GitHub or for using your own mapping definitions.

---

## Versioned Mapping System

Mapping definitions are stored as timestamped JSON files in the `config/` directory:

- `{platform}_action_YYYYMMDDTHHMMSSZ.json` maps raw events to actions
- `{platform}_activity_YYYYMMDDTHHMMSSZ.json` groups actions into activities

For each event, ghmap selects the **latest mapping version whose date is ≤ the event’s timestamp**. This ensures that historical events are interpreted according to the API schema valid at that time, while recent events use the most up‑to‑date mappings.

---

## Multi‑Platform Support

The `--platform` argument and platform‑aware preprocessing allow ghmap to handle different event sources. Each mapping file includes a `platform` field in its metadata, enabling:

- Correct field paths for `type`, `created_at`, etc.
- Platform‑specific preprocessing (e.g., GitHub’s redundant review event filtering)
- Skipping irrelevant steps for other platforms

GitLab events, which have a different structure than GitHub events, can be processed by providing custom mappings and setting `--platform gitlab`.

---

## Mapping Process

### 1. Event‑to‑Action Mapping

Each raw event is transformed into a structured **action** with a clear type and extracted details.

**Example raw event (IssuesEvent):**
```json
{
  "type": "IssuesEvent",
  "payload": { "action": "closed", "issue": { "id": 1515182791, "number": 16, "title": "..." } },
  "actor": { "login": "uhourri", "id": 72564223 },
  "repo": { "name": "uhourri/ghmap", "id": 899093732 },
  "created_at": 1672604398000,
  "id": "26170139709"
}
```

**Corresponding mapping definition (excerpt):**
```json
"CloseIssue": {
  "event": {
    "type": "IssuesEvent",
    "payload": { "action": "closed" }
  },
  "attributes": {
    "include_common_fields": true,
    "details": {
      "issue": {
        "id": "payload.issue.id",
        "number": "payload.issue.number",
        "title": "payload.issue.title"
      }
    }
  }
}
```

**Resulting action:**
```json
{
  "action": "CloseIssue",
  "event_id": "26170139709",
  "date": "2023-01-01T20:19:58Z",
  "actor": { "id": 72564223, "login": "uhourri" },
  "repository": { "id": 899093732, "name": "uhourri/ghmap" },
  "details": { "issue": { "id": 1515182791, "number": 16, "title": "..." } }
}
```

### 2. Action‑to‑Activity Mapping

Related actions are grouped into a higher‑level **activity**, capturing a complete contributor task.

**Example activity definition:**
```json
{
  "name": "CloseIssue",
  "time_window": "3s",
  "actions": [
    { "action": "CloseIssue", "optional": false, "repeat": false },
    { "action": "CreateIssueComment", "optional": true, "repeat": false,
      "validate_with": [
        { "target_action": "CloseIssue",
          "fields": [
            { "field": "issue.number", "target_field": "issue.number" }
          ]
        }
      ]
    }
  ]
}
```

**Resulting activity:**
```json
{
  "activity": "CloseIssue",
  "start_date": "2023-01-01T00:06:24Z",
  "end_date": "2023-01-01T00:06:26Z",
  "actor": { "id": 72564223, "login": "uhourri" },
  "repository": { "id": 899093732, "name": "uhourri/ghmap" },
  "actions": [
    { "action": "CloseIssue", ... },
    { "action": "CreateIssueComment", ... }
  ]
}
```

---

## Supported Actions & Activities

ghmap’s mappings cover a wide range of GitHub event types. Recent additions include:

- **New event types:** `DiscussionEvent` (maps to `CreateDiscussion`)
- **New actions for Issues and Pull Requests:** `labeled`, `unlabeled`, `assigned`, `unassigned`
- **New actions for Pull Request Reviews:** `dismissed`, `updated`
- **Grouped activities:** e.g., `ManageIssueAssignees` (combining assign/unassign actions within a time window)

The exact set of actions and activities is defined in the versioned mapping files.

---

## Custom Mappings

When processing events from a platform not covered by the built‑in mappings or when a different grouping logic is desired, you can provide your own JSON mapping files:

```bash
ghmap --raw-events gitlab-events/ \
      --output-actions actions.jsonl \
      --output-activities activities.jsonl \
      --platform gitlab \
      --custom-action-mapping my_event_to_action.json \
      --custom-activity-mapping my_action_to_activity.json
```

The custom mapping files must follow the same schema as the built‑in ones.

---

## Citation

If you use ghmap or the NumFocus dataset in your research, please cite:

### 📄 Paper

> Y. Hourri, A. Decan and T. Mens, **"A Dataset of Contributor Activities in the NumFocus Open-Source Community,"** 2025 IEEE/ACM 22nd International Conference on Mining Software Repositories (MSR), Ottawa, ON, Canada, 2025, pp. 159-163, doi: 10.1109/MSR66628.2025.00035

```bibtex
@inproceedings{hourri2025dataset,
  author={Hourri, Youness and Decan, Alexandre and Mens, Tom},
  booktitle={2025 IEEE/ACM 22nd International Conference on Mining Software Repositories (MSR)}, 
  title={A Dataset of Contributor Activities in the NumFocus Open-Source Community}, 
  year={2025},
  pages={159-163},
  keywords={Collaboration;Data science;Data mining;Open source software;Software development management;open source;software community;collaborative development;contributor activities;repository mining},
  doi={10.1109/MSR66628.2025.00035}
}
```

### 🛠️ Tool

> **ghmap: GitHub Event Mapping Tool**  
> Youness Hourri

```bibtex
@software{hourri2025ghmap,
  author       = {Hourri, Youness},
  title        = {ghmap: GitHub Event Mapping Tool},
  url          = {https://github.com/uhourri/ghmap},
  note         = {Accessed: 2025-03-21}
}
```

---

## Contributing

Contributions are welcome! If you identify issues or have suggestions for improvement, please submit an issue or pull request.

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).

---

## Credits

**ghmap** is developed by [Youness Hourri](https://github.com/uhourri) at the [Software Engineering Lab](https://informatique-umons.be/genlog/) (SGL), [University of Mons](https://www.umons.ac.be) (UMONS), Belgium.
