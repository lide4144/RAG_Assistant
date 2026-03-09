'use client';

import { useEffect, useMemo, useState } from 'react';

interface NumberTickerProps {
  value: number;
  durationMs?: number;
  className?: string;
}

export function NumberTicker({ value, durationMs = 500, className }: NumberTickerProps) {
  const target = Number.isFinite(value) ? value : 0;
  const [display, setDisplay] = useState(target);

  useEffect(() => {
    const start = performance.now();
    const initial = display;
    const delta = target - initial;

    if (delta === 0) {
      return;
    }

    let raf = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = initial + delta * eased;
      setDisplay(next);
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [durationMs, display, target]);

  const text = useMemo(() => Math.round(display).toLocaleString('zh-CN'), [display]);

  return <span className={className}>{text}</span>;
}
