# main.py — slim launcher for Student Sign-Up + Admin + BIO 205 Tutor
# Run with:  streamlit run main.py

import pathlib
from datetime import datetime

import pytz
import streamlit as st

# Local modules for the sign-up app
from bookings import load_bookings
from slots import generate_slots
from ui_components import show_student_signup, show_admin_view

# Tutor chat UI
from tutor import render_chat  # <-- this was missing

# ---------------------- App Config ----------------------
st.set_page_config(page_title="Cuesta Lab | Sign-Up + Tutor", layout="wide")

# ---------------------- Secrets -------------------------
# Use .get so app still loads if a secret is absent (you can handle None in the UI)
ADMIN_PASSCODE = st.secrets.get("ADMIN_PASSCODE")
AVAILABILITY_PASSCODE = st.secrets.get("AVAILABILITY_PASSCODE")

# ---------------------- Timezone ------------------------
pacific = pytz.timezone("US/Pacific")
now = datetime.now(pacific)

# ----------------- Data for Sign-Up/Admin ----------------
bookings_df = load_bookings()
slo_slots_by_day, ncc_slots_by_day = generate_slots()

# --------------------- Navigation -----------------------
st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio(
    "Go to:", ["Sign-Up", "Admin View", "BIO 205 Tutor"], index=0
)

# ---------------------- Routing -------------------------
if selected_tab == "Sign-Up":
    st.title("Student Appointment Sign-Up")
    show_student_signup(bookings_df, slo_slots_by_day, ncc_slots_by_day, now)

elif selected_tab == "Admin View":
    st.title("Admin View")
    # If your admin view also needs an availability passcode, pass it through.
    show_admin_view(
        bookings_df,
        slo_slots_by_day,
        ncc_slots_by_day,
        ADMIN_PASSCODE,
    )

elif selected_tab == "BIO 205 Tutor":
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

