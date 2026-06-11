# Unified Data Model: SSE + API Seamless Integration

> 核心问题：后端 filter 引入后，SSE（全量实时推送）与 API（过滤后历史查询）的数据如何统一？
>
> 答案：利用 `_id` 的单调性，两者天然不重叠，无需拼接。唯一需要处理的是 filter 变更时 rawCache 中"由隐变显"的日志。

---

## 1. 核心洞察：`_id` 单调性消除了拼接需求

日志系统的 `_id` 是**严格单调递增**的时序标识：

```
...  99  100  101  102  103  104  105  ...
      │    │    │    │    │    │    │
      ▼    ▼    ▼    ▼    ▼    ▼    ▼
    API历史  ←────────  rawCache窗口  ────────→  SSE实时
              [cacheMinId]              [cacheMaxId]
```

| 数据源 | `_id` 范围 | 与 rawCache 的关系 |
|--------|-----------|-------------------|
| **API 历史查询** | `_id < displayMinId` | 严格在 rawCache **左侧**，不重叠 |
| **rawCache** | `[cacheMinId, cacheMaxId]` | 中间窗口 |
| **SSE 实时推送** | `_id > cacheMaxId` | 严格在 rawCache **右侧**，不重叠 |

**结论**：三个数据源在 `_id` 轴上是**三段不重叠的区间**，任何日志只会从**一个**来源进入系统，不存在"同一日志来自两个接口需要拼接"的场景。

---

## 2. 统一数据模型：rawCache + 派生 visibleCache

不要试图维护两套独立的 cache 然后做 merge。用一个**全量 rawCache**，visible 部分**动态派生**。

```javascript
// ============ 第一层：全量缓存 ============
let rawCache = [];        // 所有收到/加载的日志（上限 20k）
let rawCacheMap = new Map();  // O(1) ID 查找

// ============ 第二层：派生可见集 ============
// 不独立存储，filter 变更时从 rawCache 重建
// visibleCache = rawCache.filter(isLogVisible)

// ============ 第三层：DOM 显示窗口 ============
// DOM 中只渲染 visibleCache 的一个子集
// displayMinId / displayMaxId 标记当前 DOM 窗口边界
```

**为什么这样设计？**

| 场景 | 传统方案（单 cache + display:none） | 新方案（rawCache + 派生 visible） |
|------|-------------------------------------|----------------------------------|
| Filter 极严时 DOM 行数 | 5,000 行 DOM，4,950 行 `display:none` | 50 行 DOM，**零**隐藏节点 |
| Filter 变更 | 遍历 5,000 行 DOM 改 `display` | 从 rawCache 重建 visibleCache，重新渲染 |
| 内存占用 | 大量僵尸 DOM 节点 | rawCache 20k（内存数组）+ DOM 最多 30k 可见行 |
| 向上滚动加载 | 可能加载大量隐藏行 | 只加载可见行 |

---

## 3. 三个数据入口的统一处理路径

无论数据从哪个入口进来，都走同一条**"合并 → 过滤 → 渲染"**流水线：

```
数据到达（SSE / API / rawCache重建）
    │
    ▼
mergeToRawCache(logs)          ← 统一入口
    │  · dedup by _id
    │  · sort by _id
    │  · prune to 20k
    │
    ▼
const visible = logs.filter(isLogVisible)
    │
    ▼
if (viewMode === 'live') {
    appendVisibleToDom(visible)   ← DocumentFragment 批量插入
    trimDomIfNeeded()             ← 按模式上限修剪
}
```

### 3.1 SSE 入口

```javascript
eventSource.onmessage = (event) => {
    const logs = parse(event.data);
    // SSE 推送全量日志，先进入 rawCache
    mergeToRawCache(logs);
    // 再过滤出 visible，进入渲染流水线
    const visible = logs.filter(isLogVisible);
    if (visible.length > 0 && viewMode === 'live') {
        appendVisibleToDom(visible);
        trimDomIfNeeded();
    }
    // history 模式下 visible 只进 rawCache，不进 DOM
};
```

### 3.2 API 历史入口

```javascript
function loadMoreFilteredHistory(startId, count, filterParams) {
    return fetch(`/logger/api/logs?start_log_id=${startId}&count=${count}&${filterParams}`)
        .then(data => {
            const {logs, has_more, hint} = data;
            // API 返回的已经是后端 filter 过的日志
            // 但仍然先走统一入口（rawCache 需要全量，防止 filter 变更后数据丢失）
            mergeToRawCache(logs);
            // 由于 API 已过滤，logs 本身就是 visible，直接渲染
            prependVisibleToDom(logs);
            trimDomIfNeeded();
            return {hasMore: has_more, hint};
        });
}
```

### 3.3 Filter 变更入口（rawCache 重建）

```javascript
function onFilterChange() {
    updateFilterState();  // 更新 selectedLevels / selectedModules
    
    // 从 rawCache 重建 visibleCache，不需要任何后端请求！
    const visibleCache = rawCache.filter(isLogVisible);
    
    // 直接重新渲染 DOM
    renderTableBody(visibleCache.slice(-HISTORY_DOM_LIMIT));
    
    // 如果重建后 visible 太少，再从后端补充
    if (visibleCache.length < MIN_VISIBLE_COUNT) {
        const startId = visibleCache[0]?._id || rawCache[0]?._id;
        loadMoreFilteredHistory(startId, -currentLimit, buildFilterParams());
    }
}
```

**关键点**：filter 变更时，**不需要重启 SSE**，也不需要向后端请求"重新加载"。rawCache 中已经包含了全量数据，只需要重新 `filter()` 即可。

---

## 4. 向上滚动的智能路由

```javascript
function loadMoreLogs() {
    if (isLoading) return;
    
    // ========== 第一层：rawCache 中是否有更旧的可视日志？ ==========
    const oldestVisibleIdx = rawCache.findIndex(log => log._id === displayMinId);
    if (oldestVisibleIdx > 0) {
        // rawCache 中 displayMinId 之前还有日志，检查是否有 visible 的
        const hasOlderVisible = rawCache
            .slice(0, oldestVisibleIdx)
            .some(isLogVisible);
        
        if (hasOlderVisible) {
            // 从 rawCache 加载，零后端请求
            updateDisplayFromCache();
            return;
        }
    }
    
    // ========== 第二层：rawCache 耗尽，走后端 API ==========
    if (hasMoreLogs) {
        const startId = displayMinId || rawCache[0]?._id || 'latest';
        loadMoreFilteredHistory(startId, -currentLimit, buildFilterParams());
    }
}
```

**为什么这样设计？**

| 情况 | 行为 | 优势 |
|------|------|------|
| rawCache 中有更旧的可视日志 | 前端直接加载，零网络请求 | 极快 |
| rawCache 中虽然有更旧日志，但都被 filter 隐藏 | **不**从前端加载，直接走后端 API | 避免加载大量隐藏行导致 DOM 膨胀 |
| rawCache 已耗尽 | 后端 API 带 filter 查询 | 只返回匹配行 |

---

## 5. 关键代码：updateDisplayFromCache 的改造

```javascript
function updateDisplayFromCache(options = {}) {
    const { reset = false } = options;
    
    if (rawCache.length === 0) {
        clearLogTable();
        displayMinId = null;
        displayMaxId = null;
        totalEntries = 0;
        updateEntryCount(0);
        return;
    }
    
    // 从 rawCache 派生当前 visibleCache
    const visibleCache = rawCache.filter(isLogVisible);
    
    const newDisplayMinId = visibleCache[0]?._id ?? null;
    const newDisplayMaxId = visibleCache[visibleCache.length - 1]?._id ?? null;
    
    if (reset || displayMinId === null) {
        // 全量重置：只渲染 visibleCache 的最近 N 条
        const limit = viewMode === 'live' ? MAX_LOG_LIMIT : HISTORY_DOM_LIMIT;
        const logsToRender = visibleCache.slice(-limit);
        renderTableBody(logsToRender);
        return;
    }
    
    // ========== prepend：加载更旧的可视日志 ==========
    if (newDisplayMinId < displayMinId) {
        const logsToPrepend = visibleCache.filter(log => log._id < displayMinId);
        if (logsToPrepend.length > 0) {
            prependVisibleToDom(logsToPrepend);
            // history 模式下 trim 尾部
            if (viewMode === 'history') trimDomFromTail(HISTORY_DOM_LIMIT);
        }
    }
    
    // ========== append：加载更新的可视日志 ==========
    if (newDisplayMaxId > displayMaxId) {
        const logsToAppend = visibleCache.filter(log => log._id > displayMaxId);
        if (logsToAppend.length > 0) {
            // history 模式下积压过多 → 非线性跳回
            if (viewMode === 'history' && logsToAppend.length > MAX_LOG_LIMIT) {
                enterLiveMode({ forceReset: true });
                return;
            }
            appendVisibleToDom(logsToAppend);
            trimDomIfNeeded();
        }
    }
    
    // 更新统计
    updateVisibleEntryCount();
}
```

---

## 6. 回答用户的核心疑虑

> "能保证两个接口获取到的数据能接上吗？"

**能，而且不需要任何拼接逻辑。**

| 来源 | _id 范围 | 与另一来源的关系 |
|------|---------|-----------------|
| API 历史 | `< displayMinId` | 严格在 SSE 的左侧，不重叠 |
| SSE 实时 | `> cacheMaxId` | 严格在 API 的右侧，不重叠 |

`_id` 的单调性就是天然的"防重叠屏障"。

> "会不会导致复杂的逻辑用来拼接两类 log？"

**不会。** 两类日志走**同一条 merge 流水线**进入 rawCache，然后从 rawCache 派生 visibleCache。不存在"API 日志"和"SSE 日志"两个类别，它们进入系统后就是同一种数据。

> "filter 变更时怎么办？"

**零成本重建。** rawCache 中已有全量数据，filter 变更时只需要 `rawCache.filter(isLogVisible)`，不需要任何后端请求。

---

## 7. 一句话总结

> **用一个全量 rawCache（20k）兜底，visible 部分动态派生。SSE 和 API 的数据通过 `_id` 单调性天然分区，走同一条 merge → filter → render 流水线。filter 变更时从 rawCache 重建，向上滚动时先查 rawCache 再走 API。没有拼接，没有 session，没有两套 cache。**
