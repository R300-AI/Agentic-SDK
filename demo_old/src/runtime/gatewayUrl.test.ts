import { describe, expect, it } from "vitest";

import { parseRuntimeBootstrap } from "./gatewayUrl";

describe("parseRuntimeBootstrap", () => {
  it("parses managed bootstrap params from query string", () => {
    expect(
      parseRuntimeBootstrap("?runtimeMode=managed&agentId=agt_123&apiBase=https://aihub.example.com/&token=bridge-token")
    ).toEqual({
      runtimeMode: "managed",
      agentId: "agt_123",
      apiBase: "https://aihub.example.com",
      token: "bridge-token",
    });
  });

  it("infers managed mode when bridge params exist", () => {
    expect(parseRuntimeBootstrap("?agentId=agt_456")).toEqual({
      runtimeMode: "managed",
      agentId: "agt_456",
      apiBase: undefined,
      token: undefined,
    });
  });

  it("returns empty bootstrap when no managed params exist", () => {
    expect(parseRuntimeBootstrap("")).toEqual({
      runtimeMode: undefined,
      agentId: undefined,
      apiBase: undefined,
      token: undefined,
    });
  });
});