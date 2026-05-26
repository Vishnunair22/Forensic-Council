"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
 "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-black tracking-wide transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
 {
variants: {
    variant: {
     default: "border-white/10 bg-white/[0.04] fc-text-muted",
     secondary: "border-white/5 bg-white/[0.02] fc-text-faint",
     destructive: "border-rose-500/20 bg-rose-500/[0.05] text-rose-500",
     outline: "border-white/10 fc-text-muted",
     success: "border-emerald-500/20 bg-emerald-500/[0.05] text-emerald-500",
     warning: "border-amber-500/20 bg-amber-500/[0.05] text-amber-500",
     info: "border-blue-500/20 bg-blue-500/[0.05] text-blue-500",
    },
   size: {
    default: "px-2.5 py-0.5",
    sm: "px-2 py-0.25 text-xs",
    lg: "px-3 py-1 text-xs",
   },
  },
  defaultVariants: {
   variant: "default",
   size: "default",
  },
 },
);

export interface BadgeProps
 extends React.HTMLAttributes<HTMLDivElement>,
  VariantProps<typeof badgeVariants> {
 withDot?: boolean;
 dotColor?: string;
}

export function Badge({
 className,
 variant,
 size,
 withDot,
 dotColor = "currentColor",
 ...props
}: BadgeProps) {
 return (
  <div className={cn(badgeVariants({ variant, size }), className)} {...props}>
   {withDot && (
    <span
     className="mr-1.5 h-1 w-1 rounded-full inline-block"
     style={{ backgroundColor: dotColor }}
    />
   )}
   {props.children}
  </div>
 );
}
