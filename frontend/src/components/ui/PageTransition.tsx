/**
 * PageTransition
 * ==============
 * Wraps page content in a smooth fade-up entrance animation.
 * Drop this around the main content of any page.
 *
 * Usage:
 *   <PageTransition>
 *     <YourPageContent />
 *   </PageTransition>
 */
"use client";

interface PageTransitionProps {
  children: React.ReactNode;
  className?: string;
}

export function PageTransition({ children, className = "" }: PageTransitionProps) {
  return (
    <div
      className={className}
    >
      {children}
    </div>
  );
}

/** Stagger wrapper — children  in sequence */
export function StaggerIn({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={className}
    >
      {children}
    </div>
  );
}

/** Single stagger child */
export function StaggerChild({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={className}
    >
      {children}
    </div>
  );
}
