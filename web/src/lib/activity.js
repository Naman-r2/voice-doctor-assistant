import { shortDay } from "./format.js";

/**
 * Turn the server's events into the rows of the activity log for one call.
 *
 * @param events   everything the agent did (from useClinic)
 * @param doctors  to turn doctor ids into names
 * @param call     { placedAt, answeredAt, phase, duration } from useCall
 * @returns        [{ key, at, kind, title, detail }], oldest first
 */
export function callActivity(events, doctors, call) {
  if (!call.placedAt) return [];

  const rows = [{ key: "placed", at: call.placedAt, kind: "info", title: "Call started" }];
  if (call.answeredAt) rows.push({ key: "answered", at: call.answeredAt, kind: "info", title: "Agent picked up" });

  let lastCheck = "";
  for (const event of events) {
    if (event.at < call.placedAt) continue;

    if (event.type === "checked") {
      const names = event.doctor_ids.map((id) => doctors.find((d) => d.id === id)?.name).filter(Boolean);
      const title = names.length === 1 ? `Checked ${names[0]}` : `Checked ${names.length} doctors`;
      if (title === lastCheck) continue; // the agent often checks the same doctor twice in a row
      lastCheck = title;
      rows.push({ key: event.at, at: event.at, kind: "check", title, detail: "Availability lookup" });
      continue;
    }

    lastCheck = "";
    const a = event.appointment;
    rows.push({
      key: event.at,
      at: event.at,
      kind: event.type, // "booked" | "cancelled"
      title: `${event.type === "booked" ? "Booked" : "Cancelled"} ${a.id}`,
      detail: `${a.doctor} · ${shortDay(a.day)}, ${a.time_label}`,
    });
  }

  if (call.phase === "ended" || call.phase === "idle") {
    const endedAt = (call.answeredAt || call.placedAt) + call.duration * 1000;
    rows.push({ key: "ended", at: endedAt, kind: "info", title: "Call ended" });
  }
  return rows;
}

/** Ids of appointments booked (and not cancelled again) during this call. */
export function bookedThisCall(events, placedAt) {
  const ids = new Set();
  if (!placedAt) return ids;
  for (const event of events) {
    if (event.at < placedAt || !event.appointment) continue;
    if (event.type === "booked") ids.add(event.appointment.id);
    else ids.delete(event.appointment.id);
  }
  return ids;
}
