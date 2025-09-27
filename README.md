# 📅 Fizjo-Plan

**Automated physiotherapy schedule management system for AWF Poznań**

This project automatically fetches, processes, and publishes physiotherapy class schedules from AWF Poznań (University of Physical Education in Poznań) as ICS calendar feeds. It's designed to handle multiple student groups with customizable optional subject selections.

## ✨ Features

- **🔄 Automated Schedule Fetching**: Daily automatic updates via GitHub Actions
- **👥 Multi-Group Support**: Handles different student groups (Grupa A, B, C)
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
├── requirements.txt     # Python dependencies
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
  # ... more subjects
```

### Optional Subjects
Global defaults for optional subjects:
```yaml
optional_subjects:
  GG1: true   # Include by default
  GG2: false  # Exclude by default
  # ... more subjects
```

### Calendar Definitions
Individual calendar configurations:
```yaml
calendars:
  - name: "iwonka"
    group: "Grupa B"
    optional_subjects: ["GG1", "GG2", "ZwtTzG1"]
  - name: "ola"
    group: "Grupa A"
    optional_subjects: ["GG1", "TkuwzigrG1"]
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
   pip install -r requirements.txt
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
3. Commit changes - GitHub Actions will automatically generate the new calendar

## 🔧 Technical Details

### Schedule Processing
- Fetches weekly schedules from AWF Poznań's planning system
- Processes an entire semester (September to February)
- Handles group-specific filtering and optional subject selection
- Normalizes location data and adds proper addresses
- Generates color-coded events for better visual organization

### Automation
- **GitHub Actions**: Runs daily at 3:00 AM UTC to update schedules
- **Error Handling**: Continues processing even if some weeks fail to fetch
- **Smart Commits**: Only commits when actual changes are detected

### Google Apps Script Integration
The included `Code.gs` provides advanced Google Calendar synchronization with:
- Automatic event updates and deletions
- Color coding preservation
- Quota-aware processing to handle API limits

## 📋 Requirements

- Python 3.11+
- Dependencies: `requests`, `pyyaml`, `icalendar`, `pytz`
- GitHub repository with Pages enabled (for hosting)

