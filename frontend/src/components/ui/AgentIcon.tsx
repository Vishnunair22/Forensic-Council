"use client";

import { Shield, Search, Layout, Database, Video, Mic2, CheckCircle } from "lucide-react";
import { AGENTS_DATA } from "@/lib/constants";

interface AgentIconProps {
    role?: string;
    agentId?: string;
    className?: string;
    active?: boolean;
}

export const AgentIcon = ({ role, agentId, className, active }: AgentIconProps) => {
    // Resolve role from agentId if role not provided
    let resolvedRole = role || "";
    if (!resolvedRole && agentId) {
        const agent = AGENTS_DATA.find(a => a.id === agentId);
        resolvedRole = agent?.role || "";
    }
    // Normalize string for checking
    const r = resolvedRole.toLowerCase();

    if (r.includes("integrity") || r.includes("artifact")) return <Shield className={className} />;
    if (r.includes("scene") || r.includes("lighting") || r.includes("reconstruction")) return <Search className={className} />;
    if (r.includes("object") || r.includes("weapon")) return <Layout className={className} />;
    if (r.includes("temporal") || r.includes("video") || r.includes("frame")) return <Video className={className} />;
    if (r.includes("metadata") || r.includes("context")) return <Database className={className} />;
    if (r.includes("audio") || r.includes("multimedia")) return <Mic2 className={className} />;

    return <CheckCircle className={className} />;
};
