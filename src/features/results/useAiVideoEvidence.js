import { fetchAiVideoEvidence } from "../../services/api";
import { useAsyncResource } from "./useAsyncResource";

export function useAiVideoEvidence(taskId) {
  return useAsyncResource(taskId, fetchAiVideoEvidence);
}
