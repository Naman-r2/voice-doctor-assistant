import { useEffect, useState } from "react";
import { shortDay } from "../../lib/format.js";
import Icon from "./Icon.jsx";

const VISIBLE_MS = 5000;

/** A short notice that slides up whenever the agent books or cancels something. */
export default function Toasts({ lastAction }) {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    if (!lastAction) return;
    const toast = { ...lastAction, key: lastAction.at };
    setToasts((list) => [...list.slice(-2), toast]);
    const timer = setTimeout(() => setToasts((list) => list.filter((t) => t.key !== toast.key)), VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [lastAction]);

  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map(({ key, type, appointment }) => (
        <div className={`toast is-${type}`} key={key}>
          <span className="toast-mark">
            <Icon name={type === "booked" ? "check" : "close"} size={14} strokeWidth={3} />
          </span>
          <div>
            <strong>{type === "booked" ? "Appointment booked" : "Appointment cancelled"}</strong>
            <span>
              {appointment.doctor} · {shortDay(appointment.day)}, {appointment.time_label} · {appointment.id}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
