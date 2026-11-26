/**
 * A tiny shared board between the call (which knows the agent's state and how
 * loud each side is) and the 3D scene (which draws it 60 times a second).
 *
 * Plain mutable fields, on purpose: the scene reads them inside its animation
 * loop, and putting per-frame values in React state would re-render the app
 * on every frame.
 */
export const voiceBus = {
  state: "idle", // an Agent value from useAgentState
  levels: () => ({ bot: 0, mic: 0 }), // loudness of each side, 0..1
  burstAt: 0, // performance.now() of the last booking or cancellation
  anchor: null, // the DOM element the sphere should sit behind
};

/** Make the sphere flare: something was booked or cancelled. */
export const burst = () => {
  voiceBus.burstAt = performance.now();
};
