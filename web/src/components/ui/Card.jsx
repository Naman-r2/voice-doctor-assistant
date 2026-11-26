import { useCallback } from "react";

const TILT = 2.2; // degrees at the edges

/**
 * A panel floating in the scene. It leans toward the pointer and a soft light
 * follows it: the handlers only write CSS variables, and the stylesheet does
 * the rest.
 */
export default function Card({ as: Tag = "section", className = "", children, ...rest }) {
  const onPointerMove = useCallback((e) => {
    const box = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - box.left) / box.width;
    const y = (e.clientY - box.top) / box.height;
    const style = e.currentTarget.style;
    style.setProperty("--spot-x", `${x * 100}%`);
    style.setProperty("--spot-y", `${y * 100}%`);
    style.setProperty("--tilt-x", `${(0.5 - y) * TILT}deg`);
    style.setProperty("--tilt-y", `${(x - 0.5) * TILT}deg`);
  }, []);

  const onPointerLeave = useCallback((e) => {
    e.currentTarget.style.setProperty("--tilt-x", "0deg");
    e.currentTarget.style.setProperty("--tilt-y", "0deg");
  }, []);

  return (
    <Tag className={`card ${className}`} onPointerMove={onPointerMove} onPointerLeave={onPointerLeave} {...rest}>
      {children}
    </Tag>
  );
}
