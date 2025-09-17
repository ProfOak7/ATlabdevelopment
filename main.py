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

# ---------------------- New Quizlet and Study Tool Links - Code could pull from Secrets but just posted here -------------------------
QUIZLET_LINKS: List[Dict[str, str]] = st.secrets.get("QUIZLET_LINKS", []) or [
    {"lab": "Lab Exam 1 Objectives (Canvas Exam Only)", "url": "https://quizlet.com/user/jonathan_okerblom/folders/lab-exam-1?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 2 – Cytology, Histology and Integumentary", "url": "https://quizlet.com/user/jonathan_okerblom/folders/cytology-histology-and-integumentary-lab-exam-2?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 3 – Skeletal System",                   "url": "https://quizlet.com/user/jonathan_okerblom/folders/skeletal-system-lab-exam-3?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 4 – Muscular System",             "url": "https://quizlet.com/user/jonathan_okerblom/folders/muscular-system-lab-exam-4?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 5 – Nervous System", "url": "https://quizlet.com/user/jonathan_okerblom/folders/nervous-system-lab-exam-5?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 6 – Sensory and Special Senses",             "url": "https://quizlet.com/user/jonathan_okerblom/folders/sensory-and-special-senses-lab-exam-6-oral?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 7 – Circulatory/Lymphatic Systems",  "url": "https://quizlet.com/user/jonathan_okerblom/folders/circulatorylymphatic-systems-lab-exam-7?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 8 – Respiratory System",         "url": "https://quizlet.com/858726102/respiratory-system-lab-8-exam-flash-cards/?i=4yh5vi&x=1jqt"},
    {"lab": "Lab Exam 9 – Digestive System",            "url": "https://quizlet.com/user/jonathan_okerblom/folders/digestive-system-lab-exam-9?i=4yh5vi&x=1xqt"},
    {"lab": "Lab Exam 10 – Urinary and Reproductive Systems",           "url": "https://quizlet.com/user/jonathan_okerblom/folders/urinary-and-reproductive-lab-10?i=4yh5vi&x=1xqt"},
]

TOOLS_LINKS: List[Dict[str, str]] = st.secrets.get("TOOLS_LINKS", []) or [
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
    st.caption("Curated practice for the oral exam of each lab — opens in a new tab.")
    for item in QUIZLET_LINKS:
        cols = st.columns([4, 1])
        cols[0].markdown(f"**{item.get('lab','(Unnamed)')}**")
        cols[1].markdown(f"[Open ➜]({item.get('url','#')})")

def render_tools():
    st.title("Additional Study Tools")
    st.caption("Extra practice resources built by our team (currently under construction).")
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
    "Additional Study Tools": render_tools,
    
}

st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio("Go to:", list(PAGES.keys()), index=0)

# ---------------------- Routing -------------------------
PAGES[selected_tab]()

# ---------------------- Footer ----------------
st.sidebar.markdown("---")
st.sidebar.caption("Cuesta BIO 205 • SLO & North Campus")









