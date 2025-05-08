import smtplib
from email.mime.text import MIMEText
import streamlit as st

def send_confirmation_email(to_email, student_name, slot, location):
    sender_email = st.secrets["EMAIL_ADDRESS"]
    password = st.secrets["EMAIL_PASSWORD"]

    subject = "AT Lab Appointment Confirmation"
    body = f"""Hi {student_name},

Your appointment has been successfully booked for:

{slot} @ {location}

See you at the AT Lab!

- Cuesta College"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, password)
            server.sendmail(sender_email, to_email, msg.as_string())
    except Exception as e:
        st.warning(f"Email could not be sent: {e}")
