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
    json_key = json.dumps(st.secrets["google_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(json_key), scope)

    client = gspread.authorize(creds)
    return client.open("atlab_bookings").sheet1

def load_bookings():
    sheet = get_gsheet_connection()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def append_booking(row):
    sheet = get_gsheet_connection()
    sheet.append_row(row)

def overwrite_bookings(df):
    sheet = get_gsheet_connection()
    sheet.clear()
    sheet.insert_row(df.columns.tolist(), 1)
    for row in df.itertuples(index=False):
        sheet.append_row(list(row))
