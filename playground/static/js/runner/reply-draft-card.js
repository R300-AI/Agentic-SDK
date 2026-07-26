export function isReplyDraftProfile(sceneProfile) {
  return sceneProfile?.primary_result_kind === "message";
}