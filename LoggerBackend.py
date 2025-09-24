import os
import time
import json
import traceback
import threading
from collections import defaultdict
from flask import Flask, request, jsonify, Response, session, send_file
from flask_cors import CORS

from LogFileWrapper import LogFileWrapper  # Import the updated LogFileWrapper class


class LoggerBackend:
    def __init__(self, monitoring_file_path: str, cache_limit_count: int):
        self.log_file = monitoring_file_path
        self.cache_limit_count = cache_limit_count
        self.last_validation_time = time.time()
        self.flask_thread = None
        self.app = None
        self.cache_lock = threading.Lock()

        # Use LogFileWrapper for file monitoring and log storage
        self.log_wrapper = LogFileWrapper(file_path=monitoring_file_path, limit=cache_limit_count)

        # Track last processed ID for background processing
        self.last_processed_id = -1

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
        self.app.secret_key = os.urandom(24)  # Secret key for session management
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
            print(f"Flask server running in background on http://{host}:{port}")

    def register_router(self, app: Flask) -> bool:
        if not self.app:
            self.app = app
            self.app.secret_key = os.urandom(24)  # Secret key for session management
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

    # ------------------------------------------ Web Service ------------------------------------------

    def log_viewer(self):
        return send_file('LoggerViewer.html')

    def get_module_hierarchy(self):
        with self.cache_lock:
            module_hierarchy = self.log_wrapper.get_module_hierarchy()
            return jsonify({
                'hierarchy': {k: list(v) for k, v in module_hierarchy.items()},
            })

    def get_log_stats(self):
        # Get all entries with filtering applied
        total_entries = self.log_wrapper.get_total_count()
        logs = self.log_wrapper.get_logs(
            start_id=0,
            count=total_entries
        )

        # Calculate statistics
        level_counts = defaultdict(int)
        module_counts = defaultdict(int)

        for entry in logs:
            level = entry.get('levelname', 'UNKNOWN')
            module = entry.get('module', '')

            level_counts[level] += 1
            if module:
                module_counts[module] += 1

        return jsonify({
            'totalEntries': total_entries,
            'levelCounts': level_counts,
            'moduleCounts': module_counts,
        })

    def get_logs(self):
        """Get logs with filtering and pagination using _id"""
        try:
            start_arg = request.args.get('start')
            limit = int(request.args.get('limit', 100))
            level_filter = request.args.getlist('level[]')
            module_filter = request.args.getlist('module[]')

            # Get total number of entries
            total_entries = self.log_wrapper.get_total_count()

            if start_arg is not None:
                start = int(start_arg)
            else:
                newest_id = self.log_wrapper.get_newest_log_id()
                start = newest_id - limit

            # # Calculate range to fetch (newest first)
            # end_index = total_entries - 1
            # start_index = max(0, end_index - start - limit + 1)
            # count = min(limit, end_index - start_index + 1)

            # Fetch log entries using _id
            logs = self.log_wrapper.get_logs(
                start_id=start,
                count=limit,
                filter_func=lambda entry: (
                        (not level_filter or entry.get('levelname', 'UNKNOWN') in level_filter) and
                        (not module_filter or (entry.get('module', '') + '.' + entry.get('name', '')) in module_filter)
                )
            )

            return jsonify({
                'logs': logs,
                'total': total_entries,
                'start': start,
                'limit': limit,
                'hasMore': (start + limit) < total_entries
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    def stream_logs(self):
        """Server-sent events with _id based updates"""
        # Get last_id from query parameter or session
        last_id = request.args.get('last_id', -1, type=int)
        if last_id < 0 :
            last_id = self.log_wrapper.get_newest_log_id()

        def event_stream():
            current_last_id = last_id
            last_heartbeat = time.time()

            while True:
                current_time = time.time()
                # Send heartbeat every 15 seconds
                if current_time - last_heartbeat >= 15:
                    yield ": heartbeat\n\n"
                    last_heartbeat = current_time

                # Check for new entries
                if self.log_wrapper.check_updates(current_last_id):
                    new_entries = self.log_wrapper.get_logs(
                        start_id=current_last_id + 1,
                        count=100
                    )

                    for entry in new_entries:
                        current_last_id = entry['_id']
                        yield f"data: {json.dumps(entry)}\n\n"

                time.sleep(0.5)

        return Response(event_stream(), mimetype='text/event-stream')


# ----------------------------------------------------------------------------------------------------------------------

def main():
    # Standalone service
    backend = LoggerBackend(
        monitoring_file_path="application.log",
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
