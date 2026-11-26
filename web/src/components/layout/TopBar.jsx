import { useEffect, useState } from "react";
import Icon from "../ui/Icon.jsx";

const dateLabel = (now) => now.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
const timeLabel = (now) =>
  now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true }).toUpperCase();

function useNow(everyMs = 15_000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), everyMs);
    return () => clearInterval(id);
  }, [everyMs]);
  return now;
}

/** The bar across the top: who we are, the time, whether the agent is reachable. */
export default function TopBar({ online }) {
  const now = useNow();

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">
          <Icon name="stethoscope" size={20} strokeWidth={2} />
        </span>
        <div>
          <strong>Meridian Clinic</strong>
          <span>Front desk</span>
        </div>
      </div>

      <div className="topbar-meta">
        <time className="now" dateTime={now.toISOString()}>
          <span>{dateLabel(now)}</span>
          <span className="mono">{timeLabel(now)}</span>
        </time>
        <span className={`status ${online ? "is-up" : "is-down"}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          {online ? "Agent online" : "Agent offline"}
        </span>
      </div>
    </header>
  );
}
