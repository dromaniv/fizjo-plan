#!/usr/bin/env python3
# coding: utf-8

from datetime import datetime, timedelta
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pytz
import requests
import yaml
from icalendar import Calendar


# ---------- CONFIGURATION ----------
LEGEND_FILE = "legend.yaml"
BASE_DATE = datetime(2025, 2, 17)  # Monday, AWF week 657
BASE_WEEKNUM = 657
AWF_PLAN_URL = (
    "http://web0.awf.poznan.pl/plan/plan.php?type=0&id=112976&cvsfile=true&w={week}"
)
# Broad autumn/winter fetch range; adjust to confirmed semester boundaries.
START_OF_SEMESTER = datetime(2026, 9, 1)
END_OF_SEMESTER = datetime(2027, 2, 28)
TIMEZONE = "Europe/Warsaw"
HTTP_TIMEOUT = 30
DEFAULT_LOCATION = "ul. Królowej Jadwigi 27/39, Poznań, Polska"
STREET_RE = re.compile(r"ul\.\s?[^,;\n\r]+", re.UNICODE)
GROUP_SUFFIX_RE = re.compile(r"p([ABC])$")
TITLE_COLOR_EMOJIS = {
    "gray": "⚪",
    "pale_green": "🟢",
    "green": "🟩",
    "yellow": "🟡",
    "orange": "🟠",
    "purple": "🟣",
}
OptionalConfig = Optional[Union[Sequence[str], Dict[str, bool]]]


# ---------- YAML LOADING ----------
def load_yaml(
    path: str = LEGEND_FILE,
) -> Tuple[Dict[str, str], List[str], List[Dict[str, Any]]]:
    """Load abbreviations, global optionals, and list/dict calendar configs."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    legend: Dict[str, str] = data.get("abbreviations", {}) or {}
    optional_subjects: List[str] = data.get("optional_subjects", []) or []
    calendars_raw = data.get("calendars", [])
    calendars: List[Dict[str, Any]] = []
    if isinstance(calendars_raw, dict):
        for name, cfg in calendars_raw.items():
            if isinstance(cfg, dict):
                calendars.append({"name": name, **cfg})
    elif isinstance(calendars_raw, list):
        calendars = [
            c for c in calendars_raw if isinstance(c, dict) and "name" in c
        ]
    return legend, optional_subjects, calendars


# ---------- WEEK & DATE HELPERS ----------
def get_week_number(current_date: Optional[datetime] = None) -> int:
    """Compute the AWF week number from its fixed Monday reference date."""
    if current_date is None:
        current_date = datetime.now(pytz.timezone(TIMEZONE))
    day = datetime(current_date.year, current_date.month, current_date.day)
    return BASE_WEEKNUM + (day - BASE_DATE).days // 7


def get_date_from_week_number(week_number: int) -> str:
    """Return the Monday–Sunday date range for an AWF week."""
    start = BASE_DATE + timedelta(weeks=week_number - BASE_WEEKNUM)
    end = start + timedelta(days=6)
    return f"{start:%d.%m} - {end:%d.%m.%Y}"


# ---------- CALENDAR FETCH & PROCESS ----------
def resolve_optional_selection_for_calendar(
    global_optional_subjects: List[str],
    calendar_optional_cfg: OptionalConfig = None,
) -> Tuple[str, ...]:
    """Resolve selection: empty list excludes all; null/omitted includes all."""
    if isinstance(calendar_optional_cfg, dict):
        return tuple(sorted(abbr for abbr, on in calendar_optional_cfg.items() if on))
    if isinstance(calendar_optional_cfg, (list, tuple)):
        return tuple(sorted(set(str(x) for x in calendar_optional_cfg)))
    return tuple(sorted(set(global_optional_subjects)))


def fetch_awf_calendar_week(week_number: int) -> bytes:
    """Download one AWF calendar week with an HTTP timeout."""
    response = requests.get(
        AWF_PLAN_URL.format(week=week_number),
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": "AWF-Plan-Downloader/1.0"},
    )
    response.raise_for_status()
    return response.content


def _split_summary(
    summary: str, known_abbreviations: Sequence[str],
) -> Tuple[str, str]:
    """Match the longest known prefix, allowing attached pA/pB/pC markers.

    Token offsets preserve the original description even with repeated spaces.
    Unknown subjects retain the previous first-four-words fallback.
    """
    tokens = list(re.finditer(r"\S+", summary))
    known = set(known_abbreviations)
    for count in range(len(tokens), 0, -1):
        candidate = " ".join(token.group() for token in tokens[:count])
        base = GROUP_SUFFIX_RE.sub("", candidate)
        if candidate in known or base in known:
            return candidate, summary[tokens[count - 1].end():].strip()
    if len(tokens) <= 4:
        return summary.strip(), ""
    end = tokens[3].end()
    return " ".join(token.group() for token in tokens[:4]), summary[end:].strip()


def process_calendar_bytes_for_group_and_optionals(
    calendar_bytes: bytes,
    legend: Dict[str, str],
    group: str,
    optional_subjects_list: List[str],
    optional_selected: Tuple[str, ...],
) -> bytes:
    """Filter group/optionals, expand titles, and set color/location/description.

    Attached pA/pB/pC markers are removed BEFORE optional filtering.
    Named variants such as 'Umwzf Gr 1 A' remain exact-match selections.
    """
    cal = Calendar.from_ical(calendar_bytes)
    optional_set = set(optional_subjects_list)
    selected_set = set(optional_selected)
    known = tuple(set(legend) | optional_set | selected_set)

    for component in list(cal.walk("vevent")):
        summary = component.get("summary")
        if not summary:
            continue
        s_text = str(summary)
        lower = s_text.lower()
        abbreviation, remainder = _split_summary(s_text, known)

        suffix = GROUP_SUFFIX_RE.search(abbreviation)
        if suffix:
            if suffix.group(1) != group[-1:]:
                cal.subcomponents.remove(component)
                continue
            abbreviation = abbreviation[:-2]

        if abbreviation in optional_set and abbreviation not in selected_set:
            cal.subcomponents.remove(component)
            continue

        if "wyk" in lower:
            color = "gray"
        elif "ćw" in lower:
            color = "green"
        elif "klin" in lower:
            color = "yellow"
        elif any(x in lower for x in ("gry", "gim", "pł", "la", "reh")):
            color = "orange"
        else:
            color = "purple"
        component["color"] = color
        component["summary"] = legend.get(abbreviation, abbreviation)
        component["description"] = remainder

        if "zdalne" in lower:
            component["location"] = "Zdalnie"
        else:
            street = STREET_RE.search(remainder)
            component["location"] = (
                f"ul. {street.group()[3:].strip()}, Poznań, Polska"
                if street else DEFAULT_LOCATION
            )
    return cal.to_ical()


def _add_title_color_emojis(
    calendar: Calendar,
    legend: Dict[str, str],
    subject_color_overrides: Dict[str, str],
) -> None:
    """Prefix processed titles using Apps Script color precedence.

    Overrides use YAML abbreviations and take precedence over class keywords.
    Preserve other event properties and replace any existing emoji prefix.
    """
    overrides = {
        " ".join(legend[abbr].split()).lower(): color
        for abbr, color in subject_color_overrides.items()
    }
    prefixes = tuple(f"{emoji} " for emoji in TITLE_COLOR_EMOJIS.values())
    for event in calendar.walk("vevent"):
        title = str(event.get("summary", ""))
        while title.startswith(prefixes):
            title = title.split(" ", 1)[1]
        normalized_title = " ".join(title.split()).lower()
        blob = f"{event.get('description', '')} {title}".lower()
        if normalized_title in overrides:
            color = overrides[normalized_title]
        elif "wyk" in blob:
            color = "gray"
        elif "ćw" in blob:
            color = "green"
        elif "klin" in blob:
            color = "yellow"
        elif re.search(r"\b(gry|gim|pł|la|reh)\b", blob, re.ASCII):
            # ASCII word boundaries match JavaScript's chooseColor_().
            color = "orange"
        else:
            color = "purple"
        event["summary"] = f"{TITLE_COLOR_EMOJIS[color]} {title}".rstrip()


def get_full_semester_calendar_bytes(
    *,
    group: str,
    legend: Dict[str, str],
    optional_subjects_list: List[str],
    optional_selected: Tuple[str, ...],
    start_of_semester: datetime = START_OF_SEMESTER,
    end_of_semester: datetime = END_OF_SEMESTER,
) -> Optional[bytes]:
    """Merge complete weeks covering the range, continuing after failed weeks.

    Returns None if no events remain. Boundary weeks are included in full.
    """
    if end_of_semester < start_of_semester:
        raise ValueError("Semester end must not precede semester start.")
    start_week = get_week_number(start_of_semester)
    end_week = get_week_number(end_of_semester)
    full_cal = Calendar()
    full_cal.add("prodid", "-//ATS4//Plan zajęć.//PL")
    full_cal.add("version", "2.0")
    full_cal.add("calscale", "GREGORIAN")
    full_cal.add("method", "PUBLISH")
    full_cal.add("X-WR-TIMEZONE", TIMEZONE)
    total_weeks = end_week - start_week + 1
    empty_weeks: List[int] = []
    failed_weeks: List[int] = []

    for i, week in enumerate(range(start_week, end_week + 1), start=1):
        print(f"  Fetching week {i}/{total_weeks} ({get_date_from_week_number(week)})")
        try:
            raw_bytes = fetch_awf_calendar_week(week)
            processed = process_calendar_bytes_for_group_and_optionals(
                raw_bytes,
                legend=legend,
                group=group,
                optional_subjects_list=optional_subjects_list,
                optional_selected=optional_selected,
            )
            week_cal = Calendar.from_ical(processed)
            events = list(week_cal.walk("vevent"))
            if not events:
                empty_weeks.append(week)
            for component in events:
                full_cal.add_component(component)
        except Exception as exc:
            print(f"    Could not process week {week}: {exc}")
            failed_weeks.append(week)

    for label, weeks in (("Empty after filtering", empty_weeks), ("Failed", failed_weeks)):
        if weeks:
            print(f"{label} weeks:")
            for week in weeks:
                print(f"  - {get_date_from_week_number(week)}")
    if not full_cal.subcomponents:
        print("No class schedule available for this calendar in the selected range.")
        return None
    return full_cal.to_ical()


# ---------- MAIN ----------
def ensure_output_dir() -> Path:
    """Create the GitHub Pages output directory if necessary."""
    output = Path("docs")
    output.mkdir(parents=True, exist_ok=True)
    return output


def make_filename_from_calendar_name(name: str) -> str:
    """Keep existing subscription filenames stable."""
    return f"{name}.ics"


def main() -> None:
    """Generate ICS feeds, optionally prefixing titles per calendar config."""
    legend, optional_defaults, calendars = load_yaml()
    if not calendars:
        print("No calendars defined under 'calendars' in legend.yaml.", file=sys.stderr)
        sys.exit(1)
    output_dir = ensure_output_dir()
    tz = pytz.timezone(TIMEZONE)
    for cfg in calendars:
        name = str(cfg.get("name") or "").strip()
        group = str(cfg.get("group") or "").strip()
        if not name or not group:
            print(f"Skipping calendar with missing name/group: {cfg}")
            continue
        optional_selected = resolve_optional_selection_for_calendar(
            optional_defaults, cfg.get("optional_subjects")
        )
        print(f"\nGenerating calendar for '{name}' ({group})")
        print(f"  Optional subjects: {', '.join(optional_selected) or '(none)'}")
        cal_bytes = get_full_semester_calendar_bytes(
            group=group,
            legend=legend,
            optional_subjects_list=optional_defaults,
            optional_selected=optional_selected,
        )
        if not cal_bytes:
            print(f"No output for '{name}'; any existing file is retained.")
            continue
        cal_obj = Calendar.from_ical(cal_bytes)
        if cfg.get("title_color_emojis", False):
            _add_title_color_emojis(
                cal_obj, legend, cfg.get("title_color_overrides", {})
            )
        cal_obj.add("X-CALENDAR-UPDATED", datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"))
        cal_obj.add("X-WR-CALNAME", "Plan zajęć.")
        out_path = output_dir / make_filename_from_calendar_name(name)
        out_path.write_bytes(cal_obj.to_ical())
        print(f"Wrote calendar to {out_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
