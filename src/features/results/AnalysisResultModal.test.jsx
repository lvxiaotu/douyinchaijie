import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalysisResultModal } from "./AnalysisResultModal";

vi.mock("./useAiVideoEvidence", () => ({
  useAiVideoEvidence: () => ({
    dataset: null,
    status: { loading: false, error: "" },
  }),
}));

vi.mock("./useDouyinInteractions", () => ({
  useDouyinInteractions: () => ({
    dataset: null,
    status: { loading: false, error: "" },
  }),
}));

const commentTask = {
  id: "analysis-comments-layout",
  title: "评论洞察布局验证",
  result: {
    genre: "knowledge",
    summary: "用评论数据验证结果页评论区布局。",
    douyin_target: {
      interaction_snapshot: {
        keyword_counts: { 接: 114, 好运: 9 },
        emotion_profile: {
          motivation_buckets: {
            doubt_or_controversy: 2,
            purchase_or_link: 1,
          },
        },
        pinned_comments: [{ id: "pinned", text: "置顶评论" }],
        author_replies: [{ id: "author", text: "作者留人话术" }],
        top_comments: [
          { id: "top-1", nickname: "评论 1", text: "第一条评论", digg_count: 1493, reply_count: 93 },
          { id: "top-2", nickname: "评论 2", text: "第二条评论", digg_count: 802, reply_count: 11 },
          { id: "top-3", nickname: "评论 3", text: "第三条评论", digg_count: 566, reply_count: 3 },
        ],
      },
    },
    model_runs: [
      {
        id: "run-1",
        provider: "mock",
        model: "mock-model",
        status: "done",
        purpose: "analysis",
      },
    ],
  },
};

describe("AnalysisResultModal comment workspace", () => {
  it("keeps the user result focused on comments", () => {
    const { container } = render(<AnalysisResultModal task={commentTask} pageMode onClose={() => {}} />);

    expect(screen.getByText("评论区洞察")).toBeTruthy();
    expect(screen.getByText("第一条评论")).toBeTruthy();
    expect(screen.getByText("第三条评论")).toBeTruthy();
    expect(screen.queryByText("证据概览")).toBeNull();
    expect(screen.queryByText("模型运行轨迹")).toBeNull();
    expect(container.querySelectorAll(".content-lab-top-comments article")).toHaveLength(3);
  });
});
