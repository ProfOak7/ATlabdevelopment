import streamlit as st
from datetime import datetime
import pytz

from bookings import append_booking, load_bookings, overwrite_bookings
from utils import parse_slot_time
from email_utils import send_confirmation_email

import pandas as pd

EXAM_NUMBERS = [str(i) for i in range(2, 11)]

def show_student_signup(bookings_df, slo_slots_by_day, ncc_slots_by_day, now):
    st.title("Student AT Appointment Sign-Up")

    st.markdown(f"Current Pacific Time: **{now.strftime('%A, %B %d, %Y %I:%M %p')}**")

    st.markdown("""
    **Please read before booking:**
    - You may sign up for either location (SLO or NCC).
    - Once booked, you will receive email confirmation.
    - You may only sign up for **one appointment per week**.
    - DSPS students may book a **double time block** if needed by clicking "I am a DSPS student".
    - You can reschedule future appointments, but you **cannot reschedule on the day** of your scheduled appointment.
    """)

    name = st.text_input("Enter your full name:")
    email = st.text_input("Enter your official Cuesta email:")
    student_id = st.text_input("Enter your Student ID:")
    exam_number = st.selectbox("Which oral exam are you signing up for?", EXAM_NUMBERS)
    dsps = st.checkbox("I am a DSPS student")
    lab_location = st.selectbox("Choose your AT Lab location:", ["SLO AT Lab", "NCC AT Lab"])

    if email and not (email.lower().endswith("@my.cuesta.edu") or email.lower().endswith("@cuesta.edu")):
        st.error("Please use your official Cuesta email ending in @my.cuesta.edu or @cuesta.edu")
        return

    if name and email and student_id and not student_id.startswith("900"):
        st.error("Student ID must start with 900.")
        return

    slots_by_day = slo_slots_by_day if lab_location == "SLO AT Lab" else ncc_slots_by_day
    selected_day = st.selectbox("Choose a day:", list(slots_by_day.keys()))

    pacific = pytz.timezone("US/Pacific")
    available_slots = [
        s for s in slots_by_day[selected_day]
        if s not in bookings_df["slot"].values and
        pacific.localize(parse_slot_time(s)) > now
    ]

    if not available_slots:
        st.info("No available slots for this day.")
        return

    selected_slot = st.selectbox("Choose a time:", available_slots)

    if st.button("Submit Booking") and (
        (not dsps and selected_slot) or (dsps and " and " in selected_slot)
    ):
        if not all([name, email, student_id, selected_slot]):
            st.error("Please fill out all required fields.")
            return

        selected_week = parse_slot_time(selected_slot.split(" and ")[0] if dsps else selected_slot).isocalendar().week
        selected_date = parse_slot_time(selected_slot.split(" and ")[0] if dsps else selected_slot).date()
        today = datetime.now().date()

        student_bookings = bookings_df[
            (bookings_df["email"] == email) &
            (bookings_df["exam_number"] == exam_number)
        ]

        booked_weeks = student_bookings["slot"].apply(lambda s: parse_slot_time(s).isocalendar().week)

        if selected_week in booked_weeks.values:
            same_day = False
            old_slots_to_remove = []

            for i, row in student_bookings.iterrows():
                old_date = parse_slot_time(row["slot"]).date()
                old_week = old_date.isocalendar().week

                if old_week == selected_week:
                    if old_date == today:
                        same_day = True
                    else:
                        old_slots_to_remove.append(i)

            if same_day:
                st.warning("You cannot reschedule an appointment on the day of your appointment.")
                return
            else:
                bookings_df = bookings_df.drop(old_slots_to_remove).reset_index(drop=True)
                overwrite_bookings(bookings_df)

        if dsps and " and " in selected_slot:
            block_slots = selected_slot.split(" and ")
            for slot in block_slots:
                new_row = [name, email, student_id, dsps, slot, lab_location, exam_number, "", ""]
                append_booking(new_row)
            st.success(f"Your DSPS appointment has been recorded for:\n- {block_slots[0]}\n- {block_slots[1]}")
            send_confirmation_email(email, name, f"{block_slots[0]} and {block_slots[1]}", lab_location)
        else:
            new_row = [name, email, student_id, dsps, selected_slot, lab_location, exam_number, "", ""]
            append_booking(new_row)
            st.success("Your appointment has been recorded!")
            send_confirmation_email(email, name, selected_slot, lab_location)

        st.rerun()
