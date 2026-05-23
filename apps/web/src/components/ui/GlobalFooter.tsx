export function GlobalFooter() {
  return (
    <footer className="w-full mt-auto relative z-10" role="contentinfo" aria-label="Site footer">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="border-t border-white/[0.06] py-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <span className="text-xs fc-text-faint tracking-wide">
            © {new Date().getFullYear()} Forensic Council
          </span>
          <p className="text-xs fc-text-muted text-center sm:text-right max-w-[56ch] leading-relaxed">
            Academic project. Results may not be accurate — do not rely solely on this system in legal proceedings.
          </p>
        </div>
      </div>
    </footer>
  );
}
