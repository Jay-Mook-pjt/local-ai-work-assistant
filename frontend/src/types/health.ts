export interface ComponentStatus {
  ok: boolean;
  detail?: string | null;
  version?: string | null;
  latency_ms?: number | null;
  models?: string[] | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  env: string;
  llm_model: string;
  components: Record<"database" | "ollama" | "stt", ComponentStatus>;
}
