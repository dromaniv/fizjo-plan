# AI Agent Guide for Fizjo-Plan

## Purpose

Fizjo-Plan fetches weekly physiotherapy timetables from AWF Poznań, filters events for student groups and optional-subject selections, and publishes ICS calendar feeds. An optional Google Apps Script synchronises a feed into an owned Google Calendar and applies event colours.

This guide describes stable behaviour and maintenance rules. Read the current source before making changes. Do not treat examples here as live configuration.

## Sources of truth

| Information | Read it from |
|---|---|
| AWF endpoint and timetable ID | `AWF_PLAN_URL` in `main.py` |
| Week-number reference | `BASE_DATE` and `BASE_WEEKNUM` in `main.py` |
| Python fetch range | `START_OF_SEMESTER` and `END_OF_SEMESTER` in `main.py` |
| Subject abbreviations and full names | `abbreviations` in `legend.yaml` |
| Which subjects are optional | Global `optional_subjects` in `legend.yaml` |
| Calendar names, groups and selections | `calendars` in `legend.yaml` |
| Python dependencies | `requirements.txt` |
| CI Python version, schedule and deployment steps | `.github/workflows/` |
| Google Calendar feed and destination | `ICS_URL` and `TARGET_CALENDAR_NAME` in the relevant Apps Script project |
| Google Calendar sync range | `SEM_START` and `SEM_END` in the relevant Apps Script project |
| Google Calendar colour overrides | `chooseColor_()` in the relevant Apps Script project |
| Sync write budget and throttling | Constants and guard logic in the relevant Apps Script project |

`Code.gs` is the repository's Apps Script source when present. Deployed Apps Script projects may contain independent copies; do not assume a repository edit updates them automatically.

Do not duplicate current dates, timetable IDs, subject inventories, student selections, line numbers, file lengths or dependency versions in this guide. Use clearly labelled examples only when needed to explain behaviour.

## Architecture

- `main.py`: configuration loading, week calculation, downloads, filtering, ICS generation and output.
- `legend.yaml`: subject mappings and per-calendar selection.
- `docs/`: generated calendar feeds for publication.
- `Code.gs`: optional Google Calendar synchronisation.
- `.github/workflows/`: automation and publication.
- `README.md`: user-facing setup and subscription instructions.

The Python flow is:

1. Load and normalise YAML configuration.
2. Calculate AWF week numbers for the configured range.
3. Download and process each week's ICS for each configured calendar.
4. Merge retained events and add calendar metadata.
5. Write `docs/{calendar_name}.ics` for publication.

The endpoint returns ICS despite its historically named download parameter. Do not parse it as CSV.

## Week numbers and semester ranges

Week numbers are derived from the configured reference Monday and its AWF week number:

```python
week_number = BASE_WEEKNUM + ((date - BASE_DATE).days // 7)
```

Changing semesters normally requires a new date range and possibly a different timetable ID, not a different week-number reference. Change the reference only after verifying that AWF changed its numbering.

The Python generator includes complete weeks covering the configured start and end dates. It does not trim individual events to the exact boundary dates. Distinguish the configured fetch range from officially confirmed academic semester dates.

The optional Apps Script has its own range. Keep the intended ranges aligned when updating both components. JavaScript numeric `Date` constructors use zero-based months; Python's `datetime` uses one-based months.

## Subject matching and group filtering

`_split_summary()` tries known prefixes from longest to shortest. Known abbreviations come from the legend, global optional list and selected optional list. There is no fixed five-word limit in the updated implementation.

Whitespace between tokens is normalised for matching, while token offsets retain the original remainder as the event description. Abbreviation matching is case-sensitive. Unknown summaries retain the existing first-four-words fallback; inspect unexpected abbreviations rather than inventing mappings.

Attached group suffixes are processed separately:

- Recognised suffixes are `pA`, `pB` and `pC`.
- Drop events whose suffix does not match the configured student group.
- Strip the suffix before optional-subject filtering and full-name lookup.

For example, a hypothetical `SubjectpB` maps to `Subject` after Group B filtering.

Named variants such as `SubjectG1`, `Subject Gr 1` or `Subject Gr 1 A` are independent abbreviations. They are not automatically selected by `group: "Grupa A"`. List the required variants explicitly. A base abbreviation and a group-specific abbreviation may represent separate sessions; verify the source before excluding either.

## YAML behaviour

The loader supports `calendars` as either a list of objects containing `name`, or a mapping from calendar names to configuration objects. Preserve both formats.

The global `optional_subjects` list defines which abbreviations are subject to optional filtering. A per-calendar selection alone does not classify a subject as optional. Subjects absent from the global list remain included unless another filter removes them.

| Per-calendar value | Behaviour |
|---|---|
| Omitted, `null`, or an empty YAML value | Include all globally listed optionals |
| `[]` | Exclude all globally listed optionals |
| Explicit list | Include only the listed global optionals |
| Mapping of abbreviations to booleans | Include enabled entries |

Use actual YAML booleans in mapping form, not quoted strings. The implementation tests truthiness.

Illustrative configuration only:

```yaml
abbreviations:
  Core: "Example required subject"
  Elective: "Example optional subject"
  Elective Gr 1: "Example optional subject - group 1"

optional_subjects:
  - Elective
  - Elective Gr 1

calendars:
  - name: "example"
    group: "Grupa B"
    optional_subjects:
      - Elective
      - Elective Gr 1
```

Preserve existing calendar names when updating selections: names determine published filenames and subscription URLs. Do not infer a student's selections or subgroup from another student's configuration. An unset selection includes all optionals; it does not mean none.

## Titles, descriptions, locations and colours

### Python output

- Replace a recognised abbreviation with its full name from the legend.
- Store the remaining original summary text in `DESCRIPTION`.
- Mark events containing `zdalne` as remote.
- Otherwise use `STREET_RE` to extract a street, falling back to `DEFAULT_LOCATION`.
- Read the current regex and fallback from the source; do not maintain a second copy here.

A fallback address is not a verified meeting location. Outdoor sessions or vague source descriptions may need manual interpretation. Preserve room and venue details in the description.

Python applies ordered keyword-based colours in `process_calendar_bytes_for_group_and_optionals()`. Consult that function for the current keywords and precedence. Calendar clients may display feed colours differently.

### Google Calendar output

Apps Script applies its own rules in `chooseColor_()`; it does not simply copy the Python colour property. Subject-specific overrides precede general class-type rules.

The updated title comparison collapses whitespace, trims it and lowercases it. Override strings must match that normalisation. This affects comparison only, not the displayed event title.

When changing colours, identify which layer the user intends to change. Preserve rule precedence, and test an override against a lecture description to ensure it wins over the generic lecture rule.

### Optional emoji titles

A calendar can enable `title_color_emojis` to prefix its processed event titles with color indicators. The default is disabled. Its `title_color_overrides` maps subject abbreviations from the legend to color keys in `TITLE_COLOR_EMOJIS`. These overrides precede the class-type rules, which follow Apps Script's keyword matching. Prefixes are added after filtering; preserve UIDs, times and other event properties. Do not enable this for other calendars unless requested.

## ICS and time handling

- Preserve UTF-8 and Polish characters.
- Use the Python `icalendar` package for serialisation and parsing.
- Preserve UTC timestamps ending in `Z`; do not manually add a local offset.
- Use the configured time zone for local display and metadata.
- Test dates on both sides of a daylight-saving transition when changing time handling.
- Unfold continued ICS lines before matching long titles. The updated Apps Script handles both CRLF and LF continuations.
- Preserve ICS text escaping for commas, semicolons, backslashes and newlines.
- Avoid Markdown escaping or HTML entities when returning executable source.

## Google Calendar sync behaviour and limitations

The entry point is `ColorEvents()`. It resolves an owned destination calendar, fetches the feed once, parses events and processes the configured range in monthly windows. Existing synced events are identified through `ICS-UID` markers in descriptions. Preserve those markers and the existing UID convention when making unrelated edits.

Writes include event creation, property changes, colour updates and deletions. Read the actual guard logic before changing batching or claiming quota safety.

Known behaviours in the current implementation:

- Description metadata includes a per-run sync timestamp, so unchanged events can still incur writes every run.
- `isoDate_()` uses UTC formatting, which can display the preceding date for a local-midnight boundary. This is a log display issue, not evidence of a shifted event.
- Deletion is based on absence from the current monthly feed index. Do not assume cross-month moves are handled globally just because a semester-wide index is passed into the function.
- The parser is tailored to the generated feed. Do not assume full support for arbitrary ICS recurrence, time-zone definitions or all-day event semantics.
- Missing or duplicate source UIDs can affect synchronisation. Inspect the feed if events disappear or overwrite one another.

Do not silently redesign synchronisation during a configuration-only update. If fixing sync behaviour, test repeated runs, moved events and removal of genuinely deleted events with mocks or a dedicated test calendar.

## Error handling and publication

The Python generator continues after individual failed weeks and reports failures separately from successfully parsed weeks with no retained events.

AWF can return HTML even when an ICS download is requested. A parse failure does not prove that the week has no classes. Inspect the response before classifying it as empty.

If no events remain for a calendar, the generator returns `None` and retains any existing output file. If some weeks succeed and others fail, it can publish a partial calendar. Consider that behaviour when diagnosing missing events: a downstream sync that prunes missing UIDs can interpret omissions as deletions.

Keep errors visible. Do not silently convert malformed responses into successful empty calendars. Preserve timeouts and avoid unnecessary repeated requests to AWF.

## Making changes

1. Read the actual files being changed, including workflow configuration when relevant.
2. Keep edits focused on the requested behaviour.
3. Preserve Python type hints, clear function names and useful docstrings.
4. Keep subject mappings and selections in YAML. Follow the existing constants for dates, endpoints and sync settings; avoid scattering duplicate settings.
5. Maintain compatibility with both supported calendar configuration formats.
6. Validate syntax and run focused checks for the changed behaviour.
7. Explain what was tested and distinguish local checks from live execution.
8. Update this guide only when architecture, stable behaviour or maintenance instructions change.

Before publishing generated feeds, inspect the output for missing weeks, unintended group changes and removed events. Do not edit generated calendars as the permanent fix for a source or configuration problem.

## Focused validation

Install dependencies using the repository's documented workflow and supported Python version. Examples of local checks:

```bash
python -m py_compile main.py
python main.py
rg '^SUMMARY' docs/example.ics
```

`example.ics` is illustrative; use a configured filename. Running the generator downloads the configured weeks and writes local output files. A summary search is only a quick inspection, not full ICS validation.

Relevant cases include:

- Longest-prefix matches, repeated whitespace and unknown abbreviations.
- Matching and mismatching attached group suffixes.
- Optional filtering after suffix removal.
- Empty, explicit, omitted/null and boolean-mapping selections.
- Base and named subgroup entries selected independently.
- Remote classes, explicit streets and fallback locations.
- Valid empty calendars versus HTML or malformed responses.
- UTC timestamps and daylight-saving display.
- Apps Script subject overrides, generic colours and folded titles.

For Apps Script, local JavaScript syntax checks and mocked parser/colour checks do not validate Google permissions, live quotas or calendar writes. Verify deployment with the relevant Apps Script project's execution log and calendar output.

## Automation and deployment

Read `.github/workflows/` for the current triggers, runtime, dependencies, permissions and publication mechanism. Do not assume a fixed schedule, workflow filename or Pages deployment method.

Apps Script triggers are separate from GitHub Actions. Updating the repository does not change an existing Apps Script trigger or deployed script automatically. Verify each intended project independently.

See `README.md` for user-facing setup and subscription instructions.
