// Small formatting helpers shared by the dashboard and the call panel.

/** 75 -> "01:15" */
export const clock = (seconds) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

/** "Thursday 26 November" -> "Thu 26". "Today" and "Tomorrow" stay as they are. */
export function shortDay(label) {
  const [weekday, date] = label.split(" ");
  return date ? `${weekday.slice(0, 3)} ${date}` : label;
}

/** "Dr. Rohan Mehta" -> "RM" */
export const initials = (name) =>
  name
    .replace(/^Dr\.?\s+/i, "")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

/** "9876543210" -> "98765 43210" */
export const phone = (digits) => (digits?.length === 10 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : digits);

export const todayLabel = () =>
  new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

export const timeOfDay = (ms) =>
  new Date(ms).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
