# main.py — slim launcher for Student Sign-Up + Admin + BIO 205 Tutor + Quizlet + Study Tools
# Run with:  streamlit run main.py

import pathlib
from datetime import datetime
from typing import List, Dict

import pytz
import streamlit as st

# Local modules for the sign-up app
from bookings import load_bookings
from slots import generate_slots
from ui_components import show_student_signup, show_admin_view

# Tutor chat UI
from tutor import render_chat

# ---------------------- App Config ----------------------
st.set_page_config(page_title="Cuesta Lab | Sign-Up + Tutor", layout="wide")

# ---------------------- Secrets -------------------------
# Use .get so app still loads if a secret is absent (you can handle None in the UI)
ADMIN_PASSCODE = st.secrets.get("ADMIN_PASSCODE")
AVAILABILITY_PASSCODE = st.secrets.get("AVAILABILITY_PASSCODE")  # ok if unused

# Optional: link lists from secrets (preferred), else use local fallbacks.
# Example secrets.toml:
# [[QUIZLET_LINKS]] lab = "Lab 1 – Intro" url = "https://quizlet.com/..."
# [[TOOLS_LINKS]]   name = "Photogrammetry Library" desc = "3D scans..." url = "https://..."
QUIZLET_LINKS: List[Dict[str, str]] = st.secrets.get("QUIZLET_LINKS", []) or [
    {"lab": "Lab Exam 1", "url": "https://quizlet.com/user/jonathan_okerblom/folders/lab-exam-1?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 2 – Cytology, Histology and Integumentary", "url": "https://quizlet.com/user/jonathan_okerblom/folders/cytology-histology-and-integumentary-lab-exam-2?i=4yh5vi&x=1xqt"},
    {"lab": "Lab 3 – Tissues",                   "url": "https://quizlet.com/"},
    {"lab": "Lab 4 – Integumentary",             "url": "https://quizlet.com/"},
    {"lab": "Lab 5 – Skeletal (Bones & Markings)","url": "https://quizlet.com/"},
    {"lab": "Lab 6 – Articulations",             "url": "https://quizlet.com/"},
    {"lab": "Lab 7 – Muscular (Names/Actions)",  "url": "https://quizlet.com/"},
    {"lab": "Lab 8 – Nervous (CNS/PNS)",         "url": "https://quizlet.com/"},
    {"lab": "Lab 9 – Special Senses",            "url": "https://quizlet.com/"},
    {"lab": "Lab 10 – Cardiovascular",           "url": "https://quizlet.com/"},
]

TOOLS_LINKS: List[Dict[str, str]] = st.secrets.get("TOOLS_LINKS", []) or [
    {
        "name": "Photogrammetry Library (3D Anatomy Models)",
        "desc": "High-res 3D scans of our lab models for at-home review.",
        "url": "https://example.edu/photogrammetry",
    },
    {
        "name": "Anki Decks (free)",
        "desc": "Download spaced-repetition decks aligned to BIO 205 labs.",
        "url": "https://ankiweb.net/",
    },
    {
        "name": "Anki How-To",
        "desc": "Quick start on installing Anki and syncing decks.",
        "url": "https://apps.ankiweb.net/",
    },
]

# ---------------------- Timezone ------------------------
pacific = pytz.timezone("US/Pacific")
now = datetime.now(pacific)

# ----------------- Data for Sign-Up/Admin ----------------
bookings_df = load_bookings()
slo_slots_by_day, ncc_slots_by_day = generate_slots()

# --------------------- Page Renderers --------------------
def render_quizlet():
    st.title("Quizlet Sets (Labs 1–10)")
    st.caption("Curated practice for each lab — opens in a new tab.")
    for item in QUIZLET_LINKS:
        cols = st.columns([4, 1])
        cols[0].markdown(f"**{item.get('lab','(Unnamed)')}**")
        cols[1].markdown(f"[Open ➜]({item.get('url','#')})")

def render_tools():
    st.title("Study Tools: Photogrammetry & Anki")
    st.caption("Extra practice resources built by our team.")
    for t in TOOLS_LINKS:
        with st.container(border=True):
            st.markdown(f"**{t.get('name','(Untitled)')}**")
            if t.get("desc"):
                st.write(t["desc"])
            st.markdown(f"[Open ➜]({t.get('url','#')})")

def render_tutor_page():
    st.title("BIO 205 Tutor — Human Anatomy")

    # Ensure a knowledge dir exists
    if "bio205_knowledge_dir" not in st.session_state:
        st.session_state["bio205_knowledge_dir"] = "./bio205_knowledge"

    knowledge_dir = pathlib.Path(st.session_state["bio205_knowledge_dir"])
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    # Optionally seed logistics file from secrets once
    logistics_secret = st.secrets.get("BIO205_LOGISTICS_MD")
    if logistics_secret:
        f = knowledge_dir / "bio205_logistics.md"
        if not f.exists():
            f.write_text(logistics_secret, encoding="utf-8")

    # Render the tutor chat UI
    render_chat()

# --------------------- Navigation -----------------------
PAGES = {
    "Sign-Up": lambda: (
        st.title("Student Appointment Sign-Up"),
        show_student_signup(bookings_df, slo_slots_by_day, ncc_slots_by_day, now),
    ),
    "Admin View": lambda: (
        st.title("Admin View"),
        show_admin_view(
            bookings_df,
            slo_slots_by_day,
            ncc_slots_by_day,
            ADMIN_PASSCODE,
        ),
    ),
    "BIO 205 Tutor": render_tutor_page,
    "Quizlet": render_quizlet,
    "Study Tools": render_tools,
}

st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio("Go to:", list(PAGES.keys()), index=0)

# ---------------------- Routing -------------------------
PAGES[selected_tab]()

# ---------------------- Footer (optional) ----------------
st.sidebar.markdown("---")
st.sidebar.caption("Cuesta BIO 205 • SLO & North Campus")

