import { useCallback, useEffect, useRef, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { usePipecatClient, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { OFFER_ENDPOINT } from "../api/voiceClient.js";
import { playEnd, startRing } from "../lib/sounds.js";

/** The stages of one call, in order. */
export const Phase = { IDLE: "idle", RINGING: "ringing", LIVE: "live", ENDED: "ended" };

/**
 * One voice call with the agent: connect, hang up, and where it stands.
 *
 * Returns the phase, when the call was placed and answered, how long it lasted,
 * an error message if it failed, and start() / end() / reset().
 */
export function useCall() {
  const client = usePipecatClient();
  const [phase, setPhase] = useState(Phase.IDLE);
  const [error, setError] = useState("");
  const [placedAt, setPlacedAt] = useState(0); // "Start call" was pressed
  const [answeredAt, setAnsweredAt] = useState(0); // the agent picked up
  const [duration, setDuration] = useState(0); // seconds, set when the call ends

  const stopRing = useRef(() => {});
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const answeredRef = useRef(0);
  answeredRef.current = answeredAt;

  // Move to "ended" once, whichever side hung up.
  const finish = useCallback((message = "") => {
    stopRing.current();
    if (message) setError(message);
    if (phaseRef.current === Phase.IDLE || phaseRef.current === Phase.ENDED) return;
    phaseRef.current = Phase.ENDED;
    setDuration(answeredRef.current ? Math.floor((Date.now() - answeredRef.current) / 1000) : 0);
    setPhase(Phase.ENDED);
    playEnd();
  }, []);

  const start = useCallback(async () => {
    setError("");
    setAnsweredAt(0);
    setPlacedAt(Date.now());
    setPhase(Phase.RINGING);
    stopRing.current = startRing();
    try {
      await client.connect({ webrtcRequestParams: { endpoint: OFFER_ENDPOINT } });
      stopRing.current();
      setAnsweredAt(Date.now());
      setPhase(Phase.LIVE);
    } catch (e) {
      finish(
        e?.name === "NotAllowedError"
          ? "Microphone access was blocked. Allow it in the browser and try again."
          : "Could not reach the agent. Check that the server is running.",
      );
      client.disconnect().catch(() => {});
    }
  }, [client, finish]);

  const end = useCallback(async () => {
    finish();
    await client.disconnect().catch(() => {});
  }, [client, finish]);

  const reset = useCallback(() => setPhase(Phase.IDLE), []);

  // The agent's side closed the call.
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => finish(), [finish]),
  );

  useEffect(() => () => stopRing.current(), []);

  return { phase, error, placedAt, answeredAt, duration, start, end, reset };
}

/** Seconds since `since`, ticking while `running`. */
export function useElapsed(since, running) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) return;
    const tick = () => setSeconds(Math.floor((Date.now() - since) / 1000));
    tick();
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  }, [since, running]);
  return seconds;
}
