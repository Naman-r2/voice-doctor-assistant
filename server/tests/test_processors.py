"""Cleaning what the caller said and cutting what the agent says."""

from pipecat.frames.frames import EndWorkerFrame, TTSSpeakFrame

from app.agent import guards
from app.agent.processors import ReplyCutter, scripted_reply, speakable, spoken_words
from tests.conftest import FakeCall, agent, user


def test_sound_tags_are_not_speech():
    assert spoken_words("[silence]") is None
    assert spoken_words("(coughing) [laughs]") is None
    assert spoken_words("[laughs] Yes, that's right") == "Yes, that's right"


def test_reply_stops_at_its_first_question():
    cutter = ReplyCutter()
    spoken = [cutter.feed(chunk) for chunk in ["Which slot would ", "you like? Is that", " right? Yes."]]
    assert spoken == ["Which slot would ", "you like?", ""]
    assert cutter.reply == "Which slot would you like?"


def test_invisible_characters_are_removed():
    cutter = ReplyCutter()
    assert cutter.feed("Your\u200b\u200b\u200b appointment") == "Your appointment"
    assert cutter.feed("\u200b\u200b") == ""


def test_a_runaway_reply_is_cut_short():
    cutter = ReplyCutter()
    spoken = "".join(cutter.feed("word " * 20) for _ in range(20))
    assert len(spoken) == ReplyCutter.MAX_REPLY
    assert cutter.feed("more") == ""


def test_speakable_replaces_typographic_characters():
    assert speakable("ten\u2011digit number\u2026 it\u2019s here") == "ten-digit number it's here"


def test_a_goodbye_is_answered_without_the_model():
    frames = scripted_reply(FakeCall([agent("How can I help?"), user("Okay, bye")]))
    assert [type(f) for f in frames] == [TTSSpeakFrame, EndWorkerFrame]
    assert frames[0].text == guards.FAREWELL


def test_an_identity_question_is_answered_without_the_model():
    frames = scripted_reply(FakeCall([agent("How can I help?"), user("Are you a person?")]))
    assert [f.text for f in frames] == [guards.WHO_I_AM]


def test_an_ordinary_turn_goes_to_the_model():
    assert scripted_reply(FakeCall([agent("How can I help?"), user("Is Doctor Mehta free tomorrow?")])) == []
