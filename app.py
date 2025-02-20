import re
import requests
import streamlit as st
from datetime import datetime
from icalendar import Calendar
import yaml

# Load the YAML file
with open("legend.yaml", "r") as file:
    data = yaml.safe_load(file)
    legend = data["abbreviations"]


# Helper function to calculate the current week number
def get_week_number(current_date=datetime.now()):
    current_date = datetime(current_date.year, current_date.month, current_date.day)
    base_date = datetime(2025, 2, 17)
    week_diff = (current_date - base_date).days // 7
    return 657 + week_diff  # 657 is the week number of the base date


# Function to get and prepare the calendar for download
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


# Streamlit app
st.set_page_config(page_title="Plan zajęć", page_icon="📅")

st.title("Fizjoterapia - Plan zajęć 📅")

col1, col2, col3 = st.columns([0.45, 0.01, 0.48])
with col1:
    group = st.selectbox(
        "Wybierz grupę ćwiczeniową:",
        ["Grupa A", "Grupa B", "Grupa C"],
        index=1,
    )
with col3:
    date = st.date_input("Wybierz tydzień:", datetime.now())

if group:
    week = get_week_number(date)
    try:
        calendar_bytes, calendar_filename = get_calendar(week, group)
    except Exception as e:
        st.error(f"Brak planu zajęć w wybranym tygodniu :(")
        st.stop()
    if calendar_bytes:
        if st.download_button(
            label=":rainbow[Pobierz / Importuj]",
            data=calendar_bytes,
            file_name=calendar_filename,
            mime="text/calendar",
        ):
            st.balloons()
    else:
        st.error("Nie udało się pobrać planu zajęć")

st.markdown("<br />", unsafe_allow_html=True)
st.image("https://i.pinimg.com/736x/23/86/e3/2386e3023848e6754b8f0ad9597676a7.jpg")
