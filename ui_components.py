import streamlit as st
from datetime import datetime
import pytz

from bookings import append_booking, load_bookings, overwrite_bookings
from utils import parse_slot_time
from email_utils import send_confirmation_email

import pandas as pd
from tutor import render_chat

EXAM_NUMBERS = [str(i) for i in range(2, 11)]

def render_bio212_tutor_panel(course_hint="BIO 212: Human Biology", knowledge_enabled=False):
    st.title("🧠 BIO 212 Tutor")
    st.caption("Conversational study help for BIO 212.")
    render_chat(course_hint=course_hint, knowledge_enabled=knowledge_enabled)
    
def show_student_signup(bookings_df, slo_slots_by_day, ncc_slots_by_day, now):
    st.title("Student AT Appointment Sign-Up")

    st.markdown(f"Current Pacific Time: **{now.strftime('%A, %B %d, %Y %I:%M %p')}**")

    st.markdown("""
    **Please read before booking:**
    - You may sign up for either location (SLO or NCC).
    - Once booked, you will receive email confirmation.
    - You may only sign up for **one appointment per week** for the same exam.
    - DSPS students may book a **double time block** if needed by clicking "I am a DSPS student".
    - You can reschedule future appointments, but you **cannot reschedule on the day** of your scheduled appointment.
    """)

    # --- Form Fields ---
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

    if dsps:
        # Find consecutive available slots
        available_slots = []
        day_slots = slots_by_day[selected_day]

        for i in range(len(day_slots) - 1):
            s1 = day_slots[i]
            s2 = day_slots[i + 1]

            if (
                s1 not in bookings_df["slot"].values and
                s2 not in bookings_df["slot"].values and
                pacific.localize(parse_slot_time(s1)) > now and
                pacific.localize(parse_slot_time(s2)) > now
            ):
                available_slots.append(f"{s1} and {s2}")
    else:
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
            (bookings_df["email"] == email) & (bookings_df["exam_number"] == exam_number)
        ]
        booked_weeks = student_bookings["slot"].apply(lambda s: parse_slot_time(s).isocalendar().week)

        if selected_week in booked_weeks.values:
            same_day = False
            old_slots_to_remove = []

            for i, row in student_bookings.iterrows():
                old_date = parse_slot_time(row["slot"]).date()
                if old_date.isocalendar().week == selected_week:
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

        # --- Save Booking ---
        if dsps:
            block_slots = selected_slot.split(" and ")
            for i, slot in enumerate(block_slots):
                if i == 0:
                    new_row = [name, email, student_id, dsps, slot, lab_location, exam_number, "", ""]
                else:
                    new_row = ["(DSPS block)", "", "", dsps, slot, lab_location, exam_number, "", ""]
                append_booking(new_row)
            st.success(f"Your DSPS appointment has been recorded for:\n- {block_slots[0]}\n- {block_slots[1]}")
            send_confirmation_email(email, name, selected_slot, lab_location)
        else:
            new_row = [name, email, student_id, dsps, selected_slot, lab_location, exam_number, "", ""]
            append_booking(new_row)
            st.success("Your appointment has been recorded!")
            send_confirmation_email(email, name, selected_slot, lab_location)

        st.rerun()

def show_availability_settings(*args, **kwargs):
    st.info("Availability settings coming soon.")

def show_admin_view(bookings_df, slo_slots_by_day, ncc_slots_by_day, admin_passcode):
    import streamlit as st
    import pandas as pd
    from utils import parse_slot_time
    from bookings import overwrite_bookings

    st.title("Admin Panel")
    passcode_input = st.text_input("Enter admin passcode:", type="password")

    if passcode_input != admin_passcode:
        if passcode_input:
            st.error("Incorrect passcode.")
        return

    st.success("Access granted.")

    slo_bookings = bookings_df[bookings_df["lab_location"] == "SLO AT Lab"]
    ncc_bookings = bookings_df[bookings_df["lab_location"] == "NCC AT Lab"]

    st.subheader("SLO AT Lab Bookings")
    st.dataframe(slo_bookings)
    st.download_button("Download All SLO Bookings", slo_bookings.to_csv(index=False), file_name="slo_bookings.csv")

    st.subheader("NCC AT Lab Bookings")
    st.dataframe(ncc_bookings)
    st.download_button("Download All NCC Bookings", ncc_bookings.to_csv(index=False), file_name="ncc_bookings.csv")

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
        st.markdown("### SLO AT Lab – Today's Appointments")
        st.dataframe(todays_slo)
        st.download_button("Download Today's SLO Appointments", todays_slo.to_csv(index=False), file_name="todays_slo_appointments.csv")
    else:
        st.info("No SLO appointments scheduled for today.")

    if not todays_ncc.empty:
        st.markdown("### NCC AT Lab – Today's Appointments")
        st.dataframe(todays_ncc)
        st.download_button("Download Today's NCC Appointments", todays_ncc.to_csv(index=False), file_name="todays_ncc_appointments.csv")
    else:
        st.info("No NCC appointments scheduled for today.")

    # --- Reschedule ---
    st.subheader("Reschedule a Student Appointment")
    if not bookings_df.empty:
        options = [f"{row['name']} ({row['email']}) - {row['slot']}" for _, row in bookings_df.iterrows() if row['name'] != "(DSPS block)"]
        selected = st.selectbox("Select a booking to reschedule", options)
        index = options.index(selected)
        current_booking = bookings_df[bookings_df["name"] + " (" + bookings_df["email"] + ") - " + bookings_df["slot"] == selected].iloc[0]

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

            if current_booking["dsps"]:
                same_student_rows = updated_df[
                    ((updated_df["email"] == current_booking["email"]) & (updated_df["exam_number"] == current_booking["exam_number"])) |
                    ((updated_df["name"] == "(DSPS block)") &
                     (updated_df["exam_number"] == current_booking["exam_number"]) &
                     (updated_df["lab_location"] == current_booking["lab_location"]))
                ]
                updated_df = updated_df.drop(same_student_rows.index)

                try:
                    i = slots_by_day[selected_day].index(selected_slot)
                    new_blocks = [slots_by_day[selected_day][i], slots_by_day[selected_day][i+1]]

                    row_named = current_booking.copy()
                    row_named["slot"] = new_blocks[0]

                    row_anon = current_booking.copy()
                    row_anon["slot"] = new_blocks[1]
                    row_anon["name"] = "(DSPS block)"
                    row_anon["email"] = ""
                    row_anon["student_id"] = ""

                    updated_df = pd.concat([updated_df, pd.DataFrame([row_named, row_anon])], ignore_index=True)
                    overwrite_bookings(updated_df)
                    st.success(f"Successfully rescheduled DSPS student to:\n- {new_blocks[0]}\n- {new_blocks[1]}")
                except IndexError:
                    st.error("No consecutive block found.")
            else:
                updated_df.loc[(updated_df["email"] == current_booking["email"]) & (updated_df["slot"] == current_booking["slot"]), "slot"] = selected_slot
                overwrite_bookings(updated_df)
                st.success(f"Successfully rescheduled to {selected_slot}!")

    # --- Grading ---
    st.subheader("Enter Grades")
    if not bookings_df.empty:
        grade_options = [f"{row['name']} ({row['email']}) - {row['slot']}" for _, row in bookings_df.iterrows() if row['name'] != "(DSPS block)"]
        selected_grade_entry = st.selectbox("Select a student to grade", grade_options)
        grade_index = grade_options.index(selected_grade_entry)
        selected_row = bookings_df[(bookings_df["name"] + " (" + bookings_df["email"] + ") - " + bookings_df["slot"]) == selected_grade_entry].iloc[0]

        st.markdown(f"**Current Grade:** {selected_row.get('grade', '')} &nbsp;&nbsp;|&nbsp;&nbsp; **Graded By:** {selected_row.get('graded_by', '')}")

        if "instructor_initials" not in st.session_state:
            st.session_state.instructor_initials = ""

        new_grade = st.text_input("Enter numeric grade:", value=selected_row.get("grade", ""))
        new_graded_by = st.text_input("Graded by (initials):", value=st.session_state.instructor_initials)

        if st.button("Save Grade"):
            updated_df = bookings_df.copy()
            idx = updated_df.index[updated_df["email"] == selected_row["email"]][0]
            updated_df.at[idx, "grade"] = new_grade
            updated_df.at[idx, "graded_by"] = new_graded_by
            st.session_state.instructor_initials = new_graded_by
            overwrite_bookings(updated_df)
            st.success("Grade successfully saved.")
            st.rerun()






