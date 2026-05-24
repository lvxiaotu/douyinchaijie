import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TaskStatusRow } from "./TaskStatusRow";

const errorTask = {
  id: "failed-task",
  title: "失败任务",
  status: "failed",
  progress: 100,
  updated: "18:30",
  message: "任务失败",
};

const runningTask = {
  id: "running-task",
  title: "卡住任务",
  status: "running",
  progress: 42,
  updated: "18:31",
  message: "任务进行中",
};

const pendingTask = {
  id: "pending-task",
  title: "等待任务",
  status: "pending",
  progress: 0,
  updated: "18:32",
  message: "等待执行",
};

function renderRow(props = {}) {
  return render(
    <TaskStatusRow
      title="AI 视频拆解"
      desc="任务行"
      groups={{ running: [], done: [], error: [errorTask] }}
      activeStatus="error"
      onChangeStatus={() => {}}
      onOpenTask={() => {}}
      {...props}
    />,
  );
}

describe("TaskStatusRow retry action", () => {
  it("restarts tasks from the running list", () => {
    const onRestartTask = vi.fn();
    renderRow({
      groups: { running: [runningTask], done: [], error: [] },
      activeStatus: "running",
      onRestartTask,
    });

    fireEvent.click(screen.getByRole("button", { name: /AI 视频拆解/ }));
    fireEvent.click(screen.getByRole("button", { name: "重新开始任务 卡住任务" }));

    expect(onRestartTask).toHaveBeenCalledWith(runningTask);
  });

  it("restarts tasks from the pending list", () => {
    const onRestartTask = vi.fn();
    renderRow({
      groups: { pending: [pendingTask], running: [], done: [], error: [] },
      activeStatus: "pending",
      onRestartTask,
    });

    fireEvent.click(screen.getByRole("button", { name: /AI 视频拆解/ }));
    fireEvent.click(screen.getByRole("button", { name: "重新开始任务 等待任务" }));

    expect(onRestartTask).toHaveBeenCalledWith(pendingTask);
  });

  it("retries tasks from the error list", () => {
    const onRetryTask = vi.fn();
    renderRow({ onRetryTask });

    fireEvent.click(screen.getByRole("button", { name: /AI 视频拆解/ }));
    fireEvent.click(screen.getByRole("button", { name: "重试任务 失败任务" }));

    expect(onRetryTask).toHaveBeenCalledWith(errorTask);
  });

  it("hides retry when no retry handler is available", () => {
    renderRow();

    fireEvent.click(screen.getByRole("button", { name: /AI 视频拆解/ }));

    expect(screen.queryByRole("button", { name: "重试任务 失败任务" })).toBeNull();
  });
});
