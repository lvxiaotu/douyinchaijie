import { useState } from "react";
import { Badge } from "../../components/common/index";
import { downloadDouyinFavorites, fetchDouyinFavoriteItems, fetchDouyinUserProfile, fetchDouyinUserVideos, fetchDouyinWorkDetail } from "../../services/api";
import { JsonPreview } from "./DouyinMediaViews";

export function DouyinCollectorPanel({ onBreakdown, onPromptReverse, onProductionReverse }) {
  const [userUrl, setUserUrl] = useState("");
  const [workUrl, setWorkUrl] = useState("");
  const [maxItems, setMaxItems] = useState(4);
  const [pageSize, setPageSize] = useState(20);
  const [activeTask, setActiveTask] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function runTask(taskName, runner) {
    setActiveTask(taskName);
    setError("");
    setResult(null);
    try {
      const data = await runner();
      setResult(data);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setActiveTask("");
    }
  }

  return (
    <section className="panel douyin-panel">
      <div className="panel-header">
        <div>
          <h2>抖音采集</h2>
          <p>填写参数后调用 TikHub 抖音接口；Cookie 仅用于需要登录态的收藏数据。</p>
        </div>
        <Badge status="ready">TikHub</Badge>
      </div>

      <div className="collector-grid">
        <form
          className="collector-card"
          onSubmit={(event) => {
            event.preventDefault();
            runTask("user", async () => {
              const [profile, userVideos] = await Promise.all([
                fetchDouyinUserProfile(userUrl),
                fetchDouyinUserVideos({ userUrl, pageSize: 4 }),
              ]);
              return { ...profile, user_videos: userVideos };
            });
          }}
        >
          <h3>用户主页信息</h3>
          <label>
            用户主页链接
            <input
              type="url"
              placeholder="https://www.douyin.com/user/..."
              value={userUrl}
              onChange={(event) => setUserUrl(event.target.value)}
              required
            />
          </label>
          <button className="primary-button" type="submit" disabled={activeTask === "user"}>
            查询用户
          </button>
        </form>

        <form
          className="collector-card"
          onSubmit={(event) => {
            event.preventDefault();
            runTask("work", () => fetchDouyinWorkDetail(workUrl));
          }}
        >
          <h3>作品详情</h3>
          <label>
            作品链接
            <input
              type="url"
              placeholder="https://www.douyin.com/video/..."
              value={workUrl}
              onChange={(event) => setWorkUrl(event.target.value)}
              required
            />
          </label>
          <button className="primary-button" type="submit" disabled={activeTask === "work"}>
            查询作品
          </button>
        </form>

        <form
          className="collector-card"
          onSubmit={(event) => {
            event.preventDefault();
            runTask("favorites", () => downloadDouyinFavorites({ maxItems, pageSize }));
          }}
        >
          <h3>收藏视频下载</h3>
          <div className="collector-fields">
            <label>
              下载数量
              <input
                type="number"
                min="1"
                max="50"
                value={maxItems}
                onChange={(event) => setMaxItems(event.target.value)}
              />
            </label>
            <label>
              每页数量
              <input
                type="number"
                min="1"
                max="50"
                value={pageSize}
                onChange={(event) => setPageSize(event.target.value)}
              />
            </label>
          </div>
          <button className="primary-button" type="submit" disabled={activeTask === "favorites"}>
            下载收藏
          </button>
          <button
            className="text-button"
            type="button"
            disabled={activeTask === "favorite-items"}
            onClick={() => runTask("favorite-items", () => fetchDouyinFavoriteItems({ pageSize: 4 }))}
          >
            查看全部收藏数据
          </button>
        </form>
      </div>

      {activeTask && <div className="running-note">正在执行，请稍等...</div>}
      {error && <div className="error-box">{error}</div>}
      <JsonPreview value={result} onBreakdown={onBreakdown} onPromptReverse={onPromptReverse} onProductionReverse={onProductionReverse} />
    </section>
  );
}
