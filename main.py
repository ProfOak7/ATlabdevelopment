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

# Ensure lab_location column exists
if "lab_location" not in bookings_df.columns:
    bookings_df["lab_location"] = "SLO AT Lab"

# --- Navigation ---
st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio("Go to:", ["Sign-Up", "Admin View", "Availability Settings"])

# --- Student Sign-Up Tab ---
if selected_tab == "Sign-Up":
    st.title("Student AT Appointment Sign-Up")

    # Select Lab Location
    lab_location = st.selectbox("Choose your AT Lab location:", ["SLO AT Lab", "NCC AT Lab"])

    # Time Slot Generation based on lab location
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

    single_slots = []
    slots_by_day = {}

    for day in days:
        weekday = day.weekday()
        label_day = day.strftime('%A %m/%d/%y')
        slots_by_day[label_day] = []

        if lab_location == "SLO AT Lab" and weekday in slo_hours:
            start_str, end_str = slo_hours[weekday]
        elif lab_location == "NCC AT Lab" and weekday in ncc_hours:
            start_str, end_str = ncc_hours[weekday]
        else:
            continue

        current_time = datetime.combine(day.date(), datetime.strptime(start_str, "%H:%M").time())
        end_time = datetime.combine(day.date(), datetime.strptime(end_str, "%H:%M").time())

        while current_time < end_time:
            slot = f"{label_day} {current_time.strftime('%-I:%M')}–{(current_time + timedelta(minutes=15)).strftime('%-I:%M %p')}"
            slots_by_day[label_day].append(slot)
            single_slots.append(slot)
            current_time += timedelta(minutes=15)

    double_blocks = {}
    for i in range(len(single_slots) - 1):
        if single_slots[i].split()[1] == single_slots[i+1].split()[1]:
            double_blocks[f"{single_slots[i]} and {single_slots[i+1]}"] = [single_slots[i], single_slots[i+1]]

    # Signup Form
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

        if dsps:
            double_slot_options = [label for label in double_blocks if selected_day in label and all(s not in bookings_df["slot"].values for s in double_blocks[label])]
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
            if dsps and " and " in st.session_state.selected_slot:
                for s in double_blocks[st.session_state.selected_slot]:
                    new_booking = pd.DataFrame([{ 
                        "name": name, "email": email, "student_id": student_id, "dsps": dsps, "slot": s, "lab_location": lab_location 
                    }])
                    bookings_df = pd.concat([bookings_df, new_booking], ignore_index=True)
            else:
                new_booking = pd.DataFrame([{ 
                    "name": name, "email": email, "student_id": student_id, "dsps": dsps, "slot": st.session_state.selected_slot, "lab_location": lab_location 
                }])
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

# --- Admin View Tab ---
elif selected_tab == "Admin View":
    st.title("Admin Panel")
    passcode_input = st.text_input("Enter admin passcode:", type="password")

    if passcode_input == ADMIN_PASSCODE:
        st.success("Access granted.")

        # Separate bookings by lab location
        slo_bookings = bookings_df[bookings_df["lab_location"] == "SLO AT Lab"]
        ncc_bookings = bookings_df[bookings_df["lab_location"] == "NCC AT Lab"]

        st.subheader("SLO AT Lab Bookings")
        st.dataframe(slo_bookings)
        st.download_button("Download All SLO Bookings", slo_bookings.to_csv(index=False), file_name="slo_bookings.csv")

        st.subheader("NCC AT Lab Bookings")
        st.dataframe(ncc_bookings)
        st.download_button("Download All NCC Bookings", ncc_bookings.to_csv(index=False), file_name="ncc_bookings.csv")

        st.subheader("Download Today's Appointments")
        today_str = datetime.today().strftime("%m/%d/%y")

        todays_slo = slo_bookings[slo_bookings["slot"].str.contains(today_str)].copy()
        if not todays_slo.empty:
            todays_slo["slot_dt"] = todays_slo["slot"].apply(lambda x: datetime.strptime(f"{x.split()[1]} {x.split()[2].split('–')[0]} {x.split()[3]}", "%m/%d/%y %I:%M %p"))
            todays_slo = todays_slo.sort_values("slot_dt").drop(columns="slot_dt")
            st.download_button("Download Today's SLO Appointments", todays_slo.to_csv(index=False), file_name="todays_slo_appointments.csv")
        else:
            st.info("No SLO appointments scheduled for today.")

        todays_ncc = ncc_bookings[ncc_bookings["slot"].str.contains(today_str)].copy()
        if not todays_ncc.empty:
            todays_ncc["slot_dt"] = todays_ncc["slot"].apply(lambda x: datetime.strptime(f"{x.split()[1]} {x.split()[2].split('–')[0]} {x.split()[3]}", "%m/%d/%y %I:%M %p"))
            todays_ncc = todays_ncc.sort_values("slot_dt").drop(columns="slot_dt")
            st.download_button("Download Today's NCC Appointments", todays_ncc.to_csv(index=False), file_name="todays_ncc_appointments.csv")
        else:
            st.info("No NCC appointments scheduled for today.")

        st.subheader("Reschedule a Student Appointment")
        if not bookings_df.empty:
            options = [f"{row['name']} ({row['email']}) - {row['slot']}" for _, row in bookings_df.iterrows()]
            selected = st.selectbox("Select a booking to reschedule", options)
            index = options.index(selected)
            current_booking = bookings_df.iloc[index]

            all_available_slots = [s for s in single_slots if s not in bookings_df["slot"].values or s == current_booking["slot"]]

            slot_display_options = []
            slot_lookup = {}
            for label, pair in double_blocks.items():
                if current_booking["dsps"] and all(s not in bookings_df["slot"].values or s == current_booking["slot"] for s in pair):
                    start_time = pair[0].split(" ")[-2] + " " + pair[0].split(" ")[-1]
                    end_time = pair[1].split(" ")[-2] + " " + pair[1].split(" ")[-1]
                    day_label = " ".join(pair[0].split(" ")[:2])
                    display_label = f"{day_label} {start_time}–{end_time}"
                    slot_display_options.append(display_label)
                    slot_lookup[display_label] = pair[0]

            if current_booking["dsps"] and slot_display_options:
                new_display_label = st.selectbox("Choose a new 30-minute block", slot_display_options)
                new_slot = slot_lookup[new_display_label]
            else:
                new_slot = st.selectbox("Choose a new time slot", all_available_slots)

            if st.button("Reschedule"):
                if current_booking["dsps"]:
                    old_email = current_booking["email"]
                    old_student_id = current_booking["student_id"]
                    old_name = current_booking["name"]
                    bookings_df = bookings_df[~((bookings_df["email"] == old_email) & (bookings_df["student_id"] == old_student_id))]
                    for label, pair in double_blocks.items():
                        if new_slot in pair:
                            for s in pair:
                                new_booking = pd.DataFrame([{
                                    "name": old_name,
                                    "email": old_email,
                                    "student_id": old_student_id,
                                    "dsps": True,
                                    "slot": s
                                }])
                                bookings_df = pd.concat([bookings_df, new_booking], ignore_index=True)
                            st.success(f"Successfully rescheduled to {pair[0]} and {pair[1]}!")
                            break
                else:
                    bookings_df.at[index, "slot"] = new_slot
                    st.success(f"Successfully rescheduled to {new_slot}!")

                bookings_df.to_csv(BOOKINGS_FILE, index=False)

    elif passcode_input:
        st.error("Incorrect passcode.")

# --- Availability Settings Tab ---
elif selected_tab == "Availability Settings":
    st.title("Availability Settings")
    availability_passcode = st.text_input("Enter availability admin passcode:", type="password")

    if availability_passcode == AVAILABILITY_PASSCODE:
        st.success("Access granted to Availability Settings.")

        if os.path.exists(AVAILABLE_FILE):
            availability_df = pd.read_csv(AVAILABLE_FILE)
        else:
            availability_df = pd.DataFrame({"slot": single_slots, "available": [True]*len(single_slots)})

        selected_by_day = {}
        for day, slots in slots_by_day.items():
            with st.expander(day):
                if st.button(f"Select All {day}", key=f"select_all_{day}"):
                    for slot in slots:
                        st.session_state[f"avail_{slot}"] = True
                if st.button(f"Deselect All {day}", key=f"deselect_all_{day}"):
                    for slot in slots:
                        st.session_state[f"avail_{slot}"] = False

                selected_by_day[day] = []
                for slot in slots:
                    is_selected = availability_df.loc[availability_df["slot"] == slot, "available"].values[0] if slot in availability_df["slot"].values else False
                    checked = st.checkbox(slot.split()[-2] + " " + slot.split()[-1], value=st.session_state.get(f"avail_{slot}", is_selected), key=f"avail_{slot}")
                    if checked:
                        selected_by_day[day].append(slot)

        selected_available = [slot for slots in selected_by_day.values() for slot in slots]
        availability_df["available"] = availability_df["slot"].isin(selected_available)

        if st.button("Save Availability"):
            availability_df.to_csv(AVAILABLE_FILE, index=False)
            st.success("Availability updated successfully!")
    elif availability_passcode:
        st.error("Incorrect passcode.")
