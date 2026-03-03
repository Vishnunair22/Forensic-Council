import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export function AgentResponseText({ text, className = "text-sm text-slate-300 mt-1 leading-relaxed" }: { text: string, className?: string }) {
    const [isExpanded, setIsExpanded] = useState(false);

    // Remove markdown characters like **, *, _, #, `, ~
    const cleanText = typeof text === "string" ? text.replace(/[*_#`~]+/g, "").trim() : String(text);

    const CHARACTER_LIMIT = 280;
    const isLong = cleanText.length > CHARACTER_LIMIT;

    return (
        <div className={className}>
            <p className="whitespace-pre-wrap break-words">
                {isExpanded || !isLong ? cleanText : `${cleanText.substring(0, CHARACTER_LIMIT).trim()}...`}
            </p>
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
