# GitHub Copilot Instructions for Fizjo-Plan

## Project Overview

**Fizjo-Plan** is an automated physiotherapy schedule management system for AWF Poznań (University of Physical Education in Poznań, Poland). The system fetches weekly class schedules from the university's planning system, processes them with group-specific filtering and optional subject selection, and generates ICS calendar feeds for students.

### Core Purpose
- Fetch weekly schedules from AWF Poznań's web planning system
- Process and filter events based on student groups and optional subject selections
- Generate standardized ICS calendar files for easy subscription
- Automate daily updates via GitHub Actions
- Publish calendars via GitHub Pages

## Architecture & Tech Stack

### Main Components
1. **main.py** - Core Python application (381 lines)
   - Schedule fetching and processing
   - ICS generation and transformation
   - Multi-calendar support with group-specific filtering

2. **legend.yaml** - Configuration file
   - Subject abbreviation mappings
   - Optional subject definitions
   - Calendar configurations

3. **Code.gs** - Google Apps Script (572 lines)
   - Advanced Google Calendar synchronization
   - Event upsert/delete by UID
   - Color coding preservation
   - Quota-aware API processing

4. **GitHub Actions** (.github/workflows/main.yml)
   - Scheduled daily execution at 03:00 UTC
   - Automated calendar generation and publishing

### Dependencies
- **Python 3.11+**
- **requests** (2.32.5) - HTTP requests to fetch schedules
- **PyYAML** (6.0.2) - YAML configuration parsing
- **icalendar** (6.3.1) - ICS file generation and parsing
- **pytz** - Timezone handling (Europe/Warsaw)
- **streamlit** (1.49.1) - Optional UI component

## Key Concepts & Domain Knowledge

### AWF Schedule System
- **Base Date**: February 17, 2025 (Monday) = week 657
- **Week Number Calculation**: Linear progression from base date
- **Semester Range**: Typically September to February (configurable)
- **API URL Pattern**: `http://web0.awf.poznan.pl/plan/plan.php?type=0&id=104148&cvsfile=true&w={week}`

### Student Groups
Three main groups with different schedules:
- **Grupa A** (Group A)
- **Grupa B** (Group B)
- **Grupa C** (Group C)

Events may have group suffixes: `pA`, `pB`, `pC` (e.g., "KkpA", "DfpB")

### Subject Types & Color Coding
- **wykład** (wyk) - Lectures → Gray
- **ćwiczenia** (ćw) - Exercises → Red
- **klinika** (klin) - Clinical classes → Blue
- **gry** - Games → Green
- **Other** - Dark Red

### Multi-Word Abbreviations
The system supports both single-word and space-separated multi-word abbreviations:
- Single-word: `Df`, `Kk`, `Mwf`
- Multi-word: `Boc Gr 1`, `Psozn Gr 1`, `Pswiwpm Gr 1`, `TwHiW Gr 1`

Abbreviation matching uses a progressive prefix-matching algorithm (tries up to 5 words, longest first).

### Optional Subjects
Students can select specific optional subjects. The system supports:
1. **Empty list** (`[]`) - Exclude all optional subjects
2. **Specific list** (`["Boc Gr 1", "JG1"]`) - Include only these
3. **Omitted** - Include all optional subjects from global list

### Location Handling
- **Remote Classes**: Detected by "zdalne" keyword → Location: "Zdalnie"
- **Physical Classes**: Extracted via regex pattern `ul.\s?[\w\s...]+`
- **Default**: "ul. Królowej Jadwigi 27/39, Poznań, Polska"

## Code Patterns & Conventions

### Python Code Style
```python
# Type hints are used throughout
def function_name(
    param1: Type1,
    param2: Dict[str, str],
    optional_param: Optional[Type3] = None,
) -> ReturnType:
    """
    Docstrings follow this format:
      - Brief description
      - List of key operations
    """
    pass

# Constants in UPPER_CASE
BASE_DATE = datetime(2025, 2, 17)
AWF_PLAN_URL = "http://..."

# Functions use snake_case with trailing underscore for private helpers
def get_week_number(date: datetime) -> int:
    pass

def _private_helper():
    pass
```

### YAML Configuration Structure
```yaml
abbreviations:
  SingleWord: "Full Subject Name"
  Multi Word 1: "Full Multi-Word Subject Name"

optional_subjects:
  - SubjectAbbr1
  - SubjectAbbr2

calendars:
  - name: "filename"       # Used for output: {name}.ics
    group: "Grupa X"       # Student group
    optional_subjects:     # List, dict, or empty
```

### ICS Event Processing
Events are processed with this pipeline:
1. **Parse** summary text to extract abbreviation and remainder
2. **Filter** optional subjects based on calendar config
3. **Filter** by group suffix (pA/pB/pC)
4. **Transform** abbreviation to full name using legend
5. **Add** color hints based on type keywords
6. **Normalize** location (extract street or set remote)
7. **Set** description to remainder text

## Important Implementation Details

### Abbreviation Parsing Algorithm
```python
# Progressive prefix matching (main.py lines ~147-168)
# Tries 5 words down to 1 word, matching against legend
for num_words in range(min(len(tokens), 5), 0, -1):
    candidate = " ".join(tokens[:num_words])
    if candidate in legend:
        abbreviation = candidate
        remainder = s_text[len(candidate):].strip()
        break
    # Also checks for group suffixes (pA/pB/pC)
```

### Week Number Calculation
```python
# Linear calculation from BASE_DATE (main.py lines ~54-61)
def get_week_number(current_date: Optional[datetime] = None) -> int:
    if current_date is None:
        current_date = datetime.now()
    week_diff = (current_date - BASE_DATE).days // 7
    return BASE_WEEKNUM + week_diff
```

### Error Handling Philosophy
- **Fail gracefully**: Continue processing even if individual weeks fail
- **Log failures**: Print clear error messages for debugging
- **Empty weeks**: Track and report weeks with no data
- **Return None**: When no events found for entire semester

### Google Apps Script Sync Strategy
- **Quota-aware**: Limits writes (400 per run), sleeps between batches
- **Month-by-month**: Processes current month first, then forward, then backward
- **UID-based**: Uses ICS UID for deduplication and updates
- **Error tolerance**: Stops after 12 errors to prevent runaway failures

## Common Tasks & Code Examples

### Adding a New Subject Abbreviation
```yaml
# In legend.yaml
abbreviations:
  NewAbbr: "Full Subject Name in Polish"
  New Multi Word: "Full Multi-Word Subject Name"
```

### Adding a New Calendar
```yaml
# In legend.yaml
calendars:
  - name: "newcalendar"
    group: "Grupa A"
    optional_subjects: ["SubjectAbbr1", "SubjectAbbr2"]
```

### Extending Color Coding
```python
# In process_calendar_bytes_for_group_and_optionals()
if "new_keyword" in lower:
    component.add("color", "purple")
```

### Modifying Semester Dates
```python
# In get_full_semester_calendar_bytes() function signature
start_of_semester: datetime = datetime(2026, 9, 1),  # September 1
end_of_semester: datetime = datetime(2027, 2, 28),   # February 28
```

### Testing Abbreviation Matching
```python
# Quick test pattern used in development
test_cases = [
    ('Boc Gr 1 wyk ul. Test', 'Boc Gr 1', 'wyk ul. Test'),
    ('Df ćw zdalnie', 'Df', 'ćw zdalnie'),
]
# Run matching logic and verify output
```

## Polish Language Context

### Common Terms
- **wyk** / **wykład** - Lecture
- **ćw** / **ćwiczenia** - Exercise/Practice
- **klin** / **klinika** - Clinical
- **gry** - Games
- **zdalne** - Remote
- **ul.** - Street (abbreviation for "ulica")
- **grupa** - Group

### Subject Name Patterns
- Often use abbreviations formed from first letters
- May include parenthetical expansions in legend
- Multi-word subjects typically include "Gr" (group) with number

## Testing Considerations

### Manual Testing
```bash
# Run locally
python main.py

# Check generated files
ls -la docs/*.ics

# Verify specific calendar
cat docs/iwonka.ics | grep SUMMARY
```

### Key Test Scenarios
1. **Multi-word abbreviations** - Verify "Boc Gr 1" matches correctly
2. **Group filtering** - Ensure events with wrong group suffix are excluded
3. **Optional subjects** - Test empty list, specific list, and omitted config
4. **Remote detection** - Check "zdalne" keyword triggers remote location
5. **Location extraction** - Verify street address regex works
6. **Empty weeks** - Confirm graceful handling of missing data
7. **Color coding** - Validate all type keywords produce correct colors

## GitHub Actions Workflow

### Trigger Conditions
- **Scheduled**: Daily at 03:00 UTC (`cron: "0 3 * * *"`)
- **Manual**: Via workflow_dispatch

### Deployment Process
1. Checkout repository
2. Set up Python 3.11
3. Install dependencies
4. Run main.py
5. Commit generated .ics files to docs/
6. Push to trigger GitHub Pages rebuild

### Permissions
- `contents: write` - Required to commit generated calendars

## Best Practices & Guidelines

### When Adding Features
1. **Maintain backward compatibility** with existing legend.yaml configurations
2. **Add type hints** for all function parameters and return values
3. **Document behavior** in docstrings, especially for public functions
4. **Test with real data** from legend.yaml before committing
5. **Consider Polish language** patterns and characters (ą, ć, ę, ł, ń, ó, ś, ź, ż)
6. **Handle errors gracefully** - don't fail entire run for one bad week

### Code Organization
- Keep configuration in legend.yaml, not hardcoded
- Use constants for magic numbers and strings
- Group related functions (YAML loading, date helpers, calendar processing)
- Comment complex regex patterns and algorithms

### Performance Considerations
- **Google Apps Script**: Respect quota limits (400 writes per run)
- **HTTP requests**: Use timeout (30s) and proper headers
- **Calendar processing**: Process month-by-month for large date ranges
- **Batch operations**: Sleep between write batches to avoid rate limits

### Security & Privacy
- No sensitive data in configuration files
- Public GitHub repository - all calendars are public
- Use HTTPS for external API calls
- GitHub Actions uses built-in GITHUB_TOKEN (no custom secrets needed)

## Common Pitfalls & Solutions

### Issue: Abbreviation Not Matching
**Cause**: Multi-word abbreviation not in legend, or wrong spelling
**Solution**: Verify exact spelling in legend.yaml, including spaces

### Issue: Events Not Filtered by Group
**Cause**: Group suffix logic not recognizing format
**Solution**: Check for `pA`/`pB`/`pC` suffix directly attached to abbreviation

### Issue: Wrong Location Assigned
**Cause**: Regex not matching street format, or "zdalne" misspelled
**Solution**: Verify regex pattern matches Polish street format `ul. <name>`

### Issue: Empty Calendar Generated
**Cause**: All events filtered out, or fetch failed for all weeks
**Solution**: Check optional_subjects config and verify AWF API accessibility

### Issue: GitHub Actions Fails
**Cause**: Dependency version mismatch, or Python version incompatibility
**Solution**: Pin versions in requirements.txt, use Python 3.11

## Related Documentation

- **AWF Poznań Schedule System**: http://web0.awf.poznan.pl/plan/
- **ICS Format Spec**: RFC 5545
- **Google Calendar API**: For Code.gs integration
- **GitHub Pages**: For hosting generated calendars

## Current State (February 2026)

- **Active semester**: Spring 2026 (dates configured in code)
- **Active calendars**: grupaA, grupaB, grupaC, iwonka, ola, gracjana
- **Schedule source**: AWF Poznań physiotherapy program
- **Update frequency**: Daily at 03:00 UTC via GitHub Actions
- **Hosting**: GitHub Pages at https://dromaniv.github.io/fizjo-plan/

## Future Enhancement Opportunities

1. **Web UI**: Add Streamlit interface for easier calendar configuration
2. **Multi-semester**: Support multiple concurrent semesters
3. **Notification system**: Alert on schedule changes
4. **Conflict detection**: Warn about overlapping classes
5. **Statistics**: Track class hours, types, locations
6. **Mobile app**: Native calendar integration
7. **API endpoint**: Serve JSON for custom integrations

---

When working on this project, always consider the Polish language context, respect the existing configuration structure in legend.yaml, and maintain compatibility with both the Python script and Google Apps Script components. The system is designed to be maintainable by students with basic Python knowledge, so keep code clear and well-documented.

