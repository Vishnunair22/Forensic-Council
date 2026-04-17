"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
 "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-black tracking-widest transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
 {
  variants: {
   variant: {
    default: "border-transparent bg-cyan-500/10 text-cyan-400 font-mono",
    secondary: "border-white/5 bg-white/[0.02] text-white/40",
    destructive: "border-rose-500/20 bg-rose-500/[0.05] text-rose-400",
    outline: "border-white/10 text-white/60",
    success: "border-emerald-500/20 bg-emerald-500/[0.05] text-emerald-400",
    warning: "border-amber-500/20 bg-amber-500/[0.05] text-amber-400",
    info: "border-blue-500/20 bg-blue-500/[0.05] text-blue-400",
   },
   size: {
    default: "px-2.5 py-0.5",
    sm: "px-2 py-0.25 text-[10px]",
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
