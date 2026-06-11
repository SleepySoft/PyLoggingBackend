# Backend Filter Architecture: Real-time vs. History Boundary

> 讨论范围：PyLoggingBackend 后端 filter 设计的理想架构与极端情况防护

---

## 1. 核心问题

当前前端 filter 架构在极端情况下有本质缺陷：
- 后端推送全量日志 → 前端 `display:none` 隐藏不匹配的行
- 向上加载历史时，大量不匹配日志占用网络、内存、DOM

但全量后端 filter 也有陷阱：
- SSE 广播流如果为每客户端维护独立 filter，后端状态爆炸
- 分页查询如果 filter 极严，可能触发全表扫描

---

## 2. 边界划分：前端 cache 物理范围

**后端不区分"实时"和"历史"**，只暴露两个无状态接口：

```
GET /logger/api/stream?last_log_id=X        → 增量推送（无 filter）
GET /logger/api/logs?...                    → 分页查询（带 filter）
```

**边界由前端 cache 大小决定：**

| 区域 | 范围 | Filter 执行方 | 触发条件 |
|------|------|--------------|----------|
| **Hot Cache** | 最近 5,000 条（内存中） | **前端** | 用户在前端 cache 范围内浏览 |
| **冷历史** | 5,000 条之前 | **后端** | 用户向上滚动超出 cache，或 filter 变更后 cache 中匹配行不足 |

```
后端存储（百万/千万条）
    │
    ├── 最近 5k ──→ SSE 推送 ──→ 前端 Hot Cache ──→ 前端 filter
    │                                          │
    └── 更早的 ───→ REST API ←─── 用户向上滚动超出 5k
                         ↑
                    后端 filter 执行
```

**为什么 SSE 不 filter？**
SSE 是**广播长连接**，所有客户端共享同一个事件流。如果为每客户端维护独立 filter：
- 每客户端一个独立消息队列
- filter 变更时重新建立订阅
- 连接断开后恢复状态复杂

这对于日志查看器是过度设计。SSE 保持无状态全量推送，前端只保留最近 5k，filter 在内存中执行（< 1ms）。

---

## 3. 后端 Filter API 设计

### 3.1 请求参数

```http
GET /logger/api/logs
    ?start_log_id=8000          # 游标起点（分页锚点）
    &count=-100                 # 负数=向后（更早），正数=向前（更新）
    &levels=CRITICAL,ERROR      # level 白名单
    &modules=auth.*,db.*        # module 前缀匹配（支持通配符）
    &exclude_modules=auth.test  # module 黑名单
    &time_after=2026-06-01T00:00:00  # 时间下限（可选）
```

### 3.2 响应结构

```json
{
    "logs": [...],           # 已过滤的匹配日志
    "has_more": true,        # 后端是否还有更多数据
    "scanned": 10000,        # 本次扫描了多少条候选日志
    "found": 3,              # 实际匹配多少条
    "next_cursor": 7900,     # 下次查询的游标（最小_id）
    "hint": null             # 极端情况下的提示信息
}
```

**关键字段 `scanned`**：前端可以知道"为了找到这 3 条，后端扫了 10,000 条"。这是判断 filter 是否过严的依据。

---

## 4. 极端搜索的六层防护

### 4.1 强制索引字段

只允许对**有索引的字段**做 filter，拒绝无索引字段的查询：

```python
ALLOWED_FILTER_FIELDS = {"_id", "levelname", "module", "timestamp"}

# 拒绝
if filter_field not in ALLOWED_FILTER_FIELDS:
    raise BadRequest(f"Filter on '{filter_field}' not supported (no index)")
```

索引设计（MongoDB 示例）：
```javascript
db.logs.createIndex({"_id": -1, "levelname": 1, "module": 1})
db.logs.createIndex({"module": 1, "_id": -1})
db.logs.createIndex({"timestamp": -1})
```

### 4.2 游标分页（禁止 skip）

**绝不使用 `skip`**，它会导致全表扫描：

```python
# ❌ BAD: skip 导致扫描前 10,000 条
collection.find({...}).skip(10000).limit(100)

# ✅ GOOD: 基于 _id 的范围查询，索引直接定位
collection.find({
    "_id": {"$lt": cursor_id},
    "levelname": {"$in": levels}
}).sort("_id", -1).limit(100)
```

### 4.3 单次扫描上限（MAX_SCAN）

即使 filter 极严，也限制单次查询最多扫描的候选数量：

```python
MAX_SCAN = 10000  # 最多扫描 1 万条候选

def fetch_filtered_logs(cursor_id, filter, page_size):
    query = build_query(filter)
    query["_id"] = {"$lt": cursor_id}
    
    cursor = collection.find(query).sort("_id", -1)
    results = []
    scanned = 0
    
    for doc in cursor:
        scanned += 1
        if matches_filter(doc, filter):
            results.append(doc)
        if len(results) >= page_size:
            break
        if scanned >= MAX_SCAN:
            break  # 硬上限，返回已找到的
    
    return {
        "logs": results,
        "scanned": scanned,
        "has_more": scanned < MAX_SCAN or cursor.alive,
        "hint": build_hint(results, scanned)
    }
```

**效果**：无论数据总量多大、filter 多严，单次查询最多只扫描 1 万条。

### 4.4 查询超时保护

```python
# MongoDB: maxTimeMS = 2000ms
cursor = collection.find(query).max_time_ms(2000)

# 超时后自动终止，返回已收集的结果
```

### 4.5 结果为空时智能提示

```python
def build_hint(results, scanned):
    if len(results) == 0 and scanned >= MAX_SCAN:
        return (f"Scanned {scanned:,} logs but found 0 matches. "
                f"Your filter may be too strict. "
                f"Try broadening the time range or module selection.")
    if len(results) < 10 and scanned >= MAX_SCAN // 2:
        return (f"Scanned {scanned:,} logs, only {len(results)} matched. "
                f"Loading more may take a while.")
    return None
```

前端收到 `hint` 后，在界面底部显示提示，让用户知道"不是没数据，是 filter 太严"。

### 4.6 统计预检（前端决策辅助）

```http
GET /logger/api/stats
```

返回各级别、各模块的日志分布：

```json
{
    "totalEntries": 10000000,
    "levelCounts": {"DEBUG": 8000000, "INFO": 1500000, "ERROR": 500000},
    "moduleCounts": {"auth": 500000, "db": 300000, "payment": 200000}
}
```

前端在用户 apply filter 前，可以预估：
- "选 CRITICAL 只占 0.001%，可能需要大量扫描"
- "选 auth.* 占 5%，响应会很快"

---

## 5. 前后端协同：完整数据流

### 场景 A：正常实时浏览

```
用户打开页面
    │
    ▼
GET /logs?count=100 → 后端返回最近 100 条（无 filter）
    │
    ▼
前端 cache = 100 条
前端 filter → DOM 显示匹配行
    │
    ▼
SSE /stream?last_log_id=99
    │
每 5 秒推送新日志
    │
    ▼
前端 cache 增长 → prune 到 5k
前端 filter → 匹配则渲染
```

### 场景 B：用户向上滚动加载历史

```
用户向上滚动
    │
    ▼
IntersectionObserver 触发 loadMoreLogs()
    │
    ▼
cache 中还有旧日志？
    ├── 是 → 前端 prepend（无后端请求）
    └── 否 → 后端请求
              │
              ▼
        GET /logs?start_log_id=500&count=-100&levels=ERROR&modules=auth.*
              │
              ▼
        后端扫描 10,000 条候选，找到 3 条匹配
              │
              ▼
        前端 merge → prepend → 渲染
```

### 场景 C：Filter 极严，scan 耗尽

```
用户只选了一个极少出现的 module
    │
    ▼
向上滚动 → cache 耗尽 → 后端请求
    │
    ▼
后端扫描 MAX_SCAN=10,000 条，找到 0 条
    │
    ▼
响应：{"logs": [], "scanned": 10000, "hint": "...", "has_more": true}
    │
    ▼
前端显示："已扫描 10,000 条，无匹配。Filter 可能过严。"
用户选择：
    ├── 继续搜索 → 前端用 next_cursor 再次请求
    └── 放宽 filter → 重新查询
```

### 场景 D：Filter 变更

```
用户调整 filter（如取消 DEBUG，只保留 ERROR）
    │
    ▼
纯前端操作：
    1. 更新 selectedLevels
    2. 遍历 hot cache，重新 filter
    3. DOM 更新（显示/隐藏）
    4. entryCount 更新为 visibleCount
    │
无需后端请求！无需重启 SSE！
```

---

## 6. 与当前前端代码的衔接修改

### 前端需要改什么

| 当前行为 | 需要修改 | 说明 |
|----------|----------|------|
| `fetchLogsToCache` 不带 filter | 带上 `levels` 和 `modules` 参数 | 向后端传递当前 filter 条件 |
| 后端返回 `has_more` 未使用 | 使用 `has_more` + `scanned` | 判断是否真的还有更多，还是 filter 太严 |
| 后端返回 `hint` 未处理 | 在 toolbar 显示 hint | 让用户知道扫描了多少、匹配了多少 |
| `loadMoreLogs` 的 cache 耗尽逻辑 | 带上 filter 参数请求后端 | 避免 fetch 回来再过滤 |

### 后端需要新增什么

```python
# LoggerBackend.py 中 /logger/api/logs 的 handler

def build_mongo_query(start_id, count, levels=None, modules=None, exclude_modules=None):
    query = {"_id": {"$lt": start_id}}
    
    if levels:
        query["levelname"] = {"$in": levels}
    
    if modules:
        # 支持通配符：auth.* → {"$regex": "^auth\\."}
        module_conditions = []
        for m in modules:
            if m.endswith('.*'):
                module_conditions.append({"$regex": f"^{re.escape(m[:-2])}\\."})
            else:
                module_conditions.append(m)
        if len(module_conditions) == 1:
            query["module"] = module_conditions[0]
        else:
            query["module"] = {"$in": module_conditions}
    
    if exclude_modules:
        # 黑名单：{ "$not": { "$regex": "^auth\\.test$" } }
        pass
    
    return query
```

---

## 7. 如果用 Elasticsearch（更优方案）

MongoDB 的 `$regex` 在 module 过滤时性能一般。如果日志量达到亿级，建议引入 Elasticsearch：

```json
// ES Mapping
{
    "mappings": {
        "properties": {
            "_id": {"type": "integer"},
            "timestamp": {"type": "date"},
            "levelname": {"type": "keyword"},
            "module": {"type": "keyword"},
            "message": {"type": "text"}
        }
    }
}

// ES Query
{
    "query": {
        "bool": {
            "filter": [
                {"range": {"_id": {"lt": 8000}}},
                {"terms": {"levelname": ["CRITICAL", "ERROR"]}},
                {"prefix": {"module": "auth."}}
            ]
        }
    },
    "sort": [{"_id": "desc"}],
    "size": 100
}
```

ES 的倒排索引让 filter 查询性能**与数据总量无关**，只与匹配结果集大小有关。即使是亿级日志，CRITICAL + auth.* 的查询也可以在 < 50ms 内返回。

---

## 8. 一句话总结

> **SSE 实时流无状态全量推送（前端保 5k），历史查询后端带 filter 分页（游标 + 扫描上限 + 超时保护）。后端不维护 session，filter 变更纯前端操作。极端 filter 时后端返回 scanned + hint，由用户决定是否继续深挖。**
