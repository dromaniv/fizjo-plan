#!/usr/bin/env python3
# coding: utf-8

from datetime import datetime, timedelta
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Sequence, Tuple, Union

import pytz
import requests
import yaml
from icalendar import Calendar


# ---------- YAML LOADING ----------
LEGEND_FILE = "legend.yaml"


def load_yaml(path: str = LEGEND_FILE):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    legend: Dict[str, str] = data.get("abbreviations", {}) or {}
    optional_subjects: List[str] = data.get("optional_subjects", []) or []
    remote_subjects: List[str] = data.get("remote_subjects", []) or []
    calendars_raw = data.get("calendars", [])

    # Normalize calendars to a list of dicts with 'name'
    calendars: List[Dict] = []
    if isinstance(calendars_raw, dict):
        # { "iwonka": {group: "...", optional_subjects: [...]}, ... }
        for name, cfg in calendars_raw.items():
            if not isinstance(cfg, dict):
                continue
            calendars.append({"name": name, **cfg})
    elif isinstance(calendars_raw, list):
        # [ {name: "...", group: "...", optional_subjects: [...]}, ... ]
        calendars = [c for c in calendars_raw if isinstance(c, dict) and "name" in c]
    else:
        calendars = []

    return legend, optional_subjects, remote_subjects, calendars


# ---------- WEEK & DATE HELPERS ----------

BASE_DATE = datetime(2025, 2, 17)  # Monday
BASE_WEEKNUM = 657  # week number on BASE_DATE


def get_week_number(current_date: Optional[datetime] = None) -> int:
    """
    Compute AWF 'w=' parameter week number for a given date based on a fixed base.
    """
    if current_date is None:
        now = datetime.now()
        current_date = datetime(now.year, now.month, now.day)
    else:
        current_date = datetime(current_date.year, current_date.month, current_date.day)

    week_diff = (current_date - BASE_DATE).days // 7
    return BASE_WEEKNUM + week_diff


def get_date_from_week_number(week_number: int) -> str:
    """
    Human-readable range for a given AWF week number.
    """
    week_diff = week_number - BASE_WEEKNUM
    start_of_week = BASE_DATE + timedelta(days=week_diff * 7)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%d.%m')} - {end_of_week.strftime('%d.%m.%Y')}"


# ---------- CALENDAR FETCH & PROCESS ----------

AWF_PLAN_URL = (
    "http://web0.awf.poznan.pl/plan/plan.php?type=0&id=104148&cvsfile=true&w={week}"
)

STREET_RE = re.compile(r"ul\.\s?[\w\sĄĆĘŁŃÓŚŹŻąćęłńóśźż\-]+", re.UNICODE)


def resolve_optional_selection_for_calendar(
    global_optional_subjects: List[str],
    calendar_optional_cfg: Optional[Union[Sequence[str], Dict[str, bool]]] = None,
) -> Tuple[str, ...]:
    """
    Compute which optional subjects (by abbreviation) should be INCLUDED for this calendar.

    Rules:
      - If calendar_optional_cfg is a LIST -> include exactly those abbreviations.
      - If it's a DICT -> include those where value is True (others excluded).
      - If omitted/None -> include all subjects from global list.
    """
    if isinstance(calendar_optional_cfg, dict):
        return tuple(sorted([abbr for abbr, on in calendar_optional_cfg.items() if on]))

    if isinstance(calendar_optional_cfg, (list, tuple)):
        return tuple(sorted(set(str(x) for x in calendar_optional_cfg)))

    # Fallback to include all subjects from global list
    return tuple(sorted(global_optional_subjects))


def fetch_awf_calendar_week(week_number: int) -> bytes:
    url = AWF_PLAN_URL.format(week=week_number)
    resp = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "AWF-Plan-Downloader/1.0"},
    )
    resp.raise_for_status()
    return resp.content


def process_calendar_bytes_for_group_and_optionals(
    calendar_bytes: bytes,
    legend: Dict[str, str],
    group: str,
    optional_subjects_list: List[str],
    optional_selected: Tuple[str, ...],
    remote_subjects_list: List[str],
) -> bytes:
    """
    Filter & transform the ICS:
      - remove optional subjects not selected
      - map abbreviations to full names in SUMMARY
      - color-code by type
      - normalize LOCATION (street extraction or remote)
      - trim postfix group markers like 'pA', 'pB', etc
    """
    cal = Calendar.from_ical(calendar_bytes)

    # Make a copy of subcomponents to iterate safely while removing
    events = list(cal.walk("vevent"))
    for component in events:
        summary = component.get("summary")
        if not summary:
            continue

        s_text = str(summary)
        lower = s_text.lower()

        # Determine abbreviation token using legend lookup
        abbreviation = None
        remainder = s_text

        # Try to match the first token against known abbreviations
        tokens = s_text.split()
        if tokens:
            first_token = tokens[0]

            if first_token in legend or first_token in optional_subjects_list:
                abbreviation = first_token
                remainder = s_text[len(first_token):].strip()

        # Fallback: if no abbreviation found, use first 4 words as summary
        if abbreviation is None:
            words = s_text.split()
            if len(words) <= 4:
                abbreviation = s_text
                remainder = ""
            else:
                abbreviation = " ".join(words[:4])
                remainder = " ".join(words[4:])

        # Optional subject filtering - check if it's in the list but not selected
        if (
            abbreviation in optional_subjects_list
            and abbreviation not in optional_selected
        ):
            try:
                cal.subcomponents.remove(component)
            except Exception:
                pass
            continue

        # Quick color hints (non-standard property, many clients still honor it)
        if "wyk" in lower:
            component.add("color", "gray")
        elif "ćw" in lower:
            component.add("color", "red")
        elif "klin" in lower:
            component.add("color", "blue")
        else:
            component.add("color", "darkred")

        # Group trimming logic, e.g., "XxxpA", "XxxpB"
        if abbreviation and abbreviation[-1:] in ("A", "B", "C"):
            if len(abbreviation) >= 2 and abbreviation[-2] == "p":
                # keep if matches group suffix, otherwise drop
                if abbreviation[-1] != group[-1:]:
                    try:
                        cal.subcomponents.remove(component)
                    except Exception:
                        pass
                    continue
                # strip trailing 'pA' / 'pB' / 'pC'
                abbreviation = abbreviation[:-2]

        # Replace SUMMARY with full subject name if known
        component["summary"] = legend.get(abbreviation, abbreviation)

        # DESCRIPTION = everything after the abbreviation token
        component["description"] = remainder

        # LOCATION: check if remote, extract street, or use default
        if abbreviation in remote_subjects_list:
            component["location"] = "zdalne / remote"
        else:
            street = STREET_RE.search(remainder)
            if street:
                component["location"] = f"ul. {street.group()[3:].strip()}, Poznań, Polska"
            else:
                component["location"] = "ul. Królowej Jadwigi 27/39, Poznań, Polska"

    return cal.to_ical()


def get_full_semester_calendar_bytes(
    *,
    group: str,
    legend: Dict[str, str],
    optional_subjects_list: List[str],
    optional_selected: Tuple[str, ...],
    remote_subjects_list: List[str],
    start_of_semester: datetime = datetime(2025, 9, 30),
    end_of_semester: datetime = datetime(2026, 2, 28),
) -> Optional[bytes]:
    """
    Assemble all weeks into one ICS for the whole semester.
    Returns bytes or None if no events were found at all.
    """
    start_week = get_week_number(start_of_semester)
    end_week = get_week_number(end_of_semester)

    full_cal = Calendar()
    full_cal.add("prodid", "-//ATS4//Plan zajęć.//PL")
    full_cal.add("version", "2.0")
    full_cal.add("calscale", "GREGORIAN")
    full_cal.add("method", "PUBLISH")
    full_cal.add("X-WR-TIMEZONE", "Europe/Warsaw")

    total_weeks = end_week - start_week + 1
    empty_weeks: List[int] = []
    has_any_events = False

    for i, week in enumerate(range(start_week, end_week + 1), start=1):
        print(
            f"   • Fetching week {i}/{total_weeks} ({get_date_from_week_number(week)})"
        )
        try:
            raw_bytes = fetch_awf_calendar_week(week)
            week_ics = process_calendar_bytes_for_group_and_optionals(
                raw_bytes,
                legend=legend,
                group=group,
                optional_subjects_list=optional_subjects_list,
                optional_selected=optional_selected,
                remote_subjects_list=remote_subjects_list,
            )
            week_cal = Calendar.from_ical(week_ics)
            events = list(week_cal.walk("vevent"))
            if not events:
                empty_weeks.append(week)
            else:
                has_any_events = True
                for comp in events:
                    full_cal.add_component(comp)
        except Exception as e:
            error_str = str(e)
            if error_str.startswith("Content line"):
                print(f"     ! Couldn't fetch week: empty schedule")
                empty_weeks.append(week)
            else:
                print(f"     ! Couldn't fetch week: {e}")
                empty_weeks.append(week)

    if not has_any_events:
        print("❌ No class schedule available for the semester.")
        return None

    if empty_weeks:
        print("⚠️  No data available for the following weeks:")
        for w in empty_weeks:
            print(f"   - {get_date_from_week_number(w)}")
    else:
        print("✅ All weeks fetched successfully.")

    return full_cal.to_ical()


# ---------- MAIN ----------


def ensure_output_dir() -> Path:
    out = Path("docs")
    out.mkdir(parents=True, exist_ok=True)
    return out


def make_filename_from_calendar_name(name: str) -> str:
    """
    Use the calendar name directly for the output filename "<name>.ics".
    (If you prefer sanitization, adjust here.)
    """
    return f"{name}.ics"


def main():
    legend, optional_defaults, remote_subjects, calendars = load_yaml()

    if not calendars:
        print(
            "❌ No calendars defined under 'calendars' in legend.yaml.", file=sys.stderr
        )
        sys.exit(1)

    output_dir = ensure_output_dir()
    tz = pytz.timezone("Europe/Warsaw")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")

    for cfg in calendars:
        name = str(cfg.get("name") or "").strip()
        group = str(cfg.get("group") or "").strip()

        if not name or not group:
            print(f"⏭️  Skipping calendar with missing name/group: {cfg}")
            continue

        # Compute which optional subjects to include for this calendar
        optional_selected = resolve_optional_selection_for_calendar(
            optional_defaults, cfg.get("optional_subjects")
        )

        print(f"\n📅 Generating calendar for '{name}' ({group})")
        if optional_selected:
            print(f"   Optional subjects: {', '.join(optional_selected)}")
        else:
            print("   Optional subjects: (none)")

        cal_bytes = get_full_semester_calendar_bytes(
            group=group,
            legend=legend,
            optional_subjects_list=optional_defaults,
            optional_selected=optional_selected,
            remote_subjects_list=remote_subjects,
        )

        if not cal_bytes:
            print(f"❌ Failed to generate calendar for '{name}' (no data).")
            continue

        # Add metadata and write to file
        cal_obj = Calendar.from_ical(cal_bytes)
        cal_obj.add(
            "X-CALENDAR-UPDATED", datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        )
        cal_obj.add("X-WR-CALNAME", f"Plan zajęć.")

        out_path = output_dir / make_filename_from_calendar_name(name)
        with open(out_path, "wb") as f:
            f.write(cal_obj.to_ical())

        print(f"✅ Wrote calendar to {out_path}")

    print("\n🏁 Done.")


if __name__ == "__main__":
    main()
