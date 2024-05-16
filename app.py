import re
import requests
import streamlit as st
from datetime import datetime
from icalendar import Calendar

# Define the abbreviation legend
legend = {
    "Fkwcwwc": "Fizjoterapia kliniczna w chorobach wewnętrznych w chirurgii",
    "Fkwcwwg": "Fizjoterapia kliniczna w chorobach wewnętrznych w geriatrii",
    "Fkwdurwoit": "Fizjoterapia kliniczna w dysfunkcjach układu ruchu w ortopedii i traumatologii",
    "Fkwdurwr": "Fizjoterapia kliniczna w dysfunkcjach układu ruchu w reumatologii",
    "Fkwcwwkik": "Fizjoterapia kliniczna w chorobach wewnętrznych w kardiologii i kardiochirurgii",
    "Ja": "Język angielski",
    "Kin": "Kinezyterapia",
    "Mas": "Masaż",
    "Mffib": "Medycyna fizykalna - fizykoterapia i balneoklimatologia",
    "Kpfwnin": "Kliniczne podstawy fizjoterapii w neurologii i neurochirurgii",
}


# Helper function to calculate the current week number
def get_week_number():
    base_date = datetime(2024, 5, 13)
    current_date = datetime.now()
    week_diff = (current_date - base_date).days // 7
    return 617 + week_diff  # Adjusting 617 for 13.05.2023


# Function to get and prepare the calendar for download
def get_calendar(week_number, group="Grupa B", english=False):
    # Construct the URL
    url = f"http://web0.awf.poznan.pl/plan/plan.php?type=0&id=88436&cvsfile=true&w={week_number}"

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
        abbreviation = summary.split()[0]

        # Handle english
        if abbreviation[:2] == "Ja" and abbreviation[2:] == english[6:]:
            abbreviation = abbreviation[:2]
        elif abbreviation[:2] == "Ja" and abbreviation[2:] != english[6:]:
            cal.subcomponents.remove(component)
            continue

        # Handle groups
        if abbreviation[-1] in ["A", "B", "C"]:
            if abbreviation[-2] == "p" and abbreviation[-1] == group[-1]:
                abbreviation = abbreviation[:-2]
            elif abbreviation[-2] == "p" and abbreviation[-1] != group[-1]:
                cal.subcomponents.remove(component)
                continue

        component["summary"] = legend.get(abbreviation, abbreviation)
        component["description"] = summary[len(abbreviation) :].strip()

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


# Streamlit app
st.set_page_config(page_title="Plan zajęć", page_icon="📅")

st.title("Fizjoterapia - Plan zajęć 📅")

col1, col2, col3 = st.columns([0.45, 0.01, 0.49])
with col1:
    group = st.selectbox(
        "Wybierz grupę ćwiczeniową:",
        ["Grupa A", "Grupa B", "Grupa C"],
        index=1,
    )
with col3:
    english = st.selectbox(
        "Wybierz grupę z angielskiego:",
        ["Grupa 1A", "Grupa 1B+2+3"],
        index=0,
    )

st.write("Pobierz plan zajęć:")
if group:
    col4, col5, col6 = st.columns([0.2, 0.3, 0.5])
    week = get_week_number()
    calendar_bytes, calendar_filename = get_calendar(week, group, english)
    if calendar_bytes:
        with col4:
            st.download_button(
                label="Ten tydzień",
                data=calendar_bytes,
                file_name=calendar_filename,
                mime="text/calendar",
            )
    next_calendar_bytes, next_calendar_filename = get_calendar(week + 1, group, english)
    if next_calendar_bytes:
        with col5:
            st.download_button(
                label="Następny tydzień",
                data=next_calendar_bytes,
                file_name=next_calendar_filename,
                mime="text/calendar",
            )

st.markdown("<br />", unsafe_allow_html=True)
st.image("https://i.pinimg.com/736x/23/86/e3/2386e3023848e6754b8f0ad9597676a7.jpg")
