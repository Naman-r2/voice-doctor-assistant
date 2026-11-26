import { useCallback, useEffect, useRef, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientMediaTrack,
  usePipecatClientMicControl,
  usePipecatConversation,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import { Agent, useAgentState } from "../../hooks/useAgentState.js";
import { useAudioLevels } from "../../hooks/useAudioLevels.js";
import { Phase, useElapsed } from "../../hooks/useCall.js";
import { clock } from "../../lib/format.js";
import { burst, voiceBus } from "../../lib/voiceBus.js";
import Icon from "../ui/Icon.jsx";
import NumberEntry, { typedMessage } from "./NumberEntry.jsx";
import Transcript from "./Transcript.jsx";

const SUGGESTIONS = [
  "Is Doctor Mehta free tomorrow?",
  "Book the earliest slot with any doctor",
  "Cancel my appointment",
];

const HEADLINE = {
  [Agent.IDLE]: ["The front desk, answered.", "Ask for a doctor, book a slot, cancel a visit. Out loud."],
  [Agent.RINGING]: ["Connecting…", "Allow the microphone if your browser asks."],
  [Agent.LISTENING]: ["Listening", "Go ahead, I'm here."],
  [Agent.THINKING]: ["Thinking", "One moment."],
  [Agent.SPEAKING]: ["Speaking", "You can interrupt at any time."],
  [Agent.ENDED]: ["Call ended", "Thanks for calling Meridian Clinic."],
};

/** The voice call, centre stage: the orb, the conversation, and the controls. */
export default function Stage({ call, online, lastAction, actionsThisCall }) {
  const { phase, error } = call;
  const live = phase === Phase.LIVE;
  const idle = phase === Phase.IDLE;

  const client = usePipecatClient();
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();
  const { injectMessage } = usePipecatConversation();
  const botTrack = usePipecatClientMediaTrack("audio", "bot");
  const micTrack = usePipecatClientMediaTrack("audio", "local");
  const levels = useAudioLevels(botTrack, micTrack, live);
  const state = useAgentState(phase);
  const seconds = useElapsed(call.answeredAt, live);
  const [typing, setTyping] = useState(false);
  const anchor = useRef(null);

  // The 3D scene draws the agent. Tell it where to sit, what state it is in and how loud it is.
  const shown = error ? Agent.ENDED : state;
  useEffect(() => {
    voiceBus.anchor = anchor.current;
    voiceBus.levels = levels;
    return () => {
      voiceBus.anchor = null;
    };
  }, [levels]);
  useEffect(() => {
    voiceBus.state = shown;
  }, [shown]);
  useEffect(() => {
    if (lastAction) burst();
  }, [lastAction]);

  // The agent opens the number box when it could not catch the number by ear.
  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback((data) => {
      if (data?.type === "type-phone") setTyping(true);
    }, []),
  );

  useEffect(() => {
    if (!live) setTyping(false);
  }, [live]);

  // M mutes, Escape closes the number box. Not while typing in a field.
  useEffect(() => {
    if (!live) return;
    const onKey = (e) => {
      if (e.target.closest?.("input, textarea")) {
        if (e.key === "Escape") setTyping(false);
        return;
      }
      if (e.key === "m" || e.key === "M") enableMic(!isMicEnabled);
      if (e.key === "Escape") setTyping(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [live, enableMic, isMicEnabled]);

  const sendNumber = (digits) => {
    setTyping(false);
    const text = typedMessage(digits);
    client?.sendText(text);
    // Sent text is not echoed into the conversation, so show it ourselves.
    injectMessage({ role: "user", parts: [{ text, final: true, createdAt: new Date().toISOString() }] });
  };

  const [title, hint] = error
    ? ["Call failed", error]
    : live && !isMicEnabled
      ? ["Muted", "The agent cannot hear you."]
      : HEADLINE[state];
  const timer = live ? clock(seconds) : phase === Phase.ENDED && !error ? clock(call.duration) : "";
  const notice = lastAction && lastAction.at >= call.placedAt && !idle ? lastAction : null;

  return (
    <section className={`stage is-${error ? "failed" : state}`} aria-labelledby="stage-title">
      <header className="stage-head">
        <span className="stage-tag">
          <span className="stage-dot" aria-hidden="true" />
          Voice agent
        </span>
        {timer && <span className="stage-timer mono">{timer}</span>}
      </header>

      {/* An empty box: the particle sphere in the scene behind the page lines itself up with it. */}
      <div className={`stage-orb ${idle ? "" : "is-compact"}`} ref={anchor} aria-hidden="true" />

      <div className="stage-status" aria-live="polite">
        <h2 id="stage-title" key={title}>
          {title}
        </h2>
        <p key={hint}>{hint}</p>
      </div>

      {idle ? (
        <div className="stage-idle">
          <button className="call-button" onClick={call.start} disabled={!online}>
            <span className="call-button-halo" aria-hidden="true" />
            <Icon name="phone" size={20} strokeWidth={2} />
            Start call
          </button>
          {!online && <p className="stage-note">The agent is offline. Start the server, then try again.</p>}
          <ul className="suggestions" aria-label="Things to try">
            {SUGGESTIONS.map((line) => (
              <li key={line}>“{line}”</li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          <div className="stage-body">{!error && <Transcript live={live} />}</div>

          {notice && (
            <p className={`stage-notice is-${notice.type}`} key={notice.at} role="status">
              <span className="stage-notice-mark">
                <Icon name={notice.type === "booked" ? "check" : "close"} size={14} strokeWidth={3} />
              </span>
              <span>
                <strong>
                  {notice.type === "booked" ? "Booked" : "Cancelled"} · {notice.appointment.id}
                </strong>
                {notice.appointment.doctor} · {notice.appointment.day}, {notice.appointment.time_label}
              </span>
            </p>
          )}

          {typing && live && <NumberEntry onSend={sendNumber} onClose={() => setTyping(false)} />}

          <footer className="dock">
            {phase === Phase.ENDED ? (
              <>
                <p className="dock-summary">
                  {error
                    ? "Nothing was changed."
                    : `${actionsThisCall} ${actionsThisCall === 1 ? "change" : "changes"} made on this call.`}
                </p>
                <button className="button button-light" onClick={call.start} disabled={!online}>
                  <Icon name="phone" />
                  Call again
                </button>
                <button className="button button-quiet" onClick={call.reset}>
                  Close
                </button>
              </>
            ) : (
              <>
                <DockButton
                  icon={isMicEnabled ? "mic" : "micOff"}
                  label={isMicEnabled ? "Mute" : "Unmute"}
                  hint="M"
                  pressed={!isMicEnabled}
                  disabled={!live}
                  onClick={() => enableMic(!isMicEnabled)}
                />
                <DockButton
                  icon="keypad"
                  label="Type number"
                  pressed={typing}
                  disabled={!live}
                  onClick={() => setTyping(!typing)}
                />
                <DockButton icon="hangup" label="End call" danger onClick={call.end} />
              </>
            )}
          </footer>
        </>
      )}
    </section>
  );
}

function DockButton({ icon, label, hint, pressed, danger, disabled, onClick }) {
  return (
    <button
      className={`dock-button ${danger ? "is-danger" : ""}`}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed === undefined ? undefined : pressed}
      aria-keyshortcuts={hint}
    >
      <span className="dock-icon">
        <Icon name={icon} size={20} />
      </span>
      <span className="dock-label">
        {label}
        {hint && <kbd>{hint}</kbd>}
      </span>
    </button>
  );
}
