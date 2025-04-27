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

# [Continue with your existing UI code... student signups, admin panel, etc]

# Your other tabs (Admin View, Availability Settings) stay unchanged except better calendar parsing!

# END of fixed copy 🚀
