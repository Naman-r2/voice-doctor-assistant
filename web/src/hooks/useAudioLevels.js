import { useEffect, useRef } from "react";

function analyserFor(audioContext, track) {
  if (!track) return null;
  const source = audioContext.createMediaStreamSource(new MediaStream([track]));
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.8;
  source.connect(analyser);
  return { source, analyser, data: new Uint8Array(analyser.frequencyBinCount) };
}

function loudness(node) {
  if (!node) return 0;
  node.analyser.getByteFrequencyData(node.data);
  let sum = 0;
  for (let i = 1; i < 40; i++) sum += node.data[i]; // the range a voice lives in
  return Math.min(1, sum / 39 / 170);
}

/**
 * How loud the agent and the caller are right now, each 0..1.
 *
 * Returns a ref-like reader instead of state: the orb reads it on every
 * animation frame, and re-rendering React 60 times a second would be wasteful.
 */
export function useAudioLevels(botTrack, micTrack, active) {
  const nodes = useRef({ bot: null, mic: null });

  useEffect(() => {
    if (!active) return;
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    nodes.current = { bot: analyserFor(audioContext, botTrack), mic: analyserFor(audioContext, micTrack) };
    return () => {
      nodes.current.bot?.source.disconnect();
      nodes.current.mic?.source.disconnect();
      nodes.current = { bot: null, mic: null };
      audioContext.close();
    };
  }, [botTrack, micTrack, active]);

  return useRef(() => ({ bot: loudness(nodes.current.bot), mic: loudness(nodes.current.mic) })).current;
}
