import re
import requests
import streamlit as st
import hashlib
import pytz
from datetime import datetime, timedelta
from icalendar import Calendar
import yaml

# Load the YAML file
with open("legend.yaml", "r") as file:
    data = yaml.safe_load(file)
    legend = data["abbreviations"]

# --- Revised: global font size injection (static, no sidebar) ---


def inject_global_css():
    """Inject global CSS with essential styling only (no font size overrides)."""
    st.markdown(
        f"""
        <style>
        /* Reduced spacing rules */
        .element-container {{
            margin-bottom: 0.25rem !important;
            margin-top: 0.125rem !important;
        }}
        .stSelectbox, .stRadio, .stDateInput {{
            margin-bottom: 0.25rem !important;
            margin-top: 0.125rem !important;
        }}
        /* Increase spacing between radio button options */
        .stRadio > div > label {{
            margin-right: 2rem !important;
        }}
        .stButton {{
            margin-top: 0.25rem !important;
            margin-bottom: 0.125rem !important;
        }}
        .stAlert {{
            margin-top: 0.25rem !important;
            margin-bottom: 0.25rem !important;
        }}
        /* Add padding to main content */
        .main .block-container {{
            padding-top: 0.25rem !important;
            padding-bottom: 0.25rem !important;
        }}
        /* Headings - reduced spacing and smaller title font */
        h1, .stMarkdown h1, .stApp > div > div > div > h1, 
        [data-testid="stHeader"] h1, .element-container h1 {{
            font-size: 1.3rem !important;
            margin-bottom: 0.5rem !important;
            margin-top: 0.5rem !important;
        }}
        h2, .stMarkdown h2 {{
            margin-bottom: 0.25rem !important;
            margin-top: 0.25rem !important;
        }}
        h3, .stMarkdown h3 {{
            margin-bottom: 0.125rem !important;
            margin-top: 0.125rem !important;
        }}
        /* Buttons */
        .stButton button, .stDownloadButton button {{
            padding: 0.75rem 1.25rem !important;
        }}
        /* Make download buttons full width like alerts */
        .stDownloadButton button {{
            width: 100% !important;
            padding: 1rem 1.25rem !important;
        }}
        /* Padding below download button */
        .stDownloadButton {{
            margin-bottom: 1.25rem !important;
        }}
        /* Inputs labels */
        label, .stSelectbox label, .stRadio label, .stDateInput label {{
            margin-bottom: 0.125rem !important;
        }}
        
        /* LIGHT THEME */
        /* Compact pill stats with reduced spacing */
        .pill-stats {{
            display:flex; flex-wrap:wrap; gap:.35rem; margin:.25rem 0 .5rem 0;
        }}
        .pill-stats .pill {{
            background:#f8fafc; color:#1e293b; border:1px solid #e2e8f0; border-radius:999px;
            padding:.3rem .75rem; font-size:.8rem; font-weight:600; letter-spacing:.25px; display:inline-flex; align-items:center;
            box-shadow:0 1px 3px rgba(0,0,0,.1);
        }}
        .pill-stats .pill span {{ opacity:.7; font-weight:500; margin-right:.3rem; }}
        .pill.tag-w {{ background:#e2e8f0; color:#475569; }}
        .pill.tag-c {{ background:#ffe4e6; color:#be185d; }}
        .pill.tag-k {{ background:#e0f2fe; color:#0369a1; }}
        .pill.tag-i {{ background:#fde4cf; color:#c2410c; }}
        
        /* Light theme insight cards */
        .insight-card {{
            background:linear-gradient(145deg,#ffffff 0%,#f8fafc 90%); 
            color:#1e293b; 
            padding:.8rem 1rem; 
            border:1px solid #e2e8f0; 
            border-radius:14px; 
            margin:.3rem 0 .8rem 0; 
            position:relative; 
            overflow:hidden;
            box-shadow:0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -1px rgba(0,0,0,.06);
        }}
        .insight-card:before {{
            content:""; position:absolute; inset:0; 
            background:radial-gradient(circle at 85% -10%,rgba(99,102,241,.08),transparent 60%); 
            pointer-events:none;
        }}
        .insight-card h4 {{ margin:0 0 .3rem 0; font-size:1.05rem; letter-spacing:.5px; color:#0f172a; }}
        .insight-card > div:not(.insight-meta):not(.mini-bars):not(.sparkline) {{ font-size: 1rem !important; }}
        .insight-meta {{ 
            display:flex; flex-wrap:wrap; gap:.5rem; margin-top:.4rem; 
            font-size:.7rem; opacity:.7; text-transform:uppercase; letter-spacing:.6px; 
            color:#64748b;
        }}
        .sparkline {{ height:32px; margin:.25rem 0 .15rem 0; }}
        .sparkline svg {{ width:100%; height:32px; overflow:visible; }}
        .mini-bars {{ display:flex; gap:3px; align-items:flex-end; height:32px; }}
        .mini-bars .bar {{ 
            flex:1; 
            background:linear-gradient(180deg,#6366f1,#4f46e5); 
            border-radius:3px 3px 2px 2px; 
            position:relative; 
        }}
        .mini-bars .bar span {{ 
            position:absolute; top:-13px; left:50%; transform:translateX(-50%); 
            font-size:.55rem; font-weight:500; color:#64748b; 
        }}
        .mini-bars .bar.busy {{ background:linear-gradient(180deg,#ef4444,#dc2626); }}
        .pct-badges {{ display:flex; flex-wrap:wrap; gap:.35rem; margin-top:.35rem; }}
        .pct-badges .pct {{ 
            font-size:.65rem; padding:.2rem .5rem; border-radius:6px; 
            background:#e2e8f0; color:#475569; letter-spacing:.4px; 
        }}
        /* Progress bar and status text - better targeting */
        .stProgress, .stProgress *, [data-testid="stProgress"], 
        .stProgress .stMarkdown, .element-container .stProgress *,
        .stProgress [class*="st-emotion-cache"],
        .st-emotion-cache-183lzff {{
            font-size: 0.6rem !important;
        }}
        .expander-stats > div {{ background:rgba(241,245,249,.5); }}
        
        /* DARK THEME */
        @media (prefers-color-scheme: dark) {{
          /* Pills in dark mode */
          .pill-stats .pill {{ 
            background:#1e293b; color:#f1f5f9; border-color:#334155; 
            box-shadow:0 1px 3px rgba(0,0,0,.3);
          }}
          .pill.tag-w {{ background:#334155; color:#cbd5e1; }}
          .pill.tag-c {{ background:#4c1d1d; color:#fca5a5; }}
          .pill.tag-k {{ background:#1e3a5f; color:#7dd3fc; }}
          .pill.tag-i {{ background:#513626; color:#fdba74; }}
          .pill-stats .pill span {{ color:#cbd5e1; opacity:.8; }}
          
          /* Dark theme insight cards */
          .insight-card {{
            background:linear-gradient(145deg,#1e293b 0%,#0f172a 90%); 
            color:#f1f5f9; 
            border-color:#334155;
            box-shadow:0 4px 6px -1px rgba(0,0,0,.4), 0 2px 4px -1px rgba(0,0,0,.3);
          }}
          .insight-card:before {{
            background:radial-gradient(circle at 85% -10%,rgba(99,102,241,.25),transparent 60%);
          }}
          .insight-card h4 {{ color:#f1f5f9; }}
          .insight-meta {{ color:#94a3b8; opacity:.85; }}
          .mini-bars .bar span {{ color:#94a3b8; }}
          .pct-badges .pct {{ background:#334155; color:#e2e8f0; }}
          .expander-stats > div {{ background:rgba(15,23,42,.55); }}
        }}
        
        /* Additional Streamlit theme support */
        [data-theme="light"] .insight-card,
        .stApp[data-theme="light"] .insight-card {{
            background:linear-gradient(145deg,#ffffff 0%,#f8fafc 90%); 
            color:#1e293b; 
            border-color:#e2e8f0;
        }}
        [data-theme="dark"] .insight-card,
        .stApp[data-theme="dark"] .insight-card {{
            background:linear-gradient(145deg,#1e293b 0%,#0f172a 90%); 
            color:#f1f5f9; 
            border-color:#334155;
        }}
        </style>
    """,
        unsafe_allow_html=True,
    )


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


def generate_event_hash(component):
    def norm(val):
        if hasattr(val, "dt"):
            # icalendar property: get datetime and format
            dt = val.dt
            return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        return str(val).strip()
    include_fields = ["summary", "dtstart", "dtend"]
    hash_data = [f"{f}:{norm(component.get(f))}" for f in include_fields if component.get(f)]
    combined = "|".join(hash_data)
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:8]

# Function to get and prepare the calendar for download
@st.cache_data(ttl=28800, show_spinner=False)
def get_calendar(week_number, group="Grupa B"):
    # Construct the URL
    url = f"http://web0.awf.poznan.pl/plan/plan.php?type=NaN&id=95765&cvsfile=true&w={week_number}"

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
        if "aliczeni" in lower or "gzamin" in lower:
            try:
                abbreviation = summary.split("  ")[0]
            except Exception:
                abbreviation = summary
        else:
            abbreviation = summary.split()[0]
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
                cal.subcomponents.remove(component)
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
        # Generate hash and add metadata to description
        event_hash = generate_event_hash(component)
        generated_at = datetime.now(pytz.timezone("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M:%S")
        # Append metadata to description
        current_description = component.get("description", "")
        metadata = f"\n\n--- Event Metadata ---\nHash: {event_hash}\nGenerated at: {generated_at}\nGenerated by: fizjo-plan"
        component["description"] = current_description + metadata

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


# Function to get and prepare the calendar for the full semester
def get_full_semester_calendar(group="Grupa B"):
    start_of_semester = datetime(2025, 10, 1)
    end_of_semester = datetime(2026, 2, 28)
    start_week = get_week_number(start_of_semester)
    end_week = get_week_number(end_of_semester)
    full_cal = Calendar()
    full_cal.add("prodid", "-//ATS4//Plan zajęć.//PL")
    full_cal.add("version", "2.0")
    full_cal.add("calscale", "GREGORIAN")
    full_cal.add("X-WR-CALNAME", f"Plan zajęć.")
    full_cal.add("X-WR-TIMEZONE", "Europe/Warsaw")
    total_weeks = end_week - start_week + 1
    progress_bar = st.progress(0)
    status_text = st.empty()
    empty_weeks = []
    has_any_events = False
    counts = {k: 0 for k in _DEF_TYPE_KEYS}
    per_week_events = {}
    try:
        for i, week in enumerate(range(start_week, end_week + 1)):
            status_text.text(
                f"Pobieranie tygodnia {i+1}/{total_weeks} ({get_date_from_week_number(week)})"
            )
            try:
                calendar_bytes, _, _week_stats = get_calendar(week, group)
                cal = Calendar.from_ical(calendar_bytes)  # type: ignore[arg-type]
                events = list(cal.walk("vevent"))
                per_week_events[week] = len(events)
                if not events:
                    empty_weeks.append(week)
                else:
                    has_any_events = True
                    for component in events:
                        summary = component.get("summary", "")
                        t = _classify(summary)
                        if t in counts:
                            counts[t] += 1
                        full_cal.add_component(component)
            except Exception:
                empty_weeks.append(week)
            progress_bar.progress((i + 1) / total_weeks)
        if not has_any_events:
            status_text.error("Brak planu zajęć dla semestru :(")
            return None, None, None
        if empty_weeks:
            empty_week_dates = [get_date_from_week_number(w) for w in empty_weeks]
            st.warning(
                "Brak danych dla następujących tygodni:\n\n"
                + "  \n".join(empty_week_dates)
            )
            status_text.text("")
        else:
            status_text.success("Gotowe!")
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
    finally:
        progress_bar.empty()


# --- New visual helpers ---

_DOW_LABELS = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]
_DOW_LABELS_FULL = [
    "Poniedziałek",
    "Wtorek",
    "Środa",
    "Czwartek",
    "Piątek",
    "Sobota",
    "Niedziela",
]


def _sparkline(values, stroke="#6366f1", fill="#4f46e5"):
    if not values:
        return ""
    w, h = 160, 30
    if len(values) == 1:
        values = [values[0], values[0]]
    mx = max(values) or 1
    step = w / (len(values) - 1)
    points = " ".join(f"{i*step:.2f},{h - (v/mx)*h:.2f}" for i, v in enumerate(values))
    path = f"M {points}"
    area = path + f" L {(len(values)-1)*step:.2f},{h} L 0,{h} Z"
    return f"<svg viewBox='0 0 {w} {h}' preserveAspectRatio='none'><path d='{area}' fill='{fill}33'></path><path d='{path}' fill='none' stroke='{stroke}' stroke-width='2' stroke-linejoin='round' stroke-linecap='round'></path></svg>"


def render_compact_week_stats(stats: dict):
    if not stats:
        return
    pct = stats.get("Procenty", {})
    html = f"""
    <div class='pill-stats'>
      <div class='pill'><span>Razem</span>{stats.get('Razem',0)}</div>
      <div class='pill tag-w'><span>Wykł.</span>{stats.get('Wykłady',0)} ({pct.get('Wykłady',0)}%)</div>
      <div class='pill tag-c'><span>Ćw.</span>{stats.get('Ćwiczenia',0)} ({pct.get('Ćwiczenia',0)}%)</div>
      <div class='pill tag-k'><span>Klin.</span>{stats.get('Kliniczne',0)} ({pct.get('Kliniczne',0)}%)</div>
      <div class='pill tag-i'><span>Inne</span>{stats.get('Inne',0)} ({pct.get('Inne',0)}%)</div>
      <div class='pill'><span>Dni</span>{stats.get('Dni z zajęciami',0)}</div>
      <div class='pill'><span>Śr./dzień</span>{stats.get('Średnio / dzień',0)}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_compact_sem_stats(stats: dict):
    if not stats:
        return
    pct = stats.get("Procenty", {})
    html = f"""
    <div class='pill-stats'>
      <div class='pill'><span>Tyg.</span>{stats.get('Tygodni (łącznie)',0)}</div>
      <div class='pill'><span>Z zaj.</span>{stats.get('Tygodni z zajęciami',0)}</div>
      <div class='pill'><span>Puste</span>{stats.get('Puste tygodnie',0)}</div>
      <div class='pill'><span>Razem</span>{stats.get('Razem',0)}</div>
      <div class='pill tag-w'><span>Wykł.</span>{stats.get('Wykłady',0)} ({pct.get('Wykłady',0)}%)</div>
      <div class='pill tag-c'><span>Ćw.</span>{stats.get('Ćwiczenia',0)} ({pct.get('Ćwiczenia',0)}%)</div>
      <div class='pill tag-k'><span>Klin.</span>{stats.get('Kliniczne',0)} ({pct.get('Kliniczne',0)}%)</div>
      <div class='pill tag-i'><span>Inne</span>{stats.get('Inne',0)} ({pct.get('Inne',0)}%)</div>
      <div class='pill'><span>Śr./tydz.</span>{stats.get('Średnio / tydzień',0)}</div>
      <div class='pill'><span>Max/tydz.</span>{stats.get('Max / tydzień',0)}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_week_insights(stats: dict):
    if not stats:
        return
    per_day = stats.get("per_day", {})
    total = stats.get("Razem", 0)
    if not total:
        return
    max_day_idx = max(per_day, key=lambda k: per_day[k]) if per_day else None
    busiest = (
        _DOW_LABELS_FULL[max_day_idx]
        if max_day_idx is not None and per_day[max_day_idx] > 0
        else "—"
    )
    pcts = stats.get("Procenty", {})
    sentence = f"{total} wydarzenia" if total in (2, 3, 4) else f"{total} wydarzeń"
    summary = (
        f"{sentence} w {stats.get('Dni z zajęciami',0)} dniach.\n\nNajbardziej obciążony dzień: {busiest}.\n\n"
        f"Struktura: wykł. {pcts.get('Wykłady',0)}%, ćw. {pcts.get('Ćwiczenia',0)}%, klin. {pcts.get('Kliniczne',0)}%, inne {pcts.get('Inne',0)}%."
    )
    # Daily bars
    maxv = max(per_day.values()) if per_day else 1
    day_bars = []
    for i, label in enumerate(_DOW_LABELS):
        v = per_day.get(i, 0)
        h = 6 + ((v / maxv) * 26 if maxv else 0)
        cls = "bar busy" if i == max_day_idx and v > 0 else "bar"
        day_bars.append(
            f"<div class='{cls}' style='height:{h}px'><span>{v}</span></div>"
        )
    bars_html = "<div class='mini-bars'>" + "".join(day_bars) + "</div>"
    st.markdown(
        f"""
        <div class='insight-card'>
          <h4>Tydzień: {stats.get('date_range','')}</h4>
          <div>{summary}</div>
          {bars_html}
          <div class='insight-meta'>Dni aktywne: {stats.get('Dni z zajęciami',0)} • Średnio/dzień: {stats.get('Średnio / dzień',0)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sem_insights(stats: dict):
    if not stats:
        return
    total = stats.get("Razem", 0)
    if not total:
        return
    pct = stats.get("Procenty", {})
    per_week = stats.get("per_week_events", {})
    ordered_counts = [per_week[w] for w in sorted(per_week.keys())]
    spark = _sparkline(ordered_counts)
    non_empty = stats.get("Tygodni z zajęciami", 0)
    summary = (
        f"{total} zajęć w {non_empty} tygodniach aktywnych.\n\n  "
        f"Średnio {stats.get('Średnio / tydzień',0)} / tydz. (max {stats.get('Max / tydzień',0)}).\n\n"
        f"Struktura: wykł. {pct.get('Wykłady',0)}%, ćw. {pct.get('Ćwiczenia',0)}%, klin. {pct.get('Kliniczne',0)}%, inne {pct.get('Inne',0)}%."
    )
    st.markdown(
        f"""
        <div class='insight-card'>
          <h4>Semestr: {stats.get('Zakres','')}</h4>
          <div>{summary}</div>
          <div class='sparkline'>{spark}</div>
          <div class='insight-meta'>Puste tyg.: {stats.get('Puste tygodnie',0)} • Tyg. łącznie: {stats.get('Tygodni (łącznie)',0)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
    ("Cały tydzień", "Cały semestr"),
    horizontal=True,
)

if option == "Cały tydzień":
    date = st.date_input("Wybierz tydzień:", value=datetime.now())

    download_btn_placeholder = st.empty()
    if group:
        week = get_week_number(date)
        try:
            with st.spinner("Pobieranie danych..."):
                calendar_bytes, calendar_filename, week_stats = get_calendar(
                    week, group
                )
        except Exception:
            st.error("Brak danych dla tego tygodnia :(")
            st.stop()
        if calendar_bytes:
            if download_btn_placeholder.download_button(
                label=":rainbow[Pobierz / Importuj]",
                data=calendar_bytes,
                file_name=calendar_filename,
                mime="text/calendar",
                key="week_download",
            ):
                st.balloons()
            render_compact_week_stats(week_stats)
            render_week_insights(week_stats)
            # if week_stats and week_stats.get("Razem"):
            #     with st.expander("Szczegóły liczbowe", expanded=False):
            #         cols = st.columns(6)
            #         metric_order = ["Razem","Wykłady","Ćwiczenia","Kliniczne","Inne","Dni z zajęciami"]
            #         for col, key_ in zip(cols, metric_order): col.metric(key_, week_stats.get(key_,0))
        else:
            st.error("Nie udało się pobrać planu zajęć")
elif option == "Cały semestr":
    if group:
        try:
            calendar_bytes, calendar_filename, sem_stats = get_full_semester_calendar(
                group
            )
            if calendar_bytes:
                if st.download_button(
                    label=":rainbow[Pobierz / Importuj]",
                    data=calendar_bytes,
                    file_name=calendar_filename,
                    mime="text/calendar",
                    key="semester_download",
                ):
                    st.balloons()
                render_compact_sem_stats(sem_stats)
                render_sem_insights(sem_stats)
                # if sem_stats and sem_stats.get("Razem"):
                #     with st.expander("Szczegóły liczbowe", expanded=False):
                #         row1 = st.columns(5)
                #         for col,key_ in zip(row1,["Razem","Wykłady","Ćwiczenia","Kliniczne","Inne"]): col.metric(key_, sem_stats.get(key_,0))
                #         row2 = st.columns(5)
                #         for col,key_ in zip(row2,["Tygodni (łącznie)","Tygodni z zajęciami","Puste tygodnie","Średnio / tydzień","Max / tydzień"]): col.metric(key_, sem_stats.get(key_,0))
        except Exception as e:
            st.error(f"Wystąpił błąd: {e}")
    else:
        st.warning("Proszę wybrać grupę.")
else:
    st.warning("Proszę wybrać zakres.")

st.markdown("<br>", unsafe_allow_html=True)
