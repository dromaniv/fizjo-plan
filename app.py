import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import re
import streamlit as st
from icalendar import Calendar, Event
import pytz
from googletrans import Translator
import yaml

# Constants
URL = "https://publico.agcp.ipleiria.pt/paginas/ScheduleRptCursosSemanalPublico.aspx"
PORTUGAL_TZ = pytz.timezone("Europe/Lisbon")
translator = Translator()


# Helper functions
def get_form_values(soup):
    """Extract hidden form values required for POST requests."""
    return {tag["name"]: tag["value"] for tag in soup.select("input[name][value]")}


def submit_form(url, soup, **kwargs):
    """Submit form data and return the updated BeautifulSoup object."""
    payload = get_form_values(soup)
    payload.update(kwargs)
    response = requests.post(url, data=payload)
    return BeautifulSoup(response.content, "html.parser")


def get_current_week(date):
    """Calculate the start date of the current week."""
    start_of_week = date - timedelta(days=date.weekday())
    return start_of_week.strftime("%d-%m-%Y")


@st.cache_data(ttl=28800, show_spinner=False)
def fetch_events(week, year):
    """Fetch events data from the website based on the selected week and year."""
    soup = BeautifulSoup(requests.get(URL).content, "html.parser")

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
            "ctl00$PlaceHolderMain$ddlSemanas": get_current_week(week),
            "__EVENTTARGET": "ctl00$PlaceHolderMain$ddlSemanas",
        },
    ]

    for step in steps:
        soup = submit_form(URL, soup, **step)

    script = soup.find("script", string=re.compile("c.events = "))
    if script:
        matches = re.search(r"c\.events = (\[.*?\]);", script.string, re.DOTALL)
        return json.loads(matches.group(1)) if matches else []
    return []


def convert_to_ical(events, translate=False, subjects=[]):
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

        subject = next(
            (subject for subject in subjects if subject["title"] in data[0]), None
        )

        match subject["year"]:
            case 2:
                color = "yellow"
            case 3:
                color = "green"
            case 4:
                color = "red"
            case _:
                color = "blue"

        summary_text = data[0]
        if translate:
            try:
                summary_text = translator.translate(data[0], src="pt", dest="pl").text
            except Exception:
                pass

        ical_event = Event()
        ical_event.add("summary", summary_text)
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
st.title("Leiria - Plan Zajęć 🇵🇹")

# Option to view the legend.yaml file
with st.expander("Wybrane przedmioty"):
    with open("legend.yaml", "r", encoding="utf-8") as f:
        legend_content = f.read()
    st.text(legend_content)

translate = st.checkbox("Tłumaczenie nazw zajęć", value=True)
selected_year = st.radio("Wybierz rok:", ["Auto", "2", "3", "4"], horizontal=True)

# Date picker for selecting the week
selected_date = st.date_input("Wybierz tydzień:", datetime.now())

if selected_date < datetime(2024, 9, 9).date():
    st.error("Brak danych o zajęciach na wybrany tydzień :(")
    st.stop()

# Fetch events data based on the selected week and year
with st.spinner("Pobieranie danych..."):
    events = []
    if selected_year == "Auto":
        with open("legend.yaml", "r", encoding="utf-8") as f:
            subjects = yaml.safe_load(f).get("subjects", [])

        for subject in subjects:
            subject_events = fetch_events(selected_date, subject["year"])
            events.extend(
                event
                for event in subject_events
                if subject["title"] in event["InnerHTML"]
                and any(group in event["InnerHTML"] for group in subject["groups"])
            )
    else:
        events = fetch_events(selected_date, selected_year)
    calendar_bytes = convert_to_ical(events, translate, subjects)

# Handle the display and download of the calendar
if events:
    if st.download_button(
        label=":rainbow[Pobierz / Importuj]",
        data=calendar_bytes,
        file_name=f'plan_{selected_date.strftime("%Y-%m-%d")}.ics',
        mime="text/calendar",
    ):
        st.balloons()
else:
    st.error("Brak danych o zajęciach na wybrany tydzień :(")


st.markdown("<br />", unsafe_allow_html=True)
