# 📅 Fizjo-Plan

**Automated physiotherapy schedule management system for AWF Poznań**

This project automatically fetches, processes, and publishes physiotherapy class schedules from AWF Poznań (University of Physical Education in Poznań) as ICS calendar feeds. It's designed to handle multiple student groups with customizable optional subject selections.

Group and named calendars are intentionally public and free to access. Named calendars expose the optional-subject selections in `legend.yaml`, even when their links are omitted from the index.

## ✨ Features

- **🔄 Automated Schedule Fetching**: Daily automatic updates via GitHub Actions
- **👥 Multi-Group Support**: Selects a subgroup for each subject
- **🎯 Optional Subject Filtering**: Customizable selection of optional subjects per calendar
- **📱 ICS Calendar Feeds**: Generates standard calendar files compatible with Google Calendar, Apple Calendar, etc.
- **🎨 Color Coding**: Automatically color-codes different types of classes:
  - Gray: Lectures (wykłady)
  - Red: Exercises (ćwiczenia)
  - Blue: Clinical classes (klinika)
  - Dark Red: Other activities
- **📍 Location Processing**: Extracts and formats venue addresses
- **🌐 Web Publishing**: Hosts calendars on GitHub Pages for easy subscription

## 🏗️ Project Structure

```
fizjo-plan/
├── main.py              # Main schedule processing script
├── legend.yaml          # Configuration file with subjects and calendars
├── requirements.in      # Direct Python dependencies
├── requirements.txt     # Complete dependency lock with hashes
├── Code.gs             # Google Apps Script for advanced calendar sync
├── docs/               # Generated calendars and GitHub Pages content
│   ├── index.md        # Web interface for calendar subscriptions
│   └── *.ics          # Generated calendar files
└── .github/workflows/
    └── main.yml        # GitHub Actions workflow for automation
```

## ⚙️ Configuration

The project is configured through `legend.yaml`:

### Subject Abbreviations
Maps short codes to full subject names:
```yaml
abbreviations:
  Df: "Dydaktyka fizjoterapii"
  Fipz: "Fizjoprofilaktyka i promocja zdrowia"
  Kk: "Komunikacja kliniczna"
  # ... more subjects
```

### Optional Subjects
Define which subjects are optional (available for selection per calendar):
```yaml
optional_subjects:
  - GG1
  - GG2
  - JG1
  - ZwtTzG1
  - ZwtTzG2
  - Tsonww
  - TkuwzigrG1
  - Gs
  - Pnozn
```

**How it works:**
- Optional subjects listed here can be selectively included/excluded per calendar
- If a calendar doesn't specify `optional_subjects`, all optional subjects are included by default
- If a calendar specifies a list of optional subjects, only those will be included

### Calendar Definitions
Individual calendar configurations:
```yaml
calendars:
  - name: "awf"
    subject_groups:
      Wm: A
      Pfwcw: A
    optional_subjects:  # Empty = include all optional subjects

  - name: "iwonka"
    subject_groups:
      Wm: B
      Pfwcw: B
    optional_subjects: ["GG1", "GG2", "ZwtTzG1", "ZwtTzG2", "TkuwzigrG1"]

  - name: "ola"
    subject_groups:
      Wm: B
      Pfwcw: null  # Awaiting confirmation
    optional_subjects: ["JG1", "TkuwzigrG1", "ZwtTzG1", "ZwtTzG2"]
```

`subject_groups` selects A or B separately for each subject. A null or omitted entry leaves its split sessions out until the assignment is confirmed. Shared sessions remain included.

### Remote Classes
Classes are automatically detected as remote when the summary or description contains the word "zdalne" (remote in Polish). These classes will have their location set to "Zdalnie" instead of a physical address.

Example:
```
SUMMARY: Kk wyk GBrę zajęcia zdalne
→ Location: Zdalnie
```

## 🚀 Usage

### Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dromaniv/fizjo-plan.git
   cd fizjo-plan
   ```

2. **Install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --require-hashes --only-binary=:all: -r requirements.txt
   ```

3. **Run the generator:**
   ```bash
   python main.py
   ```

4. **Find generated calendars in the `docs/` folder**

### Calendar Subscription

Visit the [live site](https://dromaniv.github.io/fizjo-plan/) to subscribe to available calendars:

1. Copy the `.ics` URL for your desired calendar
2. Add to your calendar app:
   - **Google Calendar**: Settings → Add calendar → From URL
   - **Apple Calendar**: File → New Calendar Subscription
   - **Outlook**: Add calendar → Subscribe from web

### Adding New Calendars

1. Edit `legend.yaml` to add a new calendar entry
2. Specify the student group and optional subjects
3. Commit changes. The daily GitHub Actions run generates the new calendar; use the manual workflow trigger to run it sooner.

### Testing and dependency updates

Run the local checks with the locked dependencies installed and Node.js 20 or newer:

```bash
python -m py_compile main.py
python -m unittest discover -s tests -v
node --test tests/test_sync.cjs
```

The Apps Script tests use mocks and do not write to Google Calendar. Pull requests run these checks and a dependency audit with read-only repository permissions. Dependabot checks Python dependencies and GitHub Actions weekly.

To update dependencies, edit `requirements.in` and regenerate the complete lock in a separate tooling environment using Python 3.11 and `pip-tools==7.6.2`:

```bash
pip-compile --upgrade --generate-hashes --allow-unsafe --no-emit-index-url --no-emit-trusted-host --pip-args='--only-binary=:all:' --output-file requirements.txt requirements.in
```

Install the regenerated lock in a fresh environment, run the tests, and audit it with `pip-audit --disable-pip --no-deps -r requirements.txt` before merging.

### Feed integrity and deletion safeguards

AWF's published timetable endpoint currently uses HTTP, and its HTTPS listener did not work when checked on 12 November 2026. The generator bounds response sizes, rejects redirects and malformed calendars, and removes source alarms, attachments, attendees and other properties outside the schedule fields. These checks cannot authenticate HTTP content. Use a verified AWF HTTPS endpoint if one becomes available; do not disable certificate verification or introduce an untrusted proxy.

The generator fetches AWF's full-year ICS export once and filters it to the complete weeks covering the configured range. This avoids weekly HTML responses that ambiguously mean no classes or no permission. If the snapshot download or validation fails, generation exits with an error before replacing any feeds. If the whole calendar is empty after filtering, the existing feed is retained.

Generation also stops when more than 25% of an existing feed's UIDs disappear. Inspect the source and configuration first. For an intentional bulk change, generate locally with `python main.py --allow-large-removals` and submit the reviewed feed changes through a PR. This option does not bypass download or format validation.

The Apps Script rejects malformed, empty and duplicate-UID feeds before writing. It disables deletions when more than 25% of existing synced UIDs are missing and checks UIDs across the semester so moves between months do not cause deletion or duplication. A large intentional removal needs a separate manual calendar cleanup after checking the source. Use a dedicated owned calendar for this sync.

## 🔧 Technical Details

### Schedule Processing
- Fetches weekly schedules from AWF Poznań's planning system
- Processes an entire semester (September to February)
- Handles group-specific filtering and optional subject selection
- Normalizes location data and adds proper addresses
- Generates color-coded events for better visual organization

### Automation
- The update schedule and manual trigger are defined in `.github/workflows/main.yml`.
- Generation runs with read-only repository permissions and hash-verified dependencies. Failed generation blocks publication.
- A separate publication job copies only `.ics` data and commits it. That job has repository write access and does not install project dependencies or execute feed contents.

### Google Apps Script Integration
The included `Code.gs` provides advanced Google Calendar synchronization with:
- Automatic event updates and deletions
- Color coding preservation
- Quota-aware processing to handle API limits

Repository changes do not update deployed Apps Script copies. After merging a sync change, copy the updated `Code.gs` into each intended Apps Script project and verify it in a dedicated test calendar before enabling its trigger.

## 📋 Requirements

- Python 3.11+
- Dependencies: `requests`, `pyyaml`, `icalendar`, `pytz`
- GitHub repository with Pages enabled (for hosting)
