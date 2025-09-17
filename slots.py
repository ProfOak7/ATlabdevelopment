from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

EN_DASH = "–"  # keep this consistent with the parser

def generate_slot_label(day_dt: datetime, start_dt: datetime, end_dt: datetime) -> str:
    """
    Standard slot label:
      'Monday mm/dd/yy h:MM–h:MM AM'
    AM/PM appears only once at the end (works with our tolerant parser).
    """
    label_day = day_dt.strftime("%A %m/%d/%y")
    start_fmt = start_dt.strftime("%I:%M").lstrip("0")
    end_fmt = end_dt.strftime("%I:%M %p").lstrip("0")
    return f"{label_day} {start_fmt}{EN_DASH}{end_fmt}"

def _build_day_slots(day_dt: datetime, hours: Dict[int, Tuple[str, str]], slot_minutes: int) -> List[str]:
    """
    Create all slot strings for one day given a weekday->(start,end) mapping in 24h 'HH:MM'.
    Produces half-open intervals [start, start+slot) until < end.
    """
    weekday = day_dt.weekday()
    if weekday not in hours:
        return []

    start_str, end_str = hours[weekday]
    start_time = datetime.strptime(start_str, "%H:%M").time()
    end_time = datetime.strptime(end_str, "%H:%M").time()

    cur = datetime.combine(day_dt.date(), start_time)
    end = datetime.combine(day_dt.date(), end_time)

    slots: List[str] = []
    step = timedelta(minutes=slot_minutes)

    while cur < end:
        nxt = cur + step
        if nxt > end:
            break  # avoid short tail slot
        slots.append(generate_slot_label(day_dt, cur, nxt))
        cur = nxt

    return slots

def generate_slots(horizon_days: int = 21, slot_minutes: int = 15):
    """
    Returns (slo_slots_by_day, ncc_slots_by_day), each a dict:
      { 'Weekday mm/dd/yy': ['Weekday mm/dd/yy 9:00–9:15 AM', ...] }
    """
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    days = [today + timedelta(days=i) for i in range(horizon_days)]

    # Weekday indices: Mon=0 ... Sun=6
    slo_hours = {
        0: ("09:00", "21:00"),
        1: ("09:00", "21:00"),
        2: ("08:30", "21:00"),
        3: ("08:15", "20:30"),
        4: ("09:15", "15:00"),
        5: ("09:15", "13:00"),
        # 6: closed (Sunday)
    }

    ncc_hours = {
        0: ("12:00", "16:00"),
        1: ("08:15", "20:00"),
        2: ("08:15", "17:00"),
        3: ("09:15", "17:00"),
        4: ("08:15", "15:00"),
        # 5,6: closed
    }

    slo_slots_by_day: Dict[str, List[str]] = {}
    ncc_slots_by_day: Dict[str, List[str]] = {}

    for day_dt in days:
        # SLO
        slo_slots = _build_day_slots(day_dt, slo_hours, slot_minutes)
        if slo_slots:
            day_key = day_dt.strftime("%A %m/%d/%y")
            slo_slots_by_day[day_key] = sorted(slo_slots)

        # NCC
        ncc_slots = _build_day_slots(day_dt, ncc_hours, slot_minutes)
        if ncc_slots:
            day_key = day_dt.strftime("%A %m/%d/%y")
            ncc_slots_by_day[day_key] = sorted(ncc_slots)

    return slo_slots_by_day, ncc_slots_by_day
