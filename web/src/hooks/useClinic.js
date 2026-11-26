import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAppointments, fetchDoctors, subscribeToEvents } from "../api/clinic.js";

const HIGHLIGHT_MS = 4500;
const MAX_EVENTS = 40;

/**
 * The clinic's data, kept live.
 *
 * Loads doctors and appointments, and reloads them whenever the server reports
 * that the agent did something. Also remembers what was just touched so the
 * dashboard can highlight it for a few seconds.
 */
export function useClinic() {
  const [doctors, setDoctors] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [events, setEvents] = useState([]); // everything the agent did, oldest first
  const [lastAction, setLastAction] = useState(null); // the last booking or cancellation
  const [highlights, setHighlights] = useState({}); // { [key]: "booked" | "cancelled" | "checked" }
  const [online, setOnline] = useState(true);
  const timers = useRef({});

  const load = useCallback(async () => {
    try {
      const [doctorList, appointmentList] = await Promise.all([fetchDoctors(), fetchAppointments()]);
      setDoctors(doctorList);
      setAppointments(appointmentList);
      setOnline(true);
    } catch {
      setOnline(false);
    }
  }, []);

  const highlight = useCallback((key, kind) => {
    setHighlights((current) => ({ ...current, [key]: kind }));
    clearTimeout(timers.current[key]);
    timers.current[key] = setTimeout(() => {
      setHighlights((current) => {
        const rest = { ...current };
        delete rest[key];
        return rest;
      });
    }, HIGHLIGHT_MS);
  }, []);

  useEffect(() => {
    const onEvent = (data) => {
      const event = { ...data, at: Date.now() };
      setEvents((list) => [...list.slice(-MAX_EVENTS), event]);
      if (event.type === "checked") {
        event.doctor_ids.forEach((id) => highlight(id, "checked"));
        return;
      }
      const appointment = event.appointment;
      highlight(appointment.id, event.type);
      highlight(slotKey(appointment.doctor_id, appointment.date, appointment.time), event.type);
      setLastAction({ type: event.type, appointment, at: event.at });
      load();
    };
    return subscribeToEvents({ onOpen: load, onEvent, onDown: () => setOnline(false) });
  }, [load, highlight]);

  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  return { doctors, appointments, events, lastAction, highlights, online };
}

/** The key one slot is highlighted under. */
export const slotKey = (doctorId, date, time) => `${doctorId}|${date}|${time}`;
