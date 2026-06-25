import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  deleteAgent,
  fetchCapabilities,
  listAgents,
  previewKnowledgeBase,
  runWorkflow,
  saveAgent,
} from "./api";
import { setManagedAgentId, setRuntimeMode } from "./gatewayUrl";

describe("Gateway capability API", () => {
  beforeEach(() => {
    setRuntimeMode("gateway");
    setManagedAgentId("");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches capability discovery document", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        schema_version: 1,
        node_definitions: [{ type: "builtin.retrieve", role: "retrieve", label: "Retrieve", params_schema: {} }],
        provider_refs: [],
        profile_refs: [],
        retrieve_strategy_refs: [{ ref: "lexical_file_kb", enabled: true }],
        retrieve_template_refs: [{ ref: "shoe_store_catalog_search" }],
        knowledge_base_refs: [{ ref: "shoe_store" }],
        execution_env_refs: [{ ref: "local-default", kind: "uv" }],
        export_capabilities: { runnable_bundle: true },
        feature_flags: { inline_python_hosted: false },
      }),
    } as Response);

    const capabilities = await fetchCapabilities();

    expect(fetchMock).toHaveBeenCalledWith("/v1/capabilities");
    expect(capabilities.retrieve_strategy_refs[0].ref).toBe("lexical_file_kb");
    expect(capabilities.export_capabilities.runnable_bundle).toBe(true);
  });

  it("surfaces gateway errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 503,
      text: async () => "offline",
    } as Response);

    await expect(fetchCapabilities()).rejects.toThrow("GET /v1/capabilities 失敗 (503):offline");
  });

  it("previews a knowledge base", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        knowledge_base_ref: "shoe_store",
        query: "久站",
        hits: [{ id: "stable-pro-walker", title: "StablePro 機能健走鞋", score: 0.2, source: "knowledge_base" }],
      }),
    } as Response);

    const preview = await previewKnowledgeBase("shoe_store", "久站", 2);

    expect(fetchMock).toHaveBeenCalledWith("/v1/knowledge-bases/shoe_store/preview?query=%E4%B9%85%E7%AB%99&top_k=2");
    expect(preview.hits[0].title).toBe("StablePro 機能健走鞋");
  });

  it("uses managed capability proxy when runtime mode is managed", async () => {
    setRuntimeMode("managed");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        schema_version: 1,
        node_definitions: [],
        provider_refs: [],
        profile_refs: [],
        retrieve_strategy_refs: [],
        retrieve_template_refs: [],
        knowledge_base_refs: [],
        execution_env_refs: [],
        export_capabilities: {},
        feature_flags: {},
      }),
    } as Response);

    await fetchCapabilities();

    expect(fetchMock).toHaveBeenCalledWith("/api/me/agent-playground/capabilities");
  });

  it("runs workflow through managed agent route", async () => {
    setRuntimeMode("managed");
    setManagedAgentId("agt_001");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ workflow_id: "wf_001", stream_url: "/api/me/agents/agt_001/runs/wf_001/stream" }),
    } as Response);

    await runWorkflow("name: demo", "hello");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/me/agents/agt_001/run",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("lists and saves agents through AI Hub APIs", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ agent_id: "agt_001", agent_name: "demo", description: "", workflow_yaml: "name: demo", execution_backend: "upstream", updated_at: null, last_run_at: null }),
      } as Response);

    await listAgents();
    await saveAgent({
      agentName: "demo",
      description: "",
      workflowYaml: "name: demo",
      executionBackend: "upstream",
      csrfToken: "csrf",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/me/agents");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/me/agents",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf" }),
      })
    );
  });

  it("deletes agent through AI Hub API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      text: async () => "",
    } as Response);

    await deleteAgent("agt_001", "csrf");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/me/agents/agt_001",
      expect.objectContaining({ method: "DELETE", headers: { "X-CSRF-Token": "csrf" } })
    );
  });
});