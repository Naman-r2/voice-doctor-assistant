import { useEffect, useRef } from "react";
import { timeOfDay } from "../../lib/format.js";
import Card from "../ui/Card.jsx";

/** What the agent did on the current (or last) call, newest at the bottom. */
export default function ActivityLog({ rows, live }) {
  const list = useRef(null);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [rows.length]);

  return (
    <Card aria-labelledby="activity-title">
      <header className="card-head">
        <div>
          <h2 id="activity-title">Agent activity</h2>
          <p>Each step the agent takes, as it happens.</p>
        </div>
        {live && <span className="badge badge-live">Live</span>}
      </header>

      {rows.length === 0 ? (
        <p className="empty">Start a call and the agent&apos;s steps appear here.</p>
      ) : (
        <ol className="activity" ref={list}>
          {rows.map((row) => (
            <li key={row.key} className={`is-${row.kind}`}>
              <time className="mono">{timeOfDay(row.at)}</time>
              <div>
                <strong>{row.title}</strong>
                {row.detail && <span>{row.detail}</span>}
              </div>
            </li>
          ))}
          {live && (
            <li className="is-live">
              <time className="mono">now</time>
              <div>
                <strong>Listening</strong>
              </div>
            </li>
          )}
        </ol>
      )}
    </Card>
  );
}
