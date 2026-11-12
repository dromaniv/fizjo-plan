#!/usr/bin/env python3
# coding: utf-8

from datetime import datetime, timedelta
from pathlib import Path
import argparse
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pytz
import requests
import yaml
from icalendar import Calendar, Event


# ---------- CONFIGURATION ----------
LEGEND_FILE = "legend.yaml"
BASE_DATE = datetime(2025, 2, 17)  # Monday, AWF week 657
BASE_WEEKNUM = 657
AWF_PLAN_URL = (
    # AWF's published timetable endpoint currently has no working HTTPS listener.
    "http://web0.awf.poznan.pl/plan/plan.php?type=0&id=112976&cvsfile=true&wd=1&bw=0"
)
# Broad autumn/winter fetch range; adjust to confirmed semester boundaries.
START_OF_SEMESTER = datetime(2026, 9, 1)
END_OF_SEMESTER = datetime(2027, 2, 28)
TIMEZONE = "Europe/Warsaw"
HTTP_TIMEOUT = 30
MAX_CALENDAR_BYTES = 2 * 1024 * 1024
MAX_COMPONENT_DEPTH = 8
MAX_REMOVAL_FRACTION = 0.25
SAFE_EVENT_PROPERTIES = (
    "UID",
    "DTSTART",
    "DTEND",
    "DTSTAMP",
    "SEQUENCE",
    "CLASS",
    "STATUS",
    "TRANSP",
)
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
        calendars = [c for c in calendars_raw if isinstance(c, dict) and "name" in c]
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


def fetch_awf_calendar() -> bytes:
    """Download AWF's full-year snapshot without following redirects."""
    with requests.get(
        AWF_PLAN_URL,
        timeout=HTTP_TIMEOUT,
        stream=True,
        allow_redirects=False,
        headers={"User-Agent": "AWF-Plan-Downloader/1.0"},
    ) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError(f"Unexpected AWF response status: {response.status_code}")
        content = bytearray()
        for chunk in response.iter_content(64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_CALENDAR_BYTES:
                raise ValueError("AWF calendar exceeds the response size limit.")
        return bytes(content)


def parse_calendar_bytes(
    calendar_bytes: bytes, *, allow_duplicate_uids: bool = False
) -> Calendar:
    """Reject incomplete, oversized or deeply nested calendars before parsing."""
    if len(calendar_bytes) > MAX_CALENDAR_BYTES:
        raise ValueError("Calendar exceeds the size limit.")
    text = calendar_bytes.decode("utf-8-sig").strip()
    lines = re.sub(r"\r?\n[ \t]", "", text).splitlines()
    if not lines or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        raise ValueError("Expected a complete VCALENDAR document.")
    stack: List[str] = []
    for index, line in enumerate(lines):
        if line.startswith("BEGIN:"):
            if not stack and index != 0:
                raise ValueError("Multiple calendar documents are not supported.")
            stack.append(line[6:])
            if len(stack) > MAX_COMPONENT_DEPTH:
                raise ValueError("Calendar component nesting exceeds the limit.")
        elif line.startswith("END:"):
            if not stack or stack.pop() != line[4:]:
                raise ValueError("Mismatched calendar component boundaries.")
        elif not stack:
            raise ValueError("Unexpected content outside the calendar.")
    if stack:
        raise ValueError("Incomplete calendar component.")
    calendar = Calendar.from_ical(calendar_bytes)
    if calendar.name != "VCALENDAR" or str(calendar.get("VERSION")) != "2.0":
        raise ValueError("Expected an iCalendar 2.0 document.")
    seen = set()
    top_level_ids = {id(component) for component in calendar.subcomponents}
    for event in calendar.walk("VEVENT"):
        if id(event) not in top_level_ids:
            raise ValueError("Nested events are not supported.")
        uid = str(event.get("UID", ""))
        if (
            not uid
            or re.search(r"\s", uid)
            or (uid in seen and not allow_duplicate_uids)
        ):
            raise ValueError(
                "Event UIDs must be present, unique and contain no whitespace."
            )
        seen.add(uid)
        if not str(event.get("SUMMARY", "")).strip():
            raise ValueError(f"Event {uid} has no summary.")
        start = event.decoded("DTSTART")
        end = event.decoded("DTEND")
        if (
            not isinstance(start, datetime)
            or not isinstance(end, datetime)
            or end <= start
        ):
            raise ValueError(f"Event {uid} has invalid start/end times.")
        if event.errors or any(
            key in event for key in ("RRULE", "RDATE", "RECURRENCE-ID")
        ):
            raise ValueError(f"Event {uid} has invalid or unsupported properties.")
    return calendar


def _split_summary(
    summary: str,
    known_abbreviations: Sequence[str],
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
            return candidate, summary[tokens[count - 1].end() :].strip()
    if len(tokens) <= 4:
        return summary.strip(), ""
    end = tokens[3].end()
    return " ".join(token.group() for token in tokens[:4]), summary[end:].strip()


def process_calendar_bytes_for_group_and_optionals(
    calendar_bytes: bytes,
    legend: Dict[str, str],
    subject_groups: Dict[str, Optional[str]],
    optional_subjects_list: List[str],
    optional_selected: Tuple[str, ...],
) -> bytes:
    """Filter subject groups/optionals and set titles, color and location.

    Attached pA/pB/pC markers are removed BEFORE optional filtering.
    Each subject selects its own subgroup; null or omitted excludes split sessions.
    Named variants such as 'Umwzf Gr 1 A' remain exact-match selections.
    """
    # AWF can assign the same UID to simultaneous A/B sessions. Validate their
    # uniqueness after selecting the calendar's subject groups.
    cal = parse_calendar_bytes(calendar_bytes, allow_duplicate_uids=True)
    optional_set = set(optional_subjects_list)
    selected_set = set(optional_selected)
    if any(value not in ("A", "B", None) for value in subject_groups.values()):
        raise ValueError("Subject groups must be A, B or null.")
    known = tuple(set(legend) | optional_set | selected_set)

    retained = [
        component for component in cal.subcomponents if component.name != "VEVENT"
    ]
    for source in cal.subcomponents:
        if source.name != "VEVENT":
            continue
        # Republish only schedule data; source alarms, attachments and attendee
        # instructions must not reach subscribers from this unauthenticated feed.
        component = Event()
        for key in SAFE_EVENT_PROPERTIES:
            if key in source:
                component[key] = source[key]
        component["summary"] = source.get("summary", "")
        summary = component.get("summary")
        if not summary:
            continue
        s_text = str(summary)
        lower = s_text.lower()
        abbreviation, remainder = _split_summary(s_text, known)

        suffix = GROUP_SUFFIX_RE.search(abbreviation)
        if suffix:
            base_abbreviation = abbreviation[:-2]
            if suffix.group(1) != subject_groups.get(base_abbreviation):
                continue
            abbreviation = base_abbreviation

        if abbreviation in optional_set and abbreviation not in selected_set:
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
                if street
                else DEFAULT_LOCATION
            )
        retained.append(component)
    cal.subcomponents = retained
    output = cal.to_ical()
    parse_calendar_bytes(output)
    return output


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
    subject_groups: Dict[str, Optional[str]],
    legend: Dict[str, str],
    optional_subjects_list: List[str],
    optional_selected: Tuple[str, ...],
    start_of_semester: datetime = START_OF_SEMESTER,
    end_of_semester: datetime = END_OF_SEMESTER,
    calendar_bytes: Optional[bytes] = None,
) -> Optional[bytes]:
    """Filter one complete snapshot to the configured weeks and selections.

    Returns None if no events remain. Boundary weeks are included in full.
    Apply the same subject groups to every week.
    """
    if end_of_semester < start_of_semester:
        raise ValueError("Semester end must not precede semester start.")
    start_week = get_week_number(start_of_semester)
    end_week = get_week_number(end_of_semester)
    snapshot = parse_calendar_bytes(
        calendar_bytes if calendar_bytes is not None else fetch_awf_calendar(),
        allow_duplicate_uids=True,
    )
    # Keep complete boundary weeks, as with the previous weekly downloads.
    source_tz = pytz.timezone(TIMEZONE)
    for event in list(snapshot.walk("VEVENT")):
        start = event.decoded("DTSTART")
        local_start = start.astimezone(source_tz) if start.tzinfo else start
        if not start_week <= get_week_number(local_start) <= end_week:
            snapshot.subcomponents.remove(event)
    processed = process_calendar_bytes_for_group_and_optionals(
        snapshot.to_ical(),
        legend=legend,
        subject_groups=subject_groups,
        optional_subjects_list=optional_subjects_list,
        optional_selected=optional_selected,
    )
    filtered = parse_calendar_bytes(processed)
    full_cal = Calendar()
    full_cal.add("prodid", "-//ATS4//Plan zajęć.//PL")
    full_cal.add("version", "2.0")
    full_cal.add("calscale", "GREGORIAN")
    full_cal.add("method", "PUBLISH")
    full_cal.add("X-WR-TIMEZONE", TIMEZONE)
    for event in filtered.walk("VEVENT"):
        full_cal.add_component(event)
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
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError(
            "Calendar names may contain only letters, digits, underscores and hyphens."
        )
    return f"{name}.ics"


def validate_calendar_removals(previous: bytes, current: bytes) -> None:
    """Stop unexpectedly large removals before replacing a published feed."""
    old_uids = {
        str(event["UID"]) for event in parse_calendar_bytes(previous).walk("VEVENT")
    }
    new_uids = {
        str(event["UID"]) for event in parse_calendar_bytes(current).walk("VEVENT")
    }
    if old_uids and len(old_uids - new_uids) / len(old_uids) > MAX_REMOVAL_FRACTION:
        raise ValueError(
            "Refusing a large event removal; inspect the source before using --allow-large-removals."
        )


def main(*, allow_large_removals: bool = False) -> None:
    """Generate ICS feeds, optionally prefixing titles per calendar config."""
    legend, optional_defaults, calendars = load_yaml()
    if not calendars:
        print("No calendars defined under 'calendars' in legend.yaml.", file=sys.stderr)
        sys.exit(1)
    output_dir = ensure_output_dir()
    tz = pytz.timezone(TIMEZONE)
    snapshot = fetch_awf_calendar()
    pending_outputs: Dict[Path, bytes] = {}
    for cfg in calendars:
        name = str(cfg.get("name") or "").strip()
        if not name:
            print(f"Skipping calendar with missing name: {cfg}")
            continue
        out_path = output_dir / make_filename_from_calendar_name(name)
        if out_path in pending_outputs:
            raise ValueError(f"Duplicate calendar name: {name}")
        optional_selected = resolve_optional_selection_for_calendar(
            optional_defaults, cfg.get("optional_subjects")
        )
        print(f"\nGenerating calendar for '{name}'")
        print(f"  Optional subjects: {', '.join(optional_selected) or '(none)'}")
        cal_bytes = get_full_semester_calendar_bytes(
            subject_groups=cfg.get("subject_groups") or {},
            legend=legend,
            optional_subjects_list=optional_defaults,
            optional_selected=optional_selected,
            calendar_bytes=snapshot,
        )
        if not cal_bytes:
            print(f"No output for '{name}'; any existing file is retained.")
            continue
        cal_obj = Calendar.from_ical(cal_bytes)
        if cfg.get("title_color_emojis", False):
            _add_title_color_emojis(
                cal_obj, legend, cfg.get("title_color_overrides", {})
            )
        cal_obj.add(
            "X-CALENDAR-UPDATED", datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        )
        cal_obj.add("X-WR-CALNAME", "Plan zajęć.")
        output_bytes = cal_obj.to_ical()
        if out_path.exists() and not allow_large_removals:
            validate_calendar_removals(out_path.read_bytes(), output_bytes)
        pending_outputs[out_path] = output_bytes
    # Validate every calendar before replacing any existing output.
    for out_path, output_bytes in pending_outputs.items():
        temporary_path = out_path.with_suffix(".ics.tmp")
        temporary_path.write_bytes(output_bytes)
        temporary_path.replace(out_path)
        print(f"Wrote calendar to {out_path}")
    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate public AWF calendar feeds.")
    parser.add_argument(
        "--allow-large-removals",
        action="store_true",
        help="Allow reviewed removals exceeding the normal safety limit.",
    )
    main(allow_large_removals=parser.parse_args().allow_large_removals)
