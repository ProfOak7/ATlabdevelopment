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
else:
    bookings_df = pd.DataFrame(columns=["name", "email", "student_id", "dsps", "slot"])

# Generate next week's Mon–Fri with 15-min slots
today = datetime.today()
days = [today + timedelta(days=i) for i in range(14) if (today + timedelta(days=i)).weekday() < 5]

single_slots = []
slots_by_day = {}

for day in days:
    current_time = datetime.combine(day.date(), datetime.strptime("09:00", "%H:%M").time())
    end_time = datetime.combine(day.date(), datetime.strptime("17:00", "%H:%M").time())
    label_day = day.strftime('%A %m/%d/%y')
    slots_by_day[label_day] = []
    while current_time < end_time:
        start_label = current_time.strftime("%-I:%M")
        end_label = (current_time + timedelta(minutes=15)).strftime("%-I:%M %p")
        slot_time_label = f"{start_label}–{end_label}"
        label = f"{label_day} {slot_time_label}"
        single_slots.append(label)
        slots_by_day[label_day].append(label)
        current_time += timedelta(minutes=15)

double_blocks = {}
for i in range(len(single_slots) - 1):
    date1 = single_slots[i].split(" ")[1]
    date2 = single_slots[i+1].split(" ")[1]
    if date1 == date2:
        block_label = f"{single_slots[i]} and {single_slots[i+1]}"
        double_blocks[block_label] = [single_slots[i], single_slots[i+1]]

# 📅 Calendar View of Current Sign-Ups (First Name Only)
st.sidebar.title("Navigation")
selected_tab = st.sidebar.radio("Go to:", ["Sign-Up", "Admin View", "Availability Settings"])

if selected_tab == "Sign-Up":
    st.subheader("Current Sign-Ups")
    calendar_data = bookings_df.copy()
    if not calendar_data.empty:
        now = datetime.now()
        calendar_data["slot_dt"] = calendar_data["slot"].apply(lambda x: datetime.strptime(x.split(" ")[1], "%m/%d/%y"))
        calendar_data = calendar_data[calendar_data["slot_dt"].dt.date >= now.date()]
        calendar_data["first_name"] = calendar_data["name"].apply(lambda x: x.split(" ")[0] if pd.notnull(x) else "")
        calendar_data["day"] = calendar_data["slot"].apply(lambda x: " ".join(x.split(" ")[:2]))
        grouped = calendar_data.groupby("day")
        sorted_days = sorted(grouped.groups.keys(), key=lambda d: datetime.strptime(d.split(" ")[1], "%m/%d/%y"))

        for day in sorted_days:
            group = grouped.get_group(day)
            with st.expander(f"{day} ({len(group)} sign-up{'s' if len(group) != 1 else ''})"):
                # Merge DSPS double bookings into a single row
                grouped_view = group.sort_values("slot").groupby(["first_name"])
                display_rows = []
                for name, slots in grouped_view:
                    sorted_slots = slots["slot"].tolist()
                    if len(sorted_slots) == 2:
                        start = sorted_slots[0].rsplit(" ", 1)[-1].split("–")[0]
                        end = sorted_slots[1].rsplit(" ", 1)[-1].split("–")[-1]
                        label = f"{sorted_slots[0].rsplit(' ', 1)[0]} {start}–{end}"
                        display_rows.append({"Student": name, "Time Slot": label})
                    else:
                        for s in sorted_slots:
                            display_rows.append({"Student": name, "Time Slot": s})
                st.dataframe(pd.DataFrame(display_rows))
    else:
        st.info("No appointments have been scheduled yet.")


# UI: Student Sign-In
st.title("Student AT Appointment Sign-Up")

name = st.text_input("Enter your full name:")
email = st.text_input("Enter your official Cuesta email:")
student_id = st.text_input("Enter your Student ID:")
dsps = st.checkbox("I am a DSPS student")
if st.button("Need to Reschedule?"):
        st.info("To reschedule your appointment, please speak with the current professor in the AT Lab.")

if email:
    if not (email.lower().endswith("@my.cuesta.edu") or email.lower().endswith("@cuesta.edu")):
        st.error("Please use your official Cuesta email ending in @my.cuesta.edu or @cuesta.edu")
        st.stop()

if name and email and student_id:
    if not student_id.startswith("900"):
        st.error("Student ID must start with 900.")
        st.stop()
    if st.session_state.get("selected_slot"):
        selected_week = datetime.strptime(st.session_state["selected_slot"].split(" ")[1], "%m/%d/%y").isocalendar().week
        booked_weeks = bookings_df[bookings_df["email"] == email]["slot"].apply(
            lambda s: datetime.strptime(s.split(" ")[1], "%m/%d/%y").isocalendar().week
        )
        if selected_week in booked_weeks.values:
            st.warning("You’ve already booked a slot that week. Students may only sign up once per week.")
            st.stop()

    st.subheader("Available Time Slots")
    selected_day = st.selectbox("Choose a day:", list(slots_by_day.keys()))

    available_file = "available_slots.csv"
    if os.path.exists(available_file):
        availability_df = pd.read_csv(available_file)
        allowed_slots = availability_df[availability_df["available"]]["slot"].tolist()
    else:
        allowed_slots = single_slots

    if dsps:
        grouped_blocks = {}
        for label in double_blocks:
            day = " ".join(label.split(" ")[:2])
            if selected_day in label and all(s in allowed_slots and s not in bookings_df["slot"].values for s in double_blocks[label]):
                grouped_blocks.setdefault(day, []).append(label)

        selected_block = None
        for day in sorted(grouped_blocks.keys(), key=lambda d: datetime.strptime(d.split(" ")[1], "%m/%d/%y")):
            with st.expander(f"{day} ({len(grouped_blocks[day])} available)"):
                selected_block = st.radio("Choose a double time block:", grouped_blocks[day], key=f"radio_{day}")
                if st.button(f"Select {day}"):
                    st.session_state["selected_slot"] = selected_block
                    st.session_state["confirming"] = True
            st.info("No available double blocks for this day.")
    else:
        available_slots = [s for s in slots_by_day[selected_day] if s not in bookings_df["slot"].values and s in allowed_slots]
        if available_slots:
            selected_time = st.selectbox("Choose a time:", available_slots)
            if st.button("Select This Time"):
                st.session_state["selected_slot"] = selected_time
                st.session_state["confirming"] = True
                st.rerun()
        else:
            st.info("No available slots for this day.")

    if st.session_state["confirming"] and st.session_state["selected_slot"]:
        st.subheader("Confirm Your Appointment")
        st.write(f"You have selected: **{st.session_state['selected_slot']}**")
        if st.button("Confirm"):
            if dsps and " and " in st.session_state["selected_slot"]:
                for s in double_blocks[st.session_state["selected_slot"]]:
                    new_booking = pd.DataFrame([{ "name": name, "email": email, "student_id": student_id, "dsps": dsps, "slot": s }])
                    bookings_df = pd.concat([bookings_df, new_booking], ignore_index=True)
            else:
                new_booking = pd.DataFrame([{ "name": name, "email": email, "student_id": student_id, "dsps": dsps, "slot": st.session_state["selected_slot"] }])
                bookings_df = pd.concat([bookings_df, new_booking], ignore_index=True)
            bookings_df.to_csv(BOOKINGS_FILE, index=False)
            st.success(f"Successfully booked {st.session_state['selected_slot']}!")
            st.session_state["selected_slot"] = None
            st.session_state["confirming"] = False
            st.stop()
        if st.button("Cancel"):
            st.session_state["selected_slot"] = None
            st.session_state["confirming"] = False
            st.rerun()


# Admin View
elif selected_tab == "Admin View":
    st.markdown("---")
    with st.expander("🔐 Admin Access"):
        passcode_input = st.text_input("Enter admin passcode:", type="password")

    if passcode_input == ADMIN_PASSCODE:
        st.success("Access granted.")
        st.dataframe(bookings_df)
        st.download_button("📄 Download CSV", bookings_df.to_csv(index=False), file_name="bookings.csv")

        st.subheader("Reschedule a Student Appointment")
        if not bookings_df.empty:
            options = [f"{row['name']} ({row['email']}) - {row['slot']}" for _, row in bookings_df.iterrows()]
            selected = st.selectbox("Select a booking to reschedule", options)
            index = options.index(selected)
            current_booking = bookings_df.iloc[index]

            all_available_slots = [s for s in single_slots if s not in bookings_df["slot"].values or s == current_booking["slot"]]

            if current_booking["dsps"]:
                grouped_blocks = {}
                for label, pair in double_blocks.items():
                    if all(s not in bookings_df["slot"].values or s == current_booking["slot"] for s in pair):
                        start_time = pair[0].rsplit(" ", 2)[-2] + " " + pair[0].split(" ")[-1]
                        end_time = pair[1].rsplit(" ", 2)[-2] + " " + pair[1].split(" ")[-1]
                        day_label = " ".join(pair[0].split(" ")[:2])
                        formatted_label = f"{day_label} {start_time}–{end_time}"
                        grouped_blocks.setdefault(day_label, []).append((formatted_label, label))  # Ensure only one block per day is added
                block_lookup = {}
                for day in sorted(grouped_blocks.keys(), key=lambda d: datetime.strptime(d.split(" ")[1], "%m/%d/%y")):
                    with st.expander(f"{day} ({len(grouped_blocks[day])} available)"):
                        options = [label for label, _ in grouped_blocks[day]]
                        selected_display_label = st.radio("Choose a double time block:", options, key=f"radio_admin_{day}")
                        for label, block in grouped_blocks[day]:
                            block_lookup[label] = block
                        if st.button(f"Select {day}"):
                            new_block = block_lookup[selected_display_label]
                            st.session_state["selected_slot"] = new_block
                            st.session_state["confirming"] = True
                    new_block = block_lookup[selected_display_label]
                    st.write(f"Selected block: **{selected_display_label}**")
                else:
                    st.info("No DSPS time blocks available for rescheduling.")
                    new_block = None
            else:
                new_slot = st.selectbox("Choose a new time slot", all_available_slots)

                                    if st.button("Reschedule") and (not current_booking["dsps"] or st.session_state.get("selected_slot")):
                if current_booking["dsps"]:
                    old_email = current_booking["email"]
                    old_student_id = current_booking["student_id"]
                    old_name = current_booking["name"]
                    bookings_df = bookings_df[~((bookings_df["email"] == old_email) & (bookings_df["student_id"] == old_student_id))]
                    for s in double_blocks[st.session_state["selected_slot"]]:
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
