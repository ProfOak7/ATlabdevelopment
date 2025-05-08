import streamlit as st
from datetime import datetime
import pytz

from bookings import append_booking, load_bookings
from utils import parse_slot_time
from email_utils import send_confirmation_email

import pandas as pd
from bookings import overwrite_bookings

EXAM_NUMBERS = [str(i) for i in range(2, 11)]

def show_student_signup(bookings_df, slo_slots_by_day, ncc_slots_by_day, now):
    st.title("Student AT Appointment Sign-Up")

    st.markdown(f"Current Pacific Time: **{now.strftime('%A, %B %d, %Y %I:%M %p')}**")

    st.markdown("""
    **Please read before booking:**
    - You may sign up for either location (SLO or NCC) 
    - Once booked, you will receive email confirmation.
    - You may only sign up for **one appointment per week**.
    - DSPS students may book a **double time block** if needed by clicking "I am a DSPS student".
    - You can reschedule future appointments, but you **cannot reschedule on the day** of your scheduled appointment.
    """)

    # --- Student Form ---
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

    from datetime import datetime
    from utils import parse_slot_time

    selected_week = parse_slot_time(selected_slot.split(" and ")[0] if dsps else selected_slot).isocalendar().week
    selected_date = parse_slot_time(selected_slot.split(" and ")[0] if dsps else selected_slot).date()
    today = datetime.now().date()

    # Get existing bookings for this student
    student_bookings = bookings_df[bookings_df["email"] == email]
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
            # Drop old slots (both if DSPS)
            bookings_df = bookings_df.drop(old_slots_to_remove)

    # Append new slot(s)
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

def show_admin_view(*args, **kwargs):
    st.info("Admin view coming soon.")

def show_availability_settings(*args, **kwargs):
    st.info("Availability settings coming soon.")


def show_admin_view(bookings_df, slo_slots_by_day, ncc_slots_by_day, admin_passcode):
    st.title("Admin Panel")
    passcode_input = st.text_input("Enter admin passcode:", type="password")

    if passcode_input != admin_passcode:
        if passcode_input:
            st.error("Incorrect passcode.")
        return

    st.success("Access granted.")

    # --- Split Bookings by Location
    slo_bookings = bookings_df[bookings_df["lab_location"] == "SLO AT Lab"]
    ncc_bookings = bookings_df[bookings_df["lab_location"] == "NCC AT Lab"]

    st.subheader("SLO AT Lab Bookings")
    st.dataframe(slo_bookings)
    st.download_button("Download All SLO Bookings", slo_bookings.to_csv(index=False), file_name="slo_bookings.csv")

    st.subheader("NCC AT Lab Bookings")
    st.dataframe(ncc_bookings)
    st.download_button("Download All NCC Bookings", ncc_bookings.to_csv(index=False), file_name="ncc_bookings.csv")

    # --- Download Today's Appointments
    st.subheader("Download Today's Appointments")
    today_str = pd.Timestamp.today().strftime("%m/%d/%y")

    def get_sorted_today(df):
        today_df = df[df["slot"].str.contains(today_str)].copy()
        if not today_df.empty:
            today_df["slot_dt"] = today_df["slot"].apply(parse_slot_time)
            today_df = today_df.sort_values("slot_dt").drop(columns="slot_dt")
        return today_df

    todays_slo = get_sorted_today(slo_bookings)
    todays_ncc = get_sorted_today(ncc_bookings)

    if not todays_slo.empty:
        st.download_button("Download Today's SLO Appointments", todays_slo.to_csv(index=False), file_name="todays_slo_appointments.csv")
    else:
        st.info("No SLO appointments scheduled for today.")

    if not todays_ncc.empty:
        st.download_button("Download Today's NCC Appointments", todays_ncc.to_csv(index=False), file_name="todays_ncc_appointments.csv")
    else:
        st.info("No NCC appointments scheduled for today.")

    # --- Reschedule Student
    st.subheader("Reschedule a Student Appointment")
    if not bookings_df.empty:
        options = [f"{row['name']} ({row['email']}) - {row['slot']}" for _, row in bookings_df.iterrows()]
        selected = st.selectbox("Select a booking to reschedule", options)
        index = options.index(selected)
        current_booking = bookings_df.iloc[index]

        # Filter slots
        slots_by_day = slo_slots_by_day if current_booking["lab_location"] == "SLO AT Lab" else ncc_slots_by_day
        available_by_day = {
            day: [s for s in slots if s not in bookings_df["slot"].values or s == current_booking["slot"]]
            for day, slots in slots_by_day.items()
        }
        days_with_availability = [day for day in available_by_day if available_by_day[day]]

        selected_day = st.selectbox("Choose a new day:", days_with_availability)
        selected_slot = st.selectbox("Choose a new time:", available_by_day[selected_day])

        if st.button("Reschedule"):
            updated_df = bookings_df.copy()

            if current_booking["dsps"] and updated_df[updated_df["email"] == current_booking["email"]].shape[0] == 2:
                old_slots = updated_df[updated_df["email"] == current_booking["email"]]["slot"].tolist()
                updated_df = updated_df[updated_df["email"] != current_booking["email"]]

                try:
                    i = slots_by_day[selected_day].index(selected_slot)
                    new_blocks = [slots_by_day[selected_day][i], slots_by_day[selected_day][i+1]]

                    for s in new_blocks:
                        new_row = current_booking.copy()
                        new_row["slot"] = s
                        updated_df = pd.concat([updated_df, pd.DataFrame([new_row])], ignore_index=True)

                    overwrite_bookings(updated_df)
                    st.success(f"Successfully rescheduled DSPS student to {new_blocks[0]} and {new_blocks[1]}")
                except IndexError:
                    st.error("No consecutive block found.")
            else:
                updated_df.at[index, "slot"] = selected_slot
                overwrite_bookings(updated_df)
                st.success(f"Successfully rescheduled to {selected_slot}!")

        # --- Grading Panel ---
    st.subheader("Enter Grades")

    if not bookings_df.empty:
        grade_options = [f"{row['name']} ({row['email']}) - {row['slot']}" for _, row in bookings_df.iterrows()]
        selected_grade_entry = st.selectbox("Select a student to grade", grade_options)
        grade_index = grade_options.index(selected_grade_entry)
        selected_row = bookings_df.iloc[grade_index]

        st.markdown(f"**Current Grade:** {selected_row.get('grade', '')} &nbsp;&nbsp;|&nbsp;&nbsp; **Graded By:** {selected_row.get('graded_by', '')}")

        # Store instructor initials in session state
        if "instructor_initials" not in st.session_state:
            st.session_state.instructor_initials = ""

        new_grade = st.text_input("Enter numeric grade:", value=selected_row.get("grade", ""))
        new_graded_by = st.text_input("Graded by (initials):", value=st.session_state.instructor_initials)

        if st.button("Save Grade"):
            updated_df = bookings_df.copy()
            updated_df.at[grade_index, "grade"] = new_grade
            updated_df.at[grade_index, "graded_by"] = new_graded_by
            st.session_state.instructor_initials = new_graded_by  # persist for convenience

            overwrite_bookings(updated_df)
            st.success("Grade successfully saved.")
            st.rerun()  # <--- this line refreshes everything
