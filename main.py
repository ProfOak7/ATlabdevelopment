import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- Configuration ---
st.set_page_config(page_title="Student Appointment Sign-Up", layout="wide")

BOOKINGS_FILE = "bookings.csv"
AVAILABLE_FILE = "available_slots.csv"
ADMIN_PASSCODE = "cougar2025"
AVAILABILITY_PASSCODE = "atlabadmin2025"

# --- Initialize Session State ---
if "selected_slot" not in st.session_state:
    st.session_state.selected_slot = None
if "confirming" not in st.session_state:
    st.session_state.confirming = False

# --- Load or Initialize Bookings ---
if os.path.exists(BOOKINGS_FILE):
    bookings_df = pd.read_csv(BOOKINGS_FILE)
else:
    bookings_df = pd.DataFrame(columns=["name", "email", "student_id", "dsps", "slot"])

if "lab_location" not in bookings_df.columns:
    bookings_df["lab_location"] = "SLO AT Lab"

# --- Generate Slot Templates ---
today = datetime.today()
days = [today + timedelta(days=i) for i in range(21)]

slo_hours = {
    0: ("09:00", "21:00"),
    1: ("09:00", "21:00"),
    2: ("08:30", "21:00"),
    3: ("08:15", "20:30"),
    4: ("09:15", "15:00"),
    5: ("09:15", "13:00")
}

ncc_hours = {
    0: ("12:00", "16:00"),
    1: ("08:15", "20:00"),
    2: ("08:15", "17:00"),
    3: ("09:15", "17:00"),
    4: ("08:15", "15:00")
}

slo_single_slots, ncc_single_slots = [], []
slo_slots_by_day, ncc_slots_by_day = {}, {}

for day in days:
    weekday = day.weekday()
    label_day = day.strftime('%A %m/%d/%y')

    if weekday in slo_hours:
        start_str, end_str = slo_hours[weekday]
        current_time = datetime.combine(day.date(), datetime.strptime(start_str, "%H:%M").time())
        end_time = datetime.combine(day.date(), datetime.strptime(end_str, "%H:%M").time())
        while current_time < end_time:
            slot = f"{label_day} {current_time.strftime('%-I:%M')}–{(current_time + timedelta(minutes=15)).strftime('%-I:%M %p')}"
            slo_slots_by_day.setdefault(label_day, []).append(slot)
            slo_single_slots.append(slot)
            current_time += timedelta(minutes=15)

    if weekday in ncc_hours:
        start_str, end_str = ncc_hours[weekday]
        current_time = datetime.combine(day.date(), datetime.strptime(start_str, "%H:%M").time())
        end_time = datetime.combine(day.date(), datetime.strptime(end_str, "%H:%M").time())
        while current_time < end_time:
            slot = f"{label_day} {current_time.strftime('%-I:%M')}–{(current_time + timedelta(minutes=15)).strftime('%-I:%M %p')}"
            ncc_slots_by_day.setdefault(label_day, []).append(slot)
            ncc_single_slots.append(slot)
            current_time += timedelta(minutes=15)

all_single_slots = slo_single_slots + ncc_single_slots

# --- Navigation ---
st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio("Go to:", ["Sign-Up", "Admin View", "Availability Settings"])

# --- Student Sign-Up Tab ---
if selected_tab == "Sign-Up":
    st.title("Student AT Appointment Sign-Up")

    lab_location = st.selectbox("Choose your AT Lab location:", ["SLO AT Lab", "NCC AT Lab"])
    slots_by_day = slo_slots_by_day if lab_location == "SLO AT Lab" else ncc_slots_by_day

    st.subheader("Current Sign-Ups")
    if not bookings_df.empty:
        calendar_data = bookings_df[bookings_df["lab_location"] == lab_location]
        if not calendar_data.empty:
            calendar_data["first_name"] = calendar_data["name"].apply(lambda x: x.split()[0])
            calendar_data["day"] = calendar_data["slot"].apply(lambda x: " ".join(x.split()[:2]))
            grouped = calendar_data.groupby("day")
            sorted_days = sorted(grouped.groups.keys(), key=lambda d: datetime.strptime(d.split()[1], "%m/%d/%y"))
            for day in sorted_days:
                with st.expander(f"{day} ({len(grouped.get_group(day))} sign-up{'s' if len(grouped.get_group(day)) != 1 else ''})"):
                    names = grouped.get_group(day)["first_name"].tolist()
                    st.write(", ".join(names))
        else:
            st.info("No appointments scheduled for this lab yet.")
    else:
        st.info("No appointments scheduled yet.")

    # Sign-Up Form
    name = st.text_input("Enter your full name:")
    email = st.text_input("Enter your official Cuesta email:")
    student_id = st.text_input("Enter your Student ID:")
    dsps = st.checkbox("I am a DSPS student")

    if email and not (email.lower().endswith("@my.cuesta.edu") or email.lower().endswith("@cuesta.edu")):
        st.error("Please use your official Cuesta email ending in @my.cuesta.edu or @cuesta.edu")
        st.stop()

    if name and email and student_id:
        if not student_id.startswith("900"):
            st.error("Student ID must start with 900.")
            st.stop()

        st.subheader("Available Time Slots")
        selected_day = st.selectbox("Choose a day:", list(slots_by_day.keys()))
        available_slots = [s for s in slots_by_day[selected_day] if s not in bookings_df["slot"].values]

        double_blocks = {}
        for i in range(len(slots_by_day[selected_day]) - 1):
            if slots_by_day[selected_day][i].split()[1] == slots_by_day[selected_day][i+1].split()[1]:
                double_blocks[f"{slots_by_day[selected_day][i]} and {slots_by_day[selected_day][i+1]}"] = [slots_by_day[selected_day][i], slots_by_day[selected_day][i+1]]

        if dsps:
            double_slot_options = [label for label in double_blocks if all(s not in bookings_df["slot"].values for s in double_blocks[label])]
            if double_slot_options:
                selected_block = st.selectbox("Choose a double time block:", double_slot_options)
                if st.button("Select This Time Block"):
                    st.session_state.selected_slot = selected_block
                    st.session_state.confirming = True
                    st.rerun()
            else:
                st.info("No available double blocks for this day.")
        else:
            if available_slots:
                selected_time = st.selectbox("Choose a time:", available_slots)
                if st.button("Select This Time"):
                    st.session_state.selected_slot = selected_time
                    st.session_state.confirming = True
                    st.rerun()
            else:
                st.info("No available slots for this day.")

    if st.session_state.confirming and st.session_state.selected_slot:
        st.subheader("Confirm Your Appointment")
        st.write(f"You have selected: **{st.session_state.selected_slot}**")

        if st.button("Confirm"):
            selected_week = datetime.strptime(st.session_state.selected_slot.split(" ")[1], "%m/%d/%y").isocalendar().week
            booked_weeks = bookings_df[bookings_df["email"] == email]["slot"].apply(
                lambda s: datetime.strptime(s.split(" ")[1], "%m/%d/%y").isocalendar().week
            )

            if selected_week in booked_weeks.values:
                st.warning("You already have a booking this week. Your previous booking will be replaced.")
                bookings_df = bookings_df[~((bookings_df["email"] == email) & (bookings_df["slot"].apply(
                    lambda s: datetime.strptime(s.split(" ")[1], "%m/%d/%y").isocalendar().week == selected_week)))]

            if dsps and " and " in st.session_state.selected_slot:
                for s in st.session_state.selected_slot.split(" and "):
                    new_booking = pd.DataFrame([{ "name": name, "email": email, "student_id": student_id, "dsps": dsps, "slot": s, "lab_location": lab_location }])
                    bookings_df = pd.concat([bookings_df, new_booking], ignore_index=True)
            else:
                new_booking = pd.DataFrame([{ "name": name, "email": email, "student_id": student_id, "dsps": dsps, "slot": st.session_state.selected_slot, "lab_location": lab_location }])
                bookings_df = pd.concat([bookings_df, new_booking], ignore_index=True)

            bookings_df.to_csv(BOOKINGS_FILE, index=False)
            st.success(f"Successfully booked {st.session_state.selected_slot}!")
            st.session_state.selected_slot = None
            st.session_state.confirming = False
            st.stop()

        if st.button("Cancel"):
            st.session_state.selected_slot = None
            st.session_state.confirming = False
            st.rerun()
