import { z } from "zod";

export const AgentResultSchema = z.object({
    id: z.string(),
    name: z.string(),
    role: z.string(),
    result: z.string(),
    confidence: z.number(),
});

export const ReportSchema = z.object({
    id: z.string(),
    fileName: z.string(),
    timestamp: z.string(),
    summary: z.string(),
    agents: z.array(AgentResultSchema),
});

export const HistorySchema = z.array(ReportSchema);
