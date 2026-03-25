"use client";

import { Shield, Search, Layout, Database, Video, Mic2, CheckCircle, Scale } from "lucide-react";
import { AGENTS_DATA } from "@/lib/constants";

interface AgentIconProps {
    role?: string;
    agentId?: string;
    className?: string;
    size?: number | string;
}

export const AgentIcon = ({ role, agentId, className, size = 20 }: AgentIconProps) => {
    const sizeMap: Record<string, number> = {
        sm: 16,
        md: 20,
        lg: 32,
        xl: 48
    };

    const iconSize = typeof size === 'string' && sizeMap[size] ? sizeMap[size] : size as number;

    // Resolve role from agentId if role not provided
    let resolvedRole = role || "";
    if (!resolvedRole && agentId) {
        const agent = AGENTS_DATA.find(a => a.id === agentId);
        resolvedRole = agent?.role || "";
    }
    // Normalize string for checking
    const r = resolvedRole.toLowerCase();

    const iconProps = { className, size: iconSize };

    if (r.includes("integrity") || r.includes("artifact")) return <Shield {...iconProps} />;
    if (r.includes("scene") || r.includes("lighting") || r.includes("reconstruction")) return <Search {...iconProps} />;
    if (r.includes("object") || r.includes("weapon")) return <Layout {...iconProps} />;
    if (r.includes("temporal") || r.includes("video") || r.includes("frame")) return <Video {...iconProps} />;
    if (r.includes("metadata") || r.includes("context")) return <Database {...iconProps} />;
    if (r.includes("audio") || r.includes("multimedia")) return <Mic2 {...iconProps} />;
    if (r.includes("arbiter") || r.includes("synthesis")) return <Scale {...iconProps} />;

    return <CheckCircle {...iconProps} />;
};
