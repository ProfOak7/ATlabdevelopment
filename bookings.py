import json
import pandas as pd
import gspread
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials
from io import StringIO

SHEET_NAME = "atlab_bookings"  # Must match your actual Google Sheet name

def get_gsheet_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Read credentials from st.secrets
    json_key = st.secrets["google_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(json_key), scope)

    client = gspread.authorize(creds)
    return client.open("atlab_bookings").sheet1

@st.cache_data(ttl=60)
def load_bookings():
    sheet = get_gsheet_connection()
    values = sheet.get_all_values()

    if not values or len(values) < 2:
        return pd.DataFrame(columns=[
            "name", "student_id", "email", "lab_location",
            "day", "time", "slot", "dsps", "timestamp"
        ])

    header = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=header)
    df.columns = df.columns.str.strip().str.lower()
    return df


def append_booking(row):
    sheet = get_gsheet_connection()
    sheet.append_row(row)
    st.cache_data.clear()  # Invalidate the cache after appending

def overwrite_bookings(df):
    sheet = get_gsheet_connection()
    sheet.clear()
    sheet.insert_row(df.columns.tolist(), 1)
    for row in df.itertuples(index=False):
        sheet.append_row(list(row))
    st.cache_data.clear()  # Invalidate cache after overwrite


