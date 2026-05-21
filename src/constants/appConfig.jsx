import { Archive, Boxes, Clapperboard, Database, Home, Layers3, ListChecks, Music2, Scissors, Settings, Wrench } from "lucide-react";

export const API_BASE = import.meta.env.VITE_API_BASE || "";

export const UI_VERSION = "v0.1.0";

export const THEME_STORAGE_KEY = "douyin-ops-theme";

export const sections = {
  dashboard: ["抖音工作台", "采集解析、对标账号和 AI 拆解入口统一放在同一块控制台，评论数据作为 AI 拆解步骤自动获取。"],
  taskCenter: ["任务中心", "集中查看 AI 视频拆解、提示词反推、制作反推和一句话转素材任务。"],
  draftInspector: ["查看草稿", "按项目查看剪映草稿与时间线结构，保持和主工作流一致的控制台体验。"],
  jianyingEditor: ["剪映 Skill", "围绕 AI 剧本、第三方素材补齐和剪映草稿生成的主工作流。"],
  tools: ["工具中心", "保留现有工具入口，用统一的前端壳子承接后续新增能力。"],
  runningHubTts: ["RunningHub TTS", "单独承载 RunningHub index-tts 链路，作为顶级工具并入主控制台。"],
  textToAssets: ["一句话转素材", "输入一句抽象方案，让 AI 自动拆成 A-Roll、B-Roll、音频和旁白素材清单。"],
  library: ["素材归档", "集中查看 AI 视频拆解、提示词反推与示例素材的沉淀结果。"],
  integrations: ["开源接入", "为 GitHub 项目、脚本和外部服务预留前端接入位。"],
  settings: ["配置中心", "集中管理路径、接口地址、模型与运行策略。"],
};

export const navItems = [
  ["dashboard", Home, "抖音工作台"],
  ["taskCenter", ListChecks, "任务中心"],
  ["draftInspector", Database, "查看草稿"],
  ["jianyingEditor", Scissors, "剪映 Skill"],
  ["tools", Wrench, "工具中心"],
  ["runningHubTts", Music2, "RunningHub TTS"],
  ["textToAssets", Clapperboard, "一句话转素材"],
  ["aiVideoQueue", Layers3, "AI 视频队列"],
  ["library", Archive, "素材归档"],
  ["integrations", Boxes, "开源接入"],
  ["settings", Settings, "配置中心"],
];

export const settingItems = [
  ["ai-provider", "AI 模型"],
  ["douyin", "抖音采集"],
  ["ai-video", "AI 视频拆解"],
  ["ai-prompt", "反推提示词"],
  ["ai-production", "制作反推"],
  ["jianying", "剪映草稿"],
];

export const jianyingEditorItems = [
  ["script", "剧本生成"],
  ["reference", "开发者参考"],
];

export const statusText = {
  ready: "可用",
  partial_ready: "部分补齐",
  script_ready: "剧本就绪",
  waiting_assets: "待补齐",
  waiting_audio: "待补音频",
  waiting_visual: "待补画面",
  draft: "草稿",
  pending: "等待",
  queued: "排队中",
  running: "运行中",
  done: "完成",
  paused: "暂停",
  error: "失败",
  failed: "失败",
  failed_final: "失败",
  retry_waiting: "重试等待",
  stale_requeued: "重排队",
  claimed: "已认领",
};

export const runningHubEmotionFields = [
  ["happy", "快乐"],
  ["angry", "愤怒"],
  ["sad", "悲伤"],
  ["fear", "恐惧"],
  ["hate", "厌恶"],
  ["love", "低沉"],
  ["surprise", "惊讶"],
  ["neutral", "中立"],
];

export const taskBoardStatuses = [
  ["running", "进行中"],
  ["done", "已完成"],
  ["error", "异常"],
];
