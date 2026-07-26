import { getJson } from "../shared/api-client.js";

export function fetchSceneProfile() {
  return getJson("/playground/run/profile");
}