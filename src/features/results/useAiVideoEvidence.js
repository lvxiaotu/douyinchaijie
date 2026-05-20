import { useEffect, useState } from "react";
import { fetchAiVideoEvidence } from "../../services/api";

export function useAiVideoEvidence(taskId) {
  const [dataset, setDataset] = useState(null);
  const [status, setStatus] = useState({ loading: false, error: "" });

  useEffect(() => {
    let cancelled = false;
    setDataset(null);
    setStatus({ loading: false, error: "" });
    if (!taskId) return () => {
      cancelled = true;
    };
    setStatus({ loading: true, error: "" });
    fetchAiVideoEvidence(taskId)
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
  }, [taskId]);

  return { dataset, status };
}

