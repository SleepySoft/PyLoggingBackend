# Virtual Scroll + Tiered Cache Architecture

> 核心洞察：显示、缓存、数据加载完全可以解耦。DOM 只渲染视口内容，缓存分层管理实时/历史，连续性检查自动清理无效缓存。

---

## 1. 问题回顾：当前架构的本质瓶颈

当前架构无论怎么优化，都有一个**天花板**：

```
DOM 节点数 ∝ 缓存中的日志条数
```

即使做了 `DocumentFragment`、分批渲染、2000 条限制，本质上还是在用**空间换时间**——缓存越大，DOM 越多，内存和渲染压力越大。

**真正的突破点是：让 DOM 节点数与缓存大小无关。**

---

## 2. 三层解耦架构

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Display（显示层）                                  │
│  · 只渲染视口内 + 上下各 1 屏缓冲 ≈ 100 个 DOM 节点          │
│  · 与缓存大小完全无关                                        │
│  · 滚动时计算可见范围，复用/创建节点                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 滚动超出缓冲范围
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Hot Buffer（热缓存）                               │
│  · 当前 filter 下可见的最近 N 条日志（如 5,000）             │
│  · SSE 实时推送直接进入                                      │
│  · 向下滚动回底部时直接从这里取                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 向上滚动超出 Hot Buffer
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Offline Buffer（离线缓存）                         │
│  · 按需从后端加载的历史日志，按**段**存储                    │
│  · 段 1: [id: 1000~1999, 100 条]                            │
│  · 段 2: [id: 500~999, 80 条] （filter 导致不连续）         │
│  · 连续性检查 → 不连续时自动清空                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 缓存未命中
┌─────────────────────────────────────────────────────────────┐
│  Backend API                                                │
│  GET /logs?start_id=X&count=-N&levels=...&modules=...       │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心机制详解

### 3.1 显示层：虚拟滚动

**不需要渲染 5000 条，只需要渲染用户眼睛看到的。**

```javascript
const ROW_HEIGHT = 40;           // 每行估算高度（px）
const BUFFER_SCREENS = 1;        // 上下各保留 1 屏缓冲

function getVisibleRange() {
    const container = document.querySelector('.log-entries-container');
    const scrollTop = container.scrollTop;
    const viewportHeight = container.clientHeight;
    
    // 视口内可见的起止索引
    const firstVisible = Math.floor(scrollTop / ROW_HEIGHT);
    const lastVisible = Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT);
    
    // 加上缓冲
    const bufferRows = Math.ceil(viewportHeight / ROW_HEIGHT * BUFFER_SCREENS);
    const firstIdx = Math.max(0, firstVisible - bufferRows);
    const lastIdx = Math.min(totalLogCount - 1, lastVisible + bufferRows);
    
    return { firstIdx, lastIdx };
}

function renderViewport() {
    const { firstIdx, lastIdx } = getVisibleRange();
    const neededIds = new Set();
    
    for (let i = firstIdx; i <= lastIdx; i++) {
        const log = getLogByIndex(i);  // 从 Hot/Offline Buffer 取
        if (log) neededIds.add(log._id);
    }
    
    // 复用已有 DOM 节点，只创建/更新差异
    syncDomRows(neededIds);
}
```

**关键**：tbody 中永远只有 ~100 个 `<tr>` 节点，滚动时通过改变 `transform` 或 `top` 位置来复用节点，或者创建/销毁少量差异节点。

### 3.2 Hot Buffer：实时窗口

```javascript
let hotBuffer = [];       // 当前 filter 下可见的日志，按 _id 升序
let hotBufferMap = new Map();
const HOT_BUFFER_LIMIT = 5000;

function onSseMessage(logs) {
    // 1. 过滤出 visible
    const visible = logs.filter(isLogVisible);
    
    // 2. 合并到 hot buffer
    visible.forEach(log => {
        if (!hotBufferMap.has(log._id)) {
            hotBuffer.push(log);
            hotBufferMap.set(log._id, log);
        }
    });
    
    // 3. 排序（保持升序）
    hotBuffer.sort((a, b) => a._id - b._id);
    
    // 4. 淘汰最旧的
    if (hotBuffer.length > HOT_BUFFER_LIMIT) {
        const excess = hotBuffer.length - HOT_BUFFER_LIMIT;
        const evicted = hotBuffer.splice(0, excess);
        evicted.forEach(log => hotBufferMap.delete(log._id));
        
        // 尝试将淘汰的日志移入 Offline Buffer
        migrateToOfflineBuffer(evicted);
    }
    
    // 5. 触发显示层更新
    renderViewport();
}
```

### 3.3 Offline Buffer：分段历史缓存

```javascript
let offlineBuffer = {
    segments: [],  // [{startId, endId, logs: [...]}, ...]
    totalSize: 0,
    maxSize: 10000
};

// 加载新历史段
function loadHistorySegment(startId, count, filter) {
    return fetch(`/logs?start_id=${startId}&count=${count}&...`)
        .then(data => {
            const segment = {
                startId: data.logs[0]._id,
                endId: data.logs[data.logs.length - 1]._id,
                logs: data.logs
            };
            
            // 插入到头部（因为历史是越旧的越靠前）
            offlineBuffer.segments.unshift(segment);
            offlineBuffer.totalSize += segment.logs.length;
            
            // 淘汰最旧的段
            trimOfflineBuffer();
            
            return segment;
        });
}

// 按索引取日志（跨段查询）
function getLogByIndex(index) {
    // index 0 = 最旧的日志
    let offset = 0;
    
    // 先查 offline buffer（存储更旧的历史）
    for (const seg of offlineBuffer.segments) {
        if (index < offset + seg.logs.length) {
            return seg.logs[index - offset];
        }
        offset += seg.logs.length;
    }
    
    // 再查 hot buffer
    const hotIndex = index - offset;
    if (hotIndex >= 0 && hotIndex < hotBuffer.length) {
        return hotBuffer[hotIndex];
    }
    
    return null;  // 越界或缓存未命中
}
```

### 3.4 连续性检查与自动清理

这是整个架构的**灵魂**。

```javascript
function isContinuous() {
    if (offlineBuffer.segments.length === 0) return true;
    
    const oldestHot = hotBuffer[0]?._id ?? Infinity;
    const newestOffline = offlineBuffer.segments[0].endId;  // 最新段的最后一条
    
    // 连续 = hot buffer 最旧的一条紧接 offline buffer 最新段
    return oldestHot === newestOffline + 1;
}

function ensureContinuity() {
    if (!isContinuous()) {
        console.log('Cache discontinuity detected → clearing offline buffer');
        offlineBuffer.segments = [];
        offlineBuffer.totalSize = 0;
    }
}
```

**什么时候触发连续性检查？**

| 事件 | 动作 |
|------|------|
| SSE 推送导致 hot buffer 淘汰旧日志 | 检查 hot buffer 与 offline buffer 是否连续 |
| Filter 变更导致 hot buffer 重建 | 检查新的 hot buffer 与 offline buffer 是否连续 |
| 点击 Auto Scroll / 跳转回底部 | 进入实时状态前检查，不连续则清空 offline buffer |
| 从后端加载新历史段 | 插入前检查与现有段的连续性 |

**为什么一不连续就要清空？**

假设：
- Hot Buffer: [10000, 15000]
- Offline Buffer 最新段: [8000, 8999]

中间存在空洞：9000~9999 的日志在哪？

可能的情况：
1. 真的不存在（日志系统有间隙）
2. 被 filter 隐藏了（前端不知道，因为后端 filter API 也没返回）
3. 还在后端数据库中，但前端没加载到

由于无法确定空洞原因，最安全的做法是**清空 offline buffer**，让下次向上滚动时从头加载。这比维护空洞的复杂逻辑要简单得多。

### 3.5 跳转（Auto Scroll）时的优雅处理

```javascript
function jumpToLive() {
    // 1. 进入 live mode
    viewMode = 'live';
    autoScrollEnabled = true;
    
    // 2. 连续性检查：如果 hot buffer 与 offline buffer 不连续
    //    说明用户浏览历史期间，hot buffer 已经淘汰了旧日志
    //    此时 offline buffer 中的数据已经不可靠
    if (!isContinuous()) {
        offlineBuffer.segments = [];
        offlineBuffer.totalSize = 0;
        console.log('Jump to live: offline buffer cleared due to discontinuity');
    }
    
    // 3. 渲染视口：只渲染 hot buffer 尾部的内容
    //    不需要创建 2000 个节点，只需要创建视口内的 ~50 个
    scrollToBottom();
    renderViewport();
}
```

**关键**：跳转时**不清空 hot buffer**（最新的日志始终有效），只清空可能不连续的 offline buffer。

---

## 4. 各场景的完整数据流

### 场景 A：正常实时浏览

```
SSE 推送 10 条新日志
    │
    ▼
isLogVisible 过滤 → 3 条可见
    │
    ▼
合并到 Hot Buffer（尾部 append）
    │
    ▼
Hot Buffer 超 5k？→ 淘汰最旧的 3 条
    │
    ▼
尝试移入 Offline Buffer（检查连续性）
    │
    ▼
renderViewport() → 只更新视口内变化的几行
```

### 场景 B：向上滚动加载历史

```
用户向上滚动
    │
    ▼
getVisibleRange() → firstIdx = 50（接近 Hot Buffer 头部）
    │
    ▼
预加载：启动从后端 fetch [hotBuffer.minId - 100, hotBuffer.minId)
    │
    ▼
后端返回 80 条匹配日志（filter 导致 100 条候选中只有 80 条匹配）
    │
    ▼
新段插入 Offline Buffer 头部
    │
    ▼
renderViewport() → 从 Offline Buffer + Hot Buffer 取数据渲染
```

### 场景 C：Filter 变更

```
用户取消 DEBUG，只保留 ERROR
    │
    ▼
重建 Hot Buffer：rawCache.filter(isLogVisible)
    │
    ▼
新的 Hot Buffer 可能只有 200 条（原来是 5000 条）
    │
    ▼
ensureContinuity() → 检查与 Offline Buffer 是否连续
    │
    ├── 连续 → 保留 Offline Buffer
    └── 不连续 → 清空 Offline Buffer
    │
    ▼
renderViewport() → 渲染新的可见范围
    │
    ▼
Hot Buffer 只有 200 条？→ 从后端补充更多 ERROR 日志
```

### 场景 D：长时间运行后跳转

```
用户在 history 模式浏览 2 小时
    │
    ▼
Hot Buffer 经历了多次淘汰，现在只有最新的 5k
    │
    ▼
Offline Buffer 有 3 段历史，共 8k 条
    │
    ▼
用户点击 Auto Scroll
    │
    ▼
jumpToLive():
    · viewMode = 'live'
    · ensureContinuity() → 发现不连续！
    · 清空 Offline Buffer
    · scrollToBottom()
    · renderViewport() → 只渲染 hot buffer 尾部 ~50 条
    │
    ▼
页面瞬间响应，DOM 只有 ~100 个节点
```

---

## 5. 与传统方案的对比

| 指标 | 当前方案 | 新方案（虚拟滚动 + 分层缓存） |
|------|---------|---------------------------|
| **DOM 节点数上限** | 30,000（history 模式） | ~150（视口 + 缓冲） |
| **跳转响应时间** | 200ms~数秒（取决于 2000/5000 条创建速度） | < 16ms（一帧内完成） |
| **内存占用** | 高（DOM 节点 + 缓存数组） | 低（少量 DOM + 分层缓存） |
| **Filter 变更成本** | 遍历所有 DOM 行改 `display` | 重建 Hot Buffer，清空 Offline Buffer |
| **向上滚动加载** | 可能加载大量隐藏行 | 只加载匹配 filter 的可见行 |
| **实现复杂度** | 中等 | 较高（需要虚拟滚动逻辑） |
| **浏览器兼容性** | 全兼容 | 现代浏览器（需要 `transform`/`absolute` 定位） |

---

## 6. 最小可行实现（MVP）

如果一次性实现完整的虚拟滚动成本太高，可以先做**简化版**：

### Phase 1：分层缓存 + 连续性检查（不改造虚拟滚动）

1. 保留现有 DOM 渲染逻辑（全量渲染 visible 日志）
2. 引入 Hot Buffer 和 Offline Buffer
3. 实现连续性检查和自动清理
4. 跳转时只从 Hot Buffer 渲染（不需要渲染 2000 条，因为 Hot Buffer 就是当前可见的）

**效果**：DOM 节点数 = visible 日志数（而不是缓存总大小），filter 极严时 DOM 很少。

### Phase 2：虚拟滚动（视口渲染）

1. 改造 DOM 渲染为只渲染视口内容
2. 使用 `position: absolute` + `transform: translateY()` 实现行定位
3. 设置一个巨大的 `padding-top` 和 `padding-bottom` 来模拟总高度
4. 滚动时计算可见范围，复用/创建 DOM 行

**效果**：DOM 节点数固定在 ~100 个，与缓存大小彻底无关。

---

## 7. 一句话总结

> **显示只关心视口，缓存只管连续性，加载只管按需 fetch。三者通过索引（_id）衔接，不连续时果断丢弃，始终保持一个简单、可靠、可预测的状态机。**
