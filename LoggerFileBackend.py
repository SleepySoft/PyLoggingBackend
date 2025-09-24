import itertools
import os
import time
import json
import traceback
import threading
from collections import defaultdict, deque
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

from LoggerViewerTemplate import LOGGER_VIEWER


class LoggerBackend:
    LIMIT_BY_LINE = 1
    LIMIT_BY_SIZE = 2

    def __init__(self, monitoring_file_path: str, cache_limit_by: int, cache_limit_count: int):
        self.log_file = monitoring_file_path
        self.cache_limit_by = cache_limit_by
        self.cache_limit_count = cache_limit_count
        self.log_revision = 0
        self.file_position = 0
        self.last_validation_time = time.time()
        self.app = None

        # Initialize data structures
        self.log_cache = deque(maxlen=cache_limit_count if cache_limit_by == self.LIMIT_BY_LINE else None)
        self.module_hierarchy = defaultdict(set)
        self.level_index = defaultdict(list)
        self.module_index = defaultdict(list)
        self.cache_lock = threading.Lock()
        self.seen_modules = set()

        # Warm cache on startup
        self._warm_cache()

        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_log_file, daemon=True)
        self.monitor_thread.start()

    def start_service(self, host: str = '0.0.0.0', port: int = 5000, blocking: bool = False):
        """
        Start the Flask web service either in blocking mode or in a background thread.

        Args:
            host: Host address to bind the server to
            port: Port number to listen on
            blocking: If True, runs in foreground and blocks execution;
                     if False, runs in background thread
        """
        self.app = Flask(__name__)
        CORS(self.app)
        self._register_routes()

        if blocking:
            # Run in foreground (blocking)
            self.app.run(debug=True, host=host, port=port, use_reloader=False, threaded=True)
        else:
            # Run in background thread (non-blocking)
            import threading

            def run_flask():
                """Run Flask app in a separate thread"""
                self.app.run(
                    debug=True,
                    host=host,
                    port=port,
                    use_reloader=False,  # Required for thread operation[5](@ref)
                    threaded=True  # Enable multi-threading for request handling[1](@ref)
                )

            # Create and start daemon thread
            self.flask_thread = threading.Thread(
                target=run_flask,
                daemon=True  # Thread will exit when main program exits
            )
            self.flask_thread.start()

            # Wait briefly for server initialization
            time.sleep(1)
            print(f"Flask server running in background on http://{host}:{port}")

    def register_router(self, app: Flask) -> bool:
        if not self.app:
            self.app = app
            CORS(self.app)
            self._register_routes()
            return True
        else:
            # Already registered
            return False

    def _register_routes(self):
        self.app.add_url_rule('/logger/log_viewer', 'log_viewer', self.log_viewer)
        self.app.add_url_rule('/logger/api/logs', 'get_logs', self.get_logs, methods=['GET'])
        self.app.add_url_rule('/logger/api/modules', 'get_module_hierarchy', self.get_module_hierarchy, methods=['GET'])
        self.app.add_url_rule('/logger/api/stats', 'get_log_stats', self.get_log_stats, methods=['GET'])
        self.app.add_url_rule('/logger/api/stream', 'stream_logs', self.stream_logs)

    def _warm_cache(self):
        """Initialize cache with existing log content"""
        if not os.path.exists(self.log_file):
            return

        with open(self.log_file, 'r') as f:
            for line in f:
                self._process_log_line(line)
            self.file_position = f.tell()

    def _process_log_line(self, line: str):
        """Parse and index a single log line"""
        try:
            log_entry = json.loads(line.strip())
            with self.cache_lock:
                self.log_cache.append(log_entry)
                self.log_revision += 1

                # Update indexes
                level = log_entry.get('levelname', 'UNKNOWN')
                module = log_entry.get('module', '')

                self.level_index[level].append(log_entry)
                if module:
                    self.module_index[module].append(log_entry)
                    self._update_module_hierarchy(module)

        except json.JSONDecodeError:
            pass

    def _update_module_hierarchy(self, module_path: str):
        """Update module hierarchy with deduplication"""
        if module_path in self.seen_modules:
            return

        self.seen_modules.add(module_path)
        parts = module_path.split('.')
        for i in range(1, len(parts) + 1):
            parent = '.'.join(parts[:i - 1]) if i > 1 else 'root'
            child = '.'.join(parts[:i])
            self.module_hierarchy[parent].add(child)

    def _monitor_log_file(self):
        """Background thread to monitor log file changes"""
        while True:
            try:
                # Handle file rotation/truncation
                if not os.path.exists(self.log_file):
                    time.sleep(5)
                    continue

                file_size = os.path.getsize(self.log_file)
                if file_size < self.file_position:
                    self.file_position = 0  # Reset on file rotation

                with open(self.log_file, 'r') as f:
                    f.seek(self.file_position)
                    new_lines = f.readlines()

                    if new_lines:
                        for line in new_lines:
                            self._process_log_line(line)

                        self.file_position = f.tell()

                    # Periodic cache validation (every 60s)
                    current_time = time.time()
                    if current_time - self.last_validation_time > 60:
                        self._validate_cache_consistency()
                        self.last_validation_time = current_time

                    time.sleep(0.1)

            except Exception as e:
                print(f"Monitoring error: {e}")
                time.sleep(5)

    def _validate_cache_consistency(self):
        """Ensure cache and indexes remain synchronized"""
        with self.cache_lock:
            # Check if indexes match cache size
            level_index_count = sum(len(v) for v in self.level_index.values())
            module_index_count = sum(len(v) for v in self.module_index.values())

            if len(self.log_cache) != level_index_count or len(self.log_cache) != module_index_count:
                self._rebuild_indexes()

    def _rebuild_indexes(self):
        """Reconstruct indexes from cache after inconsistency"""
        self.level_index.clear()
        self.module_index.clear()
        self.module_hierarchy.clear()
        self.seen_modules.clear()

        for log in self.log_cache:
            level = log.get('levelname', 'UNKNOWN')
            module = log.get('module', '')

            self.level_index[level].append(log)
            if module:
                self.module_index[module].append(log)
                self._update_module_hierarchy(module)

    # ------------------------------------------ Web Service ------------------------------------------

    def log_viewer(self):
        return LOGGER_VIEWER  # Assuming this HTML template exists

    def get_logs(self):
        """Get logs with filtering and pagination"""
        try:
            start = int(request.args.get('start', 0))
            limit = int(request.args.get('limit', 100))
            level_filter = request.args.getlist('level[]')
            module_filter = request.args.getlist('module[]')
            revision = int(request.args.get('revision', 0))

            with self.cache_lock:
                # Return empty if client has latest revision
                if revision >= self.log_revision:
                    return jsonify({
                        'logs': [],
                        'total': len(self.log_cache),
                        'start': start,
                        'limit': limit,
                        'revision': self.log_revision,
                        'hasMore': False
                    })

                # Use indexes for efficient filtering
                filtered_logs = []
                if level_filter and module_filter:
                    # Combined filter
                    level_sets = [set(self.level_index[l]) for l in level_filter]
                    module_sets = [set(self.module_index[m]) for m in module_filter]
                    filtered_logs = list(set.intersection(*level_sets, *module_sets))
                elif level_filter:
                    # Level filter only
                    filtered_logs = [log for l in level_filter for log in self.level_index[l]]
                elif module_filter:
                    # Module filter only
                    filtered_logs = [log for m in module_filter for log in self.module_index[m]]
                else:
                    # No filters
                    filtered_logs = list(self.log_cache)

                # Apply pagination
                total = len(filtered_logs)
                filtered_logs.reverse()  # Newest first
                result_logs = filtered_logs[start:start + limit]

                return jsonify({
                    'logs': result_logs,
                    'total': total,
                    'start': start,
                    'limit': limit,
                    'revision': self.log_revision,
                    'hasMore': (start + limit) < total
                })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    def get_module_hierarchy(self):
        with self.cache_lock:
            return jsonify({
                'hierarchy': {k: list(v) for k, v in self.module_hierarchy.items()},
                'revision': self.log_revision
            })

    def get_log_stats(self):
        with self.cache_lock:
            level_counts = {level: len(logs) for level, logs in self.level_index.items()}
            module_counts = {module: len(logs) for module, logs in self.module_index.items()}

            return jsonify({
                'totalEntries': len(self.log_cache),
                'levelCounts': level_counts,
                'moduleCounts': module_counts,
                'revision': self.log_revision
            })

    def stream_logs(self):
        """Server-sent events with revision-based updates"""

        def event_stream():
            last_count = len(self.log_cache)
            last_revision = self.log_revision
            last_heartbeat = time.time()

            while True:
                current_time = time.time()
                # 每15秒发送一次心跳
                if current_time - last_heartbeat >= 15:
                    yield ": heartbeat\n\n"  # SSE心跳（空注释行）
                    last_heartbeat = current_time

                with self.cache_lock:
                    if last_revision != self.log_revision:
                        new_logs = itertools.islice(self.log_cache, last_count, None)
                        for log in new_logs:
                            yield f"data: {json.dumps(log)}\n\n"
                        last_revision = self.log_revision

                time.sleep(0.5)

        return Response(event_stream(), mimetype='text/event-stream')


# ----------------------------------------------------------------------------------------------------------------------

def main():
    # Standalone service
    backend = LoggerBackend(
        monitoring_file_path="application.log",
        cache_limit_by=LoggerBackend.LIMIT_BY_LINE,
        cache_limit_count=10000
    )
    backend.start_service(blocking=True)

    # Integration with existing Flask app
    # app = Flask(__name__)
    # backend = LoggerBackend(
    #     monitoring_file_path="app.log",
    #     cache_limit_by=LoggerBackend.LIMIT_BY_SIZE,
    #     cache_limit_count=10485760,  # 10MB
    #     start_service=False
    # )
    # backend.register_router(app)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(str(e))
        print(traceback.format_exc())
    finally:
        pass
