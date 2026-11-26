// Ring and hang-up tones made with the Web Audio API, so there are no audio files to ship.

let ctx;
function audio() {
  ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

function beep(freqs, start, length, volume = 0.05) {
  const ac = audio();
  const gain = ac.createGain();
  gain.connect(ac.destination);
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(volume, start + 0.02);
  gain.gain.setValueAtTime(volume, start + length - 0.03);
  gain.gain.linearRampToValueAtTime(0, start + length);
  const oscillators = freqs.map((f) => {
    const osc = ac.createOscillator();
    osc.frequency.value = f;
    osc.connect(gain);
    osc.start(start);
    osc.stop(start + length);
    return osc;
  });
  return () => {
    oscillators.forEach((o) => {
      try {
        o.stop();
      } catch {
        // already stopped
      }
    });
    gain.disconnect();
  };
}

// Double "ring ring", repeated until the returned function is called.
export function startRing() {
  let stops = [];
  const cycle = () => {
    const t = audio().currentTime;
    stops = [beep([400, 450], t, 0.4), beep([400, 450], t + 0.6, 0.4)];
  };
  cycle();
  const id = setInterval(cycle, 2400);
  return () => {
    clearInterval(id);
    stops.forEach((s) => s());
  };
}

export function playEnd() {
  const t = audio().currentTime;
  [0, 0.28, 0.56].forEach((d) => beep([480], t + d, 0.16, 0.06));
}

export function playChime() {
  const t = audio().currentTime;
  beep([660], t, 0.12, 0.04);
  beep([880], t + 0.13, 0.2, 0.04);
}
