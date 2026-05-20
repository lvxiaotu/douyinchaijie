import { useEffect, useState } from "react";
import { fetchDouyinTargetVideoInteractions } from "../../services/api";

export function useDouyinInteractions(videoId) {
  const [dataset, setDataset] = useState(null);
  const [status, setStatus] = useState({ loading: false, error: "" });

  useEffect(() => {
    let cancelled = false;
    setDataset(null);
    setStatus({ loading: false, error: "" });
    if (!videoId) return () => {
      cancelled = true;
    };
    setStatus({ loading: true, error: "" });
    fetchDouyinTargetVideoInteractions(videoId)
      .then((nextDataset) => {
        if (!cancelled) {
          setDataset(nextDataset);
          setStatus({ loading: false, error: "" });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setStatus({ loading: false, error: err?.message || String(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [videoId]);

  return { dataset, status };
}

