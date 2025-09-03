import streamlit as st
from datetime import datetime
import pytz

from bookings import load_bookings
from slots import generate_slots
from ui_components import show_student_signup, show_admin_view, show_availability_settings
from tutor import init_tutor
from ui_components import render_tutor_panel
    
# --- Configuration ---
st.set_page_config(page_title="Student Appointment Sign-Up", layout="wide")

# --- Passcodes from secrets ---
ADMIN_PASSCODE = st.secrets["ADMIN_PASSCODE"]
AVAILABILITY_PASSCODE = st.secrets["AVAILABILITY_PASSCODE"]

# --- Timezone Setup ---
pacific = pytz.timezone("US/Pacific")
now = datetime.now(pacific)

# --- Load Bookings and Generate Slots ---
bookings_df = load_bookings()
slo_slots_by_day, ncc_slots_by_day = generate_slots()

# --- Sidebar Navigation ---
st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio(
    "Go to:", 
    ["Sign-Up", "Admin View", "Availability Settings", "BIO 205 Tutor"]
)


# --- Route to Appropriate View ---
if selected_tab == "Sign-Up":
    show_student_signup(bookings_df, slo_slots_by_day, ncc_slots_by_day, now)

elif selected_tab == "Admin View":
    show_admin_view(bookings_df, slo_slots_by_day, ncc_slots_by_day, ADMIN_PASSCODE)

elif selected_tab == "Availability Settings":
    show_availability_settings(AVAILABILITY_PASSCODE)

elif selected_tab == "BIO 205 Tutor":
    # Initialize tutor knowledge (optional: path to folder with .md/.txt)
    KNOWLEDGE_DIR = "./bio205_knowledge"
    init_tutor(KNOWLEDGE_DIR)

    render_tutor_panel(
    course_hint="BIO 205: Human Anatomy",
    knowledge_enabled=bool(KNOWLEDGE_DIR)
    )













