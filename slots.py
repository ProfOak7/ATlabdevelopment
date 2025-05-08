from datetime import datetime, timedelta

def generate_slots():
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    days = [today + timedelta(days=i) for i in range(21)]

    slo_hours = {
        0: ("09:00", "21:00"),
        1: ("09:00", "21:00"),
        2: ("08:30", "21:00"),
        3: ("08:15", "20:30"),
        4: ("09:15", "15:00"),
        5: ("09:15", "13:00")
    }

    ncc_hours = {
        0: ("12:00", "16:00"),
        1: ("08:15", "20:00"),
        2: ("08:15", "17:00"),
        3: ("09:15", "17:00"),
        4: ("08:15", "15:00")
    }

    slo_slots_by_day, ncc_slots_by_day = {}, {}

    for day in days:
        weekday = day.weekday()
        label_day = day.strftime('%A %m/%d/%y')

        if weekday in slo_hours:
            start_str, end_str = slo_hours[weekday]
            current_time = datetime.combine(day.date(), datetime.strptime(start_str, "%H:%M").time())
            end_time = datetime.combine(day.date(), datetime.strptime(end_str, "%H:%M").time())
            while current_time < end_time:
                start_fmt = current_time.strftime('%I:%M').lstrip("0")
                end_fmt = (current_time + timedelta(minutes=15)).strftime('%I:%M %p').lstrip("0")
                slot = f"{label_day} {start_fmt}–{end_fmt}"
                slo_slots_by_day.setdefault(label_day, []).append(slot)
                current_time += timedelta(minutes=15)

        if weekday in ncc_hours:
            start_str, end_str = ncc_hours[weekday]
            current_time = datetime.combine(day.date(), datetime.strptime(start_str, "%H:%M").time())
            end_time = datetime.combine(day.date(), datetime.strptime(end_str, "%H:%M").time())
            while current_time < end_time:
                start_fmt = current_time.strftime('%I:%M').lstrip("0")
                end_fmt = (current_time + timedelta(minutes=15)).strftime('%I:%M %p').lstrip("0")
                slot = f"{label_day} {start_fmt}–{end_fmt}"
                ncc_slots_by_day.setdefault(label_day, []).append(slot)
                current_time += timedelta(minutes=15)

    return slo_slots_by_day, ncc_slots_by_day
