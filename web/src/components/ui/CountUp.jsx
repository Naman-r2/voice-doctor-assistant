import { useEffect, useRef, useState } from "react";

const DURATION = 700;
const easeOut = (t) => 1 - (1 - t) ** 3;

/** A number that rolls to its new value instead of jumping. */
export default function CountUp({ value }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);

  useEffect(() => {
    const start = from.current;
    if (start === value || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      from.current = value;
      setShown(value);
      return;
    }
    let frame;
    const began = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - began) / DURATION);
      const current = Math.round(start + (value - start) * easeOut(t));
      from.current = current;
      setShown(current);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <span className="count">{shown}</span>;
}
