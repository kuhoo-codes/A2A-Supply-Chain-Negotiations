export type RunStatus = "running" | "completed" | "failed";

export type AgentRole = "supplier" | "manufacturer" | "retailer";

export type PhaseName =
  | "supplier_manufacturer"
  | "manufacturer_retailer";

export type HealthResponse = {
  status: string;
};

export type PipelineDependencyStatus = {
  configured: boolean;
  available: boolean;
  message: string;
};

export type PipelineExportRecord = {
  file_path: string;
  created_at: string;
};

export type SimulationTestPipelineResult = {
  success: boolean;
  message: string;
  run_id: string;
  trace_id: string | null;
  export: PipelineExportRecord | null;
  openai: PipelineDependencyStatus;
  langfuse: PipelineDependencyStatus;
  events: string[];
};

export type Agent = {
  id: string;
  name: string;
  role: AgentRole;
  objective: string;
  reservation_prices: {
    min_sell_price: number | null;
    max_buy_price: number | null;
  };
};

export type Phase = {
  name: PhaseName;
  label: string;
  order: number;
  description: string;
};

export type NegotiationStatus = "open" | "accepted" | "rejected" | "timeout";

export type ToolCallEvent = {
  id: string;
  step_index: number;
  agent_id: string;
  tool_name: string;
  arguments: Record<string, string | number | boolean | null>;
  result_summary: string;
  created_at: string;
};

export type NegotiationStep = {
  index: number;
  phase: PhaseName;
  negotiation_id: string;
  round_number: number;
  agent_id: string;
  kind: string;
  message: string;
  outcome: string;
  proposed_price: number | null;
  created_at: string;
  tool_calls: ToolCallEvent[];
};

export type DiagnosisSummary = {
  outcome: string;
  chain_effect: string;
  key_risks: string[];
  key_signals: string[];
  suggested_next_actions: string[];
};

export type ProductMarketContext = {
  product_name: string;
  product_category: string;
  market_region: string;
  baseline_unit_price: number;
  target_quantity: number;
  currency: string;
  demand_signal: string;
  supply_signal: string;
};

export type NegotiationRecord = {
  id: string;
  phase: PhaseName;
  label: string;
  seller_agent_id: string;
  buyer_agent_id: string;
  status: NegotiationStatus;
  max_rounds: number;
  quantity: number;
  rounds_completed: number;
  opening_seller_offer: number;
  opening_buyer_offer: number;
  final_price: number | null;
  outcome_summary: string;
  dependency_note: string | null;
};

export type RunSummary = {
  id: string;
  title: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  scenario: string;
  agent_count: number;
  step_count: number;
  current_phase: PhaseName;
};

export type RunRecord = {
  id: string;
  title: string;
  status: RunStatus;
  scenario: string;
  created_at: string;
  updated_at: string;
  product_context: ProductMarketContext;
  agents: Agent[];
  phases: Phase[];
  steps: NegotiationStep[];
  negotiations: NegotiationRecord[];
  diagnosis: DiagnosisSummary;
  max_rounds_per_negotiation: number;
  notes: string;
  tags: string[];
};
