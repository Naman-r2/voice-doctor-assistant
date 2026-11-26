"""The tools the model calls, with the model replaced by a recorded conversation."""

from app import clinic
from app.agent import guards, tools
from tests.conftest import FakeCall, agent, user

NUMBER = "9876543210"
TYPED_NUMBER = user(f"{guards.TYPED} {NUMBER} {guards.TYPED_NOTE}")
READ_BACK = agent("Anita with Dr. Verma tomorrow at two, number 9, 8, 7, 6, 5, 4, 3, 2, 1, 0. Is that right?")
CANCEL_READ_BACK = agent("I will cancel the appointment under 9, 8, 7, 6, 5, 4, 3, 2, 1, 0. Is that right?")


def booking(tomorrow, **changes):
    return {
        "doctor": "Dr. Neha Verma",
        "date": tomorrow,
        "time": "14:00",
        "phone_number": NUMBER,
        "phone_confirmed": True,
        "patient_name": "Anita",
        **changes,
    }


def new_bookings():
    return [a for a in clinic.appointments_view() if a["phone"] == NUMBER and a["status"] == "booked"]


# ---------- booking ----------


async def test_books_after_a_read_back_and_a_yes(tomorrow):
    call = FakeCall([user("It's Anita"), READ_BACK, user("Yes")])
    result = await call.call(tools.book_appointment, **booking(tomorrow))
    assert result["ok"] and new_bookings()[0]["patient"] == "Anita"
    # The confirmation is a fixed sentence, not the model's wording.
    assert call.said == [
        "You're booked with Dr. Neha Verma tomorrow at 2 PM. Is there anything else I can help with?"
    ]
    assert not call.model_runs_again


async def test_a_typed_number_books_without_a_read_back(tomorrow):
    call = FakeCall([user("It's Anita"), TYPED_NUMBER])
    assert (await call.call(tools.book_appointment, **booking(tomorrow)))["ok"]


async def test_refuses_an_unconfirmed_number(tomorrow):
    call = FakeCall([user("It's Anita"), user("nine eight seven six five four three two one zero")])
    result = await call.call(tools.book_appointment, **booking(tomorrow))
    assert not result["ok"] and not new_bookings()
    assert call.model_runs_again  # so it reads the number back


async def test_refuses_an_invented_number(tomorrow):
    call = FakeCall([user("It's Anita")])
    assert not (await call.call(tools.book_appointment, **booking(tomorrow, phone_number="5551234567")))["ok"]
    assert (await call.call(tools.book_appointment, **booking(tomorrow, phone_number="")))[
        "error"
    ] == tools.NO_NUMBER
    assert len(clinic.appointments_view()) == 2  # only the two sample appointments


async def test_refuses_an_invented_name(tomorrow):
    call = FakeCall([user("It's Anita"), TYPED_NUMBER])
    result = await call.call(tools.book_appointment, **booking(tomorrow, patient_name="John Doe"))
    assert not result["ok"] and "John Doe" in result["error"] and not new_bookings()
    assert call.model_runs_again  # it retries at once with the right name


async def test_books_without_a_name_when_none_was_given(tomorrow):
    call = FakeCall([user("I'd rather not say"), TYPED_NUMBER])
    assert (await call.call(tools.book_appointment, **booking(tomorrow, patient_name=None)))["ok"]
    assert new_bookings()[0]["patient"] == "Caller"


async def test_refuses_to_act_in_the_same_reply_as_a_question(tomorrow):
    call = FakeCall([user("It's Anita"), TYPED_NUMBER], reply="Booking you at two. Is that right?")
    result = await call.call(tools.book_appointment, **booking(tomorrow))
    assert result["error"] == tools.WAIT_FOR_ANSWER and not new_bookings()
    assert not call.model_runs_again  # the question is already on its way to the caller


async def test_booking_twice_says_already_booked_and_keeps_one_appointment(tomorrow):
    call = FakeCall([user("It's Anita"), TYPED_NUMBER])
    first = await call.call(tools.book_appointment, **booking(tomorrow))
    second = await call.call(tools.book_appointment, **booking(tomorrow))
    assert second["appointment"]["id"] == first["appointment"]["id"] and len(new_bookings()) == 1
    assert call.said[-1].startswith("You're already booked")


async def test_a_taken_slot_is_explained_by_the_model(tomorrow):
    clinic.book("Verma", tomorrow, "14:00", "9000000000")
    call = FakeCall([user("It's Anita"), TYPED_NUMBER])
    result = await call.call(tools.book_appointment, **booking(tomorrow))
    assert "not free" in result["error"] and call.model_runs_again and not call.said


# ---------- cancelling ----------


async def test_cancelling_needs_a_spoken_yes_even_for_a_typed_number(tomorrow):
    clinic.book("Verma", tomorrow, "14:00", NUMBER, "Anita")
    call = FakeCall([TYPED_NUMBER])
    assert not (await call.call(tools.cancel_appointment, phone_number=NUMBER, phone_confirmed=True))["ok"]
    assert new_bookings()


async def test_cancels_after_a_read_back_and_a_yes(tomorrow):
    clinic.book("Verma", tomorrow, "14:00", NUMBER, "Anita")
    call = FakeCall([CANCEL_READ_BACK, user("Yes")])
    result = await call.call(tools.cancel_appointment, phone_number=NUMBER, phone_confirmed=True)
    assert result["ok"] and not new_bookings()
    assert call.said == [
        "I've cancelled your appointment with Dr. Neha Verma tomorrow at 2 PM. Is there anything else I can help with?"
    ]


async def test_cannot_pick_which_appointment_to_cancel_while_asking(tomorrow):
    first = clinic.book("Verma", tomorrow, "14:00", NUMBER, "Anita")
    clinic.book("Verma", tomorrow, "18:00", NUMBER, "Anita")
    call = FakeCall([CANCEL_READ_BACK, user("Yes")], reply="You have two appointments. Which one?")
    result = await call.call(
        tools.cancel_appointment, phone_number=NUMBER, phone_confirmed=True, appointment_id=first["id"]
    )
    assert result["error"] == tools.WAIT_FOR_ANSWER and len(new_bookings()) == 2


async def test_cannot_cancel_someone_elses_appointment():
    call = FakeCall([CANCEL_READ_BACK, user("Yes")])
    result = await call.call(tools.cancel_appointment, phone_number=NUMBER, phone_confirmed=True)
    assert not result["ok"] and all(a["status"] == "booked" for a in clinic.appointments_view())


# ---------- the typing box ----------


async def test_typing_box_opens_after_two_voice_tries():
    asked_twice = [
        agent("And the phone number, please?"),
        user("A2"),
        agent("Could you say the number again?"),
        user("394"),
    ]
    call = FakeCall(asked_twice)
    assert (await call.call(tools.ask_caller_to_type_number))["ok"]
    assert call.said == [guards.TYPE_IT] and not call.model_runs_again
    assert any(getattr(f, "data", None) == {"type": "type-phone"} for f in call.frames)


async def test_typing_box_does_not_open_after_one_voice_try():
    call = FakeCall([agent("And the phone number, please?"), user("A2 394")])
    assert not (await call.call(tools.ask_caller_to_type_number))["ok"]
    assert not call.frames


# ---------- availability ----------


async def test_availability_reports_an_unknown_doctor():
    result = await FakeCall().call(tools.check_doctor_availability, doctor="Gupta")
    assert not result["ok"] and "Dr. Anjali Sharma" in result["error"]


async def test_availability_takes_the_slot_the_caller_named(tomorrow):
    result = await FakeCall().call(
        tools.check_doctor_availability, doctor="Verma", date=tomorrow, time="09:00"
    )
    assert result["slot_is_free"]["time"] == "9:00 AM" and "availability" not in result


async def test_availability_offers_others_when_the_named_slot_is_taken(tomorrow):
    clinic.book("Verma", tomorrow, "09:00", "9000000000")
    result = await FakeCall().call(
        tools.check_doctor_availability, doctor="Verma", date=tomorrow, time="09:00"
    )
    assert "9:00 AM" in result["note"] and "9:00 AM" not in result["availability"][0]["free_slots"]


async def test_availability_notices_a_time_the_caller_said(tomorrow):
    call = FakeCall([user("Book Doctor Verma tomorrow at nine AM.")])
    result = await call.call(tools.check_doctor_availability, doctor="Verma", date=tomorrow)
    assert result["slot_is_free"]["time"] == "9:00 AM"


async def test_a_typed_number_books_even_if_the_model_says_unconfirmed(tomorrow):
    call = FakeCall([user("It's Anita"), TYPED_NUMBER])
    assert (await call.call(tools.book_appointment, **booking(tomorrow, phone_confirmed=False)))["ok"]


async def test_end_call_says_goodbye_then_hangs_up():
    from pipecat.frames.frames import EndWorkerFrame

    call = FakeCall([user("I'm all set")])
    await call.call(tools.end_call)
    assert call.said == [guards.FAREWELL]
    assert isinstance(call.frames[-1], EndWorkerFrame)
    assert not call.model_runs_again


async def test_end_call_does_not_say_goodbye_twice():
    call = FakeCall([user("I'm all set")], reply="Goodbye, take care.")
    await call.call(tools.end_call)
    assert call.said == []
    assert call.frames and not call.model_runs_again


async def test_end_call_waits_when_the_agent_asked_something():
    call = FakeCall([user("Hmm")], reply="Is there anything else?")
    await call.call(tools.end_call)
    assert not call.result["ok"] and not call.frames
