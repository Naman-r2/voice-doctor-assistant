import { useCallback, useEffect, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Phase } from "./useCall.js";

/** What the agent is doing at this moment. Drives the orb and the headline. */
export const Agent = {
  IDLE: "idle", // no call
  RINGING: "ringing",
  LISTENING: "listening", // waiting for, or hearing, the caller
  THINKING: "thinking", // the caller stopped; the reply is on its way
  SPEAKING: "speaking",
  ENDED: "ended",
};

/**
 * Follows the conversation's turn-taking from the events the server sends:
 * the caller stops -> thinking -> the agent speaks -> listening again.
 */
export function useAgentState(phase) {
  const [turn, setTurn] = useState(Agent.LISTENING);

  useEffect(() => {
    if (phase === Phase.LIVE) setTurn(Agent.LISTENING);
  }, [phase]);

  useRTVIClientEvent(
    RTVIEvent.BotStartedSpeaking,
    useCallback(() => setTurn(Agent.SPEAKING), []),
  );
  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => setTurn(Agent.LISTENING), []),
  );
  useRTVIClientEvent(
    RTVIEvent.UserStartedSpeaking,
    useCallback(() => setTurn(Agent.LISTENING), []),
  );
  useRTVIClientEvent(
    RTVIEvent.UserStoppedSpeaking,
    useCallback(() => setTurn(Agent.THINKING), []),
  );

  if (phase === Phase.IDLE) return Agent.IDLE;
  if (phase === Phase.RINGING) return Agent.RINGING;
  if (phase === Phase.ENDED) return Agent.ENDED;
  return turn;
}
