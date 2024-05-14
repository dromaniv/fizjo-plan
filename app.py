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
    "Ja1A": "Język angielski - 1 A",
    "Ja1B+2+3": "Język angielski - 1 B + 2B + 3B",
    "Kin": "Kinezyterapia",
    "Mas": "Masaż",
    "Mffib": "Medycyna fizykalna - fizykoterapia i balneoklimatologia",
}
filtered_words = {"pA", "pB", "pC", "wyk", "ćw", "klin"}


# Helper function to calculate the current week number
def get_week_number():
    base_date = datetime(2024, 5, 13)
    current_date = datetime.now()
    week_diff = (current_date - base_date).days // 7
    return 617 + week_diff  # Adjusting 617 for 13.05.2023


# Function to get and prepare the calendar for download
def get_calendar(group):
    # Construct the URL
    week_number = get_week_number()
    url = f"http://web0.awf.poznan.pl/plan/plan.php?type=0&id=88436&cvsfile=true&w={week_number}"

    # Download the calendar file
    response = requests.get(url)
    response.raise_for_status()  # Ensure we got a successful response

    # Load and process the calendar
    cal = Calendar.from_ical(response.content)
    for component in cal.walk("vevent"):
        summary = component.get("summary")
        # Determine the prefix based on the type of class
        title = ""
        if "wyk" in summary:
            title = "W - "
            component.add("categories", "wyklad")
        elif "ćw" in summary:
            title = "ĆW - "
            component.add("categories", "cwiczenia")
        elif "klin" in summary:
            title = "K - "
            component.add("categories", "klinika")

        # Extract the abbreviation and add it to the title
        abbreviation = summary.split()[0]
        description = summary[len(abbreviation) :].strip()

        # Handle groups
        if abbreviation[-1] in ["A", "B", "C"]:
            if abbreviation[-2] == "p" and abbreviation[-1] == group[-1]:
                abbreviation = abbreviation[:-2]
            elif abbreviation[-2] == "p" and abbreviation[-1] != group[-1]:
                cal.subcomponents.remove(component)
                continue

        component["summary"] = title + legend.get(abbreviation, abbreviation)
        component["description"] = " ".join(
            [word for word in description.split() if word not in filtered_words]
        )

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

group = st.selectbox("Wybierz grupę:", ["grupa A", "grupa B", "grupa C"], index=1)

if group:
    calendar_bytes, calendar_filename = get_calendar(group)
    st.download_button(
        label="Pobierz",
        data=calendar_bytes,
        file_name=calendar_filename,
        mime="text/calendar",
        disabled=calendar_filename[9] != group[-1], 
    )

st.markdown("---")
st.image("https://i.pinimg.com/736x/23/86/e3/2386e3023848e6754b8f0ad9597676a7.jpg")
