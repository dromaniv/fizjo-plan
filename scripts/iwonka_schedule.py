from datetime import datetime, timedelta
import pytz
from icalendar import Calendar
from pathlib import Path
import re
import requests
import yaml


# Load the YAML file
with open("legend.yaml", "r") as file:
    data = yaml.safe_load(file)
    legend = data["abbreviations"]
    optional_subjects_config = data.get(
        "optional_subjects", {}
    )  # abbreviation -> default(bool)

# === CONFIGURATION ===
GROUP = "Grupa B"

# Optional subjects you want to include (exact abbreviations)
OPTIONAL_SUBJECTS = (
    "GG1", "GG2", "ZwtTzG1", "ZwtTzG2", "TkuwzigrG1"
)

OUTPUT_FILE = Path("iwonka.ics")


# Helper function to calculate the current week number
def get_week_number(current_date=datetime.now()):
    current_date = datetime(current_date.year, current_date.month, current_date.day)
    base_date = datetime(2025, 2, 17)
    week_diff = (current_date - base_date).days // 7
    return 657 + week_diff  # 657 is the week number of the base date


# Helper function to get a date range from a week number
def get_date_from_week_number(week_number):
    base_date = datetime(2025, 2, 17)  # This is a Monday
    week_diff = week_number - 657
    start_of_week = base_date + timedelta(days=week_diff * 7)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%d.%m')} - {end_of_week.strftime('%d.%m.%Y')}"


# Classification helper
_DEF_TYPE_KEYS = ["Wykłady", "Ćwiczenia", "Kliniczne", "Inne"]


def _classify(summary: str):
    s = summary.lower()
    if "wyk" in s:
        return "Wykłady"
    if "ćw" in s:
        return "Ćwiczenia"
    if "klin" in s:
        return "Kliniczne"
    return "Inne"


# Function to get and prepare the calendar for download (standalone version)
def get_calendar(week_number, group="Grupa B", optional_selected=()):
    # Construct the URL
    url = f"http://web0.awf.poznan.pl/plan/plan.php?type=0&id=104148&cvsfile=true&w={week_number}"

    # Download the calendar file
    response = requests.get(url)
    response.raise_for_status()  # Ensure we got a successful response

    # Stats containers
    counts = {k: 0 for k in _DEF_TYPE_KEYS}
    per_day = {i: 0 for i in range(7)}  # Monday=0

    # Load and process the calendar
    cal = Calendar.from_ical(response.content)
    for component in list(cal.walk("vevent")):
        summary = component.get("summary")
        if not summary:
            continue
        lower = summary.lower()
        # Determine abbreviation early for filtering
        if "aliczeni" in lower or "gzamin" in lower:
            try:
                abbreviation = summary.split("  ")[0]
            except Exception:
                abbreviation = summary
        elif lower.startswith("zapisy"):
            # Special case: don't split "Zapisy" summaries
            abbreviation = "Zapisy na praktyki zawodowe"
        else:
            # first token
            abbreviation = summary.split()[0]
        # Optional subject filtering
        if (
            abbreviation in optional_subjects_config
            and abbreviation not in optional_selected
        ):
            # remove and skip
            try:
                cal.subcomponents.remove(component)
            except Exception:
                pass
            continue
        if "wyk" in lower:
            component.add("color", "gray")
        elif "ćw" in lower:
            component.add("color", "red")
        elif "klin" in lower:
            component.add("color", "blue")
        else:
            component.add("color", "darkred")
        t = _classify(summary)
        counts[t] += 1
        dtstart = component.get("dtstart")
        try:
            if dtstart:
                dt = dtstart.dt
                if hasattr(dt, "weekday"):
                    per_day[dt.weekday()] += 1
        except Exception:
            pass
        # Group related trimming (unchanged logic, now abbreviation already computed)
        if abbreviation and abbreviation[-1] in ["A", "B", "C"]:
            if (
                len(abbreviation) >= 2
                and abbreviation[-2] == "p"
                and abbreviation[-1] == group[-1]
            ):
                abbreviation = abbreviation[:-2]
            elif (
                len(abbreviation) >= 2
                and abbreviation[-2] == "p"
                and abbreviation[-1] != group[-1]
            ):
                try:
                    cal.subcomponents.remove(component)
                except Exception:
                    pass
                continue
        component["summary"] = legend.get(abbreviation, abbreviation)
        component["description"] = summary[len(abbreviation) :].strip()
        pattern = r"ul\.\s?[\w\s]+"
        street = re.search(pattern, component["description"])
        component["location"] = (
            ("ul. " + street.group()[3:].strip() + ", Poznań, Polska")
            if street
            else "ul. Królowej Jadwigi 27/39, Poznań, Polska"
        )

    total_events = sum(counts.values())
    active_days = len([1 for c in per_day.values() if c > 0])
    avg_day = round(total_events / active_days, 2) if total_events else 0
    pct = {
        k: (round((counts[k] / total_events) * 100, 1) if total_events else 0.0)
        for k in counts
    }
    stats = {
        "week_number": week_number,
        "date_range": get_date_from_week_number(week_number),
        "Razem": total_events,
        **counts,
        "Procenty": pct,
        "Dni z zajęciami": active_days,
        "Średnio / dzień": avg_day,
        "per_day": per_day,
    }
    return cal.to_ical(), f"calendar_{group[-1]}_{week_number}.ics", stats


# Function to get and prepare the calendar for the full semester (standalone version)
def get_full_semester_calendar(group="Grupa B", optional_selected=()):
    start_of_semester = datetime(2025, 9, 30)
    end_of_semester = datetime(2026, 2, 28)
    start_week = get_week_number(start_of_semester)
    end_week = get_week_number(end_of_semester)
    full_cal = Calendar()
    full_cal.add("prodid", "-//ATS4//Plan zajęć.//PL")
    full_cal.add("version", "2.0")
    full_cal.add("calscale", "GREGORIAN")
    full_cal.add("method", "PUBLISH")
    full_cal.add("X-WR-CALNAME", f"Plan zajęć.")
    full_cal.add("X-WR-TIMEZONE", "Europe/Warsaw")
    total_weeks = end_week - start_week + 1
    empty_weeks = []
    has_any_events = False
    counts = {k: 0 for k in _DEF_TYPE_KEYS}
    per_week_events = {}
    
    for i, week in enumerate(range(start_week, end_week + 1)):
        print(f"Pobieranie tygodnia {i+1}/{total_weeks} ({get_date_from_week_number(week)})")
        try:
            calendar_bytes, _, week_stats = get_calendar(
                week, group, optional_selected=optional_selected
            )
            cal = Calendar.from_ical(calendar_bytes)  # type: ignore[arg-type]
            events = list(cal.walk("vevent"))
            per_week_events[week] = len(events)
            if not events:
                empty_weeks.append(week)
            else:
                has_any_events = True
                for category in _DEF_TYPE_KEYS:
                    if category in week_stats:
                        counts[category] += week_stats[category]
                for component in events:
                    full_cal.add_component(component)
        except Exception as e:
            print(f"Błąd dla tygodnia {week}: {e}")
            empty_weeks.append(week)
    
    if not has_any_events:
        print("❌ Brak planu zajęć dla semestru :(")
        return None, None, None
    
    if empty_weeks:
        empty_week_dates = [get_date_from_week_number(w) for w in empty_weeks]
        print("⚠️ Brak danych dla następujących tygodni:")
        for date in empty_week_dates:
            print(f"   - {date}")
    else:
        print("✅ Gotowe!")
    
    total_events = sum(counts.values())
    non_empty = total_weeks - len(empty_weeks)
    avg_week = round(total_events / non_empty, 2) if total_events else 0
    pct = {
        k: (round((counts[k] / total_events) * 100, 1) if total_events else 0.0)
        for k in counts
    }
    stats = {
        "Zakres": f"{start_of_semester.strftime('%d.%m.%Y')} - {end_of_semester.strftime('%d.%m.%Y')}",
        "Tygodni (łącznie)": total_weeks,
        "Tygodni z zajęciami": non_empty,
        "Puste tygodnie": len(empty_weeks),
        "Razem": total_events,
        **counts,
        "Procenty": pct,
        "Średnio / tydzień": avg_week,
        "Max / tydzień": max(per_week_events.values()) if per_week_events else 0,
        "per_week_events": per_week_events,
    }
    return full_cal.to_ical(), f"calendar_semester_{group[-1]}.ics", stats


def main():
    print("📅 Generating full semester calendar...")

    calendar_bytes, calendar_filename, stats = get_full_semester_calendar(
        group=GROUP,
        optional_selected=OPTIONAL_SUBJECTS,
    )

    if not calendar_bytes:
        raise RuntimeError("❌ Failed to generate calendar (no data)")

    # Parse the calendar so we can append a timestamp
    cal = Calendar.from_ical(calendar_bytes)
    tz = pytz.timezone("Europe/Warsaw")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    cal.add("X-CALENDAR-UPDATED", f"Generated {now}")

    # Write final file
    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())

    print(f"✅ Wrote updated schedule to {OUTPUT_FILE}")
    print(f"   Events: {stats.get('Razem', 'unknown')}")
    print(f"   Weeks: {stats.get('Tygodni z zajęciami', 'unknown')} / {stats.get('Tygodni (łącznie)', 'unknown')}")


if __name__ == "__main__":
    main()
