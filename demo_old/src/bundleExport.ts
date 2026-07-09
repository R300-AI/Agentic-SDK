import { dump } from "js-yaml";
import type { CapabilityDocument } from "./runtime/api";
import type { WorkflowConfig } from "./types";
import { configToYaml } from "./adapter";

export interface BundleFile {
  path: string;
  content: string;
  mime: string;
}

export function buildBundleFiles(
  config: WorkflowConfig,
  mainPy: string,
  capabilities: CapabilityDocument | null
): BundleFile[] {
  const retrieveSpec = config.nodes.retrieve;
  const retrieveParams = retrieveSpec?.params ?? {};
  const profileRef = String(retrieveParams.knowledge_base_ref ?? config.name ?? "default");
  const templateRef = String(retrieveParams.retrieve_template_ref ?? "");

  const registries = {
    schema_version: capabilities?.schema_version ?? 1,
    retrieve_strategy_refs: capabilities?.retrieve_strategy_refs ?? [],
    retrieve_template_refs: capabilities?.retrieve_template_refs ?? [],
    knowledge_base_refs: capabilities?.knowledge_base_refs ?? [],
    execution_env_refs: capabilities?.execution_env_refs ?? [],
  };

  const profile = {
    schema_version: 1,
    profile_ref: profileRef,
    workflow_name: config.name ?? "demo",
    retrieve_template_ref: templateRef || null,
    knowledge_base_ref: retrieveParams.knowledge_base_ref ?? null,
    entry: config.entry,
  };

  return [
    { path: "main.py", content: mainPy, mime: "text/x-python;charset=utf-8" },
    { path: "workflow.yaml", content: configToYaml(config), mime: "application/yaml;charset=utf-8" },
    { path: "profile.yaml", content: dump(profile, { sortKeys: false, lineWidth: 120 }), mime: "application/yaml;charset=utf-8" },
    { path: "registries.yaml", content: dump(registries, { sortKeys: false, lineWidth: 120 }), mime: "application/yaml;charset=utf-8" },
  ];
}
