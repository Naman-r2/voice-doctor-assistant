import { useEffect, useMemo, useState } from "react";
import { slotKey } from "../../hooks/useClinic.js";
import { initials, shortDay } from "../../lib/format.js";
import Card from "../ui/Card.jsx";

const STEP = 30; // minutes per column
const STATE_LABEL = { free: "available", booked: "booked", past: "past" };

const minutes = (hhmm) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3));
const hourLabel = (m) => `${((Math.floor(m / 60) + 11) % 12) + 1} ${m < 720 ? "AM" : "PM"}`;
const shortTime = (label) => label.replace(/\s?[AP]M$/, "").replace(":00", "");

/** The span of the day to draw: from the first slot's hour to the hour after the last. */
function useDayAxis(doctors) {
  return useMemo(() => {
    const all = doctors.flatMap((d) => d.days[0]?.slots.map((s) => minutes(s.time)) || []);
    if (!all.length) return { start: 540, columns: 0 };
    const start = Math.floor(Math.min(...all) / 60) * 60;
    const end = Math.max(...all) + STEP; // the last slot's own column, no empty tail
    return { start, columns: (end - start) / STEP };
  }, [doctors]);
}

/** Where "now" falls on the axis, 0..1, or null when it is outside it. */
function useNowPosition(axis, isToday) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);
  if (!isToday || !axis.columns) return null;
  const at = (now.getHours() * 60 + now.getMinutes() - axis.start) / (axis.columns * STEP);
  return at >= 0 && at <= 1 ? at : null;
}

/**
 * The clinic's day as a timeline: doctors down the side, time across.
 * A row lights up while the agent checks that doctor, and a slot pops when it
 * is booked or freed.
 */
export default function Schedule({ doctors, appointments, highlights, lastAction }) {
  const [dayIndex, setDayIndex] = useState(0);
  const days = doctors[0]?.days || [];
  const axis = useDayAxis(doctors);
  const today = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time
  const nowAt = useNowPosition(axis, days[dayIndex]?.date === today);

  // Jump to the day the agent just booked or cancelled on, so the change is visible.
  useEffect(() => {
    const i = days.findIndex((day) => day.date === lastAction?.appointment.date);
    if (i >= 0) setDayIndex(i);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastAction]);

  // Who holds each booked slot, so the block can carry a name.
  const patients = useMemo(() => {
    const map = {};
    for (const a of appointments) if (a.status === "booked") map[slotKey(a.doctor_id, a.date, a.time)] = a.patient;
    return map;
  }, [appointments]);

  const grid = { gridTemplateColumns: `repeat(${axis.columns}, minmax(0, 1fr))`, "--columns": axis.columns };

  return (
    <Card className="schedule-card" aria-labelledby="schedule-title">
      <header className="card-head">
        <div>
          <h2 id="schedule-title">Schedule</h2>
          <p>Live. Slots change as the agent books and cancels.</p>
        </div>
        <div className="segmented" role="tablist" aria-label="Day">
          {days.map((day, i) => (
            <button key={day.date} role="tab" aria-selected={i === dayIndex} onClick={() => setDayIndex(i)}>
              {shortDay(day.label)}
            </button>
          ))}
        </div>
      </header>

      {doctors.length === 0 ? (
        <div className="skeleton-rows" aria-label="Loading the schedule">
          {Array.from({ length: 5 }, (_, i) => (
            <div className="skeleton" key={i} style={{ "--i": i }} />
          ))}
        </div>
      ) : (
        <div className="timeline-scroll">
          <div className="timeline">
            <div className="timeline-axis" style={grid} aria-hidden="true">
              {Array.from({ length: axis.columns }, (_, i) => (
                <span key={i} className={i % 2 === 0 ? "is-hour" : ""}>
                  {i % 2 === 0 ? hourLabel(axis.start + i * STEP) : ""}
                </span>
              ))}
            </div>

            <ul className="timeline-rows" key={dayIndex}>
              {doctors.map((doctor, row) => {
                const day = doctor.days[dayIndex];
                const checking = highlights[doctor.id] === "checked";
                const open = day.slots.filter((s) => s.free).length;
                return (
                  <li
                    key={doctor.id}
                    className={checking ? "is-checking" : ""}
                    style={{ "--i": row, "--hue": doctor.hue ?? row * 62 + 205 }}
                  >
                    <div className="doctor">
                      <span className="avatar" aria-hidden="true">
                        {initials(doctor.name)}
                      </span>
                      <div>
                        <strong>{doctor.name}</strong>
                        <span>
                          {doctor.speciality}
                          <em className={`open-count ${open ? "" : "is-full"}`}>
                            {checking ? "Checking…" : open ? `${open} open` : "Full"}
                          </em>
                        </span>
                      </div>
                    </div>

                    <div className="track" style={grid}>
                      {day.slots.map((slot) => {
                        const state = slot.state || (slot.free ? "free" : "booked");
                        const key = slotKey(doctor.id, day.date, slot.time);
                        const flash = highlights[key];
                        const patient = state === "booked" ? patients[key] : null;
                        return (
                          <span
                            key={slot.time}
                            className={`slot is-${state} ${flash ? `flash-${flash}` : ""}`}
                            style={{ gridColumn: (minutes(slot.time) - axis.start) / STEP + 1 }}
                            title={`${slot.label} · ${patient ? `booked by ${patient}` : STATE_LABEL[state]}`}
                          >
                            <b>{shortTime(slot.label)}</b>
                            {patient && <i>{patient.split(" ")[0]}</i>}
                            <span className="sr-only">, {STATE_LABEL[state]}</span>
                          </span>
                        );
                      })}
                    </div>
                  </li>
                );
              })}
            </ul>

            {nowAt !== null && (
              <div className="now-line" style={{ "--at": nowAt }} aria-hidden="true">
                <span>Now</span>
              </div>
            )}
          </div>
        </div>
      )}

      <footer className="legend" aria-hidden="true">
        <span className="key is-free">Available</span>
        <span className="key is-booked">Booked</span>
        <span className="key is-past">Past</span>
      </footer>
    </Card>
  );
}
