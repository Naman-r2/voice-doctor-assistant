"""The clinic's data and the three things that can be done to it."""

import pytest

from app import clinic


def test_finds_a_doctor_from_a_misheard_name(tomorrow):
    free = clinic.availability(doctor="doctor meta", day=tomorrow)
    assert free[0]["doctor"] == "Dr. Rohan Mehta"


def test_unknown_doctor_error_lists_who_the_clinic_has():
    with pytest.raises(clinic.ClinicError, match="Dr. Neha Verma"):
        clinic.availability(doctor="Gupta")


def test_availability_without_a_date_offers_only_the_earliest_slots(tomorrow):
    assert all(len(day["free_slots"]) <= 2 for day in clinic.availability(doctor="mehta"))
    assert len(clinic.availability(doctor="mehta", day=tomorrow)[0]["free_slots"]) == 5


def test_books_and_normalises_the_phone_number(tomorrow):
    a = clinic.book("Mehta", tomorrow, "15:00", "+91 98290 11122", "Naman")
    assert (a["status"], a["phone"], a["time_label"]) == ("booked", "9829011122", "3:00 PM")


def test_a_taken_slot_cannot_be_booked_by_someone_else(tomorrow):
    clinic.book("Mehta", tomorrow, "15:00", "9829011122")
    with pytest.raises(clinic.ClinicError, match="not free"):
        clinic.book("Mehta", tomorrow, "3:00 PM", "9000000000")


def test_booking_the_same_slot_twice_returns_the_same_appointment(tomorrow):
    first = clinic.book("Mehta", tomorrow, "15:00", "9829011122", "Naman")
    again = clinic.book("Dr. Rohan Mehta", tomorrow, "15:00", "9829011122", "Naman")
    assert again["id"] == first["id"]
    assert len([a for a in clinic.appointments_view() if a["phone"] == "9829011122"]) == 1


def test_a_phone_number_must_have_ten_digits(tomorrow):
    with pytest.raises(clinic.ClinicError, match="10 digits"):
        clinic.book("Mehta", tomorrow, "15:00", "12345")


def test_cancel_frees_the_slot(tomorrow):
    clinic.book("Mehta", tomorrow, "15:00", "9829011122")
    assert clinic.cancel("9829011122")["status"] == "cancelled"
    assert clinic.book("Mehta", tomorrow, "15:00", "9000000000")["status"] == "booked"


def test_cancel_needs_an_appointment_under_that_number():
    with pytest.raises(clinic.ClinicError, match="No active appointment"):
        clinic.cancel("9000000000")


def test_cancel_asks_which_one_when_there_are_several(tomorrow):
    first = clinic.book("Mehta", tomorrow, "15:00", "9829011122")
    clinic.book("Verma", tomorrow, "09:00", "9829011122")
    assert clinic.cancel("9829011122")["needs_choice"]
    assert clinic.cancel("9829011122", first["id"])["id"] == first["id"]


def test_schedule_marks_each_slot_free_booked_or_past(tomorrow):
    clinic.book("Mehta", tomorrow, "15:00", "9829011122")
    mehta = next(d for d in clinic.doctors_view() if d["id"] == "mehta")
    day = next(d for d in mehta["days"] if d["date"] == tomorrow)
    states = {slot["time"]: slot["state"] for slot in day["slots"]}
    assert states["15:00"] == "booked" and states["10:00"] == "free"


def test_events_are_published_to_subscribers(tomorrow):
    queue = clinic.subscribe()
    try:
        clinic.book("Mehta", tomorrow, "15:00", "9829011122")
        assert queue.get_nowait()["type"] == "booked"
    finally:
        clinic.unsubscribe(queue)
