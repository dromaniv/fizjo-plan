import re
import requests
import streamlit as st
from datetime import datetime, timedelta
from icalendar import Calendar
import yaml

# Load the YAML file
with open("legend.yaml", "r") as file:
    data = yaml.safe_load(file)
    legend = data["abbreviations"]

# --- Revised: global font size injection (static, no sidebar) ---

def inject_global_css():
    """Inject global CSS with a fixed larger font size (no user control)."""
    base_size = 18  # Increased base font size
    st.markdown(f"""
        <style>
        :root {{
            --base-font-size: {base_size}px;
        }}
        /* Global font size */
        .stApp, .stApp * {{
            font-size: var(--base-font-size) !important;
        }}
        /* Increased spacing between elements */
        .element-container {{
            margin-bottom: 0.5rem !important;
            margin-top: 0.25rem !important;
        }}
        .stSelectbox, .stRadio, .stDateInput {{
            margin-bottom: 0.5rem !important;
            margin-top: 0.25rem !important;
        }}
        /* Increase spacing between radio button options */
        .stRadio > div > label {{
            margin-right: 2rem !important;
        }}
        .stButton {{
            margin-top: 0.5rem !important;
            margin-bottom: 0.25rem !important;
        }}
        .stAlert {{
            margin-top: 0.5rem !important;
            margin-bottom: 0.5rem !important;
        }}
        /* Add padding to main content */
        .main .block-container {{
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
        }}
        /* Headings - more specific targeting */
        h1, .stMarkdown h1, .stApp > div > div > div > h1, 
        [data-testid="stHeader"] h1, .element-container h1 {{
            font-size: calc(var(--base-font-size) * 1.8) !important;
            margin-bottom: 0.75rem !important;
            margin-top: 0.5rem !important;
        }}
        h2, .stMarkdown h2 {{
            font-size: calc(var(--base-font-size) * 1.7) !important;
            margin-bottom: 0.5rem !important;
            margin-top: 0.5rem !important;
        }}
        h3, .stMarkdown h3 {{
            font-size: calc(var(--base-font-size) * 1.35) !important;
            margin-bottom: 0.25rem !important;
            margin-top: 0.25rem !important;
        }}
        /* Buttons */
        .stButton button, .stDownloadButton button {{
            font-size: calc(var(--base-font-size) * 1.1) !important;
            padding: 1rem 1.5rem !important;
        }}
        /* Make download buttons full width like alerts */
        .stDownloadButton button {{
            width: 100% !important;
            font-size: calc(var(--base-font-size) * 1.2) !important;
            padding: 1.25rem 1.5rem !important;
        }}
        /* Inputs labels */
        label, .stSelectbox label, .stRadio label, .stDateInput label {{
            font-size: calc(var(--base-font-size) * 1.05) !important;
            margin-bottom: 0.25rem !important;
        }}
        /* Alerts */
        .stAlert p {{
            font-size: calc(var(--base-font-size) * 1.0) !important;
        }}
        /* Progress bar and status text - better targeting */
        .stProgress, .stProgress *, [data-testid="stProgress"], 
        .stProgress .stMarkdown, .element-container .stProgress *,
        .st-emotion-cache-183lzff, [class*="st-emotion-cache"] {{
            font-size: calc(var(--base-font-size) * 0.9) !important;
        }}
        </style>
    """, unsafe_allow_html=True)

# Helper function to calculate the current week number
def get_week_number(current_date=datetime.now()):
    current_date = datetime(current_date.year, current_date.month, current_date.day)
    base_date = datetime(2025, 2, 17)
    week_diff = (current_date - base_date).days // 7
    return 657 + week_diff  # 657 is the week number of the base date

# Helper function to get a date range from a week number
def get_date_from_week_number(week_number):
    base_date = datetime(2025, 2, 17) # This is a Monday
    week_diff = week_number - 657
    start_of_week = base_date + timedelta(days=week_diff * 7)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%d.%m')} - {end_of_week.strftime('%d.%m.%Y')}"


# Function to get and prepare the calendar for download
@st.cache_data(ttl=28800, show_spinner=False)
def get_calendar(week_number, group="Grupa B"):
    # Construct the URL
    url = f"http://web0.awf.poznan.pl/plan/plan.php?type=NaN&id=95765&cvsfile=true&w={week_number}"

    # Download the calendar file
    response = requests.get(url)
    response.raise_for_status()  # Ensure we got a successful response

    # Load and process the calendar
    cal = Calendar.from_ical(response.content)
    for component in cal.walk("vevent"):
        summary = component.get("summary")
        # Determine the color based on the type of class
        if "wyk" in summary:
            component.add("color", "gray")
        elif "ćw" in summary:
            component.add("color", "red")
        elif "klin" in summary:
            component.add("color", "blue")
        else:
            component.add("color", "darkred")

        # Extract the abbreviation and add it to the title
        if "aliczeni" in summary or "gzamin" in summary:
            try:
                abbreviation = summary.split("  ")[0]
            except:
                abbreviation = summary
        else:
            abbreviation = summary.split()[0]

        # Handle groups
        if abbreviation[-1] in ["A", "B", "C"]:
            if abbreviation[-2] == "p" and abbreviation[-1] == group[-1]:
                abbreviation = abbreviation[:-2]
            elif abbreviation[-2] == "p" and abbreviation[-1] != group[-1]:
                cal.subcomponents.remove(component)
                continue

        component["summary"] = legend.get(abbreviation, abbreviation)
        component["description"] = ("zajęcia " + summary[len(abbreviation) :].strip())

        # Regex pattern to extract Polish street
        pattern = r"ul\.\s?[\w\s]+"
        street = re.search(pattern, component["description"])
        if street:
            component["location"] = (
                "ul. " + street.group()[3:].strip() + ", Poznań, Polska"
            )
        else:
            component["location"] = "ul. Królowej Jadwigi 27/39, Poznań, Polska"

    return cal.to_ical(), f"calendar_{group[-1]}_{week_number}.ics"


# Function to get and prepare the calendar for the full semester
def get_full_semester_calendar(group="Grupa B"):
    start_of_semester = datetime(2025, 10, 1)
    end_of_semester = datetime(2026, 2, 28)

    start_week = get_week_number(start_of_semester)
    end_week = get_week_number(end_of_semester)

    full_cal = Calendar()
    full_cal.add('prodid', '-//Fizjo-Plan Full Semester//dromaniv.github.io//')
    full_cal.add('version', '2.0')
    full_cal.add('X-WR-CALNAME', f'Fizjoterapia semestr zimowy - {group}')
    full_cal.add('X-WR-TIMEZONE', 'Europe/Warsaw')

    total_weeks = end_week - start_week + 1
    progress_bar = st.progress(0)
    status_text = st.empty()
    empty_weeks = []
    has_any_events = False

    try:
        for i, week in enumerate(range(start_week, end_week + 1)):
            status_text.text(f"Pobieranie tygodnia {i + 1}/{total_weeks} ({get_date_from_week_number(week)})")
            try:
                calendar_bytes, _ = get_calendar(week, group)
                cal = Calendar.from_ical(calendar_bytes)  # type: ignore[arg-type]
                events_in_week = list(cal.walk('vevent'))
                if not events_in_week:
                    empty_weeks.append(week)
                else:
                    has_any_events = True
                    for component in events_in_week:
                        full_cal.add_component(component)
            except Exception:
                empty_weeks.append(week)
            progress_bar.progress((i + 1) / total_weeks)
        
        if not has_any_events:
            status_text.error("Brak planu zajęć w całym semestrze :(")
            return None, None

        if empty_weeks:
            empty_week_dates = [get_date_from_week_number(w) for w in empty_weeks]
            st.warning(
                "Brak danych dla następujących tygodni:\n\n" +
                "  \n".join(empty_week_dates)  # ⬅ two spaces before \n
            )
            status_text.text("")  # Clear the progress text
        else:
            status_text.success("Gotowe!")

        return full_cal.to_ical(), f"calendar_semester_{group[-1]}.ics"
    finally:
        progress_bar.empty()


# Streamlit app configuration
st.set_page_config(page_title="Plan zajęć", page_icon="📅")

# Inject static enlarged typography (slider removed)
inject_global_css()

st.title("Fizjoterapia - Plan zajęć 📅")

group = st.selectbox(
    "Wybierz grupę ćwiczeniową:",
    ["Grupa A", "Grupa B", "Grupa C"],
    index=1,
)

option = st.radio(
    "Wybierz zakres planu:",
    ('Cały tydzień', 'Cały semestr (01.10 - 28.02)'),
    horizontal=True,
)

if option == 'Cały tydzień':
    date = st.date_input(
        "Wybierz tydzień:",
        value=datetime.now(),
        help=f"Zakres dni: {get_date_from_week_number(get_week_number(datetime.now()))}"
    )

    download_btn_placeholder = st.empty()
    if group:
        week = get_week_number(date)
        try:
            with st.spinner("Pobieranie danych..."):
                calendar_bytes, calendar_filename = get_calendar(week, group)
        except Exception as e:
            st.error("Brak planu zajęć w wybranym tygodniu :(")
            st.stop()
        
        if calendar_bytes:
            if download_btn_placeholder.download_button(
                label=":rainbow[Pobierz / Importuj]",
                data=calendar_bytes,
                file_name=calendar_filename,
                mime="text/calendar",
                key="week_download"
            ):
                st.balloons()
        else:
            st.error("Nie udało się pobrać planu zajęć")
elif option == 'Cały semestr (01.10 - 28.02)':
    if group:
        try:
            calendar_bytes, calendar_filename = get_full_semester_calendar(group)
            if calendar_bytes:
                if st.download_button(
                    label=":rainbow[Pobierz / Importuj]",
                    data=calendar_bytes,
                    file_name=calendar_filename,
                    mime="text/calendar",
                    key="semester_download"
                ):
                    st.balloons()
        except Exception as e:
            st.error(f"Wystąpił błąd: {e}")
    else:
        st.warning("Proszę wybrać grupę.")
else:
    st.warning("Proszę wybrać zakres.")

st.markdown("<br>", unsafe_allow_html=True)
