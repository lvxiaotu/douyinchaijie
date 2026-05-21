import { fetchDouyinTargetVideoInteractions } from "../../services/api";
import { useAsyncResource } from "./useAsyncResource";

export function useDouyinInteractions(videoId) {
  return useAsyncResource(videoId, fetchDouyinTargetVideoInteractions);
}
