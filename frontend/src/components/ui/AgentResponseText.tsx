import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export function AgentResponseText({ text, className = "text-sm text-slate-300 mt-1 leading-relaxed" }: { text: string, className?: string }) {
    const [isExpanded, setIsExpanded] = useState(false);

    // Normalise input to string and strip residual markdown formatting
    const raw = typeof text === "string" ? text : String(text ?? "");
    const cleanText = raw
        .replace(/\*\*([^*]+)\*\*/g, "$1")   // **bold** → bold
        .replace(/\*([^*]+)\*/g, "$1")        // *italic* → italic
        .replace(/__([^_]+)__/g, "$1")        // __underline__ → underline
        .replace(/~~([^~]+)~~/g, "$1")        // ~~strike~~ → strike
        .replace(/^#{1,6}\s+/gm, "")          // heading markers
        .replace(/`([^`]+)`/g, "$1")          // inline code
        .trim();

    // Split into meaningful paragraphs / bullet lines
    const lines = cleanText
        .split(/\n+/)
        .map(l => l.trim())
        .filter(Boolean);

    const CHARACTER_LIMIT = 300;
    const totalLength = cleanText.length;
    const isLong = totalLength > CHARACTER_LIMIT;

    // When collapsed, show only the first couple of lines (up to limit)
    const visibleLines: string[] = [];
    if (!isExpanded && isLong) {
        let charCount = 0;
        for (const line of lines) {
            if (charCount + line.length > CHARACTER_LIMIT) {
                // Add a truncated version of this line
                const remaining = CHARACTER_LIMIT - charCount;
                if (remaining > 30) {
                    visibleLines.push(line.substring(0, remaining).trim() + "...");
                }
                break;
            }
            visibleLines.push(line);
            charCount += line.length;
        }
    }

    const displayLines = isExpanded || !isLong ? lines : visibleLines;

    return (
        <div className={className}>
            <div className="space-y-1.5">
                {displayLines.map((line, i) => (
                    <p key={i} className="whitespace-pre-wrap break-words">{line}</p>
                ))}
            </div>
            {isLong && (
                <button
                    onClick={(e) => { e.stopPropagation(); setIsExpanded(!isExpanded); }}
                    className="flex items-center gap-1 text-emerald-500 hover:text-emerald-400 text-xs font-semibold mt-2 transition-all p-1 -ml-1 rounded hover:bg-emerald-500/10"
                >
                    {isExpanded ? (
                        <>Show Less <ChevronUp className="w-3 h-3" /></>
                    ) : (
                        <>Show More <ChevronDown className="w-3 h-3" /></>
                    )}
                </button>
            )}
        </div>
    );
}
