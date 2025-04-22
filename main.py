import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
import requests

st.set_page_config(page_title="Student Appointment Sign-Up", layout="wide")

BOOKINGS_FILE = "bookings.csv"
ADMIN_PASSCODE = "cougar2025"

# Initialize session state variables
if "selected_slot" not in st.session_state:
    st.session_state["selected_slot"] = None
if "confirming" not in st.session_state:
    st.session_state["confirming"] = False

# Load or create bookings file
if os.path.exists(BOOKINGS_FILE):
    bookings_df = pd.read_csv(BOOKINGS_FILE)
            

                                                                if st.button("Reschedule"):
                if current_booking["dsps"]:
                    old_email = current_booking["email"]
                    old_student_id = current_booking["student_id"]
                    old_name = current_booking["name"]
                                    bookings_df = bookings_df[~((bookings_df["email"] == old_email) & (bookings_df["student_id"] == old_student_id))]
                                                    for s in double_blocks[new_block]:
                        new_booking = pd.DataFrame([{"name": old_name, "email": old_email, "student_id": old_student_id, "dsps": True, "slot": s}])
                        bookings_df = pd.concat([bookings_df, new_booking], ignore_index=True)
                    st.success(f"Successfully rescheduled to {new_block}!")
                else:
                    bookings_df.at[index, "slot"] = new_slot
                    st.success(f"Successfully rescheduled to {new_slot}!")
            bookings_df.to_csv(BOOKINGS_FILE, index=False)
    elif passcode_input:
        st.error("Incorrect passcode.")

# Availability Settings
elif selected_tab == "Availability Settings":
    st.markdown("---")
    with st.expander("🔒 Availability Admin Access"):
        availability_passcode = st.text_input("Enter availability admin passcode:", type="password")

    AVAILABILITY_PASSCODE = "atlabadmin2025"

    if availability_passcode == AVAILABILITY_PASSCODE:
        st.success("Access granted to Availability Settings.")
        available_file = "available_slots.csv"
        if os.path.exists(available_file):
            availability_df = pd.read_csv(available_file)
        else:
            availability_df = pd.DataFrame({"slot": single_slots, "available": [True]*len(single_slots)})

        selected_available = st.multiselect(
            "Select available time slots:",
            options=single_slots,
            default=availability_df[availability_df["available"]]["slot"].tolist(),
            key="availability_selector"
        )

        availability_df["available"] = availability_df["slot"].isin(selected_available)

        if st.button("Save Availability"):
            availability_df.to_csv(available_file, index=False)
            st.success("Availability updated successfully!")
    elif availability_passcode:
        st.error("Incorrect passcode.")
