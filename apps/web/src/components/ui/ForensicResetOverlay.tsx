"use client";

import { motion } from "framer-motion";

/**
 * ForensicResetOverlay: The 'Atmospheric Reset'
 * A high-speed, barely noticeable dim-and-blur transition.
 * Caller handles conditional rendering.
 */
export function ForensicResetOverlay() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="fixed inset-0 z-[1000] pointer-events-none bg-black/20 backdrop-blur-md"
    />
  );
}
