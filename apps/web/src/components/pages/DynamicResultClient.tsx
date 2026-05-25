"use client";

import React, { useEffect } from "react";
import { motion } from "framer-motion";
import { ResultLayout } from "@/components/result/ResultLayout";
import { useSound } from "@/hooks/useSound";

export function DynamicResultClient({ sessionId }: { sessionId: string }) {
  const { playSound } = useSound();

  useEffect(() => {
    document.body.style.overflow = "";
    playSound("stamp");
  }, [playSound]);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{
        duration: 0.45,
        ease: [0.16, 1, 0.3, 1],
      }}
      className="relative"
    >
      <motion.div
        className="absolute inset-0 bg-white/10 z-50 pointer-events-none"
        initial={{ opacity: 1 }}
        animate={{ opacity: 0 }}
        transition={{ duration: 0.8, ease: "circOut" }}
      />
      <ResultLayout initialSessionId={sessionId} />
    </motion.div>
  );
}
