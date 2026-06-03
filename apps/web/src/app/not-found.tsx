import Link from "next/link";
import { ShieldAlert, Home, ArrowLeft } from "lucide-react";

export default function NotFound() {
 return (
  <div className="min-h-screen text-foreground flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
   <div className="relative z-10 max-w-md w-full flex flex-col items-center gap-6">
    <div className="w-20 h-20 rounded-2xl bg-primary/10 border border-primary/25 flex items-center justify-center">
     <ShieldAlert
      className="w-10 h-10 text-primary"
      aria-hidden="true"
     />
    </div>

    <div className="space-y-2">
     <p className="text-primary font-mono text-xs tracking-wide ">
      404 — Route Not Found
     </p>
     <h1 className="text-3xl font-extrabold text-foreground tracking-tight">
      Page Not Found
     </h1>
     <p className="fc-text-muted text-sm leading-relaxed max-w-xs mx-auto">
      This route does not exist. The investigation system only serves
      defined forensic pipeline endpoints.
     </p>
    </div>

    <div className="flex flex-col sm:flex-row gap-3 w-full">
     <Link
      href="/"
      className="fc-btn-primary flex-1 py-3"
     >
      <Home className="w-4 h-4" aria-hidden="true" />
      Dashboard
     </Link>
     <Link
       href="/?upload=1"
       className="fc-btn-ghost flex-1 py-3"
     >
      <ArrowLeft className="w-4 h-4" aria-hidden="true" />
      New Investigation
     </Link>
    </div>
   </div>
  </div>
 );
}
