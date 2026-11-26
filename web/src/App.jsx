import { useEffect, useMemo } from "react";
import Stage from "./components/call/Stage.jsx";
import ActivityLog from "./components/dashboard/ActivityLog.jsx";
import Appointments from "./components/dashboard/Appointments.jsx";
import Schedule from "./components/dashboard/Schedule.jsx";
import StatTiles from "./components/dashboard/StatTiles.jsx";
import TopBar from "./components/layout/TopBar.jsx";
import Scene from "./components/scene/Scene.jsx";
import Toasts from "./components/ui/Toasts.jsx";
import { Phase, useCall } from "./hooks/useCall.js";
import { useClinic } from "./hooks/useClinic.js";
import { bookedThisCall, callActivity } from "./lib/activity.js";
import { playChime } from "./lib/sounds.js";

/**
 * The front desk. A 3D scene fills the page: the agent is a sphere of particles
 * on the left, and the clinic's schedule, appointments and activity float on the right.
 */
export default function App() {
  const call = useCall();
  const { doctors, appointments, events, lastAction, highlights, online } = useClinic();

  // A short chime when the agent books or cancels during a call.
  useEffect(() => {
    if (lastAction && call.phase === Phase.LIVE) playChime();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastAction]);

  const activity = useMemo(() => callActivity(events, doctors, call), [events, doctors, call]);
  const bookedNow = useMemo(() => bookedThisCall(events, call.placedAt), [events, call.placedAt]);
  const actionsThisCall = events.filter((e) => e.appointment && e.at >= call.placedAt && call.placedAt).length;

  return (
    <div className="app">
      <Scene />
      <div className="grain" aria-hidden="true" />

      <TopBar online={online} />

      <div className="workspace">
        <aside className="stage-column" aria-label="Voice call">
          <Stage call={call} online={online} lastAction={lastAction} actionsThisCall={actionsThisCall} />
        </aside>

        <main className="content">
          <StatTiles doctors={doctors} appointments={appointments} callsToday={events.length} />
          <Schedule doctors={doctors} appointments={appointments} highlights={highlights} lastAction={lastAction} />
          <div className="split">
            <Appointments appointments={appointments} highlights={highlights} bookedThisCall={bookedNow} />
            <ActivityLog rows={activity} live={call.phase === Phase.LIVE} />
          </div>
        </main>
      </div>

      <Toasts lastAction={lastAction} />
    </div>
  );
}
