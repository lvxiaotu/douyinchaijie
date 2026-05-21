import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAsyncResource } from "./useAsyncResource";

describe("useAsyncResource", () => {
  it("loads data and clears loading state", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useAsyncResource("task-1", fetcher));

    expect(result.current.status.loading).toBe(true);
    await waitFor(() => expect(result.current.status.loading).toBe(false));
    expect(result.current.dataset).toEqual({ ok: true });
    expect(result.current.status.error).toBe("");
    expect(fetcher).toHaveBeenCalledWith("task-1");
  });

  it("captures failures as error text", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useAsyncResource("task-2", fetcher));

    await waitFor(() => expect(result.current.status.loading).toBe(false));
    expect(result.current.dataset).toBeNull();
    expect(result.current.status.error).toBe("boom");
  });

  it("does not fetch without a key", async () => {
    const fetcher = vi.fn();

    const { result } = renderHook(() => useAsyncResource("", fetcher));

    await waitFor(() => expect(result.current.status.loading).toBe(false));
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.dataset).toBeNull();
  });
});
