# main.py — slim launcher for Student Sign‑Up + Admin + BIO 205 Tutor
# Run with:  streamlit run main.py

import streamlit as st
from datetime import datetime
import pytz

# Local modules for the sign‑up app
from bookings import load_bookings
from slots import generate_slots
from ui_components import (
    show_student_signup,
    show_admin_view,
)

# ---------------------- App Config ----------------------
st.set_page_config(page_title="Cuesta Lab | Sign‑Up + Tutor", layout="wide")

# ---------------------- Secrets -------------------------
ADMIN_PASSCODE = st.secrets["ADMIN_PASSCODE"]
AVAILABILITY_PASSCODE = st.secrets.get("AVAILABILITY_PASSCODE")  # optional if not used here

# ---------------------- Timezone ------------------------
pacific = pytz.timezone("US/Pacific")
now = datetime.now(pacific)

# ----------------- Data for Sign‑Up/Admin ----------------
bookings_df = load_bookings()
slo_slots_by_day, ncc_slots_by_day = generate_slots()

# --------------------- Navigation -----------------------
st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio("Go to:", ["Sign‑Up", "Admin View", "BIO 205 Tutor"], index=0)

# ---------------------- Routing -------------------------
if selected_tab == "Sign‑Up":
    st.title("Student Appointment Sign‑Up")
    show_student_signup(bookings_df, slo_slots_by_day, ncc_slots_by_day, now)

elif selected_tab == "Admin View":
    st.title("Admin View")
    show_admin_view(bookings_df, slo_slots_by_day, ncc_slots_by_day, ADMIN_PASSCODE)

elif selected_tab == "BIO 205 Tutor":
    st.title("BIO 205 Tutor — Human Anatomy")

    # Render the Tutor chat UI (self‑contained; sidebar there has a Reindex button)
    render_tutor_chat()




