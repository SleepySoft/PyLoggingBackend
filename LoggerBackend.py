import os
import time
import json
import argparse
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
            start_log_id=0,
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
            start_arg = request.args.get('start_log_id')
            limit = int(request.args.get('limit', 100))
            level_filter = request.args.getlist('level[]')
            module_filter = request.args.getlist('module[]')

            if start_arg is not None:
                start_log_id = int(start_arg)
            else:
                newest_id = self.log_wrapper.get_newest_log_id()
                start_log_id = newest_id - limit

            filter_func = lambda entry: (
                    (not level_filter or entry.get('levelname', 'UNKNOWN') in level_filter) and
                    (not module_filter or (entry.get('module', '') + '.' + entry.get('name', '')) in module_filter)
            )

            # Fetch log entries using _id
            logs = self.log_wrapper.get_logs(start_log_id=start_log_id, count=limit, filter_func=filter_func)

            # Get total number of entries
            total_entries = self.log_wrapper.get_total_count(filter_func)
            newest_log_id = self.log_wrapper.get_newest_log_id()

            return jsonify({
                'logs': logs,
                'total': total_entries,
                'start': start_log_id,
                'limit': limit,
                'hasMore': logs and logs[-1]['_id'] < newest_log_id
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    def stream_logs(self):
        """Server-sent events with _id based updates"""
        # Get last_id from query parameter or session
        limit = int(request.args.get('limit', 100))
        last_log_id_arg  = request.args.get('last_log_id')

        last_log_id = int(last_log_id_arg) if last_log_id_arg is not None else None

        if not last_log_id or last_log_id < 0:
            newest_id = self.log_wrapper.get_newest_log_id()
            last_log_id = newest_id - limit

        def event_stream():
            current_last_id = last_log_id
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
                        start_log_id=current_last_id + 1,
                        count=limit
                    )

                    if new_entries:
                        current_last_id = new_entries[-1]['_id']
                        yield f"data: {json.dumps(new_entries)}\n\n"

                time.sleep(0.5)

        return Response(event_stream(), mimetype='text/event-stream')


# ----------------------------------------------------------------------------------------------------------------------

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='Logger Backend Service')

    parser.add_argument('-m', '--monitoring_file_path',
                        type=str,
                        default='application.log',
                        help='Path to the monitoring log file (default: application.log)')

    parser.add_argument('-c', '--cache_limit_count',
                        type=int,
                        default=10000,
                        help='Maximum cache limit count (default: 10000)')

    parser.add_argument('-p', '--port',
                        type=int,
                        default=5000,
                        help='Port number for the service (default: 5000)')

    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='Enable verbose output')

    args = parser.parse_args()

    # Standalone service with command line arguments
    backend = LoggerBackend(
        monitoring_file_path=args.monitoring_file_path,
        cache_limit_count=args.cache_limit_count
    )

    if args.verbose:
        print(
            f"Starting service on port {args.port} with log file: {args.monitoring_file_path}, cache limit: {args.cache_limit_count}")

    backend.start_service(port=args.port, blocking=True)

    # Example: Integration with existing Flask app
    # app = Flask(__name__)
    # backend = LoggerBackend(
    #     monitoring_file_path="application.log",
    #     cache_limit_count=10000
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
