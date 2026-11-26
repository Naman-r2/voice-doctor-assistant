import { useEffect, useRef } from "react";
import { usePipecatConversation } from "@pipecat-ai/client-react";
import { TYPED_MARKER, typedDisplay } from "./NumberEntry.jsx";

// Ask for the words the agent has already said, not the ones still to come,
// so the text keeps pace with the voice.
const SPOKEN_ONLY = { unspoken: false };

// A message part is plain text (the caller) or { spoken, unspoken } (the agent).
const partText = (text) => {
  if (typeof text === "string") return typedDisplay(text);
  return text && typeof text === "object" ? text.spoken || "" : "";
};

/** The conversation as it happens. The agent's words fade in one by one as they are spoken. */
export default function Transcript({ live }) {
  const { messages } = usePipecatConversation({ botOutputFilter: SPOKEN_ONLY });
  const end = useRef(null);

  const lines = messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m, i) => ({
      key: `${m.createdAt}-${i}`,
      fromCaller: m.role === "user",
      // Each part is one spoken segment; without the space they run together.
      text: (m.parts || [])
        .map((p) => partText(p.text))
        .filter(Boolean)
        .join(" "),
      typed: (m.parts || []).some((p) => typeof p.text === "string" && p.text.includes(TYPED_MARKER)),
    }))
    .filter((line) => line.text); // no bubble until the agent has said its first word

  useEffect(() => {
    // Scroll the conversation's own box. scrollIntoView would also move the page.
    const box = end.current?.closest(".stage-body");
    box?.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [messages]);

  if (lines.length === 0) {
    return (
      <p className="transcript-empty">
        {live ? "Say hello. The conversation appears here." : "Connecting you to the front desk…"}
      </p>
    );
  }

  const last = lines.length - 1;
  return (
    <ol className="transcript" aria-label="Conversation" aria-live="polite">
      {lines.map((line, i) => (
        <li
          key={line.key}
          className={`${line.fromCaller ? "from-caller" : "from-agent"} ${i === last ? "is-latest" : ""}`}
        >
          <span className="speaker">{line.fromCaller ? (line.typed ? "You · typed" : "You") : "Agent"}</span>
          <p>
            {line.fromCaller
              ? line.text
              : // Keyed by position: a word already on screen keeps its element, a new one animates in.
                line.text.split(/\s+/).map((word, n) => (
                  <span className="word" key={n}>
                    {word}{" "}
                  </span>
                ))}
          </p>
        </li>
      ))}
      <li ref={end} aria-hidden="true" />
    </ol>
  );
}
