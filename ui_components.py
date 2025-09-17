# ui_components.py — unified components for Student Sign-Up, Admin, Tutor
from __future__ import annotations
from datetime import datetime
from typing import List, Dict, Any
from uuid import uuid4

import pandas as pd
import pytz
import streamlit as st

from bookings import (
    load_bookings,
    overwrite_bookings,
    append_booking_dict,   # use dict-based appends to avoid column-order issues
)
from utils import parse_slot_time
from email_utils import send_confirmation_email

# ----------------------------- Constants -----------------------------
EXAM_NUMBERS = [str(i) for i in range(2, 11)]

STATUS_BOOKED = "booked"
STATUS_CANCELED = "canceled"
DSPS_ANONYMIZE_SECOND_SLOT = True  # display-only if you ever show rosters

# Canonical columns used throughout the app (superset of legacy)
REQUIRED_COLS = [
    "name",
    "email",
    "student_id",
    "dsps",
    "slot",
    "lab_location",
    "exam_number",
    "grade",
    "graded_by",
    "group_id",
    "status",
    "created_at",
    "updated_at",
]

PACIFIC = pytz.timezone("US/Pacific")

# --------------------------- Data Utilities --------------------------
def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in REQUIRED_COLS:
        if c not in df.columns:
            if c in ("grade", "graded_by", "group_id"):
                df[c] = ""
            elif c == "status":
                df[c] = STATUS_BOOKED
            elif c in ("created_at", "updated_at"):
                df[c] = ""
            else:
                df[c] = ""
    # Normalize dsps to bool if possible
    if "dsps" in df.columns:
        df["dsps"] = df["dsps"].apply(
            lambda v: True
            if str(v).strip().lower() in ("true", "1", "yes")
            else False if str(v).strip().lower() in ("false", "0", "no")
            else v
        )
    return df

def _active(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_columns(df)
    # treat blank/na status as active (back-compat)
    mask = (df["status"].isin([STATUS_BOOKED, ""])) | (df["status"].isna())
    return df[mask].copy()

def _now_iso() -> str:
    return datetime.now(PACIFIC).isoformat(timespec="seconds")

def _assign_group_ids_for_legacy_dsps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Backfill missing group_id on older DSPS rows (those may have had '(DSPS block)' etc.).
    We group by (email, exam_number, lab_location, calendar-date) and assign a fresh group_id if >=2 rows.
    """
    df = _ensure_columns(df)
    dsps_rows = df[(df["dsps"] == True) & ((df["group_id"] == "") | (df["group_id"].isna()))]
    if dsps_rows.empty:
        return df

    def _date_of(slot_str: str):
        try:
            return parse_slot_time(slot_str).date()
        except Exception:
            return None

    dsps_rows = dsps_rows.copy()
    dsps_rows["__date"] = dsps_rows["slot"].apply(_date_of)

    keys = ["email", "exam_number", "lab_location", "__date"]
    for _, g in dsps_rows.groupby(keys):
        if len(g) >= 2:
            gid = str(uuid4())
            df.loc[g.index, "group_id"] = gid
            # Normalize status
            df.loc[g.index, "status"] = df.loc[g.index, "status"].replace("", STATUS_BOOKED)
            df.loc[g.index, "updated_at"] = _now_iso()

    if "__date" in df.columns:
        df = df.drop(columns=["__date"], errors="ignore")
    return df

# --------------------------- Tutor Panel -----------------------------
def render_tutor_panel(course_hint="BIO 205: Human Anatomy", knowledge_enabled=False):
    """
    Thin wrapper so you can call this from anywhere without import cycles.
    """
    from tutor import render_chat  # lazy import to avoid circular deps
    st.title("🧠 BIO 205 Tutor")
    st.caption("Conversational study help for BIO 205.")
    render_chat(course_hint=course_hint, knowledge_enabled=knowledge_enabled)

# ------------------------ Student Sign-Up UI -------------------------
def show_student_signup(bookings_df: pd.DataFrame, slo_slots_by_day: Dict[str, List[str]],
                        ncc_slots_by_day: Dict[str, List[str]], now: datetime):
    bookings_df = _ensure_columns(bookings_df)
    active_df = _active(bookings_df)

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
    if not slots_by_day:
        st.info("No availability has been configured yet.")
        return

    selected_day = st.selectbox("Choose a day:", list(slots_by_day.keys()))

    # Build availability from ACTIVE bookings only
    active_slots = set(active_df["slot"].values)

    if dsps:
        available_slots = []
        day_slots = slots_by_day[selected_day]
        for i in range(len(day_slots) - 1):
            s1, s2 = day_slots[i], day_slots[i + 1]
            # both slots must be free and in the future
            if (s1 not in active_slots and s2 not in active_slots
                and PACIFIC.localize(parse_slot_time(s1)) > now
                and PACIFIC.localize(parse_slot_time(s2)) > now):
                available_slots.append(f"{s1} and {s2}")
    else:
        available_slots = [
            s for s in slots_by_day[selected_day]
            if s not in active_slots and PACIFIC.localize(parse_slot_time(s)) > now
        ]

    if not available_slots:
        st.info("No available slots for this day.")
        return

    selected_slot = st.selectbox("Choose a time:", available_slots)

    if st.button("Submit Booking") and (
        (not dsps and selected_slot) or (dsps and " and " in selected_slot)
    ):
        # Validate form completeness
        if not all([name, email, student_id, selected_slot]):
            st.error("Please fill out all required fields.")
            return

        # Enforce one-per-week-per-exam & reschedule safely (not same day)
        first_slot_str = selected_slot.split(" and ")[0] if dsps else selected_slot
        target_week = parse_slot_time(first_slot_str).isocalendar().week
        target_date = parse_slot_time(first_slot_str).date()
        today = datetime.now(PACIFIC).date()

        student_bookings = active_df[
            (active_df["email"] == email) & (active_df["exam_number"] == exam_number)
        ]
        weeks = student_bookings["slot"].apply(lambda s: parse_slot_time(s).isocalendar().week)

        # Start from canonical DF for mutations
        updated_df = bookings_df.copy()

        if target_week in weeks.values:
            same_week_rows = student_bookings[student_bookings["slot"].apply(
                lambda s: parse_slot_time(s).isocalendar().week == target_week
            )]

            # no rescheduling on the same calendar day
            if any(parse_slot_time(s).date() == today for s in same_week_rows["slot"].tolist()):
                st.warning("You cannot reschedule an appointment on the day of your appointment.")
                return

            # Cancel by group if available, otherwise cancel matching single(s)
            if same_week_rows["group_id"].replace("", pd.NA).notna().any():
                for gid in same_week_rows["group_id"].unique():
                    if not gid:
                        continue
                    mask = updated_df["group_id"] == gid
                    updated_df.loc[mask, "status"] = STATUS_CANCELED
                    updated_df.loc[mask, "updated_at"] = _now_iso()
            else:
                mask = (
                    (updated_df["email"] == email) &
                    (updated_df["exam_number"] == exam_number) &
                    (updated_df["slot"].apply(lambda s: parse_slot_time(s).isocalendar().week == target_week)) &
                    ((updated_df["status"].isin(["", STATUS_BOOKED])) | updated_df["status"].isna())
                )
                updated_df.loc[mask, "status"] = STATUS_CANCELED
                updated_df.loc[mask, "updated_at"] = _now_iso()

            overwrite_bookings(updated_df)
            bookings_df = updated_df  # keep in sync

        # --- Create new booking rows ---
        created_at = _now_iso()

        if dsps:
            s1, s2 = selected_slot.split(" and ")
            gid = str(uuid4())

            # Write FULL name on both rows; anonymize only in any student-facing roster later
            for s in (s1, s2):
                append_booking_dict({
                    "name": name,
                    "email": email,
                    "student_id": student_id,
                    "dsps": True,
                    "slot": s,
                    "lab_location": lab_location,
                    "exam_number": exam_number,
                    "grade": "",
                    "graded_by": "",
                    "group_id": gid,
                    "status": STATUS_BOOKED,
                    "created_at": created_at,
                    "updated_at": created_at,
                })

            st.success(f"Your DSPS appointment has been recorded for:\n- {s1}\n- {s2}")
            send_confirmation_email(email, name, f"{s1} and {s2}", lab_location)

        else:
            append_booking_dict({
                "name": name,
                "email": email,
                "student_id": student_id,
                "dsps": False,
                "slot": selected_slot,
                "lab_location": lab_location,
                "exam_number": exam_number,
                "grade": "",
                "graded_by": "",
                "group_id": str(uuid4()),
                "status": STATUS_BOOKED,
                "created_at": created_at,
                "updated_at": created_at,
            })
            st.success("Your appointment has been recorded!")
            send_confirmation_email(email, name, selected_slot, lab_location)

        st.rerun()

# -------------------- Availability Settings (stub) --------------------
def show_availability_settings(*args, **kwargs):
    st.info("Availability settings coming soon.")

# --------------------------- Admin View UI ----------------------------
def show_admin_view(bookings_df: pd.DataFrame, slo_slots_by_day: Dict[str, List[str]],
                    ncc_slots_by_day: Dict[str, List[str]], admin_passcode: str):
    passcode_input = st.text_input("Enter admin passcode:", type="password")
    if passcode_input != admin_passcode:
        if passcode_input:
            st.error("Incorrect passcode.")
        return
    st.success("Access granted.")

    # Normalize schema + upgrade legacy DSPS pairs with group_id
    bookings_df = _ensure_columns(bookings_df)
    upgraded_df = _assign_group_ids_for_legacy_dsps(bookings_df)
    if not upgraded_df.equals(bookings_df):
        overwrite_bookings(upgraded_df)
        bookings_df = upgraded_df

    active_df = _active(bookings_df)

    # --- Campus views ---
    slo_bookings = active_df[active_df["lab_location"] == "SLO AT Lab"]
    ncc_bookings = active_df[active_df["lab_location"] == "NCC AT Lab"]

    st.subheader("SLO AT Lab Bookings")
    st.dataframe(slo_bookings)
    st.download_button("Download All SLO Bookings", slo_bookings.to_csv(index=False), file_name="slo_bookings.csv")

    st.subheader("NCC AT Lab Bookings")
    st.dataframe(ncc_bookings)
    st.download_button("Download All NCC Bookings", ncc_bookings.to_csv(index=False), file_name="ncc_bookings.csv")

    # --- Today's Appointments ---
    st.subheader("Download Today's Appointments")
    today_str = pd.Timestamp.now(tz=PACIFIC).strftime("%m/%d/%y")

    def _today_sorted(df: pd.DataFrame) -> pd.DataFrame:
        df2 = df[df["slot"].str.contains(today_str, na=False)].copy()
        if not df2.empty:
            df2["slot_dt"] = df2["slot"].apply(parse_slot_time)
            df2 = df2.sort_values("slot_dt").drop(columns="slot_dt")
        return df2

    todays_slo = _today_sorted(slo_bookings)
    todays_ncc = _today_sorted(ncc_bookings)

    if not todays_slo.empty:
        st.markdown("### SLO AT Lab – Today")
        st.dataframe(todays_slo)
        st.download_button("Download Today's SLO Appointments", todays_slo.to_csv(index=False), file_name="todays_slo_appointments.csv")
    else:
        st.info("No SLO appointments scheduled for today.")

    if not todays_ncc.empty:
        st.markdown("### NCC AT Lab – Today")
        st.dataframe(todays_ncc)
        st.download_button("Download Today's NCC Appointments", todays_ncc.to_csv(index=False), file_name="todays_ncc_appointments.csv")
    else:
        st.info("No NCC appointments scheduled for today.")

    # --- Reschedule (group-aware for DSPS) ---
    st.subheader("Reschedule a Student Appointment")
    if active_df.empty:
        st.info("No active bookings to reschedule.")
        return

    # Build label list; DSPS groups appear once (by earliest slot)
    display_rows: List[Dict[str, Any]] = []
    seen_groups = set()

    for idx, row in active_df.iterrows():
        gid = str(row.get("group_id", "") or "")
        if gid:
            if gid in seen_groups:
                continue
            g = active_df[active_df["group_id"] == gid]
            earliest = g.sort_values("slot").iloc[0]
            label = f"[DSPS] {earliest['name']} ({earliest['email']}) - {earliest['lab_location']} - {', '.join(sorted(g['slot'].tolist()))}"
            display_rows.append({
                "label": label,
                "dsps": True,
                "group_id": gid,
                "lab_location": earliest["lab_location"],
            })
            seen_groups.add(gid)
        else:
            label = f"{row['name']} ({row['email']}) - {row['lab_location']} - {row['slot']}"
            display_rows.append({
                "label": label,
                "dsps": False,
                "row_index": idx,
                "lab_location": row["lab_location"],
            })

    options = [r["label"] for r in display_rows]
    selected = st.selectbox("Select a booking to reschedule", options)
    meta = display_rows[options.index(selected)]

    slots_by_day = slo_slots_by_day if meta["lab_location"] == "SLO AT Lab" else ncc_slots_by_day
    active_slots = set(active_df["slot"].values)

    if meta["dsps"]:
        # Choose a new day with at least one consecutive pair
        day_candidates = [d for d in slots_by_day if len(slots_by_day[d]) >= 2]
        if not day_candidates:
            st.info("No days with consecutive availability.")
            return
        new_day = st.selectbox("Choose a new day:", day_candidates)

        # candidate first slots of consecutive pairs
        firsts = []
        for i in range(len(slots_by_day[new_day]) - 1):
            s1, s2 = slots_by_day[new_day][i], slots_by_day[new_day][i + 1]
            if (s1 not in active_slots) and (s2 not in active_slots):
                firsts.append(s1)

        if not firsts:
            st.info("No consecutive block available for that day.")
            return

        new_first = st.selectbox("Choose the first slot of the DSPS block:", firsts)

        if st.button("Reschedule"):
            i = slots_by_day[new_day].index(new_first)
            new_pair = [slots_by_day[new_day][i], slots_by_day[new_day][i + 1]]

            # Cancel entire group, then re-add with same group_id
            updated_df = bookings_df.copy()
            mask = updated_df["group_id"] == meta["group_id"]
            updated_df.loc[mask, "status"] = STATUS_CANCELED
            updated_df.loc[mask, "updated_at"] = _now_iso()

            g_orig = bookings_df[bookings_df["group_id"] == meta["group_id"]]
            student_name = g_orig.iloc[0]["name"]
            student_email = g_orig.iloc[0]["email"]
            student_id = g_orig.iloc[0]["student_id"]
            exam_number = g_orig.iloc[0]["exam_number"]
            lab_location = meta["lab_location"]

            overwrite_bookings(updated_df)  # persist cancellation

            created_at = _now_iso()
            for s in new_pair:
                append_booking_dict({
                    "name": student_name,
                    "email": student_email,
                    "student_id": student_id,
                    "dsps": True,
                    "slot": s,
                    "lab_location": lab_location,
                    "exam_number": exam_number,
                    "grade": "",
                    "graded_by": "",
                    "group_id": meta["group_id"],
                    "status": STATUS_BOOKED,
                    "created_at": created_at,
                    "updated_at": created_at,
                })

            st.success(f"Successfully rescheduled DSPS student to:\n- {new_pair[0]}\n- {new_pair[1]}")
            st.rerun()

    else:
        # Standard reschedule
        day_options = list(slots_by_day.keys())
        new_day = st.selectbox("Choose a new day:", day_options)

        current_slot = active_df.loc[meta["row_index"], "slot"]
        available = [s for s in slots_by_day[new_day] if (s not in active_slots) or (s == current_slot)]
        if not available:
            st.info("No available slots for that day.")
            return

        new_slot = st.selectbox("Choose a new time:", available)

        if st.button("Reschedule"):
            updated_df = bookings_df.copy()
            # cancel old row
            old_idx = meta["row_index"]
            old_row = updated_df.loc[old_idx]
            updated_df.at[old_idx, "status"] = STATUS_CANCELED
            updated_df.at[old_idx, "updated_at"] = _now_iso()
            overwrite_bookings(updated_df)  # persist cancellation

            # add a fresh row
            created_at = _now_iso()
            append_booking_dict({
                "name": old_row["name"],
                "email": old_row["email"],
                "student_id": old_row["student_id"],
                "dsps": False,
                "slot": new_slot,
                "lab_location": old_row["lab_location"],
                "exam_number": old_row["exam_number"],
                "grade": old_row.get("grade", ""),
                "graded_by": old_row.get("graded_by", ""),
                "group_id": "",
                "status": STATUS_BOOKED,
                "created_at": created_at,
                "updated_at": created_at,
            })

            st.success(f"Successfully rescheduled to {new_slot}!")
            st.rerun()

    # ---------------------------- Grading -----------------------------
    st.subheader("Enter Grades")
    if active_df.empty:
        st.info("No active bookings to grade.")
        return

    grade_options = [
        f"{row['name']} ({row['email']}) - {row['slot']}"
        for _, row in active_df.iterrows()
    ]
    selected_grade_entry = st.selectbox("Select a student to grade", grade_options)
    selected_row = active_df[
        (active_df["name"] + " (" + active_df["email"] + ") - " + active_df["slot"]) == selected_grade_entry
    ].iloc[0]

    st.markdown(
        f"**Current Grade:** {selected_row.get('grade', '')} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"**Graded By:** {selected_row.get('graded_by', '')}"
    )

    if "instructor_initials" not in st.session_state:
        st.session_state.instructor_initials = ""

    new_grade = st.text_input("Enter numeric grade:", value=selected_row.get("grade", ""))
    new_graded_by = st.text_input("Graded by (initials):", value=st.session_state.instructor_initials)

    if st.button("Save Grade"):
        updated_df = load_bookings()  # fresh read to avoid race
        updated_df = _ensure_columns(updated_df)

        # choose the first matching active row for that student+slot
        mask = (
            (updated_df["email"] == selected_row["email"]) &
            (updated_df["slot"] == selected_row["slot"]) &
            (updated_df["status"].isin([STATUS_BOOKED, ""]) | updated_df["status"].isna())
        )
        idxs = updated_df.index[mask].tolist()
        if not idxs:
            st.error("Could not locate the booking (it may have been changed).")
            st.stop()

        idx = idxs[0]
        updated_df.at[idx, "grade"] = new_grade
        updated_df.at[idx, "graded_by"] = new_graded_by
        updated_df.at[idx, "updated_at"] = _now_iso()

        overwrite_bookings(updated_df)
        st.session_state.instructor_initials = new_graded_by
        st.success("Grade successfully saved.")
        st.rerun()
