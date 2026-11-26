import { useState } from "react";

/**
 * Marks a phone number as typed rather than spoken. The server trusts a typed
 * number without reading it back, and no spoken sentence can contain this
 * marker (see TYPED in the server's guards).
 */
export const TYPED_MARKER = "[typed]";

// Sent after the digits. A note inside the message is followed more reliably
// than the same rule in the agent's instructions. Keep in step with TYPED_NOTE in guards.py.
const TYPED_NOTE = "(typed on screen: exact and confirmed, do not read it back)";

/** The message the agent receives for a typed number. */
export const typedMessage = (digits) => `${TYPED_MARKER} ${digits} ${TYPED_NOTE}`;

/** What to show in the transcript for that message: just the digits. */
export const typedDisplay = (text) => text.replace(TYPED_MARKER, "").replace(TYPED_NOTE, "").trim();

const LENGTH = 10;

/**
 * A box to type the phone number in, for when saying it out loud is not working.
 * One real input sits invisibly over ten cells, so typing, pasting and the
 * phone keyboard all behave normally while each digit lands in its own cell.
 */
export default function NumberEntry({ onSend, onClose }) {
  const [digits, setDigits] = useState("");
  const ready = digits.length === LENGTH;

  return (
    <form
      className="number-entry"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) onSend(digits);
      }}
    >
      <div className="number-head">
        <label htmlFor="typed-phone">Type your phone number</label>
        <button type="button" className="number-close" onClick={onClose} aria-label="Close">
          Esc
        </button>
      </div>

      <div className="number-cells">
        <input
          id="typed-phone"
          type="tel"
          inputMode="numeric"
          autoComplete="tel-national"
          autoFocus
          value={digits}
          aria-describedby="typed-phone-count"
          onChange={(e) => setDigits(e.target.value.replace(/\D/g, "").slice(0, LENGTH))}
        />
        {Array.from({ length: LENGTH }, (_, i) => (
          <span
            key={i}
            className={`cell ${digits[i] ? "is-filled" : ""} ${i === digits.length ? "is-next" : ""} ${i === 5 ? "has-gap" : ""}`}
            aria-hidden="true"
          >
            {digits[i] || ""}
          </span>
        ))}
      </div>

      <div className="number-foot">
        <span id="typed-phone-count" className="hint">
          {ready
            ? "Looks good. Press Enter to send."
            : `${LENGTH - digits.length} more ${LENGTH - digits.length === 1 ? "digit" : "digits"}`}
        </span>
        <button type="submit" className="button button-light" disabled={!ready}>
          Send
        </button>
      </div>
    </form>
  );
}
