// Canonical agent-event contract. Sync this file into frontend/gateway local type files.

export type AgentChatMode = 'local' | 'web' | 'hybrid';

export type PlanningEvent = {
  type: 'planning';
  traceId: string;
  mode: AgentChatMode;
  timestamp: string;
  phase: 'planning';
  decisionResult?: string;
  selectedPath?: string;
  selectedToolsOrSkills?: string[];
  plannerSource?: 'rule' | 'llm' | 'fallback';
  plannerSourceMode?: 'rule_only' | 'shadow_compare' | 'llm_primary_with_rule_fallback';
  executionSource?: 'rule' | 'llm' | 'fallback';
};

export type ToolSelectionEvent = {
  type: 'toolSelection';
  traceId: string;
  mode: AgentChatMode;
  timestamp: string;
  toolName: string;
  callId: string;
  status: 'selected';
};

export type ToolRunningEvent = {
  type: 'toolRunning';
  traceId: string;
  mode: AgentChatMode;
  timestamp: string;
  toolName: string;
  callId: string;
  status: 'running';
};

export type ToolResultEvent = {
  type: 'toolResult';
  traceId: string;
  mode: AgentChatMode;
  timestamp: string;
  toolName: string;
  callId: string;
  status: 'succeeded' | 'failed' | 'clarify_required' | 'blocked' | 'skipped';
  resultKind?: 'final' | 'intermediate' | 'empty' | 'failed' | 'clarify_required';
  message?: string;
};

export type FallbackEvent = {
  type: 'fallback';
  traceId: string;
  mode: AgentChatMode;
  timestamp: string;
  fallbackScope: 'planner' | 'tool' | 'legacy';
  reasonCode: string;
  failedTool?: string;
  continues: boolean;
  message?: string;
};

export type AgentEvent = PlanningEvent | ToolSelectionEvent | ToolRunningEvent | ToolResultEvent | FallbackEvent;
