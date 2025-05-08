import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_NAME = "atlab_bookings"  # Must match your actual Google Sheet name

def get_gsheet_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

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
