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
OPTIONAL_SUBJECTS = ("GG1", "GG2", "ZwtTzG1", "ZwtTzG2", "TkuwzigrG1")

# Output file - automatically saved to schedules/ folder
OUTPUT_FILE = "iwonka.ics"


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


# Function to get and prepare the calendar for download (standalone version)
def get_calendar(week_number, group="Grupa B", optional_selected=()):
    # Construct the URL
    url = f"http://web0.awf.poznan.pl/plan/plan.php?type=0&id=104148&cvsfile=true&w={week_number}"

    # Download the calendar file
    response = requests.get(url)
    response.raise_for_status()  # Ensure we got a successful response

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

    return cal.to_ical()


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

    for i, week in enumerate(range(start_week, end_week + 1)):
        print(f"Fetching week {i+1}/{total_weeks} ({get_date_from_week_number(week)})")
        try:
            calendar_bytes = get_calendar(
                week, group, optional_selected=optional_selected
            )
            cal = Calendar.from_ical(calendar_bytes)  # type: ignore[arg-type]
            events = list(cal.walk("vevent"))
            if not events:
                empty_weeks.append(week)
            else:
                has_any_events = True
                for component in events:
                    full_cal.add_component(component)
        except Exception:
            print(f"Error for week {get_date_from_week_number(week)}")
            empty_weeks.append(week)

    if not has_any_events:
        print("❌ No class schedule available for the semester :(")
        return None, None

    if empty_weeks:
        empty_week_dates = [get_date_from_week_number(w) for w in empty_weeks]
        print("⚠️ No data available for the following weeks:")
        for date in empty_week_dates:
            print(f"   - {date}")
    else:
        print("✅ Done!")

    return full_cal.to_ical()


def main():
    print("📅 Generating full semester calendar...")

    result = get_full_semester_calendar(
        group=GROUP,
        optional_selected=OPTIONAL_SUBJECTS,
    )

    if not result:
        raise RuntimeError("❌ Failed to generate calendar (no data)")

    calendar_bytes = result

    # Parse the calendar so we can append a timestamp
    cal = Calendar.from_ical(calendar_bytes)
    tz = pytz.timezone("Europe/Warsaw")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    cal.add("X-CALENDAR-UPDATED", f"Generated {now}")

    # Ensure the output directory exists and construct full path
    schedules_dir = Path("schedules")
    schedules_dir.mkdir(parents=True, exist_ok=True)
    output_path = schedules_dir / OUTPUT_FILE

    # Write final file
    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    print(f"✅ Successfully wrote updated schedule to {output_path}")


if __name__ == "__main__":
    main()
