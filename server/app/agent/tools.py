"""The tools the LLM can call.

These are Pipecat direct functions: the tool schema sent to the LLM is built
from each signature and docstring, so the docstrings below are part of the
prompt.

Booking and cancelling validate against the conversation (see guards.py)
before touching clinic data, and confirm with a fixed sentence.
"""

import asyncio

from pipecat.frames.frames import EndWorkerFrame, FunctionCallResultProperties, TTSSpeakFrame
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.services.llm_service import FunctionCallParams

from app import clinic
from app.agent.guards import (
    FAREWELL,
    PHONE_DIGITS,
    TYPE_IT,
    VOICE_TRIES,
    phone_digits,
    phone_was_confirmed,
    reply_in_progress,
    said_by_caller,
    time_caller_named,
    voice_tries,
)

NOT_CONFIRMED = "Not done. Read the phone number back as separate digits, ask if it is right, and stop. Call again only after the caller says yes."
NO_NUMBER = "Not done. The caller has not given a phone number yet. Never invent one. Ask for it."
ANYTHING_ELSE = "Is there anything else I can help with?"

WAIT_FOR_ANSWER = (
    "Not done. You asked the caller a question in the same reply. Wait for their answer, then call again."
)


async def asked_a_question(params: FunctionCallParams) -> bool:
    """True if the reply that made this tool call also asks the caller something.

    The model will ask "Is that right?" and act in the same reply, before the
    caller can answer.
    """
    await asyncio.sleep(0.1)  # let the rest of the reply reach OneQuestionGate
    return "?" in reply_in_progress(params.context)


async def refuse(params: FunctionCallParams, error: str):
    """Returns an error to the model.

    If a question is already being spoken the model is not re-run, so it does
    not talk over itself; it runs again on the caller's answer.
    """
    asked = await asked_a_question(params)
    await params.result_callback(
        {"ok": False, "error": error},
        properties=FunctionCallResultProperties(run_llm=not asked),
    )


async def done(params: FunctionCallParams, result: dict, say: str):
    """Returns success and speaks a fixed confirmation instead of the model's own."""

    async def speak():
        await params.llm.push_frame(TTSSpeakFrame(say))

    await params.result_callback(
        result, properties=FunctionCallResultProperties(run_llm=False, on_context_updated=speak)
    )


def spoken_when(appointment: dict) -> str:
    """'today at 6 PM', 'on Thursday 26 November at 10:30 AM'."""
    day = appointment["day"]
    day = day.lower() if day in ("Today", "Tomorrow") else f"on {day}"
    return f"{day} at {appointment['time_label'].replace(':00', '')}"


def summary(appointment: dict) -> dict:
    """The fields the model needs. Tool results are re-sent every turn, so keep them short."""
    return {k: appointment[k] for k in ("id", "doctor", "day", "time_label")}


async def check_doctor_availability(
    params: FunctionCallParams,
    doctor: str | None = None,
    speciality: str | None = None,
    date: str | None = None,
    time: str | None = None,
):
    """Look up free slots. Call before offering any slot.

    Args:
        doctor: Doctor's name, e.g. "Mehta". Null for any doctor.
        speciality: One of Cardiology, Dermatology, Pediatrics, Orthopedics, General Medicine. Null if a doctor was named.
        date: YYYY-MM-DD. Null for the next few open days.
        time: 24-hour HH:MM, only if the caller already named the time they want. Else null.
    """
    try:
        slots = clinic.availability(doctor=doctor or "", speciality=speciality or "", day=date or "")
        # The model rarely passes `time`, so fall back to what the caller said.
        time = time or time_caller_named(params.context)
        wanted = clinic.time_label(clinic.parse_time(time)) if time and date else None
        if wanted and len(slots) == 1 and wanted in slots[0]["free_slots"]:
            # Without an explicit instruction the model offers other times anyway.
            await params.result_callback(
                {
                    "ok": True,
                    "slot_is_free": {
                        "doctor": slots[0]["doctor"],
                        "date": slots[0]["date"],
                        "day": slots[0]["day"],
                        "time": wanted,
                    },
                    "next": "The slot the caller asked for is free and is now picked. Do not offer other times. Ask for the patient's name.",
                }
            )
            return
        result = {"ok": True, "availability": slots}
        if wanted:
            result["note"] = f"{wanted} is not free. Offer up to three of these instead."
        await params.result_callback(result)
    except clinic.ClinicError as e:
        await params.result_callback({"ok": False, "error": str(e)})


async def book_appointment(
    params: FunctionCallParams,
    doctor: str,
    date: str,
    time: str,
    phone_number: str,
    phone_confirmed: bool,
    patient_name: str | None = None,
):
    """Book one slot for the caller.

    Args:
        doctor: e.g. "Dr. Rohan Mehta".
        date: YYYY-MM-DD.
        time: 24-hour HH:MM, e.g. "15:00".
        phone_number: Ten digits, no spaces.
        phone_confirmed: True only if you read the number back in an earlier reply and the caller then said yes.
        patient_name: The name the caller gave. Null if they gave none. Never invent one.
    """
    if await asked_a_question(params):
        await refuse(params, WAIT_FOR_ANSWER)
        return
    if len(phone_digits(phone_number)) < PHONE_DIGITS:
        await refuse(params, NO_NUMBER)
        return
    # phone_confirmed is the model's claim; check the conversation instead.
    if not phone_was_confirmed(params.context, phone_number, typed_is_enough=True):
        await refuse(params, NOT_CONFIRMED)
        return
    if patient_name and not said_by_caller(params.context, patient_name):
        await refuse(
            params,
            f'Not done. The caller never said the name "{patient_name}". Call again now with the name they said, or null if they gave none.',
        )
        return
    try:
        existing = {a["id"] for a in clinic.appointments_view()}
        appointment = clinic.book(doctor, date, time, phone_number, patient_name or "")
        # book() is idempotent: the same caller and slot returns the existing appointment.
        opening = "You're already booked" if appointment["id"] in existing else "You're booked"
        await done(
            params,
            {"ok": True, "appointment": summary(appointment)},
            f"{opening} with {appointment['doctor']} {spoken_when(appointment)}. {ANYTHING_ELSE}",
        )
    except clinic.ClinicError as e:
        await params.result_callback({"ok": False, "error": str(e)})


async def cancel_appointment(
    params: FunctionCallParams,
    phone_number: str,
    phone_confirmed: bool,
    appointment_id: str | None = None,
):
    """Cancel the caller's appointment, found by phone number.

    Args:
        phone_number: Ten digits, no spaces.
        phone_confirmed: True only if you read the number back in an earlier reply and the caller then said yes.
        appointment_id: Only when the caller has several appointments, e.g. "APT-1003". Else null.
    """
    if await asked_a_question(params):
        await refuse(params, WAIT_FOR_ANSWER)
        return
    # Cancelling is destructive, so even a typed number needs a spoken yes.
    if not phone_was_confirmed(params.context, phone_number):
        await refuse(params, NOT_CONFIRMED)
        return
    try:
        result = clinic.cancel(phone_number, appointment_id or "")
        if result.get("needs_choice"):
            await params.result_callback(
                {
                    "ok": False,
                    "error": "The caller has more than one appointment. Ask which one, then call again with its appointment_id.",
                    "appointments": [summary(a) for a in result["appointments"]],
                }
            )
        else:
            await done(
                params,
                {"ok": True, "cancelled": summary(result)},
                f"I've cancelled your appointment with {result['doctor']} {spoken_when(result)}. {ANYTHING_ELSE}",
            )
    except clinic.ClinicError as e:
        await params.result_callback({"ok": False, "error": str(e)})


async def ask_caller_to_type_number(params: FunctionCallParams):
    """Open a box on the caller's screen where they type their phone number.

    Call this after the caller has tried to say the number twice and it still is
    not ten clear digits, or they say your read-back is wrong.
    """
    if await asked_a_question(params):
        await refuse(params, WAIT_FOR_ANSWER)
        return
    if voice_tries(params.context) < VOICE_TRIES:
        await params.result_callback(
            {"ok": False, "error": "Not yet. Ask the caller to say their phone number again first."}
        )
        return
    await params.llm.push_frame(RTVIServerMessageFrame(data={"type": "type-phone"}))
    await done(
        params, {"ok": True, "asked": "The caller was asked to type the number. Wait for it."}, TYPE_IT
    )


async def end_call(params: FunctionCallParams):
    """Say goodbye and hang up. Call this when the caller says they need nothing else or says goodbye."""
    if await asked_a_question(params):
        await refuse(params, WAIT_FOR_ANSWER)
        return

    async def hang_up():
        # Skip the fixed goodbye if the model already said its own.
        if not reply_in_progress(params.context).strip():
            await params.llm.push_frame(TTSSpeakFrame(FAREWELL))
        # Queued behind the goodbye, so the call closes after it is heard.
        await params.llm.push_frame(EndWorkerFrame(reason="agent ended the call"))

    await params.result_callback(
        {"ok": True}, properties=FunctionCallResultProperties(run_llm=False, on_context_updated=hang_up)
    )


TOOLS = [check_doctor_availability, book_appointment, cancel_appointment, ask_caller_to_type_number, end_call]
