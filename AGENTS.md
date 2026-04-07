# AI Agent Guide for Fizjo-Plan

**Last Updated:** April 7, 2026

This document provides AI agents (like GitHub Copilot) with essential context and guidelines for working with the Fizjo-Plan codebase.

## Quick Project Summary

**Fizjo-Plan** is an automated physiotherapy schedule management system for AWF Poznań (University of Physical Education in Poznań, Poland). It fetches weekly class schedules, processes them with intelligent filtering, and generates ICS calendar feeds for students.

### Key Facts
- **Language:** Python 3.11+ with type hints throughout
- **Domain:** Polish university scheduling system
- **Deployment:** GitHub Actions + GitHub Pages
- **Update Frequency:** Daily at 03:00 UTC
- **Main Output:** ICS calendar files in `docs/` directory

## Core Architecture

### Main Components

| Component | Purpose | Lines | Key Technologies |
|-----------|---------|-------|------------------|
| `main.py` | Schedule fetching, processing, ICS generation | 381 | requests, icalendar, PyYAML |
| `legend.yaml` | Configuration: subjects, abbreviations, calendars | N/A | YAML |
| `Code.gs` | Google Calendar sync (optional) | 572 | Google Apps Script |
| `.github/workflows/main.yml` | Automation workflow | N/A | GitHub Actions |

### Data Flow

```
AWF API → fetch_awf_calendar_week() → process_calendar_bytes_for_group_and_optionals() 
  → get_full_semester_calendar_bytes() → docs/{name}.ics → GitHub Pages
```

## Critical Domain Knowledge

### AWF Schedule System

**Week Number Calculation:**
- Base Date: February 17, 2025 (Monday) = week 657
- Formula: `week_number = 657 + ((date - base_date).days // 7)`
- API URL: `http://web0.awf.poznan.pl/plan/plan.php?type=0&id=104148&cvsfile=true&w={week}`

**Student Groups:**
- Grupa A, Grupa B, Grupa C
- Events may have suffixes: `pA`, `pB`, `pC` (e.g., "KkpA" = Kk for Grupa A)

### Multi-Word Abbreviation Matching

**Algorithm (lines 147-168 in main.py):**
```python
# Progressive prefix matching: tries 5 words → 4 → 3 → 2 → 1
for num_words in range(min(len(tokens), 5), 0, -1):
    candidate = " ".join(tokens[:num_words])
    if candidate in legend:
        # Match found
        abbreviation = candidate
        remainder = s_text[len(candidate):].strip()
        break
```

**Examples:**
- Single-word: `Df`, `Kk`, `Mwf`
- Multi-word: `Boc Gr 1`, `Psozn Gr 1`, `Pswiwpm Gr 1`

### Optional Subjects Logic

**Three Configuration Modes:**

1. **Empty list** `[]` → Exclude all optional subjects
2. **Specific list** `["Boc Gr 1", "JG1"]` → Include only these
3. **Omitted/None** → Include all from global `optional_subjects` list

### Color Coding

| Type | Keywords | Color |
|------|----------|-------|
| Lectures | `wyk` | gray |
| Exercises | `ćw` | green |
| Clinical | `klin` | yellow |
| Physical Activities | `gry`, `gim`, `pł`, `la`, `reh` | orange |
| Other | (default) | purple |

### Location Processing

**Rules:**
1. **Remote:** Contains "zdalne" → Location: "Zdalnie"
2. **Physical:** Extract via regex `ul.\s?[\w\s...]+` → "ul. {street}, Poznań, Polska"
3. **Default:** "ul. Królowej Jadwigi 27/39, Poznań, Polska"

## Code Style & Conventions

### Python

```python
# Type hints are REQUIRED for all functions
def function_name(
    param1: Type1,
    param2: Dict[str, str],
    optional_param: Optional[Type3] = None,
) -> ReturnType:
    """
    Docstrings: brief description + list of key operations
    """
    pass

# Constants in UPPER_CASE
BASE_DATE = datetime(2025, 2, 17)
AWF_PLAN_URL = "http://..."

# snake_case for functions
# Private helpers with leading underscore
```

### YAML Configuration

```yaml
# Subject abbreviations (single or multi-word)
abbreviations:
  SingleWord: "Full Subject Name"
  Multi Word 1: "Full Multi-Word Subject Name"

# Global optional subjects list
optional_subjects:
  - SubjectAbbr1
  - SubjectAbbr2

# Individual calendar configurations
calendars:
  - name: "filename"       # Output: {name}.ics
    group: "Grupa X"       # Student group
    optional_subjects:     # List, empty, or omitted
      - SubjectAbbr1
```

## Common Modification Patterns

### Adding a Subject Abbreviation

**File:** `legend.yaml`
```yaml
abbreviations:
  NewAbbr: "Pełna nazwa przedmiotu po polsku"
  New Multi Word: "Full Multi-Word Subject Name"
```

### Adding a Calendar

**File:** `legend.yaml`
```yaml
calendars:
  - name: "newstudent"
    group: "Grupa B"
    optional_subjects: ["SubjectAbbr1", "SubjectAbbr2"]
```

### Extending Color Coding

**File:** `main.py`, function `process_calendar_bytes_for_group_and_optionals()`
```python
# Around line 189-198
if "new_keyword" in lower:
    component.add("color", "purple")
```

### Changing Semester Dates

**File:** `main.py`, function `get_full_semester_calendar_bytes()` (line 238-239)
```python
start_of_semester: datetime = datetime(2026, 9, 1),  # September 1
end_of_semester: datetime = datetime(2027, 2, 28),   # February 28
```

## Error Handling Philosophy

**Graceful Degradation:**
- Continue processing even if individual weeks fail
- Log failures clearly for debugging
- Track empty weeks and report at end
- Return `None` only when entire semester has no data

**Example:**
```python
try:
    raw_bytes = fetch_awf_calendar_week(week)
    # ... process ...
except Exception as e:
    print(f"     ! Couldn't fetch week: {e}")
    empty_weeks.append(week)
    # Continue to next week
```

## Testing Guidelines

### Manual Testing

```bash
# Run locally
python main.py

# Verify output
ls -la docs/*.ics

# Inspect specific calendar
cat docs/iwonka.ics | grep SUMMARY
```

### Key Test Scenarios

1. ✅ **Multi-word abbreviations** - Verify "Boc Gr 1" matches correctly
2. ✅ **Group filtering** - Events with wrong suffix (`pA`/`pB`/`pC`) are excluded
3. ✅ **Optional subjects** - Test empty list, specific list, omitted config
4. ✅ **Remote detection** - "zdalne" triggers remote location
5. ✅ **Location extraction** - Street regex works for Polish addresses
6. ✅ **Empty weeks** - Graceful handling when no data
7. ✅ **Color coding** - All type keywords produce correct colors

## Polish Language Context

### Common Terms

| Polish | English | Context |
|--------|---------|---------|
| wyk / wykład | lecture | Type of class |
| ćw / ćwiczenia | exercise/practice | Type of class |
| klin / klinika | clinical | Type of class |
| gry | games | Physical activity |
| zdalne | remote | Location type |
| ul. | street | Address abbreviation |
| grupa | group | Student group |

### Character Encoding

Always use UTF-8. Polish special characters: **ą, ć, ę, ł, ń, ó, ś, ź, ż**

Example: "Dydaktyka fizjoterapii", "ćwiczenia", "Królowej Jadwigi"

## GitHub Actions Workflow

### Trigger
- **Scheduled:** Daily at 03:00 UTC (`cron: "0 3 * * *"`)
- **Manual:** Via `workflow_dispatch`

### Steps
1. Checkout repository
2. Set up Python 3.11
3. Install dependencies from `requirements.txt`
4. Run `python main.py`
5. Commit generated `.ics` files to `docs/`
6. Push (triggers GitHub Pages rebuild)

### Permissions
- `contents: write` - Required for committing generated files

## Common Issues & Solutions

### Issue: Abbreviation Not Matching

**Symptoms:** Subject appears as abbreviation instead of full name

**Causes:**
- Multi-word abbreviation missing from `legend.yaml`
- Spelling mismatch (including spaces)

**Solution:** Verify exact spelling in `legend.yaml`, including spaces and case

### Issue: Events Not Filtered by Group

**Symptoms:** Student sees events for other groups

**Causes:**
- Group suffix logic not recognizing format
- Wrong group specified in calendar config

**Solution:** Check for `pA`/`pB`/`pC` suffix directly attached to abbreviation (no spaces)

### Issue: Wrong Location Assigned

**Symptoms:** Remote classes show physical address or vice versa

**Causes:**
- "zdalne" keyword misspelled or missing
- Regex not matching Polish street format

**Solution:**
- Verify "zdalne" appears in summary or description
- Check regex pattern: `ul.\s?[\w\sĄĆĘŁŃÓŚŹŻąćęłńóśźż\-]+`

### Issue: Empty Calendar Generated

**Symptoms:** Calendar file exists but has no events

**Causes:**
- All events filtered out (wrong optional_subjects)
- AWF API not responding for all weeks
- Wrong semester dates

**Solution:**
- Verify `optional_subjects` config
- Test AWF API accessibility
- Check semester date range

### Issue: GitHub Actions Fails

**Symptoms:** Workflow fails to complete

**Causes:**
- Dependency version mismatch
- Python version incompatibility
- AWF API unreachable

**Solution:**
- Pin versions in `requirements.txt`
- Use Python 3.11 exactly
- Add retry logic for API calls

## Best Practices for AI Agents

### When Making Changes

1. ✅ **Read before edit** - Always read the file first with `read_file`
2. ✅ **Validate after edit** - Call `get_errors` on modified files
3. ✅ **Test locally** - Suggest running `python main.py` after changes
4. ✅ **Maintain backward compatibility** - Don't break existing `legend.yaml` configs
5. ✅ **Preserve type hints** - All function parameters and returns must be typed
6. ✅ **Document changes** - Update docstrings for modified functions

### Code Organization Principles

- **Configuration in YAML** - Never hardcode subjects or settings
- **Constants for magic values** - No magic strings or numbers
- **Group related functions** - Keep date helpers, calendar processing separate
- **Comment complex logic** - Especially regex and algorithms

### Performance Considerations

- **HTTP timeouts** - Use 30s timeout for AWF API calls
- **Batch operations** - Process week-by-week, not day-by-day
- **Error limits** - Stop after reasonable number of failures
- **Sleep between requests** - Respect rate limits (if any)

## Project Status (April 2026)

- **Current Semester:** Spring 2026 (March 11 - July 10, 2026)
- **Active Calendars:** grupaA, grupaB, grupaC, iwonka, ola, gracjana
- **Hosting:** https://dromaniv.github.io/fizjo-plan/
- **Last Major Update:** February 2026 (updated semester dates)

## Future Enhancement Opportunities

1. **Web UI** - Streamlit interface for calendar configuration
2. **Multi-semester** - Support concurrent semesters
3. **Notifications** - Alert on schedule changes
4. **Conflict detection** - Warn about overlapping classes
5. **Statistics** - Track hours by subject type, location
6. **Mobile app** - Native calendar integration
7. **API endpoint** - Serve JSON for custom integrations

## Quick Reference Links

- **AWF Schedule System:** http://web0.awf.poznan.pl/plan/
- **ICS Format Spec:** RFC 5545
- **GitHub Pages:** https://dromaniv.github.io/fizjo-plan/
- **Repository:** https://github.com/dromaniv/fizjo-plan

---

**For User Documentation:** See `README.md`

