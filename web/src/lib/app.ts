// App shell types shared by views and hooks.
import type { ConversationSummary } from "../types";

export type View = "chat" | "overview" | "graph" | "agents" | "eval";
export type DetailTab = "research" | "verification" | "evidence" | "cypher" | "diagnostics" | "graph";

export const EMPTY_ARRAY: ConversationSummary[] = [];
