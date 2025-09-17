from __future__ import annotations
import re
from datetime import datetime
from typing import Tuple, Optional

# Precompile a tolerant pattern:
# Examples matched:
#   "Monday 05/06/24 9:00–9:15 AM"
#   "Mon 5/6/2024 09:00-09:15 am"
#   "Tuesday 05/06/24 9:00 to 9:15 PM"
#   "Friday 05/06/24 9:00—9:15"
_SLOT_RE = re.compile(
    r"""
    ^\s*
    (?P<day>[A-Za-z]{3,9})         # Weekday, ignored
    \s+
    (?P<date>\d{1,2}/\d{1,2}/\d{2,4})
    \s+
    (?P<start>\d{1,2}:\d{2})
    \s*(?:–|—|-|to)\s*             # en dash, em dash, hyphen, or 'to'
    (?P<end>\d{1,2}:\d{2})
    (?:\s*(?P<ampm>(?:AM|PM|am|pm)))?
    \s*$
    """,
    re.VERBOSE,
)

# Sometimes apps emit AM/PM after each time; catch that too:
_SLOT_RE_BOTH_AMPM = re.compile(
    r"""
    ^\s*
    (?P<day>[A-Za-z]{3,9})
    \s+
    (?P<date>\d{1,2}/\d{1,2}/\d{2,4})
    \s+
    (?P<start>\d{1,2}:\d{2})\s*(?P<ampm_start>(?:AM|PM|am|pm))?
    \s*(?:–|—|-|to)\s*
    (?P<end>\d{1,2}:\d{2})\s*(?P<ampm_end>(?:AM|PM|am|pm))?
    \s*$
    """,
    re.VERBOSE,
)

def _parse_date(date_str: str) -> str:
    """Return normalized date string in mm/dd/yy or mm/dd/YYYY usable for strptime."""
    # Try mm/dd/yy first, then mm/dd/YYYY
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            # Preserve the *original* intended year by reformatting to the matched format
            return dt.strftime(fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {date_str!r}")

def _normalize_ampm(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip().upper()
    return "AM" if s == "AM" else ("PM" if s == "PM" else None)

def _try_parse(dt_part: str, fmt: str) -> Optional[datetime]:
    try:
        return datetime.strptime(dt_part, fmt)
    except ValueError:
        return None

def parse_slot_time(slot_str: str) -> datetime:
    """
    Return the *start* datetime of a slot string like:
      'Monday 05/06/24 9:00–9:15 AM'
    Robust to dash variants, 'to', 2/4-digit years, and AM/PM placement.
    Produces a timezone-naive datetime (localize later in the app).
    """
    start_dt, _ = parse_slot_range(slot_str)
    return start_dt

def parse_slot_range(slot_str: str) -> Tuple[datetime, datetime]:
    """
    Parse a slot string and return (start_datetime, end_datetime), both naive.
    """
    m = _SLOT_RE.match(slot_str)
    ampm_start = ampm_end = None
    if not m:
        m = _SLOT_RE_BOTH_AMPM.match(slot_str)
        if not m:
            raise ValueError(f"Error parsing slot time: {slot_str!r} (pattern mismatch)")
        ampm_start = _normalize_ampm(m.group("ampm_start"))
        ampm_end = _normalize_ampm(m.group("ampm_end"))
    else:
        ampm = _normalize_ampm(m.group("ampm"))
        ampm_start = ampm_end = ampm

    date_s = _parse_date(m.group("date"))
    start_s = m.group("start")
    end_s = m.group("end")

    # Build candidate formats. If AM/PM present, use 12h; else try 12h then 24h.
    start_candidates = []
    end_candidates = []

    if ampm_start:
        start_candidates.append((f"{date_s} {start_s} {ampm_start}", "%m/%d/%y %I:%M %p"))
        start_candidates.append((f"{date_s} {start_s} {ampm_start}", "%m/%d/%Y %I:%M %p"))
    else:
        # Try with 12h (no am/pm given) → ambiguous, but sometimes upstream forgets it
        start_candidates.append((f"{date_s} {start_s}", "%m/%d/%y %I:%M"))
        start_candidates.append((f"{date_s} {start_s}", "%m/%d/%Y %I:%M"))
        # Then 24h
        start_candidates.append((f"{date_s} {start_s}", "%m/%d/%y %H:%M"))
        start_candidates.append((f"{date_s} {start_s}", "%m/%d/%Y %H:%M"))

    if ampm_end:
        end_candidates.append((f"{date_s} {end_s} {ampm_end}", "%m/%d/%y %I:%M %p"))
        end_candidates.append((f"{date_s} {end_s} {ampm_end}", "%m/%d/%Y %I:%M %p"))
    else:
        end_candidates.append((f"{date_s} {end_s}", "%m/%d/%y %I:%M"))
        end_candidates.append((f"{date_s} {end_s}", "%m/%d/%Y %I:%M"))
        end_candidates.append((f"{date_s} {end_s}", "%m/%d/%y %H:%M"))
        end_candidates.append((f"{date_s} {end_s}", "%m/%d/%Y %H:%M"))

    start_dt = None
    for s, fmt in start_candidates:
        start_dt = _try_parse(s, fmt)
        if start_dt:
            break
    if not start_dt:
        raise ValueError(f"Could not parse start time from: {slot_str!r}")

    end_dt = None
    for s, fmt in end_candidates:
        end_dt = _try_parse(s, fmt)
        if end_dt:
            break
    if not end_dt:
        raise ValueError(f"Could not parse end time from: {slot_str!r}")

    # If only one AM/PM given (common), ensure end follows start; if end < start, assume it shares the same AM/PM context
    if end_dt < start_dt:
        # Heuristic: add 12 hours to end (crossed noon) if format ambiguity created a wrap
        end_dt = end_dt.replace(hour=(end_dt.hour + 12) % 24)

    return start_dt, end_dt

# Handy helpers used throughout the app
def slot_week(slot_str: str) -> int:
    """ISO week number for a slot (for 'one per week' checks)."""
    return parse_slot_time(slot_str).isocalendar().week

def slot_date(slot_str: str):
    """date() for a slot's start."""
    return parse_slot_time(slot_str).date()

def same_iso_week(a_slot: str, b_slot: str) -> bool:
    """True if two slots fall in the same ISO week."""
    return slot_week(a_slot) == slot_week(b_slot)
