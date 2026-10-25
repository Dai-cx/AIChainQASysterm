// Extracted from App.tsx during the P7b module split.
import type { AgentTask, ConversationTurn, VerificationResult } from "../types";

export function verificationFromResult(result: ConversationTurn["result"]): VerificationResult | undefined {
  return (
    asVerification(result.verification) ??
    asVerification(result.research_outputs?.verification) ??
    asVerification(result.diagnostics?.agent_verification)
  );
}

export function verificationFromTask(task: AgentTask): VerificationResult | undefined {
  return asVerification(task.research_outputs?.verification) ?? asVerification(task.diagnostics?.agent_verification);
}

export function asVerification(value: unknown): VerificationResult | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  return typeof record.status === "string" ? (record as unknown as VerificationResult) : undefined;
}

export function verificationStatusLabel(status?: string) {
  if (status === "pass") return "通过";
  if (status === "warn") return "需关注";
  if (status === "fail") return "未通过";
  return "未校验";
}
