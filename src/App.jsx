import React, { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { archiveTask, createAiProductionReverseJob, createAiPromptReverseJob, createAiVideoBreakdownJob, deleteTask, fetchAiProductionReverseArchives, fetchAiPromptReverseArchives, fetchAiVideoArchives, fetchTasks, fetchWorkbench } from "./services/api";
import { fallbackWorkbench } from "./workbenchSeed";
import { Database, FolderCog, Languages, MoonStar, RefreshCw, SunMedium } from "lucide-react";
import { Badge, ToolCard } from "./components/common/index";
import { THEME_STORAGE_KEY, UI_VERSION, jianyingEditorItems, navItems, sections, settingItems } from "./constants/appConfig";
import { DouyinCollectorPanel } from "./features/douyin";
import { DouyinTargetPanel } from "./features/douyinTarget";
import { DraftInspectorPanel, JianyingEditorSdkPanel, JianyingNaturalScriptPanel } from "./features/jianying";
import { LibraryArchiveGroup, LibraryItemModal } from "./features/library/LibraryPanels";
import { AnalysisResultModal, ProductionReverseResultModal, PromptReverseResultModal } from "./features/results";
import { RunningHubTtsPanel } from "./features/runningHub/RunningHubTtsPanel";
import { AiProductionReverseSettingsPanel, AiPromptReverseSettingsPanel, AiProviderSettingsPanel, AiVideoSettingsPanel, DouyinSettingsPanel, JianyingDraftSettingsPanel } from "./features/settings";
import { TaskRecordModal, TaskStatusRow } from "./features/tasks";
import { TextToAssetsPanel, TextToAssetsResultModal } from "./features/textToAssets";
import { archiveIdSet, archivePresentation, groupTasksByStatus, normalizeAnalysisTask, normalizeCommercialAnalysisResult, normalizeProductionReverseTask, normalizePromptReverseTask, normalizeTextToAssetsTask, preferredTaskStatus } from "./utils/appUtils";

export function App() {
  const [activeSection, setActiveSection] = useState("dashboard");
  const [activeSetting, setActiveSetting] = useState("ai-provider");
  const [activeJianyingEditor, setActiveJianyingEditor] = useState("script");
  const [activeToolId, setActiveToolId] = useState("");
  const [activeAnalysisStatus, setActiveAnalysisStatus] = useState("running");
  const [activePromptStatus, setActivePromptStatus] = useState("running");
  const [activeProductionStatus, setActiveProductionStatus] = useState("running");
  const [activeTextToAssetsStatus, setActiveTextToAssetsStatus] = useState("running");
  const [selectedTaskRecord, setSelectedTaskRecord] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [workbench, setWorkbench] = useState(fallbackWorkbench);
  const [analysisTasks, setAnalysisTasks] = useState([]);
  const [promptReverseTasks, setPromptReverseTasks] = useState([]);
  const [productionReverseTasks, setProductionReverseTasks] = useState([]);
  const [textToAssetsTasks, setTextToAssetsTasks] = useState([]);
  const [analysisArchives, setAnalysisArchives] = useState([]);
  const [promptReverseArchives, setPromptReverseArchives] = useState([]);
  const [productionReverseArchives, setProductionReverseArchives] = useState([]);
  const [libraryType, setLibraryType] = useState("all");
  const [selectedAnalysisTask, setSelectedAnalysisTask] = useState(null);
  const [selectedPromptReverseTask, setSelectedPromptReverseTask] = useState(null);
  const [selectedProductionReverseTask, setSelectedProductionReverseTask] = useState(null);
  const [selectedTextToAssetsTask, setSelectedTextToAssetsTask] = useState(null);
  const [selectedLibraryItem, setSelectedLibraryItem] = useState(null);
  const [taskSyncError, setTaskSyncError] = useState("");
  const [lastTaskRefresh, setLastTaskRefresh] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [uiTheme, setUiTheme] = useState(() => {
    if (typeof window === "undefined") return "light";
    return window.localStorage.getItem(THEME_STORAGE_KEY) || "light";
  });

  async function refreshAnalysisTaskList() {
    const tasks = await fetchTasks("ai_video_analysis");
    setAnalysisTasks(tasks.map((task) => normalizeAnalysisTask(task)));
    setTaskSyncError("");
    setLastTaskRefresh(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }

  async function refreshPromptReverseTaskList() {
    const tasks = await fetchTasks("ai_prompt_reverse");
    setPromptReverseTasks(tasks.map(normalizePromptReverseTask));
    setTaskSyncError("");
    setLastTaskRefresh(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }

  async function refreshProductionReverseTaskList() {
    const tasks = await fetchTasks("ai_production_reverse");
    setProductionReverseTasks(tasks.map(normalizeProductionReverseTask));
    setTaskSyncError("");
    setLastTaskRefresh(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }

  async function refreshTextToAssetsTaskList() {
    const tasks = await fetchTasks("text_to_assets");
    setTextToAssetsTasks(tasks.map(normalizeTextToAssetsTask));
    setTaskSyncError("");
    setLastTaskRefresh(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }

  useEffect(() => {
    fetchWorkbench()
      .then((data) => {
        setWorkbench(data);
      });
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "emerald");
    document.documentElement.setAttribute("data-ui-mode", uiTheme);
    window.localStorage.setItem(THEME_STORAGE_KEY, uiTheme);
  }, [uiTheme]);

  useEffect(() => {
    async function loadArchives() {
      try {
        const [analysis, promptReverse, productionReverse] = await Promise.all([
          fetchAiVideoArchives(),
          fetchAiPromptReverseArchives(),
          fetchAiProductionReverseArchives(),
        ]);
        setAnalysisArchives(analysis);
        setPromptReverseArchives(promptReverse);
        setProductionReverseArchives(productionReverse);
      } catch {
        // Archive panels can stay empty if backend is still starting.
      }
    }

    loadArchives();
  }, [analysisTasks, promptReverseTasks, productionReverseTasks]);

  useEffect(() => {
    let mounted = true;

    async function loadPromptReverseTasks() {
      try {
        if (mounted) {
          await refreshPromptReverseTaskList();
        }
      } catch (err) {
        if (mounted) {
          setTaskSyncError(`提示词反推任务刷新失败：${err.message}`);
        }
      }
    }

    loadPromptReverseTasks();
    const timer = window.setInterval(loadPromptReverseTasks, 2500);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadProductionReverseTasks() {
      try {
        if (mounted) {
          await refreshProductionReverseTaskList();
        }
      } catch (err) {
        if (mounted) {
          setTaskSyncError(`制作方式反推任务刷新失败：${err.message}`);
        }
      }
    }

    loadProductionReverseTasks();
    const timer = window.setInterval(loadProductionReverseTasks, 2500);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadTextToAssetsTasks() {
      try {
        if (mounted) {
          await refreshTextToAssetsTaskList();
        }
      } catch (err) {
        if (mounted) {
          setTaskSyncError(`一句话转素材任务刷新失败：${err.message}`);
        }
      }
    }

    loadTextToAssetsTasks();
    const timer = window.setInterval(loadTextToAssetsTasks, 3000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadAnalysisTasks() {
      try {
        if (mounted) {
          await refreshAnalysisTaskList();
        }
      } catch (err) {
        if (mounted) {
          setTaskSyncError(`AI 视频拆解任务刷新失败：${err.message}`);
        }
      }
    }

    loadAnalysisTasks();
    const timer = window.setInterval(loadAnalysisTasks, 2500);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  async function handleCreateVideoBreakdown(video) {
    const task = await createAiVideoBreakdownJob(video);
    const normalized = normalizeAnalysisTask(task);
    setAnalysisTasks((current) => [normalized, ...current.filter((item) => item.id !== normalized.id)]);
    window.setTimeout(() => refreshAnalysisTaskList().catch((err) => setTaskSyncError(`AI 视频拆解任务刷新失败：${err.message}`)), 800);
    window.setTimeout(() => refreshAnalysisTaskList().catch((err) => setTaskSyncError(`AI 视频拆解任务刷新失败：${err.message}`)), 3000);
    return { job_id: normalized.id, status: normalized.status, result: normalized.result };
  }

  async function handleCreatePromptReverse(video) {
    const task = await createAiPromptReverseJob(video);
    const normalized = normalizePromptReverseTask(task);
    setPromptReverseTasks((current) => [normalized, ...current.filter((item) => item.id !== normalized.id)]);
    window.setTimeout(() => refreshPromptReverseTaskList().catch((err) => setTaskSyncError(`提示词反推任务刷新失败：${err.message}`)), 800);
    window.setTimeout(() => refreshPromptReverseTaskList().catch((err) => setTaskSyncError(`提示词反推任务刷新失败：${err.message}`)), 3000);
    return { job_id: normalized.id, status: normalized.status, result: normalized.result };
  }

  async function handleCreateProductionReverse(video) {
    const task = await createAiProductionReverseJob(video);
    const normalized = normalizeProductionReverseTask(task);
    setProductionReverseTasks((current) => [normalized, ...current.filter((item) => item.id !== normalized.id)]);
    window.setTimeout(() => refreshProductionReverseTaskList().catch((err) => setTaskSyncError(`制作方式反推任务刷新失败：${err.message}`)), 800);
    window.setTimeout(() => refreshProductionReverseTaskList().catch((err) => setTaskSyncError(`制作方式反推任务刷新失败：${err.message}`)), 3000);
    return { job_id: normalized.id, status: normalized.status, result: normalized.result };
  }

  async function handleArchiveAnalysisTask(task) {
    const response = await archiveTask(task.id);
    if (response.archive) {
      setAnalysisArchives((current) => [response.archive, ...current.filter((item) => (item.task_id || item.id) !== task.id)]);
    }
  }

  async function handleArchivePromptReverseTask(task) {
    const response = await archiveTask(task.id);
    if (response.archive) {
      setPromptReverseArchives((current) => [response.archive, ...current.filter((item) => (item.task_id || item.id) !== task.id)]);
    }
  }

  async function handleArchiveProductionReverseTask(task) {
    const response = await archiveTask(task.id);
    if (response.archive) {
      setProductionReverseArchives((current) => [response.archive, ...current.filter((item) => (item.task_id || item.id) !== task.id)]);
    }
  }

  async function handleDeleteTextToAssetsTask(task) {
    if (!window.confirm("确认删除这个任务吗？")) {
      return;
    }
    await deleteTask(task.id, false);
    setTextToAssetsTasks((current) => current.filter((item) => item.id !== task.id));
    setSelectedTextToAssetsTask((current) => (current?.id === task.id ? null : current));
  }

  async function handleDeleteAnalysisTask(task) {
    if (!window.confirm("确认删除这个任务及关联归档吗？")) {
      return;
    }
    await deleteTask(task.id);
    setAnalysisTasks((current) => current.filter((item) => item.id !== task.id));
    setAnalysisArchives((current) => current.filter((item) => item.task_id !== task.id && item.id !== task.id));
  }

  async function handleDeletePromptReverseTask(task) {
    if (!window.confirm("确认删除这个任务及关联归档吗？")) {
      return;
    }
    await deleteTask(task.id);
    setPromptReverseTasks((current) => current.filter((item) => item.id !== task.id));
    setPromptReverseArchives((current) => current.filter((item) => item.task_id !== task.id && item.id !== task.id));
  }

  async function handleDeleteProductionReverseTask(task) {
    if (!window.confirm("确认删除这个任务及关联归档吗？")) {
      return;
    }
    await deleteTask(task.id);
    setProductionReverseTasks((current) => current.filter((item) => item.id !== task.id));
    setProductionReverseArchives((current) => current.filter((item) => item.task_id !== task.id && item.id !== task.id));
  }

  async function handleGlobalRefresh() {
    setRefreshing(true);
    const [analysisResult, promptResult, productionResult, textToAssetsResult, workbenchResult, analysisArchiveResult, promptArchiveResult, productionArchiveResult] = await Promise.allSettled([
      refreshAnalysisTaskList(),
      refreshPromptReverseTaskList(),
      refreshProductionReverseTaskList(),
      refreshTextToAssetsTaskList(),
      fetchWorkbench(),
      fetchAiVideoArchives(),
      fetchAiPromptReverseArchives(),
      fetchAiProductionReverseArchives(),
    ]);

    if (workbenchResult.status === "fulfilled") {
      setWorkbench(workbenchResult.value);
    }

    if (analysisArchiveResult.status === "fulfilled") {
      setAnalysisArchives(analysisArchiveResult.value);
    }
    if (promptArchiveResult.status === "fulfilled") {
      setPromptReverseArchives(promptArchiveResult.value);
    }
    if (productionArchiveResult.status === "fulfilled") {
      setProductionReverseArchives(productionArchiveResult.value);
    }

    const errors = [];
    if (analysisResult.status === "rejected") {
      errors.push(`AI 视频拆解任务刷新失败：${analysisResult.reason?.message || analysisResult.reason}`);
    }
    if (promptResult.status === "rejected") {
      errors.push(`提示词反推任务刷新失败：${promptResult.reason?.message || promptResult.reason}`);
    }
    if (productionResult.status === "rejected") {
      errors.push(`制作方式反推任务刷新失败：${productionResult.reason?.message || productionResult.reason}`);
    }
    if (textToAssetsResult.status === "rejected") {
      errors.push(`一句话转素材任务刷新失败：${textToAssetsResult.reason?.message || textToAssetsResult.reason}`);
    }
    setTaskSyncError(errors.join("；"));
    setRefreshing(false);
  }

  function openSection(sectionId) {
    startTransition(() => {
      setActiveSection(sectionId);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function toggleTheme() {
    setUiTheme((current) => (current === "light" ? "dark" : "light"));
  }

  const tools = workbench.tools?.length ? workbench.tools : fallbackWorkbench.tools;
  const library = workbench.library?.length ? workbench.library : fallbackWorkbench.library;
  const integrations = workbench.integrations?.length
    ? workbench.integrations
    : fallbackWorkbench.integrations;
  const deferredQuery = useDeferredValue(query);

  const filteredTools = useMemo(() => {
    const normalized = deferredQuery.trim().toLowerCase();
    return tools.filter((tool) => {
      if (tool.id === "jianying-editor-sdk") return false;
      const filterMatched = filter === "all" || tool.status === filter;
      const text = [tool.name, tool.desc, tool.status, ...tool.tags].join(" ").toLowerCase();
      return filterMatched && (!normalized || text.includes(normalized));
    });
  }, [deferredQuery, filter, tools]);

  const filteredLibrary = useMemo(() => {
    const normalized = deferredQuery.trim().toLowerCase();
    if (!normalized) return library;
    return library.filter((item) =>
      [item.title, item.desc, item.type, ...item.tags].join(" ").toLowerCase().includes(normalized),
    );
  }, [deferredQuery, library]);

  const archiveItems = useMemo(() => {
    const analysisItems = analysisArchives.map((item) => {
      const result = normalizeCommercialAnalysisResult(item.result || {});
      return {
        ...item,
        result,
        archiveType: "analysis",
        type: "AI 视频拆解",
        desc: result.summary || "商业拆解档案",
      };
    });
    const promptItems = promptReverseArchives.map((item) => ({
      ...item,
      archiveType: "prompt",
      type: "AI 提示词反推",
      desc: item.result?.summary || item.result?.master_prompt || "提示词反推档案",
    }));
    const productionItems = productionReverseArchives.map((item) => ({
      ...item,
      archiveType: "production",
      type: "AI 制作方式反推",
      desc: item.result?.summary || item.result?.production_overview?.main_workflow || "制作方式反推档案",
    }));
    const combined = [...analysisItems, ...promptItems, ...productionItems];
    if (libraryType === "analysis") return analysisItems;
    if (libraryType === "prompt") return promptItems;
    if (libraryType === "production") return productionItems;
    return combined;
  }, [analysisArchives, promptReverseArchives, productionReverseArchives, libraryType]);

  const archivedAnalysisIds = useMemo(() => archiveIdSet(analysisArchives), [analysisArchives]);
  const archivedPromptReverseIds = useMemo(() => archiveIdSet(promptReverseArchives), [promptReverseArchives]);
  const archivedProductionReverseIds = useMemo(() => archiveIdSet(productionReverseArchives), [productionReverseArchives]);
  const visibleLibraryItems = useMemo(() => {
    const items = libraryType === "seed" ? filteredLibrary : archiveItems;
    const normalized = deferredQuery.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) => {
      const presentation = archivePresentation(item);
      const text = [
        presentation.toolLabel,
        presentation.toolDetail,
        presentation.headline,
        presentation.summary,
        ...(presentation.tags || []),
      ].join(" ").toLowerCase();
      return text.includes(normalized);
    });
  }, [archiveItems, deferredQuery, filteredLibrary, libraryType]);

  const libraryGroups = useMemo(() => {
    if (libraryType === "seed") {
      return [
        {
          key: "seed",
          title: "示例素材",
          desc: "系统内置的参考素材和占位内容。",
          items: visibleLibraryItems,
        },
      ];
    }
    return [
      {
        key: "analysis",
        title: "AI 视频拆解",
        desc: "手动归档的视频商业拆解结果，适合复盘钩子、场景和转化逻辑。",
        items: visibleLibraryItems.filter((item) => item.archiveType === "analysis"),
      },
      {
        key: "prompt",
        title: "AI 提示词反推",
        desc: "手动归档的生成提示词反推结果，适合二次创作和模型复用。",
        items: visibleLibraryItems.filter((item) => item.archiveType === "prompt"),
      },
      {
        key: "production",
        title: "AI 制作方式反推",
        desc: "手动归档的视频制作方式反推结果，适合复做素材、包装和剪辑流程。",
        items: visibleLibraryItems.filter((item) => item.archiveType === "production"),
      },
    ].filter((group) => libraryType === "all" || group.key === libraryType);
  }, [libraryType, visibleLibraryItems]);

  const analysisTaskGroups = useMemo(() => groupTasksByStatus(analysisTasks), [analysisTasks]);
  const promptReverseTaskGroups = useMemo(() => groupTasksByStatus(promptReverseTasks), [promptReverseTasks]);
  const productionReverseTaskGroups = useMemo(() => groupTasksByStatus(productionReverseTasks), [productionReverseTasks]);
  const textToAssetsTaskGroups = useMemo(() => groupTasksByStatus(textToAssetsTasks), [textToAssetsTasks]);

  useEffect(() => {
    const nextStatus = preferredTaskStatus(analysisTaskGroups, activeAnalysisStatus);
    if (nextStatus !== activeAnalysisStatus) {
      setActiveAnalysisStatus(nextStatus);
    }
  }, [analysisTaskGroups, activeAnalysisStatus]);

  useEffect(() => {
    const nextStatus = preferredTaskStatus(promptReverseTaskGroups, activePromptStatus);
    if (nextStatus !== activePromptStatus) {
      setActivePromptStatus(nextStatus);
    }
  }, [promptReverseTaskGroups, activePromptStatus]);

  useEffect(() => {
    const nextStatus = preferredTaskStatus(productionReverseTaskGroups, activeProductionStatus);
    if (nextStatus !== activeProductionStatus) {
      setActiveProductionStatus(nextStatus);
    }
  }, [productionReverseTaskGroups, activeProductionStatus]);

  useEffect(() => {
    const nextStatus = preferredTaskStatus(textToAssetsTaskGroups, activeTextToAssetsStatus);
    if (nextStatus !== activeTextToAssetsStatus) {
      setActiveTextToAssetsStatus(nextStatus);
    }
  }, [textToAssetsTaskGroups, activeTextToAssetsStatus]);

  const [title] = sections[activeSection];

  useEffect(() => {
    document.title = `${title} | 抖音解析`;
  }, [title]);

  const subnavItems =
    activeSection === "settings"
      ? settingItems.map(([value, text]) => ({
          value,
          text,
          active: activeSetting === value,
          onClick: () =>
            startTransition(() => {
              setActiveSetting(value);
            }),
        }))
      : activeSection === "jianyingEditor"
        ? jianyingEditorItems.map(([value, text]) => ({
            value,
            text,
            active: activeJianyingEditor === value,
            onClick: () =>
              startTransition(() => {
                setActiveJianyingEditor(value);
              }),
          }))
        : [];

  let sectionContent = null;

  if (activeSection === "dashboard") {
    sectionContent = (
      <section className="dashboard-stack">
        <DouyinCollectorPanel
          onBreakdown={handleCreateVideoBreakdown}
          onPromptReverse={handleCreatePromptReverse}
          onProductionReverse={handleCreateProductionReverse}
        />
        <section className="panel task-board-panel">
          <div className="panel-header">
            <div>
              <h2>任务中心</h2>
              <p>任务按工具分行排列，点击状态切换列表，点击任务查看详情。</p>
            </div>
            <Badge status={taskSyncError ? "error" : "running"}>
              {taskSyncError || `自动刷新中${lastTaskRefresh ? ` · ${lastTaskRefresh}` : ""}`}
            </Badge>
          </div>
          <div className="task-board-rows">
            <TaskStatusRow
              title="AI 视频拆解"
              desc="展示 AI 视频拆解的进行中、已完成和异常任务。"
              groups={analysisTaskGroups}
              activeStatus={activeAnalysisStatus}
              onChangeStatus={setActiveAnalysisStatus}
              onOpenTask={(task) => setSelectedTaskRecord({ type: "analysis", title: "AI 视频拆解", task })}
            />
            <TaskStatusRow
              title="AI 提示词反推"
              desc="展示提示词反推的进行中、已完成和异常任务。"
              groups={promptReverseTaskGroups}
              activeStatus={activePromptStatus}
              onChangeStatus={setActivePromptStatus}
              onOpenTask={(task) => setSelectedTaskRecord({ type: "prompt", title: "AI 提示词反推", task })}
            />
            <TaskStatusRow
              title="AI 制作方式反推"
              desc="展示制作方式反推的进行中、已完成和异常任务。"
              groups={productionReverseTaskGroups}
              activeStatus={activeProductionStatus}
              onChangeStatus={setActiveProductionStatus}
              onOpenTask={(task) => setSelectedTaskRecord({ type: "production", title: "AI 制作方式反推", task })}
            />
            <TaskStatusRow
              title="一句话转素材"
              desc="展示 Text-to-Assets 的进行中、已完成和异常任务。"
              groups={textToAssetsTaskGroups}
              activeStatus={activeTextToAssetsStatus}
              onChangeStatus={setActiveTextToAssetsStatus}
              onOpenTask={(task) => setSelectedTaskRecord({ type: "text_to_assets", title: "一句话转素材", task })}
            />
          </div>
        </section>
      </section>
    );
  } else if (activeSection === "douyinTarget") {
    sectionContent = (
      <section>
        <DouyinTargetPanel />
      </section>
    );
  } else if (activeSection === "tools") {
    sectionContent = (
      <section>
        {activeToolId === "jianying-editor-sdk" ? (
          <>
            <div className="section-toolbar">
              <button className="text-button" type="button" onClick={() => setActiveToolId("")}>
                返回工具列表
              </button>
            </div>
            <JianyingEditorSdkPanel />
          </>
        ) : (
          <>
            <div className="section-toolbar">
              <div className="segmented">
                {[
                  ["all", "全部"],
                  ["ready", "可用"],
                  ["draft", "草稿"],
                ].map(([id, label]) => (
                  <button
                    className={filter === id ? "active" : ""}
                    key={id}
                    type="button"
                    onClick={() => setFilter(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <Badge status="ready">{filteredTools.length} 个工具</Badge>
            </div>
            <div className="tool-grid">
              {filteredTools.map((tool) => (
                <ToolCard key={tool.id} tool={tool} onOpen={(item) => setActiveToolId(item.id)} />
              ))}
            </div>
          </>
        )}
      </section>
    );
  } else if (activeSection === "runningHubTts") {
    sectionContent = (
      <section>
        <RunningHubTtsPanel />
      </section>
    );
  } else if (activeSection === "textToAssets") {
    sectionContent = (
      <section>
        <TextToAssetsPanel />
      </section>
    );
  } else if (activeSection === "jianyingEditor") {
    sectionContent = (
      <section>
        {activeJianyingEditor === "script" ? (
          <JianyingNaturalScriptPanel />
        ) : (
          <JianyingEditorSdkPanel activeView={activeJianyingEditor} />
        )}
      </section>
    );
  } else if (activeSection === "draftInspector") {
    sectionContent = (
      <section>
        <DraftInspectorPanel />
      </section>
    );
  } else if (activeSection === "library") {
    sectionContent = (
      <section className="library-layout">
        <aside className="filter-panel">
          <div className="filter-panel-head">
            <div>
              <h2>筛选</h2>
              <p>点击下方条目查看完整内容。</p>
            </div>
            <Badge>{visibleLibraryItems.length} 条结果</Badge>
          </div>
          <label>
            类型
            <select value={libraryType} onChange={(event) => setLibraryType(event.target.value)}>
              <option value="all">AI 归档全部</option>
              <option value="analysis">AI 拆解</option>
              <option value="prompt">反推提示词</option>
              <option value="production">制作方式反推</option>
              <option value="seed">示例素材</option>
            </select>
          </label>
          <div className="filter-panel-note">
            <strong>搜索已生效</strong>
            <p>顶部搜索会同步过滤归档与工具面板。</p>
          </div>
        </aside>
        <div className="library-list">
          {libraryGroups.map((group) => (
            <LibraryArchiveGroup key={group.key} title={group.title} desc={group.desc} items={group.items}>
              {group.items.map((item) => {
                const presentation = archivePresentation(item);
                return (
                  <article
                    className={`library-card ${item.archiveType ? "archive-library-card" : ""}`}
                    key={item.id}
                    onClick={() => {
                      if (item.archiveType === "analysis") {
                        setSelectedAnalysisTask({
                          id: item.task_id,
                          title: item.title,
                          result: item.result,
                        });
                      }
                      if (item.archiveType === "prompt") {
                        setSelectedPromptReverseTask({
                          id: item.task_id,
                          title: item.title,
                          result: item.result,
                        });
                      }
                      if (item.archiveType === "production") {
                        setSelectedProductionReverseTask({
                          id: item.task_id,
                          title: item.title,
                          result: item.result,
                        });
                      }
                      if (!item.archiveType) {
                        setSelectedLibraryItem({
                          ...item,
                          presentation,
                          raw: item,
                        });
                      }
                    }}
                  >
                    <div className="archive-thumb">
                      <span>{presentation.toolLabel}</span>
                      <strong>{item.archiveType === "analysis" ? "拆解" : item.archiveType === "prompt" ? "提示词" : "素材"}</strong>
                    </div>
                    <div className="archive-card-body">
                      <div className="archive-card-head">
                        <span>{presentation.toolDetail}</span>
                        <h3>{presentation.headline}</h3>
                      </div>
                      <p>{presentation.summary}</p>
                      {presentation.highlights.length > 0 && (
                        <div className="archive-highlight-grid">
                          {presentation.highlights.slice(0, 3).map(([label, value]) => (
                            <div className="archive-highlight" key={label}>
                              <span>{label}</span>
                              <p>{value}</p>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="library-meta">
                        {presentation.tags.map((tag) => (
                          <Badge key={tag}>{tag}</Badge>
                        ))}
                      </div>
                    </div>
                  </article>
                );
              })}
            </LibraryArchiveGroup>
          ))}
          {!visibleLibraryItems.length && <div className="empty-result">暂无归档内容。在任务中心点击“归档”后会出现在这里。</div>}
        </div>
      </section>
    );
  } else if (activeSection === "integrations") {
    sectionContent = (
      <section className="integration-grid">
        {integrations.map((integration) => (
          <article className="panel integration-card" key={integration.id}>
            <div className="integration-icon">
              {integration.kind === "python" ? <FolderCog size={20} /> : <Database size={20} />}
            </div>
            <div>
              <h2>{integration.name}</h2>
              <p>{integration.desc}</p>
              <div className="tool-meta">
                <Badge>{integration.kind}</Badge>
                <Badge status={integration.status}>{integration.status}</Badge>
              </div>
            </div>
          </article>
        ))}
      </section>
    );
  } else if (activeSection === "settings") {
    sectionContent = (
      <section className="settings-grid">
        {activeSetting === "ai-provider" && <AiProviderSettingsPanel />}
        {activeSetting === "douyin" && <DouyinSettingsPanel />}
        {activeSetting === "ai-video" && <AiVideoSettingsPanel />}
        {activeSetting === "ai-prompt" && <AiPromptReverseSettingsPanel />}
        {activeSetting === "ai-production" && <AiProductionReverseSettingsPanel />}
        {activeSetting === "jianying" && <JianyingDraftSettingsPanel />}
      </section>
    );
  }

  return (
    <>
      <div className="ccx-app-shell">
        <header className="app-header">
          <div className="app-header-left">
            <a className="app-logo" href="https://github.com/lvxiaotu/douyinchaijie" target="_blank" rel="noreferrer" aria-label="打开项目仓库">
              <span>抖</span>
            </a>
            <div className="header-title">
              <div className="header-nav" role="tablist" aria-label="主导航">
                {navItems.map(([id, Icon, label], index) => (
                  <React.Fragment key={id}>
                    <button
                      className={`api-type-text ${activeSection === id ? "active" : ""}`}
                      type="button"
                      onClick={() => openSection(id)}
                    >
                      <Icon size={15} />
                      <span>{label}</span>
                    </button>
                    {index < navItems.length - 1 && <span className="api-type-text separator">/</span>}
                  </React.Fragment>
                ))}
                <span className="brand-text">抖音解析</span>
              </div>
            </div>
          </div>

          <div className="app-header-right">
            <div className={`version-badge ${taskSyncError ? "version-update" : "version-latest"}`}>
              <span className="version-text">{UI_VERSION}</span>
            </div>
            <div className="header-info-chip">
              <Languages size={14} />
              <span>ZH</span>
            </div>
            <button className="header-btn" type="button" onClick={toggleTheme} title={uiTheme === "light" ? "切换到暗色模式" : "切换到亮色模式"}>
              {uiTheme === "light" ? <MoonStar size={18} /> : <SunMedium size={18} />}
            </button>
            <button className="header-btn" type="button" onClick={() => handleGlobalRefresh().catch(() => {})} title="刷新工作台">
              <RefreshCw size={18} className={refreshing ? "spin" : ""} />
            </button>
          </div>
        </header>

        <main className="shell">
          {subnavItems.length > 0 && (
            <div className="section-subnav">
              {subnavItems.map((item) => (
                <button
                  className={`section-subnav-item ${item.active ? "active" : ""}`}
                  key={item.value}
                  type="button"
                  onClick={item.onClick}
                >
                  {item.text}
                </button>
              ))}
            </div>
          )}

          <section className="content-shell">{sectionContent}</section>
        </main>
      </div>

      <TaskRecordModal
        record={selectedTaskRecord}
        archivedIds={
          selectedTaskRecord?.type === "analysis"
            ? archivedAnalysisIds
            : selectedTaskRecord?.type === "prompt"
              ? archivedPromptReverseIds
              : selectedTaskRecord?.type === "production"
                ? archivedProductionReverseIds
              : new Set()
        }
        onClose={() => setSelectedTaskRecord(null)}
        onOpenResult={(task) => {
          if (selectedTaskRecord?.type === "analysis") {
            setSelectedAnalysisTask(task);
          } else if (selectedTaskRecord?.type === "prompt") {
            setSelectedPromptReverseTask(task);
          } else if (selectedTaskRecord?.type === "production") {
            setSelectedProductionReverseTask(task);
          } else if (selectedTaskRecord?.type === "text_to_assets") {
            setSelectedTextToAssetsTask(task);
          }
        }}
        onArchiveTask={
          selectedTaskRecord?.type === "analysis"
            ? handleArchiveAnalysisTask
            : selectedTaskRecord?.type === "prompt"
              ? handleArchivePromptReverseTask
              : selectedTaskRecord?.type === "production"
                ? handleArchiveProductionReverseTask
              : null
        }
        onDeleteTask={
          selectedTaskRecord?.type === "analysis"
            ? handleDeleteAnalysisTask
            : selectedTaskRecord?.type === "prompt"
              ? handleDeletePromptReverseTask
              : selectedTaskRecord?.type === "production"
                ? handleDeleteProductionReverseTask
              : selectedTaskRecord?.type === "text_to_assets"
                ? handleDeleteTextToAssetsTask
                : null
        }
      />
      <AnalysisResultModal task={selectedAnalysisTask} onClose={() => setSelectedAnalysisTask(null)} />
      <PromptReverseResultModal task={selectedPromptReverseTask} onClose={() => setSelectedPromptReverseTask(null)} />
      <ProductionReverseResultModal task={selectedProductionReverseTask} onClose={() => setSelectedProductionReverseTask(null)} />
      <TextToAssetsResultModal task={selectedTextToAssetsTask} onClose={() => setSelectedTextToAssetsTask(null)} />
      <LibraryItemModal item={selectedLibraryItem} onClose={() => setSelectedLibraryItem(null)} />
    </>
  );
}
