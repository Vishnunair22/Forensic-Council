export type Agent = {
    name: string;
    role: string;
    desc: string;
};

export type AgentResult = {
    id: string;
    name: string;
    role: string;
    result: string;
    confidence: number;
    thinking?: string;
};

export type Report = {
    id: string;
    fileName: string;
    timestamp: string;
    summary: string;
    agents: AgentResult[];
};
