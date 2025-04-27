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

# Generate next week's Mon–Sat with 15-min slots

# [The rest of your code would continue here... including the fixed calendar_data parser!]

# In your "Sign-Up" tab where calendar_data is processed, use:
if selected_tab == "Sign-Up":
    st.subheader("Current Sign-Ups")
    calendar_data = bookings_df.copy()
    if not calendar_data.empty:
        now = datetime.now()
        # 🔄 Fixed datetime parser
        calendar_data["slot_dt"] = calendar_data["slot"].apply(
            lambda x: datetime.strptime(f"{x.split()[1]} {x.split()[2].split('–')[0]} {x.split()[3]}", "%m/%d/%y %I:%M %p")
        )
        calendar_data = calendar_data[calendar_data["slot_dt"].dt.date >= now.date()]
        calendar_data["first_name"] = calendar_data["name"].apply(lambda x: x.split(" ")[0] if pd.notnull(x) else "")
        calendar_data["day"] = calendar_data["slot"].apply(lambda x: " ".join(x.split(" ")[:2]))
        grouped = calendar_data.groupby("day")
        sorted_days = sorted(grouped.groups.keys(), key=lambda d: datetime.strptime(d.split(" ")[1], "%m/%d/%y"))

        for day in sorted_days:
            group = grouped.get_group(day)
            with st.expander(f"{day} ({len(group)} sign-up{'s' if len(group) != 1 else ''})"):
                grouped_view = group.sort_values("slot").groupby(["first_name", "email"])
                display_rows = []
                for (name, _), slots in grouped_view:
                    sorted_slots = slots["slot"].tolist()
                    if len(sorted_slots) == 2:
                        start = sorted_slots[0].rsplit(" ", 1)[-1].split("-")[0]
                        end = sorted_slots[1].rsplit(" ", 1)[-1].split("-")[-1]
                        label = f"{sorted_slots[0].rsplit(' ', 1)[0]} {start}-{end}"
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
            weekly_bookings = bookings_df[(bookings_df["email"] == email) & (
                bookings_df["slot"].apply(lambda s: datetime.strptime(s.split(" ")[1], "%m/%d/%y").isocalendar().week == selected_week)
            )]

                        # Prevent rescheduling on the same day
            today_str = datetime.today().strftime("%m/%d/%y")
            today_bookings = [b for b in weekly_bookings["slot"] if b.split(" ")[1] == today_str]
            if today_bookings:
                st.warning("You cannot reschedule an appointment on the same day. Please speak with a professor if needed.")
                st.stop()

            if len(weekly_bookings) == 1:
                bookings_df = bookings_df[~((bookings_df["email"] == email) & (bookings_df["slot"].isin(weekly_bookings["slot"])))].copy()
                st.info("Your previous booking for this week will be replaced with the new one.")
            elif len(weekly_bookings) == 2 and weekly_bookings.iloc[0]['dsps']:
                for s in weekly_bookings["slot"]:
                    bookings_df = bookings_df[~((bookings_df["email"] == email) & (bookings_df["slot"] == s))].copy()
                st.info("Your DSPS booking for this week will be replaced with the new one.")
            else:
                st.warning("Unable to determine which appointment to reschedule. Please contact an administrator.")
                st.stop()
                # Prevent rescheduling on the same day
                today_str = datetime.today().strftime("%m/%d/%y")
                booking_dates = [b.split(" ")[1] for b in weekly_bookings["slot"]]
                if today_str in booking_dates:
                    st.warning("You cannot reschedule an appointment on the same day. Please speak with a professor if needed.")
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
        double_slot_options = [label for label in double_blocks if selected_day in label and all(s in allowed_slots and s not in bookings_df["slot"].values for s in double_blocks[label])]
        if double_slot_options:
            selected_block = st.selectbox("Choose a double time block:", double_slot_options)
            if st.button("Select This Time Block"):
                st.session_state["selected_slot"] = selected_block
                st.session_state["confirming"] = True
                st.rerun()
        else:
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
                new_booking = pd.DataFrame([{ 
                    "name": name, 
                    "email": email, 
                    "student_id": student_id, 
                    "dsps": dsps, 
                    "slot": s 
                }])
                bookings_df = pd.concat([bookings_df, new_booking], ignore_index=True)
          else:
            new_booking = pd.DataFrame([{ 
                "name": name, 
                "email": email, 
                "student_id": student_id, 
                "dsps": dsps, 
                "slot": st.session_state["selected_slot"] 
            }])
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

        # New feature: Download today's sign-ups in chronological order
        st.subheader("Download Today's Sign-Ups")
        today_str = datetime.today().strftime("%m/%d/%y")
        todays_df = bookings_df[bookings_df["slot"].str.contains(today_str)].copy()
        todays_df["slot_dt"] = todays_df["slot"].apply(lambda x: datetime.strptime(f"{x.split()[1]} {x.split()[2].split('–')[0]} {x.split()[3]}", "%m/%d/%y %I:%M %p"))
        todays_df = todays_df.sort_values("slot_dt").drop(columns=["slot_dt"])
        st.download_button("📅 Download Today's Appointments", todays_df.to_csv(index=False), file_name="todays_appointments.csv")

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
                    slot_lookup[display_label] = pair[0]  # store only the first slot to identify the pair later

            if current_booking["dsps"]:
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

        selected_by_day = {}

        for day, slots in slots_by_day.items():
            with st.expander(f"{day}"):
                if st.button(f"Select All {day}", key=f"select_all_{day}"):
                    for slot in slots:
                        st.session_state[f"avail_{slot}"] = True

                if st.button(f"Deselect All {day}", key=f"deselect_all_{day}"):
                    for slot in slots:
                        st.session_state[f"avail_{slot}"] = False

                weekday_label = day.split()[0]
                

                selected_by_day[day] = []
                for slot in slots:
                    is_selected = availability_df.loc[availability_df["slot"] == slot, "available"].values[0] if slot in availability_df["slot"].values else False
                    checked = st.checkbox(slot.split(" ")[-2] + " " + slot.split(" ")[-1], value=st.session_state.get(f"avail_{slot}", is_selected), key=f"avail_{slot}")
                    if checked:
                        selected_by_day[day].append(slot)

        selected_available = [slot for slots in selected_by_day.values() for slot in slots]
        availability_df["available"] = availability_df["slot"].isin(selected_available)

        if st.button("Save Availability"):
            availability_df.to_csv(available_file, index=False)
            st.success("Availability updated successfully!")
    elif availability_passcode:
        st.error("Incorrect passcode.")
