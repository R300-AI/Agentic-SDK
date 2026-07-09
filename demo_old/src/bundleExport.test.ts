import { describe, expect, it } from "vitest";
import { buildBundleFiles } from "./bundleExport";
import { DEFAULT_WORKFLOW } from "./defaultWorkflow";

describe("deploy bundle export", () => {
  it("builds runnable bundle contract files", () => {
    const files = buildBundleFiles(DEFAULT_WORKFLOW, "print('ok')\n", {
      schema_version: 1,
      node_definitions: [],
      provider_refs: [],
      profile_refs: [],
      retrieve_strategy_refs: [{ ref: "lexical_file_kb" }],
      retrieve_template_refs: [{ ref: "shoe_store_catalog_search" }],
      knowledge_base_refs: [{ ref: "shoe_store" }],
      execution_env_refs: [{ ref: "local-default", kind: "uv" }],
      export_capabilities: { runnable_bundle: true },
      feature_flags: { inline_python_hosted: false },
    });

    expect(files.map((file) => file.path)).toEqual([
      "main.py",
      "workflow.yaml",
      "profile.yaml",
      "registries.yaml",
    ]);
    expect(files[0].content).toContain("print('ok')");
    expect(files.find((file) => file.path === "workflow.yaml")?.content).toContain("knowledge_base_ref: shoe_store");
    expect(files.find((file) => file.path === "profile.yaml")?.content).toContain("retrieve_template_ref: shoe_store_catalog_search");
    expect(files.find((file) => file.path === "registries.yaml")?.content).toContain("lexical_file_kb");
  });
});
