"use client";

import React, { useEffect, useState } from "react";
import { animate, useMotionValue } from "framer-motion";

export function AnimatedNumber({ value }: { value: number }) {
  const count = useMotionValue(0);
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    const controls = animate(count, value, {
      duration: 1.5,
      ease: [0.16, 1, 0.3, 1], // Custom classy ease (exponential)
      onUpdate: (latest) => setDisplayValue(Math.round(latest)),
    });
    return controls.stop;
  }, [value, count]);

  return <>{displayValue}</>;
}
