// The clinic's REST API and live event stream (served by the Python server under /api).

const getJson = (path) =>
  fetch(path).then((response) => {
    if (!response.ok) throw new Error(`${path} answered ${response.status}`);
    return response.json();
  });

export const fetchDoctors = () => getJson("/api/doctors");
export const fetchAppointments = () => getJson("/api/appointments");

/**
 * Subscribe to what the agent does: availability checks, bookings, cancellations.
 * Reconnects on its own, because a browser gives up on an event stream for good
 * once the server answers with an error (for example while it restarts).
 * Returns a function that stops listening.
 */
export function subscribeToEvents({ onOpen, onEvent, onDown, retryMs = 2000 }) {
  let source;
  let retry;
  const connect = () => {
    source = new EventSource("/api/events");
    source.onopen = () => onOpen?.();
    source.onmessage = (message) => onEvent(JSON.parse(message.data));
    source.onerror = () => {
      onDown?.();
      source.close();
      retry = setTimeout(connect, retryMs);
    };
  };
  connect();
  return () => {
    clearTimeout(retry);
    source.close();
  };
}
