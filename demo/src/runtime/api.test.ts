import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCapabilities, previewKnowledgeBase } from "./api";

describe("Gateway capability API", () => {
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
});