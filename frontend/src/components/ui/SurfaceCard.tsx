"use client";

import { ReactNode } from "react";

interface SurfaceCardProps {
  children: ReactNode;
  className?: string;
}

export function SurfaceCard({ children, className = "" }: SurfaceCardProps) {
  return (
    <div className={`surface-panel p-6 ${className}`}>
      {children}
    </div>
  );
}
