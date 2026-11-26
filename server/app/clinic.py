"""In-memory clinic data: doctors, slots and appointments.

State lives in this process and resets on restart. The agent's tools and the
REST API both go through this module.
"""

from __future__ import annotations

import asyncio
import difflib
import itertools
import re
from datetime import date, datetime, timedelta

DAYS_AHEAD = 5  # working days open for booking

DOCTORS = [
    {
        "id": "sharma",
        "name": "Dr. Anjali Sharma",
        "speciality": "Cardiology",
        "times": ["09:30", "10:00", "11:30", "16:00", "16:30"],
    },
    {
        "id": "mehta",
        "name": "Dr. Rohan Mehta",
        "speciality": "Dermatology",
        "times": ["10:00", "10:30", "12:00", "15:00", "17:30"],
    },
    {
        "id": "iyer",
        "name": "Dr. Kavya Iyer",
        "speciality": "Pediatrics",
        "times": ["09:00", "09:30", "11:00", "14:30", "15:00"],
    },
    {
        "id": "khan",
        "name": "Dr. Imran Khan",
        "speciality": "Orthopedics",
        "times": ["11:00", "11:30", "13:00", "16:30", "17:00"],
    },
    {
        "id": "verma",
        "name": "Dr. Neha Verma",
        "speciality": "General Medicine",
        "times": ["09:00", "10:30", "12:30", "14:00", "18:00"],
    },
]

_appointments: list[dict] = []
_ids = itertools.count(1001)
_subscribers: set[asyncio.Queue] = set()


class ClinicError(Exception):
    """An error worded for the agent to relay to the caller."""


def working_days() -> list[date]:
    days, d = [], date.today()
    while len(days) < DAYS_AHEAD:
        if d.weekday() != 6:  # clinic is closed on Sunday
            days.append(d)
        d += timedelta(days=1)
    return days


def day_label(d: date) -> str:
    if d == date.today():
        return "Today"
    if d == date.today() + timedelta(days=1):
        return "Tomorrow"
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def time_label(t: str) -> str:
    return datetime.strptime(t, "%H:%M").strftime("%I:%M %p").lstrip("0")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    # "+91 98290 12345" and "098290 12345" are the same caller as "9829012345".
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ClinicError(
            f"A phone number has 10 digits, but {len(digits)} were heard. Ask the caller to say the full number again."
        )
    return digits


def find_doctor(query: str) -> dict | None:
    """Match a spoken name like 'doctor mehta' or 'Rohan' to a doctor."""
    q = re.sub(r"\b(dr|doctor)\b\.?", "", (query or "").lower()).strip()
    if not q:
        return None
    for doc in DOCTORS:
        name = doc["name"].lower().replace("dr. ", "")
        if q == doc["id"] or q in name or any(part == q for part in name.split()):
            return doc
    # Speech-to-text often misspells names, so allow a close match.
    words = {w: doc for doc in DOCTORS for w in doc["name"].lower().replace("dr. ", "").split()}
    for word in q.split():
        close = difflib.get_close_matches(word, list(words), n=1, cutoff=0.75)
        if close:
            return words[close[0]]
    return None


def parse_date(text: str) -> date | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    if t == "today":
        return date.today()
    if t == "tomorrow":
        return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(t)
    except ValueError:
        pass
    for d in working_days():
        if d.strftime("%A").lower() == t:
            return d
    raise ClinicError(f"Could not understand the date '{text}'. Use YYYY-MM-DD.")


def parse_time(text: str) -> str:
    t = (text or "").strip().upper().replace(".", "")
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            return datetime.strptime(t, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ClinicError(f"Could not understand the time '{text}'. Use HH:MM in 24-hour format.")


def _is_taken(doctor_id: str, day: str, time: str) -> bool:
    return any(
        a["status"] == "booked" and a["doctor_id"] == doctor_id and a["date"] == day and a["time"] == time
        for a in _appointments
    )


def _free_times(doc: dict, d: date) -> list[str]:
    now = datetime.now().strftime("%H:%M")
    return [
        t
        for t in doc["times"]
        if not _is_taken(doc["id"], d.isoformat(), t) and not (d == date.today() and t <= now)
    ]


def _who_we_have() -> str:
    return "The clinic has: " + ", ".join(f"{d['name']} ({d['speciality']})" for d in DOCTORS) + "."


def availability(doctor: str = "", speciality: str = "", day: str = "") -> list[dict]:
    """Free slots, filtered by doctor and/or speciality and/or date."""
    docs = DOCTORS
    if doctor:
        match = find_doctor(doctor)
        if not match:
            raise ClinicError(f"No doctor found matching '{doctor}'. {_who_we_have()}")
        docs = [match]
    elif speciality:
        s = speciality.lower()
        # "dermatologist" and "Dermatology" share a stem; a plain substring test misses that.
        docs = [
            d
            for d in DOCTORS
            if s in d["speciality"].lower()
            or d["speciality"].lower() in s
            or s[:6] == d["speciality"].lower()[:6]
        ]
        if not docs:
            raise ClinicError(f"We have no doctor for '{speciality}'. {_who_we_have()}")

    wanted = parse_date(day)
    days = working_days()
    if wanted:
        if wanted not in days:
            raise ClinicError("We only book from today up to the next five working days, and not on Sunday.")
        days = [wanted]
    # Tool results are re-sent to the LLM on every turn, so without a date
    # return only the next few open days and the earliest slots.
    max_days = len(days) if wanted else (3 if len(docs) == 1 else 1)

    result = []
    for doc in docs:
        shown = 0
        for d in days:
            free = _free_times(doc, d)
            if free and shown < max_days:
                shown += 1
                result.append(
                    {
                        "doctor": doc["name"],
                        "date": d.isoformat(),
                        "day": day_label(d),
                        "free_slots": [time_label(t) for t in (free if wanted else free[:2])],
                    }
                )
                if doctor:
                    continue
                result[-1]["speciality"] = doc["speciality"]
    publish({"type": "checked", "doctor_ids": [d["id"] for d in docs]})
    return result


def book(doctor: str, day: str, time: str, phone: str, patient_name: str = "") -> dict:
    doc = find_doctor(doctor)
    if not doc:
        raise ClinicError(f"No doctor found matching '{doctor}'.")
    d = parse_date(day)
    if not d or d not in working_days():
        raise ClinicError("That date is not open for booking.")
    t = parse_time(time)
    number = normalize_phone(phone)
    for a in _appointments:
        if a["status"] == "booked" and (a["doctor_id"], a["date"], a["time"], a["phone"]) == (
            doc["id"],
            d.isoformat(),
            t,
            number,
        ):
            # Idempotent: the agent sometimes books the same slot twice.
            return a
    if t not in _free_times(doc, d):
        free = ", ".join(time_label(x) for x in _free_times(doc, d)) or "nothing"
        raise ClinicError(f"{time_label(t)} is not free. Free on {day_label(d)}: {free}.")

    appointment = {
        "id": f"APT-{next(_ids)}",
        "doctor_id": doc["id"],
        "doctor": doc["name"],
        "speciality": doc["speciality"],
        "date": d.isoformat(),
        "day": day_label(d),
        "time": t,
        "time_label": time_label(t),
        "phone": number,
        "patient": patient_name.strip() or "Caller",
        "status": "booked",
    }
    _appointments.append(appointment)
    publish({"type": "booked", "appointment": appointment})
    return appointment


def cancel(phone: str, appointment_id: str = "") -> dict:
    number = normalize_phone(phone)
    active = [a for a in _appointments if a["phone"] == number and a["status"] == "booked"]
    if not active:
        raise ClinicError(
            "No active appointment is booked under that number. A caller can only cancel their own. "
            "Say so once; do not ask for the number again."
        )
    if appointment_id:
        active = [a for a in active if a["id"].lower() == appointment_id.strip().lower()]
        if not active:
            raise ClinicError("That appointment id does not belong to this number.")
    if len(active) > 1:
        return {"needs_choice": True, "appointments": active}
    appointment = active[0]
    appointment["status"] = "cancelled"
    publish({"type": "cancelled", "appointment": appointment})
    return appointment


def doctors_view() -> list[dict]:
    view = []
    for doc in DOCTORS:
        days = []
        for d in working_days():
            free = set(_free_times(doc, d))
            days.append(
                {
                    "date": d.isoformat(),
                    "label": day_label(d),
                    "slots": [
                        {
                            "time": t,
                            "label": time_label(t),
                            "free": t in free,
                            "state": "free"
                            if t in free
                            else "booked"
                            if _is_taken(doc["id"], d.isoformat(), t)
                            else "past",
                        }
                        for t in doc["times"]
                    ],
                }
            )
        view.append({"id": doc["id"], "name": doc["name"], "speciality": doc["speciality"], "days": days})
    return view


def appointments_view() -> list[dict]:
    return sorted(_appointments, key=lambda a: (a["status"] != "booked", a["date"], a["time"]))


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def publish(event: dict) -> None:
    for q in _subscribers:
        q.put_nowait(event)


def reset() -> None:
    """Restores the seed data. Used by the tests."""
    global _ids
    _appointments.clear()
    _ids = itertools.count(1001)
    seed()


def seed() -> None:
    """Adds two sample appointments so the dashboard is not empty."""
    if _appointments:
        return
    days = working_days()
    for doc_id, d, t, phone, name in [
        ("iyer", days[1], "11:00", "9829012345", "Aarav Jain"),
        ("khan", days[2], "16:30", "9414067890", "Meera Nair"),
    ]:
        doc = next(x for x in DOCTORS if x["id"] == doc_id)
        _appointments.append(
            {
                "id": f"APT-{next(_ids)}",
                "doctor_id": doc["id"],
                "doctor": doc["name"],
                "speciality": doc["speciality"],
                "date": d.isoformat(),
                "day": day_label(d),
                "time": t,
                "time_label": time_label(t),
                "phone": phone,
                "patient": name,
                "status": "booked",
            }
        )
