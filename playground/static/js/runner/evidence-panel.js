export function hasEvidence(result) {
  return Array.isArray(result?.evidence) && result.evidence.length > 0;
}