"""Whether a requested time fits a caregiver's saved availability (#297, #307).

A request is only sent for time the caregiver has opened on their
Availability calendar. Care that runs past midnight needs open time on each
day it covers: until the end of the first day and from the start of the next.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

from caregivers.models import CaregiverAvailability

# A slot ending at 23:59 counts as open until midnight (time fields stop there).
END_OF_DAY = time(23, 59)


def day_pieces(start, end):
    """The local (day, from, to) pieces of [start, end); `to` is None for midnight."""
    start, end = timezone.localtime(start), timezone.localtime(end)
    pieces = []
    day = start.date()
    while True:
        day_end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time()))
        piece_start = start if day == start.date() else day_end - timedelta(days=1)
        if end <= day_end:
            pieces.append((day, piece_start.time(), end.time()))
            break
        pieces.append((day, piece_start.time(), None))
        day += timedelta(days=1)
    return pieces


def covered_by_availability(caregiver, start, end):
    """True when every part of [start, end) falls inside one of the
    caregiver's availability slots on that day."""
    pieces = day_pieces(start, end)
    slots = {}
    for slot in CaregiverAvailability.objects.filter(
        caregiver=caregiver, date__in=[day for day, _, _ in pieces]
    ):
        slots.setdefault(slot.date, []).append(slot)
    for day, piece_start, piece_end in pieces:
        if not any(
            slot.start_time <= piece_start
            and (
                slot.end_time >= END_OF_DAY
                if piece_end is None
                else slot.end_time >= piece_end
            )
            for slot in slots.get(day, [])
        ):
            return False
    return True
