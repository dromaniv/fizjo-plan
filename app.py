import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import re
import streamlit as st
from icalendar import Calendar, Event
import pytz
from googletrans import Translator

# Constants
URL = "https://publico.agcp.ipleiria.pt/paginas/ScheduleRptCursosSemanalPublico.aspx"
PORTUGAL_TZ = pytz.timezone("Europe/Lisbon")
translator = Translator()


# Helper functions
def get_form_values(soup):
    """Extract hidden form values required for POST requests."""
    return {
        tag["name"]: tag["value"]
        for tag in soup.select("input[name][value]")
        if tag["name"] in ["__VIEWSTATE", "__EVENTVALIDATION"]
    }


def submit_form(session, url, soup, **kwargs):
    """Submit form data and return the updated BeautifulSoup object."""
    payload = get_form_values(soup)
    payload.update(kwargs)
    response = session.post(url, data=payload)
    return BeautifulSoup(response.content, "html.parser")


def current_week(date):
    """Calculate the start date of the current week."""
    start_of_week = date - timedelta(days=date.weekday())
    return start_of_week.strftime("%d-%m-%Y")


# Core functions
def fetch_events(week, year):
    """Fetch events data from the website based on the selected week."""
    session = requests.Session()
    soup = BeautifulSoup(session.get(URL).content, "html.parser")

    steps = [
        {
            "ctl00$PlaceHolderAGCPUO$ddlUO": "5",
            "__EVENTTARGET": "ctl00$PlaceHolderAGCPUO$ddlUO",
        },
        {
            "ctl00$PlaceHolderMain$ddlCursos": "9504",
            "__EVENTTARGET": "ctl00$PlaceHolderAGCPUO$ddlCursos",
        },
        {
            "ctl00$PlaceHolderMain$ddlAnosCurr": year,
            "__EVENTTARGET": "ctl00$PlaceHolderMain$ddlAnosCurr",
        },
        {
            "ctl00$PlaceHolderMain$ddlSemanas": current_week(week),
            "__EVENTTARGET": "ctl00$PlaceHolderMain$ddlSemanas",
        },
    ]

    for step in steps:
        soup = submit_form(session, URL, soup, **step)

    script = soup.find("script", string=re.compile("c.events = "))
    if script:
        matches = re.search(r"c\.events = (\[.*?\]);", script.string, re.DOTALL)
        if matches:
            return json.loads(matches.group(1))
    return []


def convert_to_ical(events, translate=False):
    """Convert fetched events data to iCalendar format."""
    cal = Calendar()
    cal.add("prodid", "-//Leiria Schedule//Plan zajec//PT")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Plan zajec")
    cal.add("x-wr-timezone", "Europe/Lisbon")

    for event in events:
        data = event["InnerHTML"].split(" - ")
        color = "red" if "TP" in data[0] else "blue"

        ical_event = Event()
        ical_event.add(
            "summary",
            (
                translator.translate(data[0], src="pt", dest="pl").text
                if translate
                else data[0]
            ),
        )
        ical_event.add("description", event["InnerHTML"])
        ical_event.add("location", data[3])
        ical_event.add("color", color)

        start_time = datetime.strptime(
            event["Start"], "%B %d, %Y %H:%M:%S %z"
        ).astimezone(PORTUGAL_TZ) - timedelta(hours=1)
        end_time = datetime.strptime(event["End"], "%B %d, %Y %H:%M:%S %z").astimezone(
            PORTUGAL_TZ
        ) - timedelta(hours=1)

        ical_event.add("dtstart", start_time)
        ical_event.add("dtend", end_time)

        cal.add_component(ical_event)

    return cal.to_ical()


# Streamlit app setup
st.set_page_config(page_title="Plan Zajęć", page_icon="🌴")

st.markdown(
    """
    <style>
    .stApp {
        background-image: url("https://i.postimg.cc/LXttDXJB/leiria-5.png");
        background-size: cover;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Leiria - Plan Zajęć 🇵🇹 ")

translate = st.checkbox("Tłumaczenie nazw zajęć", value=True)

selected_year = st.radio(
    "Wybierz rok:", ["1", "2", "3", "4", "5"], horizontal=True, index=None
)

# Wait until the user selects a year
while selected_year is None:
    st.stop()

# Date picker for selecting the week
selected_date = st.date_input("Wybierz tydzień:", datetime.now())

# Loading spinner
with st.spinner("Pobieranie danych..."):
    events = fetch_events(selected_date, selected_year)
    calendar_bytes = convert_to_ical(events, translate)

# Handle the display and download of the calendar
if events:
    st.download_button(
        label=":rainbow[Pobierz / Importuj]",
        data=calendar_bytes,
        file_name=f'plan_{selected_date.strftime("%Y-%m-%d")}.ics',
        mime="text/calendar",
    )
else:
    st.error("Brak danych o zajęciach na wybrany tydzień :(")

st.markdown("<br />", unsafe_allow_html=True)
