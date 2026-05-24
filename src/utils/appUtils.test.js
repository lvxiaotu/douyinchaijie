import { describe, expect, it } from "vitest";
import { groupTasksByStatus, normalizeAnalysisTask, videoTitle } from "./appUtils";

describe("analysis task titles", () => {
  it("uses a stable fallback for blank video title fields", () => {
    expect(videoTitle({ desc: "  ", title: "", aweme_id: "aweme-fallback" })).toBe("aweme-fallback");
    expect(videoTitle({ desc: "  ", title: " " })).toBe("未命名视频");
  });

  it("normalizes a blank task title to the compact video fallback", () => {
    const task = normalizeAnalysisTask({
      id: "task-title-fallback",
      title: " ",
      status: "done",
      progress: 100,
      updated_at: 1779439800,
      payload: { video: { aweme_id: "aweme-from-task" } },
      result: {},
    });

    expect(task.title).toBe("aweme-from-task");
  });
});

describe("task status groups", () => {
  it("splits pending and running tasks", () => {
    const groups = groupTasksByStatus([
      { id: "pending", status: "pending" },
      { id: "queued", status: "queued" },
      { id: "running", status: "running" },
      { id: "claimed", status: "claimed" },
    ]);

    expect(groups.pending.map((task) => task.id)).toEqual(["pending", "queued"]);
    expect(groups.running.map((task) => task.id)).toEqual(["running", "claimed"]);
  });

  it("classifies comment collection failures as error tasks", () => {
    const groups = groupTasksByStatus([
      {
        id: "comment-failed",
        status: "done",
        commentCollection: { status: "failed", error: "comment api failed" },
      },
    ]);

    expect(groups.done).toEqual([]);
    expect(groups.error.map((task) => task.id)).toEqual(["comment-failed"]);
  });
});
