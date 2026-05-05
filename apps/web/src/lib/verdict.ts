import { CheckCircle, AlertTriangle, AlertCircle } from "lucide-react";

export interface VerdictConfig {
  label: string;
  color: "emerald" | "red" | "amber";
  textColor: string;
  dotColor: string;
  Icon: typeof CheckCircle;
  desc: string;
}

export function getVerdictConfig(v: string): VerdictConfig {
  const u = (v ?? "").toUpperCase();

  if (u === "AUTHENTIC" || u === "CERTAIN") {
    return {
      label: "Authentic",
      color: "emerald",
      textColor: "text-emerald-400",
      dotColor: "bg-emerald-400",
      Icon: CheckCircle,
      desc: "No forensic evidence of manipulation found.",
    };
  }
  if (u === "LIKELY_AUTHENTIC") {
    return {
      label: "Likely Authentic",
      color: "emerald",
      textColor: "text-emerald-400",
      dotColor: "bg-emerald-400",
      Icon: CheckCircle,
      desc: "Evidence is consistent with authenticity.",
    };
  }
  if (u === "MANIPULATED" || u === "MANIPULATION DETECTED") {
    return {
      label: "Manipulation Detected",
      color: "red",
      textColor: "text-red-400",
      dotColor: "bg-red-400",
      Icon: AlertTriangle,
      desc: "Forensic signals confirm tampering.",
    };
  }
  if (u === "LIKELY_MANIPULATED") {
    return {
      label: "Likely Manipulated",
      color: "red",
      textColor: "text-red-400",
      dotColor: "bg-red-400",
      Icon: AlertTriangle,
      desc: "Significant manipulation signals detected.",
    };
  }
  if (u === "INCONCLUSIVE") {
    return {
      label: "Inconclusive",
      color: "amber",
      textColor: "text-amber-400",
      dotColor: "bg-amber-400",
      Icon: AlertCircle,
      desc: "Insufficient signal strength for a verdict.",
    };
  }
  if (u === "SUSPICIOUS") {
    return {
      label: "Suspicious",
      color: "amber",
      textColor: "text-amber-400",
      dotColor: "bg-amber-400",
      Icon: AlertTriangle,
      desc: "Forensic anomalies warrant closer review.",
    };
  }
  if (u === "LIKELY_AI_GENERATED" || u === "AI_GENERATED") {
    return {
      label: u === "AI_GENERATED" ? "AI Generated" : "Likely AI Generated",
      color: "red",
      textColor: "text-red-400",
      dotColor: "bg-red-400",
      Icon: AlertTriangle,
      desc: "Signals consistent with AI-generated or synthetic content.",
    };
  }
  if (u === "TAMPERED") {
    return {
      label: "Tampered",
      color: "red",
      textColor: "text-red-400",
      dotColor: "bg-red-400",
      Icon: AlertTriangle,
      desc: "Evidence strongly consistent with manual tampering.",
    };
  }
  if (u === "ABSTAIN") {
    return {
      label: "Abstain",
      color: "amber",
      textColor: "text-amber-400",
      dotColor: "bg-amber-400",
      Icon: AlertCircle,
      desc: "Insufficient evidence to reach a reliable verdict.",
    };
  }
  if (u === "NEEDS_REVIEW") {
    return {
      label: "Needs Review",
      color: "amber",
      textColor: "text-amber-400",
      dotColor: "bg-amber-400",
      Icon: AlertCircle,
      desc: "Manual expert review required before reaching a conclusion.",
    };
  }
  if (u === "CLEAN") {
    return {
      label: "Authentic",
      color: "emerald",
      textColor: "text-emerald-400",
      dotColor: "bg-emerald-400",
      Icon: CheckCircle,
      desc: "No forensic evidence of manipulation found.",
    };
  }
  return {
    label: "Review Required",
    color: "amber",
    textColor: "text-amber-400",
    dotColor: "bg-amber-400",
    Icon: AlertTriangle,
    desc: "Manual expert review is recommended.",
  };
}
