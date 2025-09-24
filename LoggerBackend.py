import os
import time
import json
import threading
import traceback
from collections import defaultdict
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

from LoggerViewerTemplate import LOGGER_VIEWER
from LogFileWrapper import LogFileWrapper  # Import the LogFileWrapper class


class LoggerBackend:
    LIMIT_BY_LINE = 1
    LIMIT_BY_SIZE = 2

    def __init__(self, monitoring_file_path: str, cache_limit_by: int, cache_limit_count: int):
        self.log_file = monitoring_file_path
        self.cache_limit_by = cache_limit_by
        self.cache_limit_count = cache_limit_count
        self.log_revision = 0
        self.last_validation_time = time.time()
        self.flask_thread = None
        self.app = None

        # Initialize data structures
        self.module_hierarchy = defaultdict(set)
        self.level_index = defaultdict(list)
        self.module_index = defaultdict(list)
        self.cache_lock = threading.Lock()
        self.seen_modules = set()

        # Use LogFileWrapper for file monitoring and log storage
        self.log_wrapper = LogFileWrapper(
            file_path=monitoring_file_path,
            limit=cache_limit_count if cache_limit_by == self.LIMIT_BY_LINE else 0
        )

        # Start processing thread to handle new log entries
        self.processing_thread = threading.Thread(target=self._process_new_entries, daemon=True)
        self.processing_thread.start()

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
            def run_flask():
                """Run Flask app in a separate thread"""
                self.app.run(
                    debug=True,
                    host=host,
                    port=port,
                    use_reloader=False,
                    threaded=True
                )

            # Create and start daemon thread
            self.flask_thread = threading.Thread(
                target=run_flask,
                daemon=True
            )
            self.flask_thread.start()

            # Wait briefly for server initialization
            time.sleep(1)
            print(f"Logger viewer is running on http://{host}:{port}/logger/log_viewer")

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

    def _process_log_entry(self, log_entry: dict):
        """Index a single log entry"""
        with self.cache_lock:
            self.log_revision += 1

            # Update indexes
            level = log_entry.get('levelname', 'UNKNOWN')
            module = log_entry.get('module', '')

            self.level_index[level].append(log_entry)
            if module:
                self.module_index[module].append(log_entry)
                self._update_module_hierarchy(module)

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

    def _process_new_entries(self):
        """Background thread to process new log entries from LogFileWrapper"""
        # Create a session to track new entries
        session = self.log_wrapper.get_start_session()

        while True:
            try:
                # Get new log entries since last check
                new_entries = self.log_wrapper.get_realtime_logs(session, 100)

                if new_entries:
                    for entry in new_entries:
                        self._process_log_entry(entry)

                # Periodic cache validation (every 60s)
                current_time = time.time()
                if current_time - self.last_validation_time > 60:
                    self._validate_cache_consistency()
                    self.last_validation_time = current_time

                time.sleep(0.1)
            except Exception as e:
                print(f"Processing error: {e}")
                time.sleep(5)

    def _validate_cache_consistency(self):
        """Ensure cache and indexes remain synchronized"""
        with self.cache_lock:
            # Check if indexes match the number of entries in LogFileWrapper
            level_index_count = sum(len(v) for v in self.level_index.values())
            module_index_count = sum(len(v) for v in self.module_index.values())
            log_wrapper_count = len(self.log_wrapper.log_entries)

            if log_wrapper_count != level_index_count or log_wrapper_count != module_index_count:
                self._rebuild_indexes()

    def _rebuild_indexes(self):
        """Reconstruct indexes from LogFileWrapper after inconsistency"""
        with self.cache_lock:
            self.level_index.clear()
            self.module_index.clear()
            self.module_hierarchy.clear()
            self.seen_modules.clear()
            self.log_revision = 0

            # Rebuild indexes from all entries in LogFileWrapper
            for log in self.log_wrapper.log_entries:
                self._process_log_entry(log)

    # ------------------------------------------ Web Service ------------------------------------------

    def log_viewer(self):
        return LOGGER_VIEWER

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
                        'total': len(self.log_wrapper.log_entries),
                        'start': start,
                        'limit': limit,
                        'revision': self.log_revision,
                        'hasMore': False
                    })

                # Get all entries from LogFileWrapper
                all_entries = list(self.log_wrapper.log_entries)

                # Apply filters
                filtered_logs = []
                for entry in reversed(all_entries):  # Newest first
                    level_match = not level_filter or entry.get('levelname', 'UNKNOWN') in level_filter
                    module_match = not module_filter or entry.get('module', '') in module_filter

                    if level_match and module_match:
                        filtered_logs.append(entry)

                # Apply pagination
                total = len(filtered_logs)
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
                'totalEntries': len(self.log_wrapper.log_entries),
                'levelCounts': level_counts,
                'moduleCounts': module_counts,
                'revision': self.log_revision
            })

    def stream_logs(self):
        """Server-sent events with revision-based updates"""

        def event_stream():
            last_revision = self.log_revision
            last_heartbeat = time.time()

            while True:
                current_time = time.time()
                # Send heartbeat every 15 seconds
                if current_time - last_heartbeat >= 15:
                    yield ": heartbeat\n\n"
                    last_heartbeat = current_time

                with self.cache_lock:
                    if last_revision != self.log_revision:
                        # Get all entries since last revision
                        all_entries = list(self.log_wrapper.log_entries)
                        new_entries = []

                        # Find new entries (simplified approach)
                        # In a real implementation, we'd track which entries were already sent
                        for entry in reversed(all_entries):
                            # This is a simplified approach - in production you'd need a better way
                            # to track which entries have been sent to this client
                            new_entries.append(entry)
                            if len(new_entries) >= 100:  # Limit batch size
                                break

                        for log in reversed(new_entries):  # Send in chronological order
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
