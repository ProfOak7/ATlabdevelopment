# main.py — robust loader with lazy imports to avoid import-time KeyErrors
import streamlit as st
from tutor import render_chat  # safe to import upfront

st.set_page_config(page_title="Student Appointment Sign-Up", layout="wide")

# --- Sidebar Navigation ---
st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio("Go to:", ["Sign-Up", "BIO 205 Tutor", "Admin View"], index=0)

# --- BIO 205 Tutor (safe; self-bootstraps) ---
if selected_tab == "BIO 205 Tutor":
    st.title("BIO 205 Tutor — Human Anatomy")
    render_chat()

# --- Sign-Up (lazy imports; avoid import-time secrets crash) ---
elif selected_tab == "Sign-Up":
    st.title("Student Appointment Sign-Up")
    try:
        from datetime import datetime
        import pytz
        from bookings import load_bookings
        from slots import generate_slots
        from ui_components import show_student_signup

        pacific = pytz.timezone("US/Pacific")
        now = datetime.now(pacific)

        bookings_df = load_bookings()
        slo_slots_by_day, ncc_slots_by_day = generate_slots()

        show_student_signup(bookings_df, slo_slots_by_day, ncc_slots_by_day, now)
    except Exception as e:
        st.error("Could not load the Sign-Up tab due to an error in one of the modules.")
        st.exception(e)
        st.info("Tip: this often happens if a module reads st.secrets['MISSING_KEY'] at import time.")

# --- Admin View (lazy imports; safer secrets access) ---
elif selected_tab == "Admin View":
    st.title("Admin View")
    try:
        from bookings import load_bookings
        from slots import generate_slots
        from ui_components import show_admin_view

        # Use .get() so a missing secret doesn’t crash the app here
        ADMIN_PASSCODE = st.secrets.get("ADMIN_PASSCODE")
        if not ADMIN_PASSCODE:
            st.error("Missing secret: ADMIN_PASSCODE")
        else:
            bookings_df = load_bookings()
            slo_slots_by_day, ncc_slots_by_day = generate_slots()
            show_admin_view(bookings_df, slo_slots_by_day, ncc_slots_by_day, ADMIN_PASSCODE)
    except Exception as e:
        st.error("Could not load the Admin View due to an error in one of the modules.")
        st.exception(e)
        st.info("Tip: check your modules for st.secrets[...] lookups at import time.")




