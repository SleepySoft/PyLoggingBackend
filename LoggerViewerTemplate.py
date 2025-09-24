LOGGER_VIEWER = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Log Viewer</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --sidebar-width: 350px;
            --sidebar-collapsed-width: 50px;
            --transition-speed: 0.3s;
        }
        
        body {
            overflow: hidden;
            height: 100vh;
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        
        .main-container {
            display: flex;
            height: 100vh;
            transition: all var(--transition-speed);
        }
        
        .sidebar {
            width: var(--sidebar-width);
            height: 100%;
            overflow-y: auto;
            background-color: #f8f9fa;
            border-right: 1px solid #dee2e6;
            transition: all var(--transition-speed);
            display: flex;
            flex-direction: column;
            position: relative;
        }
        
        .sidebar.collapsed {
            width: var(--sidebar-collapsed-width);
        }
        
        .sidebar-content {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            display: block;
        }
        
        .sidebar.collapsed .sidebar-content {
            display: none;
        }
        
        .toggle-sidebar-btn {
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 1000;
            background: #6c757d;
            border: none;
            border-radius: 4px;
            color: white;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }
        
        .toggle-sidebar-btn:hover {
            background: #5a6268;
        }
        
        .sidebar.collapsed .toggle-sidebar-btn {
            right: 8px;
        }
        
        .log-container {
            flex: 1;
            height: 100vh;
            display: flex;
            flex-direction: column;
            background-color: white;
        }
        
        .log-entries-container {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
        }
        
        .log-entry {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 12px;
            padding: 8px 12px;
            border-left: 4px solid transparent;
            margin-bottom: 4px;
            background-color: white;
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            line-height: 1.4;
        }
        
        .log-level-DEBUG { border-left-color: #6c757d; background-color: #f8f9fa; }
        .log-level-INFO { border-left-color: #0dcaf0; background-color: #e8f4f8; }
        .log-level-WARNING { border-left-color: #ffc107; background-color: #fff9e6; }
        .log-level-ERROR { border-left-color: #dc3545; background-color: #fdecea; }
        .log-level-CRITICAL { border-left-color: #6f42c1; background-color: #f3f0f7; }
        
        .timestamp { 
            color: #6c757d; 
            font-weight: bold;
            margin-right: 8px;
        }
        
        .module { 
            color: #0d6efd; 
            font-weight: bold;
            margin-right: 8px;
        }
        
        .level-badge {
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 10px;
            margin-right: 8px;
            color: white;
        }
        
        .badge-DEBUG { background-color: #6c757d; }
        .badge-INFO { background-color: #0dcaf0; }
        .badge-WARNING { background-color: #ffc107; }
        .badge-ERROR { background-color: #dc3545; }
        .badge-CRITICAL { background-color: #6f42c1; }
        
        .module-tree {
            max-height: 300px;
            overflow-y: auto;
            font-size: 14px;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 8px;
            background-color: white;
            margin-bottom: 1rem;
        }
        
        .filter-section {
            margin-bottom: 1rem;
        }
        
        .form-check-input:checked {
            background-color: #0d6efd;
            border-color: #0d6efd;
        }
        
        .scroll-observer {
            height: 1px;
            width: 100%;
            visibility: hidden;
        }
        
        .log-controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 1rem;
            background-color: #f8f9fa;
            border-top: 1px solid #dee2e6;
        }
        
        .stats-item {
            margin-bottom: 0.5rem;
        }
        
        .stats-value {
            font-weight: bold;
            float: right;
        }
        
        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.25rem 0.75rem;
            border-radius: 1rem;
            font-size: 0.875rem;
            font-weight: 500;
        }
        
        .status-indicator .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }
        
        .status-connected {
            background-color: #198754;
            color: #fff;
        }
        
        .status-connected .dot {
            background-color: #fff;
        }
        
        .status-connecting {
            background-color: #ffc107;
            color: #000;
        }
        
        .status-connecting .dot {
            background-color: #000;
            animation: pulse 1.5s infinite;
        }
        
        .status-disconnected {
            background-color: #dc3545;
            color: #fff;
        }
        
        .status-disconnected .dot {
            background-color: #fff;
        }
        
        .loading-indicator {
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 1rem;
            color: #6c757d;
        }
        
        .loading-spinner {
            width: 1.5rem;
            height: 1.5rem;
            border: 2px solid #f3f3f3;
            border-top: 2px solid #0d6efd;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 0.5rem;
        }
        
        .log-controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 1rem;
            background-color: #f8f9fa;
            border-top: 1px solid #dee2e6;
            position: sticky;
            bottom: 0;
            z-index: 100;
        }
        
        .auto-scroll-btn {
            background: transparent;
            border: none;
            color: #6c757d;
            cursor: pointer;
            font-size: 0.875rem;
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }
        
        .auto-scroll-btn.active {
            color: #0d6efd;
        }
        
        .auto-scroll-btn:hover {
            color: #0d6efd;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.4; }
            100% { opacity: 1; }
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .scroll-to-bottom {
            position: fixed;
            right: 2rem;
            bottom: 5rem;
            background-color: #0d6efd;
            color: white;
            width: 2.5rem;
            height: 2.5rem;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            z-index: 1000;
            opacity: 0;
            transition: opacity 0.3s;
        }
        
        .scroll-to-bottom.visible {
            opacity: 1;
        }
        
        /* 修复状态指示器布局 */
        .status-container {
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }
        
        .collapsed-status {
            display: none;
            position: absolute;
            bottom: 10px;
            left: 10px;
            z-index: 1000;
        }
        
        .sidebar.collapsed .collapsed-status {
            display: block;
        }
        
        .collapsed-status .status-indicator {
            padding: 0.15rem 0.5rem;
            font-size: 0.75rem;
        }
        
        .collapsed-status .status-indicator .dot {
            width: 6px;
            height: 6px;
        }
    </style>
</head>
<body>
    <div class="main-container">
        <!-- Left Sidebar -->
        <div class="sidebar" id="sidebar">
            <button class="toggle-sidebar-btn" onclick="toggleSidebar()">
                <i class="fas fa-bars" id="sidebarIcon"></i>
            </button>
            
            <!-- 折叠状态下的状态指示器 -->
            <div class="collapsed-status">
                <span id="collapsedConnectionStatus" class="status-indicator status-connecting">
                    <span class="dot"></span>
                    <span id="collapsedStatusText">Connecting</span>
                </span>
            </div>
            
            <div class="sidebar-content">
                <!-- Filters Panel -->
                <div class="card mb-3">
                    <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                        <span><i class="fas fa-filter"></i> Filters</span>
                        <button class="btn btn-sm btn-light" onclick="refreshModules()">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                    <div class="card-body">
                        <!-- Level Filter - Multi-select -->
                        <div class="filter-section">
                            <label class="form-label fw-bold">Log Levels:</label>
                            <div class="form-check">
                                <input class="form-check-input level-checkbox" type="checkbox" value="DEBUG" id="level-debug" checked>
                                <label class="form-check-label" for="level-debug">DEBUG</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input level-checkbox" type="checkbox" value="INFO" id="level-info" checked>
                                <label class="form-check-label" for="level-info">INFO</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input level-checkbox" type="checkbox" value="WARNING" id="level-warning" checked>
                                <label class="form-check-label" for="level-warning">WARNING</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input level-checkbox" type="checkbox" value="ERROR" id="level-error" checked>
                                <label class="form-check-label" for="level-error">ERROR</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input level-checkbox" type="checkbox" value="CRITICAL" id="level-critical" checked>
                                <label class="form-check-label" for="level-critical">CRITICAL</label>
                            </div>
                        </div>
                        
                        <!-- Module Tree -->
                        <div class="filter-section">
                            <label class="form-label fw-bold">Modules:</label>
                            <div class="module-tree" id="moduleTree">
                                <div class="text-center text-muted">
                                    <i class="fas fa-spinner fa-spin"></i> Loading modules...
                                </div>
                            </div>
                        </div>
                        
                        <button class="btn btn-primary w-100" onclick="applyFilters()">
                            <i class="fas fa-check"></i> Apply Filters
                        </button>
                        
                        <div class="filter-status-bar">
                            <small>Show Level: <span id="filterStatus">ALL</span></small>
                        </div>
                    </div>
                </div>
                
                <!-- Statistics -->
                <div class="card">
                    <div class="card-header bg-info text-white">
                        <i class="fas fa-chart-bar"></i> Statistics
                    </div>
                    <div class="card-body" id="statsPanel">
                        <div class="text-center text-muted">
                            <i class="fas fa-spinner fa-spin"></i> Loading statistics...
                        </div>
                    </div>
                </div>
                
                <div class="log-controls">
                    <div class="status-container">
                        <span id="connectionStatus" class="status-indicator status-connecting">
                            <span class="dot"></span>
                            <span id="statusText">Connecting</span>
                        </span>
                    </div>
                    <div>
                        <button id="autoScrollBtn" class="auto-scroll-btn active" title="自动滚动到底部">
                            <i class="fas fa-arrow-down"></i>
                            <span>Auto Scroll</span>
                        </button>
                        <span class="text-muted ms-2" id="entryCount">0 Items</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Main Log Content -->
        <div class="log-container">
            <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center">
                <span><i class="fas fa-list"></i> Log Entries</span>
                <span class="text-muted" id="loadStatus">Ready</span>
                <div class="form-check form-switch mb-0">
                    <input class="form-check-input" type="checkbox" id="autoRefresh" checked>
                    <label class="form-check-label text-white" for="autoRefresh">
                        Auto Refresh
                    </label>
                </div>
            </div>
            
            <div class="log-entries-container" id="logEntries">
                <div class="scroll-observer" id="scrollObserver"></div>
            </div>
            
            <div class="text-center p-3 text-muted" id="initialLoading">
                <i class="fas fa-spinner fa-spin"></i> Loading logs...
            </div>
            
            <div class="log-controls">
                <div>
                    <span class="text-muted" id="mainEntryCount">0 Entries</span>
                </div>
            </div>
            
            <div id="scrollToBottom" class="scroll-to-bottom" title="滚动到底部">
                <i class="fas fa-arrow-down"></i>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Global variables
        let currentStart = 0;
        let currentLimit = 100;
        let isLoading = false;
        let hasMoreLogs = true;
        let eventSource = null;
        let selectedModules = [];
        let selectedLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];
        let observer = null;
        let totalEntries = 0;
        let autoScrollEnabled = true;
        let isNearBottom = true;
        
        // Initialize application
        document.addEventListener('DOMContentLoaded', function() {
            initializeEventListeners();
            loadInitialData();
            setupEventSource();
            setupScrollObserver();
            setupScrollToBottom();
            setInterval(updateStats, 30000);
        });
        
        window.addEventListener('beforeunload', () => {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        });
        
        // Initialize event listeners
        function initializeEventListeners() {
            // Level checkbox listeners
            document.querySelectorAll('.level-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', updateSelectedLevels);
            });
            
            var applyButton = document.querySelector('button[onclick="applyFilters()"]');
            if (applyButton) {
                applyButton.addEventListener('click', applyFilters);
            }
            
            // 自动滚动按钮监听
            document.getElementById('autoScrollBtn').addEventListener('click', toggleAutoScroll);
            
            // 滚动到底部按钮监听
            document.getElementById('scrollToBottom').addEventListener('click', scrollToBottom);
            
            // 监听滚动事件以检测是否接近底部
            document.querySelector('.log-entries-container').addEventListener('scroll', checkScrollPosition);
            
            // Auto-refresh toggle
            document.getElementById('autoRefresh').addEventListener('change', function() {
                if (this.checked && !eventSource) {
                    setupEventSource();
                } else if (!this.checked && eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
            });
        }
        
        // Toggle sidebar collapse/expand
        function toggleSidebar() {
            const sidebar = document.getElementById('sidebar');
            const icon = document.getElementById('sidebarIcon');
            
            sidebar.classList.toggle('collapsed');
            if (sidebar.classList.contains('collapsed')) {
                icon.className = 'fas fa-chevron-right';
            } else {
                icon.className = 'fas fa-bars';
            }
        }
        
        // Setup Intersection Observer for infinite scroll
        function setupScrollObserver() {
            const options = {
                root: document.querySelector('.log-entries-container'),
                rootMargin: '0px',
                threshold: 0.1
            };
            
            observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting && hasMoreLogs && !isLoading) {
                        loadMoreLogs();
                    }
                });
            }, options);
            
            const observerElement = document.getElementById('scrollObserver');
            if (observerElement) {
                observer.observe(observerElement);
            }
        }
        
        function checkScrollPosition() {
            const container = document.querySelector('.log-entries-container');
            const scrollTop = container.scrollTop;
            const scrollHeight = container.scrollHeight;
            const clientHeight = container.clientHeight;
            
            // 如果距离底部小于100px，则认为接近底部
            isNearBottom = (scrollHeight - scrollTop - clientHeight) < 100;
            
            // 显示或隐藏"滚动到底部"按钮
            const scrollButton = document.getElementById('scrollToBottom');
            if (isNearBottom) {
                scrollButton.classList.remove('visible');
                if (autoScrollEnabled) {
                    scrollToBottom();
                }
            } else {
                scrollButton.classList.add('visible');
            }
        }
        
        // 设置滚动到底部按钮
        function setupScrollToBottom() {
            // 初始检查位置
            checkScrollPosition();
        }
        
        // 滚动到底部
        function scrollToBottom() {
            const container = document.querySelector('.log-entries-container');
            container.scrollTop = container.scrollHeight;
        }
        
        // 切换自动滚动
        function toggleAutoScroll() {
            autoScrollEnabled = !autoScrollEnabled;
            const button = document.getElementById('autoScrollBtn');
            
            if (autoScrollEnabled) {
                button.classList.add('active');
                button.title = "自动滚动已启用";
                scrollToBottom();
            } else {
                button.classList.remove('active');
                button.title = "自动滚动已禁用";
            }
        }
        
        // Update selected levels from checkboxes
        function updateSelectedLevels() {
            selectedLevels = Array.from(document.querySelectorAll('.level-checkbox:checked'))
                .map(checkbox => checkbox.value.toUpperCase());
            console.log('Selected levels:', selectedLevels);
        }
        
        // Load initial data
        function loadInitialData() {
            fetchModuleHierarchy();
            fetchLogs(true);
            updateStats();
        }
        
        // Fetch module hierarchy
        function fetchModuleHierarchy() {
            fetch('/logger/api/modules')
                .then(response => {
                    if (!response.ok) throw new Error('Network response was not ok');
                    return response.json();
                })
                .then(data => {
                    renderModuleTree(data.hierarchy);
                })
                .catch(error => {
                    console.error('Error fetching module hierarchy:', error);
                    document.getElementById('moduleTree').innerHTML = 
                        '<div class="text-center text-danger">Error loading modules</div>';
                });
        }
        
        // Refresh modules
        function refreshModules() {
            const moduleTree = document.getElementById('moduleTree');
            moduleTree.innerHTML = '<div class="text-center text-muted"><i class="fas fa-spinner fa-spin"></i> Refreshing modules...</div>';
            
            fetchModuleHierarchy();
        }
        
        // Render module tree with checkboxes
        function renderModuleTree(hierarchy) {
            const treeContainer = document.getElementById('moduleTree');
            
            // Clear existing content
            treeContainer.innerHTML = '';
            
            // Create select all/none buttons
            const buttonGroup = document.createElement('div');
            buttonGroup.className = 'btn-group w-100 mb-2';
            buttonGroup.innerHTML = `
                <button class="btn btn-sm btn-outline-primary" onclick="selectAllModules()">Select All</button>
                <button class="btn btn-sm btn-outline-secondary" onclick="deselectAllModules()">Select None</button>
            `;
            treeContainer.appendChild(buttonGroup);
            
            // Create module list container
            const moduleList = document.createElement('div');
            moduleList.className = 'module-list';
            moduleList.style.maxHeight = '250px';
            moduleList.style.overflowY = 'auto';
            
            // Function to recursively render modules
            function renderModules(modules, parentKey = 'root', level = 0) {
                const children = hierarchy[parentKey] || [];
                if (children.length === 0) return '';
                
                let html = '';
                children.forEach(module => {
                    const indent = level * 20;
                    html += `
                        <div class="form-check" style="margin-left: ${indent}px;">
                            <input class="form-check-input module-checkbox" type="checkbox" value="${module}" id="module-${module}">
                            <label class="form-check-label" for="module-${module}" title="${module}">
                                ${module.split('.').pop() || module}
                            </label>
                        </div>
                    `;
                    // Recursively render child modules
                    html += renderModules(modules, module, level + 1);
                });
                
                return html;
            }
            
            moduleList.innerHTML = renderModules(hierarchy);
            treeContainer.appendChild(moduleList);
            
            // Add event listeners to checkboxes
            document.querySelectorAll('.module-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', updateSelectedModules);
            });
            
            updateSelectedModules();
        }
        
        // Select all modules
        function selectAllModules() {
            document.querySelectorAll('.module-checkbox').forEach(checkbox => {
                checkbox.checked = true;
            });
            updateSelectedModules();
        }
        
        // Deselect all modules
        function deselectAllModules() {
            document.querySelectorAll('.module-checkbox').forEach(checkbox => {
                checkbox.checked = false;
            });
            updateSelectedModules();
        }
        
        // Update selected modules array
        function updateSelectedModules() {
            selectedModules = Array.from(document.querySelectorAll('.module-checkbox:checked'))
                .map(checkbox => checkbox.value);
            console.log('Selected modules:', selectedModules);
        }
        
        // Apply filters and reload logs
        function applyFilters() {
            updateSelectedLevels();
            updateSelectedModules();
            updateFilterStatus();
            fetchLogs(true);
        }
        
        // Fetch logs with current filters
        function fetchLogs(reset = false) {
            if (isLoading) {
                console.log('Already loading logs, skipping request');
                return;
            }
            
            if (reset) {
                currentStart = 0;
                hasMoreLogs = true;
            }
            
            if (!hasMoreLogs) {
                console.log('No more logs to load');
                return;
            }
            
            isLoading = true;
            document.getElementById('loadStatus').textContent = 'Loading...';
            
            // Show loading indicator for initial load
            if (reset) {
                document.getElementById('initialLoading').style.display = 'block';
            }
            
            // Build query parameters
            const params = new URLSearchParams({
                start: currentStart,
                limit: currentLimit
            });
            
            // Add level filters
            selectedLevels.forEach(level => {
                params.append('level[]', level);
            });
            
            // Add module filters
            selectedModules.forEach(module => {
                params.append('module[]', module);
            });
            
            console.log('Fetching logs with params:', params.toString());
            
            fetch('/logger/api/logs?' + params.toString())
                .then(response => {
                    if (!response.ok) throw new Error('Network response was not ok');
                    return response.json();
                })
                .then(data => {
                    console.log('Received logs data:', data);
                    
                    if (reset) {
                        document.getElementById('logEntries').innerHTML = 
                            '<div class="scroll-observer" id="scrollObserver"></div>';
                    }
                    
                    const filteredLogs = filterLogs(data.logs);
                    renderLogs(filteredLogs, reset);
                    
                    currentStart += filteredLogs.length;
                    hasMoreLogs = data.hasMore;
                    totalEntries = data.total;
                    
                    // Update entry count
                    document.getElementById('entryCount').textContent = 
                        `${data.total.toLocaleString()} Entries`;
                    document.getElementById('mainEntryCount').textContent = 
                        `${data.total.toLocaleString()} Entries`;
                    
                    isLoading = false;
                    document.getElementById('loadStatus').textContent = '';
                    
                    const initialLoadingElement = document.getElementById('initialLoading');
                    if (initialLoadingElement) {
                        initialLoadingElement.style.display = 'none';
                    } else {
                        console.error('Error: Element with ID "initialLoading" was not found in the DOM.');
                    }
                    
                    // Re-setup observer after DOM update
                    if (observer) {
                        observer.disconnect();
                        const observerElement = document.getElementById('scrollObserver');
                        if (observerElement) {
                            observer.observe(observerElement);
                        }
                    }
                })
                .catch(error => {
                    console.error('Error fetching logs:', error);
                    isLoading = false;
                    document.getElementById('loadStatus').textContent = 'Error loading logs';
                    const initialLoadingElement = document.getElementById('initialLoading');
                    if (initialLoadingElement) {
                        initialLoadingElement.style.display = 'none';
                    } else {
                        console.error('Error: Element with ID "initialLoading" was not found in the DOM.');
                    }
                });
        }
        
        // 更新加载状态
        function updateLoadStatus(message, type = 'info') {
            const statusElement = document.getElementById('loadStatus');
            statusElement.textContent = message;
            
            // 根据类型设置颜色
            statusElement.className = '';
            if (type === 'error') {
                statusElement.classList.add('text-danger');
            } else if (type === 'warning') {
                statusElement.classList.add('text-warning');
            } else {
                statusElement.classList.add('text-muted');
            }
        }
        
        // 更新连接状态
        function updateConnectionStatus(status) {
            const statusElement = document.getElementById('connectionStatus');
            const collapsedStatusElement = document.getElementById('collapsedConnectionStatus');
            
            statusElement.className = 'status-indicator';
            collapsedStatusElement.className = 'status-indicator';
            
            switch(status) {
                case 'connected':
                    statusElement.classList.add('status-connected');
                    statusElement.innerHTML = '<span class="dot"></span><span>已连接</span>';
                    collapsedStatusElement.classList.add('status-connected');
                    collapsedStatusElement.innerHTML = '<span class="dot"></span><span>已连接</span>';
                    break;
                case 'connecting':
                    statusElement.classList.add('status-connecting');
                    statusElement.innerHTML = '<span class="dot"></span><span>连接中...</span>';
                    collapsedStatusElement.classList.add('status-connecting');
                    collapsedStatusElement.innerHTML = '<span class="dot"></span><span>连接中...</span>';
                    break;
                case 'disconnected':
                    statusElement.classList.add('status-disconnected');
                    statusElement.innerHTML = '<span class="dot"></span><span>已断开</span>';
                    collapsedStatusElement.classList.add('status-disconnected');
                    collapsedStatusElement.innerHTML = '<span class="dot"></span><span>已断开</span>';
                    break;
                case 'error':
                    statusElement.classList.add('status-disconnected');
                    statusElement.innerHTML = '<span class="dot"></span><span>连接错误</span>';
                    collapsedStatusElement.classList.add('status-disconnected');
                    collapsedStatusElement.innerHTML = '<span class="dot"></span><span>连接错误</span>';
                    break;
            }
        }
        
        // 设置事件源（Server-Sent Events）
        function setupEventSource() {
            if (eventSource) {
                eventSource.close();
            }
            
            updateConnectionStatus('connecting');
            
            const params = new URLSearchParams();
            selectedLevels.forEach(level => params.append('level[]', level));
            selectedModules.forEach(module => params.append('module[]', module));
            
            eventSource = new EventSource('/logger/api/stream?' + params.toString());
            
            eventSource.addEventListener('open', () => {
                console.log('SSE连接已建立');
                updateConnectionStatus('connected');
            });
            
            eventSource.addEventListener('error', (err) => {
                console.error('SSE连接错误:', err);
                updateConnectionStatus('error');
                // 尝试重新连接
                setTimeout(setupEventSource, 5000);
            });
            
            eventSource.onopen = function() {
                console.log('SSE连接已建立');
                updateConnectionStatus('connected');
                updateLoadStatus('实时更新中');
            };
            
            eventSource.onmessage = function(event) {
                if (!document.getElementById('autoRefresh').checked) return;
                
                try {
                    const log = JSON.parse(event.data);
                    
                    if (isLogVisible(log, selectedLevels, selectedModules)) {
                        addNewLogEntry(log);
                        
                        // 更新统计信息
                        totalEntries++;
                        document.getElementById('entryCount').textContent = 
                            `${totalEntries.toLocaleString()} Entries`;
                        document.getElementById('mainEntryCount').textContent = 
                            `${totalEntries.toLocaleString()} Entries`;
                    }
                } catch (error) {
                    console.error('解析SSE消息错误:', error);
                }
            };
            
            eventSource.onerror = function(error) {
                console.error('SSE连接错误:', error);
                
                if (eventSource.readyState === EventSource.CLOSED) {
                    updateConnectionStatus('disconnected');
                    updateLoadStatus('连接已关闭，5秒后重试...');
                    
                    // 5秒后重试连接
                    setTimeout(setupEventSource, 5000);
                } else {
                    updateConnectionStatus('error');
                    updateLoadStatus('连接错误，尝试重试...', 'error');
                }
            };
        }
        
        function isLogVisible(log, levels, modules) {
            const levelMatch = levels.includes(log.levelname);
            const moduleMatch = modules.length === 0 || modules.includes(log.module);
            return levelMatch && moduleMatch;
        }
        
        function filterLogs(logs) {
            return logs.filter(log => {
                const levelMatch = selectedLevels.includes(log.levelname);
                const moduleMatch = selectedModules.length === 0 || 
                                   selectedModules.includes(log.module);
                return levelMatch && moduleMatch;
            });
        }
        
        function updateFilterStatus() {
            const statusText = `${selectedLevels.join(', ')} ${selectedModules.length > 0 ? '| Modules: ' + selectedModules.join(', ') : ''}`;
            document.getElementById('filterStatus').textContent = statusText;
        }
        
        // 添加新的日志条目
        function addNewLogEntry(log) {
            if (!isLogVisible(log, selectedLevels, selectedModules)) {
                return;
            }
    
            const container = document.getElementById('logEntries');
            const logElement = createLogElement(log);
            
            // 添加到容器
            container.appendChild(logElement);
            
            // 如果自动滚动启用且用户接近底部，滚动到底部
            if (autoScrollEnabled && isNearBottom) {
                setTimeout(() => {
                    scrollToBottom();
                }, 50);
            }
            
            // 移除初始加载提示（如果存在）
            document.getElementById('initialLoading').style.display = 'none';
        }
        
        // 创建日志元素
        function createLogElement(log) {
            const logElement = document.createElement('div');
            logElement.className = `log-entry log-level-${log.levelname}`;
            
            let html = `<span class="timestamp">${log.asctime}</span>`;
            html += `<span class="level-badge badge-${log.levelname}">${log.levelname}</span>`;
            
            if (log.module) {
                html += `<span class="module" title="${log.module}">${log.module}</span>`;
            }
            
            html += `<span>${log.message}</span>`;
            
            if (log.funcName) {
                html += ` <small class="text-muted">(${log.funcName})</small>`;
            }
            
            logElement.innerHTML = html;
            return logElement;
        }
        
        // 渲染日志
        function renderLogs(logs, reset = false) {
            const container = document.getElementById('logEntries');
            
            if (reset) {
                container.innerHTML = '';
            }
            
            const fragment = document.createDocumentFragment();
            
            logs.forEach(log => {
                const logElement = createLogElement(log);
                fragment.appendChild(logElement);
            });
            
            if (reset) {
                container.appendChild(fragment);
            } else {
                // 在现有内容前添加新日志
                const firstChild = container.firstChild;
                container.insertBefore(fragment, firstChild);
            }
            
            // 添加滚动观察器（如果不存在）
            if (!document.getElementById('scrollObserver')) {
                const observerElement = document.createElement('div');
                observerElement.className = 'scroll-observer';
                observerElement.id = 'scrollObserver';
                container.appendChild(observerElement);
                
                if (observer) {
                    observer.observe(observerElement);
                }
            }
        }
        
        // Load more logs when scrolling up
        function loadMoreLogs() {
            if (!isLoading && hasMoreLogs) {
                fetchLogs(false);
            }
        }
        
        // Update statistics panel
        function updateStats() {
            fetch('/logger/api/stats')
                .then(response => {
                    if (!response.ok) throw new Error('Network response was not ok');
                    return response.json();
                })
                .then(data => {
                    let html = `
                        <div class="stats-item">
                            <span>Total Entries:</span>
                            <span class="stats-value">${data.totalEntries.toLocaleString()}</span>
                        </div>
                        <div class="stats-item">
                            <strong>Level Distribution:</strong>
                    `;
                    
                    for (const [level, count] of Object.entries(data.levelCounts)) {
                        const percentage = data.totalEntries > 0 ? 
                            ((count / data.totalEntries) * 100).toFixed(1) : 0;
                        html += `
                            <div class="stats-item">
                                <span>${level}:</span>
                                <span class="stats-value">${count.toLocaleString()} (${percentage}%)</span>
                            </div>
                        `;
                    }
                    
                    html += `</div>`;
                    
                    document.getElementById('statsPanel').innerHTML = html;
                })
                .catch(error => {
                    console.error('Error fetching stats:', error);
                    document.getElementById('statsPanel').innerHTML = 
                        '<div class="text-center text-danger">Error loading statistics</div>';
                });
        }
    </script>
</body>
</html>
"""