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
  return {
    label: "Review Required",
    color: "amber",
    textColor: "text-amber-400",
    dotColor: "bg-amber-400",
    Icon: AlertTriangle,
    desc: "Manual expert review is recommended.",
  };
}
