import { useEffect, useRef, useState } from "react";

const EASE = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Subtle count-up for KPI figures. Animates once on mount and on every value
 * change, and respects reduced-motion by jumping straight to the value.
 */
export function useCountUp(target: number, duration = 900) {
  const [value, setValue] = useState(0);
  const from = useRef(0);
  const raf = useRef<number>(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      from.current = target;
      return;
    }
    const start = performance.now();
    const origin = from.current;
    const delta = target - origin;

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setValue(origin + delta * EASE(t));
      if (t < 1) raf.current = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);

  return value;
}

export function CountUp({
  value,
  duration,
  format,
  className,
}: {
  value: number;
  duration?: number;
  format: (n: number) => string;
  className?: string;
}) {
  const animated = useCountUp(value, duration);
  return <span className={className}>{format(animated)}</span>;
}
