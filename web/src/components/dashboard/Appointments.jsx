import { phone, shortDay } from "../../lib/format.js";
import Card from "../ui/Card.jsx";

/** Every appointment as a ticket, active ones first. New ones slide in; changed ones glow. */
export default function Appointments({ appointments, highlights, bookedThisCall }) {
  const active = appointments.filter((a) => a.status === "booked").length;

  return (
    <Card aria-labelledby="appointments-title">
      <header className="card-head">
        <div>
          <h2 id="appointments-title">Appointments</h2>
          <p>
            {active} active · {appointments.length - active} cancelled
          </p>
        </div>
      </header>

      {appointments.length === 0 ? (
        <p className="empty">Nothing booked yet.</p>
      ) : (
        <ul className="tickets">
          {appointments.map((a, i) => (
            <li
              key={a.id}
              className={`ticket ${a.status === "cancelled" ? "is-cancelled" : ""} ${highlights[a.id] ? `flash-${highlights[a.id]}` : ""}`}
              style={{ "--i": Math.min(i, 8) }}
            >
              <div className="ticket-when">
                <strong>{a.time_label}</strong>
                <span>{shortDay(a.day)}</span>
              </div>
              <div className="ticket-who">
                <strong>{a.patient}</strong>
                <span>
                  {a.doctor} · {a.speciality}
                </span>
              </div>
              <div className="ticket-meta">
                <span className="mono">{phone(a.phone)}</span>
                <span className="mono ticket-id">{a.id}</span>
              </div>
              <div className="ticket-state">
                {bookedThisCall.has(a.id) && <span className="badge badge-accent">This call</span>}
                <span className={`badge ${a.status === "booked" ? "badge-ok" : "badge-muted"}`}>
                  {a.status === "booked" ? "Booked" : "Cancelled"}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
