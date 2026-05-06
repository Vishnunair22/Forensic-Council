"use client";

import React from "react";
import { Activity } from "lucide-react";

export function AgentProgressSkeleton() {
  return (
    <div className="flex flex-col w-full max-w-[1560px] mx-auto gap-8 pb-24 pt-24 animate-pulse">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-10 w-full mb-12 px-2">
        <div className="flex flex-col gap-4">
          <div className="h-16 w-80 bg-white/5 rounded-2xl" />
          <div className="flex items-center gap-4">
            <div className="h-4 w-32 bg-white/5 rounded-full" />
            <div className="w-[1px] h-3 bg-white/10" />
            <div className="h-4 w-48 bg-white/5 rounded-full" />
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="glass-panel px-6 py-5 rounded-2xl flex items-center gap-6 border-white/5 bg-white/[0.02]">
             <div className="flex flex-col gap-2">
               <div className="h-3 w-16 bg-white/5 rounded-full" />
               <div className="h-8 w-12 bg-white/5 rounded-lg" />
             </div>
             <div className="w-12 h-12 rounded-full border border-white/5 flex items-center justify-center bg-white/5">
                <Activity className="w-6 h-6 text-white/10" />
             </div>
          </div>
          <div className="h-20 w-32 bg-white/5 rounded-2xl" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-[400px] rounded-[2.5rem] border border-white/5 bg-white/[0.02] overflow-hidden p-8 space-y-6">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-white/5" />
              <div className="space-y-2">
                <div className="h-6 w-32 bg-white/5 rounded-lg" />
                <div className="h-3 w-20 bg-white/5 rounded-full" />
              </div>
            </div>
            <div className="space-y-3">
              <div className="h-4 w-full bg-white/5 rounded-full" />
              <div className="h-4 w-[90%] bg-white/5 rounded-full" />
              <div className="h-4 w-[80%] bg-white/5 rounded-full" />
            </div>
            <div className="pt-8 grid grid-cols-2 gap-4">
              <div className="h-10 bg-white/5 rounded-xl" />
              <div className="h-10 bg-white/5 rounded-xl" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
