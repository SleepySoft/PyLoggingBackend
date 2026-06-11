# Log Viewer: Scroll Behavior and View Mode Design

> Document version: 2026-06-10  
> Scope: `PyLoggingBackend/LoggerViewer.html` core interaction logic

---

## 1. Problem Statement

The original log viewer had a single hard limit (`MAX_LOG_LIMIT = 5000`) that was applied simultaneously to three layers:

| Layer | Original Behavior | Problem |
|-------|-------------------|---------|
| **Backend cache** (`logCache`) | Spliced to 5000 entries | Old logs disappeared while the user was scrolling through history |
| **DOM rows** (`<tr>` elements) | Oldest rows removed on append | Even if the cache still had the data, the DOM could not display it |
| **Upward loading** (IntersectionObserver) | Blocked at 5000 rows | The user could not load more history beyond the limit |

Additionally, there was no explicit **live / history** mode concept. The system relied only on `autoScrollEnabled`, which caused:
- New logs always rendered immediately, pushing old rows out of the DOM
- No clear boundary between "watching real-time" and "browsing history"
- A jarring jump when returning from history to live (thousands of buffered logs rendered at once)

---

## 2. Design Philosophy

> **The cache is the river. The DOM is a sliding window.**

The user should be able to move the window freely along the river. When the window reaches the downstream end (the newest logs), it automatically connects to the real-time flow (SSE). When the window moves upstream (older logs), the real-time flow continues underneath without disturbing the view.

### Key Principles

1. **Separation of concerns**
   - Cache manages memory and data continuity
   - DOM manages what the user currently sees
   - View mode manages behavior during state transitions

2. **Natural scroll boundaries**
   - No manual mode switching required
   - Scrolling away from the bottom enters history mode automatically
   - Scrolling back to the bottom resumes live mode automatically

3. **Bounded but continuous**
   - Cache has a memory ceiling (soft limit + hot-tail retention)
   - The newest segment is always preserved for seamless live recovery
   - Evicted old logs are re-fetched from the backend on demand

---

## 3. Architecture

### 3.1 Three-Layer Model

```
Backend (MongoDB / LogFileWrapper)
    ↓  HTTP API: start_log_id + count
Frontend Cache (logCache)
    ↓  Array sorted by _id ascending
DOM Display (log-table tbody)
    ↓  Only rows inside or near the viewport are rendered
User Eye (viewport)
```

### 3.2 State Machine: `viewMode`

```
┌─────────┐     scrollBottom > 150px      ┌───────────┐
│  LIVE   │ ─────────────────────────────→│  HISTORY  │
│  mode   │                               │   mode    │
└─────────┘←──────────────────────────────┘
     ↑      scrollBottom <= 30px  (or click Auto Scroll)
     │
     └─ SSE onmessage: merge + render + scroll

HISTORY mode ── SSE onmessage: merge only (no render)
     │
     └─ User scrolls down → incremental render from cache
```

### 3.3 Mode Transition Triggers

| Event | Condition | Action |
|-------|-----------|--------|
| Scroll up | `scrollBottom > 150px` | Auto-enter **history** mode |
| Scroll down to bottom | `scrollBottom <= 30px` | Auto-enter **live** mode |
| Click "Auto Scroll" button | Manual | Force-enter **live** mode with DOM reset |
| SSE new log | `viewMode === 'live'` | Render immediately + scroll if near bottom |
| SSE new log | `viewMode === 'history'` | Merge into cache only; render on next downward scroll |

---

## 4. Cache Design

### 4.1 Constants

```javascript
const MAX_LOG_LIMIT    = 5000;   // DOM row ceiling in live mode
const CACHE_SOFT_LIMIT = 20000;  // Total cache memory ceiling (~10 MB @ 500 B/log)
const HOT_CACHE_SIZE   = 5000;   // Newest logs that are NEVER pruned
```

### 4.2 Pruning Strategy: Hot-Tail Retention

When `logCache.length > CACHE_SOFT_LIMIT`:

1. Calculate `excess = logCache.length - CACHE_SOFT_LIMIT`
2. Calculate `safeToDelete = logCache.length - HOT_CACHE_SIZE`
3. `deleteCount = min(excess, safeToDelete)`
4. Remove `deleteCount` oldest entries from the head of the array

**Why this works:**
- Memory is bounded (max ~10 MB under normal load)
- The newest 5000 logs are always in memory, guaranteeing that:
  - Live mode never loses continuity
  - A non-linear jump back to live always has data available
- Old logs beyond the soft limit are evicted, but the backend API can re-fetch them when the user scrolls up

### 4.3 Pruning Timing

`pruneCache()` is called automatically at the end of every `mergeLogsToCache()` invocation. This ensures the cache never grows unboundedly, even if the user stays in history mode for hours.

---

## 5. DOM Display Design

### 5.1 Live Mode: Sliding Window

In live mode, the DOM is a **sliding window** of at most `MAX_LOG_LIMIT` rows:

```javascript
// Inside updateDisplayFromCache() -- append path
logsToAppend.forEach(addLogRow);

// After append, prune oldest rows if exceeded
if (viewMode === 'live') {
    const rows = logTableBody.querySelectorAll('tr[data-log-id]');
    const excess = rows.length - MAX_LOG_LIMIT;
    if (excess > 0) {
        for (let i = 0; i < excess; i++) {
            if (rows[i]) rows[i].remove();
        }
    }
}
```

This keeps the DOM lightweight and rendering fast, regardless of how many logs have passed through the system.

### 5.2 History Mode: Expandable Canvas

In history mode, the DOM **does not prune old rows**. The user can scroll up freely, loading more and more history into the DOM without any artificial ceiling.

The only limit is physical memory (browser + OS), which is typically not a concern for sessions under a few hundred thousand rows.

### 5.3 Upward Infinite Scroll

The IntersectionObserver on the `scrollObserver` element (positioned at the top of the table) triggers `loadMoreLogs()` when:
- The element enters the viewport
- The user is scrolling **up**
- There are older logs available (either in cache or on the backend)

**Guard condition:** In live mode, if the DOM already has `MAX_LOG_LIMIT` rows, upward loading is paused to prevent the sliding window from expanding. In history mode, this guard is removed.

---

## 6. Non-Linear Jump-Back Design

### 6.1 The Problem

If the user has scrolled deep into history (e.g., viewing logs from 30 minutes ago), and thousands of new logs have arrived in the meantime, clicking "Auto Scroll" would previously attempt to render **all** accumulated logs at once. This causes:
- Browser freeze (thousands of `createLogRow` + `appendChild` calls)
- A massive jump in scroll position
- Poor user experience

### 6.2 The Solution: `forceReset`

`enterLiveMode()` accepts an options object:

```javascript
function enterLiveMode(options = {}) {
    if (viewMode === 'live') return;
    viewMode = 'live';
    autoScrollEnabled = true;

    if (options.forceReset) {
        // Non-linear jump: reset DOM to the most recent MAX_LOG_LIMIT rows
        const recentLogs = logCache.slice(-MAX_LOG_LIMIT);
        renderTableBody(recentLogs);
    } else {
        // Natural scroll to bottom: incremental render
        updateDisplayFromCache();
    }
}
```

| Trigger | `forceReset` | Behavior |
|---------|-------------|----------|
| Natural scroll to bottom | `false` (default) | `updateDisplayFromCache()` renders only logs with `_id > displayMaxId` incrementally |
| Click "Auto Scroll" button | `true` | `renderTableBody(logCache.slice(-MAX_LOG_LIMIT))` instant reset to latest |

This gives the user two distinct mental models:
- **Browsing back to the present** (smooth, gradual)
- **Teleporting to the present** (instant, like a "jump to now" button)

---

## 7. Scroll Metrics and Thresholds

```javascript
const scrollBottom = scrollHeight - scrollTop - clientHeight;

isNearBottom = scrollBottom < 30;      // "At the bottom"
historyTrigger = scrollBottom > 150;   // "Far enough from bottom to enter history"
incrementalRenderTrigger = scrollBottom < 300 && !isScrollingUp;
                                       // "Close enough to bottom to start rendering buffered logs"
```

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| `isNearBottom` | `< 30px` | Tight: only true when genuinely at the bottom |
| `historyTrigger` | `> 150px` | Loose: a small downward adjustment does not accidentally exit history |
| `incrementalRenderTrigger` | `< 300px` + scrolling down | Start rendering cached new logs before the user reaches the absolute bottom, for a seamless transition |

---

## 8. API Compatibility

The current backend API (`/logger/api/logs?start_log_id=X&count=Y`) already supports the required pagination semantics:

- `count > 0`: Fetch forward from `start_log_id`
- `count < 0`: Fetch backward from `start_log_id`

No backend changes are required for this design. Potential future enhancements (optional):
- `?latest=N` endpoint for simpler initial load
- Total log count in response for more precise `hasMoreLogs` tracking

---

## 9. Testing Checklist

| Scenario | Expected Behavior |
|----------|-------------------|
| Live mode, new logs arriving | DOM slides: appends new rows, removes oldest rows. Scroll stays at bottom if `autoScrollEnabled`. |
| Scroll up > 150px | Auto-enters history mode. DOM stops pruning. New SSE logs merge silently into cache. |
| In history mode, scroll down toward bottom | Incrementally renders buffered logs from cache. No freeze. |
| In history mode, scroll to absolute bottom | Auto-enters live mode. Seamless transition. |
| Deep in history, click "Auto Scroll" | DOM resets to latest 5000 rows. Instant jump to bottom. |
| Leave tab open for hours in history mode | Cache auto-prunes to 20k rows (newest 5k preserved). Memory stable. |
| Scroll up beyond cached range | IntersectionObserver triggers `fetchLogsToCache`. Backend loads older logs. No error. |

---

## 10. Related Files

| File | Role |
|------|------|
| `PyLoggingBackend/LoggerViewer.html` | Main viewer UI and all interaction logic documented above |
| `PyLoggingBackend/LoggerBackend.py` | Flask backend serving `/logger/api/logs` and `/logger/api/stream` |
| `PyLoggingBackend/LogFileWrapper.py` | File monitoring and indexed log storage |
| `PyLoggingBackend/LogGenerator.py` | Test log generator (includes stress patterns for long messages, bursts, etc.) |
