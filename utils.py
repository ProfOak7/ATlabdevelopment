from datetime import datetime

def parse_slot_time(slot_str):
    """
    Parses a slot string like 'Monday 05/06/24 9:00–9:15 AM'
    and returns a datetime object for the start time.
    """
    try:
        parts = slot_str.split()
        return datetime.strptime(f"{parts[1]} {parts[2].split('–')[0]} {parts[3]}", "%m/%d/%y %I:%M %p")
    except Exception as e:
        raise ValueError(f"Error parsing slot time: '{slot_str}' → {e}")
