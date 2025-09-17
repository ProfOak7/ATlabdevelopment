# bookings.py — Google Sheets I/O with schema enforcement & backward-compat
import json
from typing import List, Dict, Any

import pandas as pd
import gspread
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials

SHEET_NAME = "atlab_bookings"  # Must match your actual Google Sheet name

# ---- Canonical schema (super-set of legacy) ----
# Order matters; we’ll write headers in this order if we need to create/expand.
REQUIRED_COLS: List[str] = [
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

# Legacy columns we’ll preserve if present (we won’t delete them). If your sheet
# has these, we keep them and fill from data when possible.
LEGACY_COLS: List[str] = [
    "day",
    "time",
    "timestamp",
]

# Minimal defaults for new columns when migrating legacy rows
DEFAULTS: Dict[str, Any] = {
    "grade": "",
    "graded_by": "",
    "group_id": "",
    "status": "booked",
    "created_at": "",
    "updated_at": "",
    "exam_number": "",
}

# ----------------- Internal helpers -----------------
def _get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    json_key = st.secrets["google_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(json_key), scope)
    client = gspread.authorize(creds)
    # Use the first worksheet of the spreadsheet named SHEET_NAME
    return client.open(SHEET_NAME).sheet1

def _clear_cache():
    # Invalidate streamlit cache after mutations
    st.cache_data.clear()

def _normalize_header(names: List[str]) -> List[str]:
    """Lowercase & trim; safe for comparison and DataFrame columns."""
    return [c.strip().lower() for c in names]

def _ensure_header(sheet) -> List[str]:
    """
    Ensure the sheet has a header row and includes REQUIRED_COLS.
    - If empty sheet: write REQUIRED_COLS as the header.
    - If legacy header: append any missing REQUIRED_COLS to the end (don’t delete legacy cols).
    Returns the effective header list as it exists on the sheet (preserving order).
    """
    values = sheet.get_all_values()
    if not values:
        sheet.insert_row(REQUIRED_COLS, 1)
        return REQUIRED_COLS[:]

    if len(values) >= 1:
        raw_header = values[0]
        header = _normalize_header(raw_header)
        # Append any missing required cols
        missing = [c for c in REQUIRED_COLS if c not in header]
        if missing:
            # extend header row (Google Sheets needs a full row update)
            new_header = raw_header + missing
            sheet.update(f"A1:{chr(64+len(new_header))}1", [new_header])
            header = _normalize_header(new_header)
        return header

    # Fallback
    sheet.insert_row(REQUIRED_COLS, 1)
    return REQUIRED_COLS[:]

def _coerce_df(df: pd.DataFrame, header: List[str]) -> pd.DataFrame:
    """Reindex to include all header columns; fill defaults for missing."""
    df = df.copy()
    # Ensure all header columns exist
    for col in header:
        if col not in df.columns:
            # default values for new columns
            df[col] = DEFAULTS.get(col, "")
    # Make sure columns contain at least the header (preserve sheet order)
    df = df.reindex(columns=header)
    # Coerce booleans for dsps from legacy strings if necessary
    if "dsps" in df.columns:
        df["dsps"] = df["dsps"].apply(lambda v: True if str(v).strip().lower() in ("true", "1", "yes") else (False if str(v).strip().lower() in ("false", "0", "no") else v))
    return df

def _pad_row_to_header(row: List[Any], header: List[str]) -> List[Any]:
    """Pad/truncate a list row to match header length."""
    if len(row) < len(header):
        row = row + [""] * (len(header) - len(row))
    elif len(row) > len(header):
        row = row[:len(header)]
    return row

# ----------------- Public API -----------------
@st.cache_data(ttl=60)
def load_bookings() -> pd.DataFrame:
    """
    Loads the entire sheet into a DataFrame.
    - Ensures header includes REQUIRED_COLS (appends them if missing).
    - Preserves legacy columns (day, time, timestamp) if present.
    - Returns DF with columns in the same order as the sheet header.
    """
    sheet = _get_sheet()
    header = _ensure_header(sheet)  # may append missing cols

    values = sheet.get_all_values()
    if not values or len(values) < 2:
        # Sheet with only header or empty
        return pd.DataFrame(columns=header)

    raw_header = _normalize_header(values[0])
    rows = values[1:]
    df = pd.DataFrame(rows, columns=raw_header)

    # If legacy day/time exist but slot missing, keep both, do not overwrite slot
    # (Your app already writes 'slot'. This just preserves old data.)
    df = _coerce_df(df, header)

    return df

def append_booking(row: List[Any]) -> None:
    """
    Append a row (list) to the sheet.
    - Pads/truncates to header length.
    - Assumes the row is already in the intended order (prefer REQUIRED_COLS order).
    """
    sheet = _get_sheet()
    header = _ensure_header(sheet)
    safe_row = _pad_row_to_header(row, header)
    sheet.append_row(safe_row)
    _clear_cache()

def append_booking_dict(row_dict: Dict[str, Any]) -> None:
    """
    Append a row from a dict (keys can be a subset/superset of header).
    Missing keys are defaulted; extra keys are ignored.
    """
    sheet = _get_sheet()
    header = _ensure_header(sheet)
    row = [row_dict.get(k, DEFAULTS.get(k, "")) for k in header]
    sheet.append_row(row)
    _clear_cache()

def overwrite_bookings(df: pd.DataFrame) -> None:
    """
    Replace the sheet content with df.
    - Ensures the header includes REQUIRED_COLS (appending if needed).
    - Reindexes df to match the sheet header (includes legacy cols if present on sheet).
    - Uses simple append loop (fine for class sizes; switch to batch if needed).
    """
    sheet = _get_sheet()
    header = _ensure_header(sheet)

    # Reindex df to sheet header
    df = df.copy()
    # Normalize incoming columns
    df.columns = _normalize_header(list(df.columns))
    df = _coerce_df(df, header)

    # Clear and write header + rows
    sheet.clear()
    sheet.insert_row(header, 1)
    if not df.empty:
        for row in df.itertuples(index=False):
            sheet.append_row(list(row))
    _clear_cache()
