"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ShieldAlert, Home, ArrowLeft } from "lucide-react";

export default function NotFound() {
 return (
  <div className="min-h-screen text-foreground flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
   <motion.div
    className="relative z-10 max-w-md w-full flex flex-col items-center gap-6"
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5 }}
   >
    <motion.div
     className="w-20 h-20 rounded-2xl bg-primary/10 border border-primary/25 flex items-center justify-center shadow-[0_0_40px_rgba(16,185,129,0.15)]"
     animate={{ scale: [1, 1.05, 1] }}
     transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
    >
     <ShieldAlert
      className="w-10 h-10 text-primary"
      aria-hidden="true"
     />
    </motion.div>

    <div className="space-y-2">
     <p className="text-primary font-mono text-xs tracking-wide ">
      404 — Route Not Found
     </p>
     <h1 className="text-3xl font-black text-foreground tracking-tight">
      Page Not Found
     </h1>
     <p className="text-slate-500 text-sm leading-relaxed max-w-xs mx-auto">
      This route does not exist. The investigation system only serves
      defined forensic pipeline endpoints.
     </p>
    </div>

    <div className="flex flex-col sm:flex-row gap-3 w-full">
     <Link
      href="/"
      className="btn-primary flex-1 py-3 rounded-xl font-medium inline-flex items-center justify-center gap-2 text-white border border-primary/30"
     >
      <Home className="w-4 h-4" aria-hidden="true" />
      Dashboard
     </Link>
     <Link
      href="/evidence"
      className="flex-1 py-3 rounded-xl inline-flex items-center justify-center gap-2 font-semibold text-white/80 bg-white/[0.04] border border-white/[0.09] hover:bg-primary/[0.07] hover:border-primary/28 hover:text-primary transition-colors"
     >
      <ArrowLeft className="w-4 h-4" aria-hidden="true" />
      New Investigation
     </Link>
    </div>
   </motion.div>
  </div>
 );
}
