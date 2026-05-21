import { useEffect, useState } from "react";

export function useAsyncResource(key, fetcher) {
  const [dataset, setDataset] = useState(null);
  const [status, setStatus] = useState({ loading: false, error: "" });

  useEffect(() => {
    let cancelled = false;
    setDataset(null);
    setStatus({ loading: false, error: "" });
    if (!key) {
      return () => {
        cancelled = true;
      };
    }
    setStatus({ loading: true, error: "" });
    Promise.resolve()
      .then(() => fetcher(key))
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
  }, [key, fetcher]);

  return { dataset, status };
}
