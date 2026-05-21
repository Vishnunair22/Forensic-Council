"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { motion, HTMLMotionProps } from "framer-motion";

interface GlassPanelProps extends HTMLMotionProps<"div"> {
  children: React.ReactNode;
  className?: string;
}

export const GlassPanel = ({
  children,
  className,
  ...props
}: GlassPanelProps) => {
  return (
    <motion.div
      className={cn("fc-surface-quiet rounded-2xl p-6", className)}
      initial={{ opacity: 0, y: 4 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.16, ease: "easeOut" }}
      {...props}
    >
      {children}
    </motion.div>
  );
};
