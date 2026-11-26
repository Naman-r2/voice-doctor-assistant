"""The checks that read the real conversation instead of trusting the model."""

import pytest

from app.agent import guards
from tests.conftest import FakeCall, agent, user

NUMBER = "9876543210"
READ_BACK = agent("Anita with Dr. Mehta tomorrow at ten, number 9, 8, 7, 6, 5, 4, 3, 2, 1, 0. Is that right?")


@pytest.mark.parametrize(
    "said, expected",
    [
        ("Seven seven Seven seven", True),
        ("A2 394-79403", True),
        ("My number is nine eight two", True),
        ("Seven, seven, seven, seven, seven, seven Seven seven seven seven", False),  # all ten
        ("9876543210", False),
        ("10:30", False),
        ("3 PM please", False),
        ("Mm, Thursday", False),
        ("Yes, it is", False),
    ],
)
def test_is_partial_phone_number(said, expected):
    assert guards.is_partial_phone_number(said) is expected


def test_spoken_digits_reads_numerals_and_words():
    assert guards.spoken_digits("9, 8, seven, oh") == "9870"


def test_a_number_the_agent_never_read_back_is_not_confirmed():
    call = FakeCall([user("It is " + NUMBER)])
    assert not guards.phone_was_confirmed(call, NUMBER)


def test_a_read_back_needs_the_callers_answer():
    assert not guards.phone_was_confirmed(FakeCall([READ_BACK]), NUMBER)
    assert guards.phone_was_confirmed(FakeCall([READ_BACK, user("Yes")]), NUMBER)


def test_a_different_number_than_the_one_read_back_is_not_confirmed():
    assert not guards.phone_was_confirmed(FakeCall([READ_BACK, user("Yes")]), "9876543211")


def test_one_yes_covers_one_action():
    done = {"role": "tool", "content": '{"ok": true, "appointment": {"id": "APT-1003"}}'}
    assert not guards.phone_was_confirmed(FakeCall([READ_BACK, user("Yes"), done, user("Cancel it")]), NUMBER)


def test_a_typed_number_counts_only_where_allowed():
    call = FakeCall([user(f"{guards.TYPED} {NUMBER}")])
    assert guards.phone_was_confirmed(call, NUMBER, typed_is_enough=True)
    assert not guards.phone_was_confirmed(call, NUMBER)
    assert not guards.phone_was_confirmed(call, "9876543211", typed_is_enough=True)


def test_said_by_caller_matches_whole_words_only():
    call = FakeCall([user("It's Anita"), agent("Thanks John")])
    assert guards.said_by_caller(call, "Anita Sharma")
    assert not guards.said_by_caller(call, "John Doe")
    assert not guards.said_by_caller(call, "Ani")


ASK = agent("And the phone number, please?")
ASK_AGAIN = agent("Could you give me the ten-digit phone number, please?")


def test_typing_is_not_offered_after_one_failed_try():
    assert not guards.should_offer_typing(FakeCall([ASK, user("It's to see")]))


def test_typing_is_offered_after_two_failed_tries():
    call = FakeCall([ASK, user("It's to see"), ASK_AGAIN, user("nine eight two")])
    assert guards.voice_tries(call) == 2 and guards.should_offer_typing(call)


def test_typing_is_not_offered_when_the_second_try_worked():
    call = FakeCall(
        [ASK, user("It's to see"), ASK_AGAIN, user("nine eight two nine zero one seven two two two")]
    )
    assert not guards.should_offer_typing(call)


def test_typing_is_offered_when_the_second_read_back_is_rejected():
    call = FakeCall([ASK, user("um"), ASK_AGAIN, user("9829017222"), READ_BACK, user("No, that's wrong")])
    assert guards.should_offer_typing(call)


def test_typing_is_offered_only_once():
    call = FakeCall([ASK, user("um"), ASK_AGAIN, user("uh"), agent(guards.TYPE_IT), user("okay")])
    assert not guards.should_offer_typing(call)


@pytest.mark.parametrize(
    "said, expected",
    [
        ("I'd like Doctor Verma tomorrow at nine AM.", "09:00"),
        ("Tomorrow at 10:30 am please", "10:30"),
        ("ten thirty PM", "22:30"),
        ("12 pm", "12:00"),
        ("3 p.m.", "15:00"),
        ("Tomorrow at ten", None),  # no AM or PM: could be anything
        ("nine eight seven six five four three two one zero", None),
        ("I am fine", None),
    ],
)
def test_time_caller_named(said, expected):
    assert guards.time_caller_named(FakeCall([user("earlier, at 5 PM"), user(said)])) == expected


def test_a_request_without_a_question_mark_is_still_a_try():
    call = FakeCall(
        [
            ASK,
            user("It's to see"),
            agent("Please say your ten-digit phone number again."),
            user("nine eight two"),
        ]
    )
    assert guards.voice_tries(call) == 2 and guards.should_offer_typing(call)


def test_mentioning_a_number_is_not_asking_for_it():
    said = [
        agent("May I have the patient's name, please?"),
        agent("I'm sorry, there is no active appointment under that number."),
    ]
    assert guards.voice_tries(FakeCall(said)) == 0


# ---------- hanging up ----------

ANYTHING_ELSE = agent(
    "You're booked with Dr. Rohan Mehta tomorrow at 10:30 AM. Is there anything else I can help with?"
)


@pytest.mark.parametrize(
    "said", ["No thanks. Goodbye", "End the call, please", "Okay bye", "That's all", "You can hang up now"]
)
def test_a_goodbye_ends_the_call(said):
    assert guards.caller_is_done(FakeCall([agent("How can I help?"), user(said)]))


@pytest.mark.parametrize("said", ["No", "No, thank you.", "Nope, I'm good"])
def test_no_after_anything_else_ends_the_call(said):
    assert guards.caller_is_done(FakeCall([ANYTHING_ELSE, user(said)]))


@pytest.mark.parametrize("said", ["No", "No thanks", "No, the number is wrong"])
def test_no_to_another_question_does_not_end_the_call(said):
    assert not guards.caller_is_done(
        FakeCall([agent("Booking you at ten thirty. Is that right?"), user(said)])
    )


def test_wanting_something_else_does_not_end_the_call():
    assert not guards.caller_is_done(
        FakeCall([ANYTHING_ELSE, user("No, wait, I also want to cancel my other appointment")])
    )
    assert not guards.caller_is_done(FakeCall([ANYTHING_ELSE, user("Yes, is Doctor Khan free on Monday?")]))


# ---------- who the caller is talking to ----------


@pytest.mark.parametrize(
    "said",
    [
        "Hi, what's your name?",
        "No. Am I talking to a person?",
        "Are you a person or an AI agent?",
        "Is your name actually Sarah?",
        "How old are you?",
        "What's your last name?",
        "Are you a real human",
        "Okay. Are you an adult at least",
    ],
)
def test_asking_who_the_agent_is_gets_the_fixed_answer(said):
    assert guards.asks_who_is_speaking(FakeCall([agent("How can I help?"), user(said)]))


@pytest.mark.parametrize(
    "said",
    [
        "My name is Anita",
        "Is Doctor Mehta free tomorrow?",
        "The name is Rehman",
        "Are you open on Sunday?",
        "Book it for my son, he is a person of ten",
    ],
)
def test_ordinary_requests_are_left_to_the_model(said):
    assert not guards.asks_who_is_speaking(FakeCall([agent("How can I help?"), user(said)]))
