import Card from "../ui/Card.jsx";
import CountUp from "../ui/CountUp.jsx";
import Icon from "../ui/Icon.jsx";

function slotTotals(doctors, dayIndex) {
  let free = 0;
  let total = 0;
  for (const doctor of doctors) {
    doctor.days.forEach((day, i) => {
      if (dayIndex !== undefined && i !== dayIndex) return;
      total += day.slots.length;
      free += day.slots.filter((slot) => slot.free).length;
    });
  }
  return { free, total };
}

/** The headline numbers. Each rolls to its new value, and the bars show how full the clinic is. */
export default function StatTiles({ doctors, appointments, callsToday }) {
  const today = slotTotals(doctors, 0);
  const week = slotTotals(doctors);
  const active = appointments.filter((a) => a.status === "booked").length;

  const tiles = [
    { icon: "clock", label: "Open today", value: today.free, of: today.total },
    { icon: "calendar", label: "Open, 5 days", value: week.free, of: week.total },
    { icon: "check", label: "Booked", value: active },
    { icon: "pulse", label: "Agent steps", value: callsToday },
  ];

  return (
    <dl className="stats">
      {tiles.map((tile, i) => (
        <Card as="div" className="stat" key={tile.label} style={{ "--i": i }}>
          <span className="stat-icon">
            <Icon name={tile.icon} />
          </span>
          <dt>{tile.label}</dt>
          <dd>
            <CountUp value={tile.value} />
            {tile.of !== undefined && <small>/ {tile.of}</small>}
          </dd>
          {tile.of !== undefined && (
            <span className="meter" aria-hidden="true">
              <span style={{ "--fill": tile.of ? tile.value / tile.of : 0 }} />
            </span>
          )}
        </Card>
      ))}
    </dl>
  );
}
