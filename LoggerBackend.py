import logging
import os
import time
import json
import logging
import argparse
import traceback
import threading
from collections import defaultdict
from flask import Flask, request, jsonify, Response, send_file, send_from_directory, abort
from flask_cors import CORS

if __name__ == '__main__':
    from LogFileWrapper import LogFileWrapper
else:
    from .LogFileWrapper import LogFileWrapper

logger = logging.getLogger(__name__)
self_path = os.path.dirname(os.path.abspath(__file__))


class LoggerBackend:
    def __init__(self,
                 monitoring_file_path: str,
                 cache_limit_count: int,
                 link_file_roots: dict = None,
                 project_root: str | None = None,
                 with_logger_manager: bool = False):

        self.log_file = monitoring_file_path
        self.cache_limit_count = cache_limit_count

        # If you run LoggerBackend standalone. LoggerManager is useless.
        if with_logger_manager:
            if __name__ == '__main__':
                from LoggerManager import LoggerManager
            else:
                from .LoggerManager import LoggerManager
            self.logger_manager = LoggerManager(project_root)
        else:
            self.logger_manager = None

        self.last_validation_time = time.time()
        self.flask_thread = None
        self.app = None
        self.cache_lock = threading.Lock()

        # Use LogFileWrapper for file monitoring and log storage
        self.log_wrapper = LogFileWrapper(file_path=monitoring_file_path, limit=cache_limit_count)

        # Track last processed ID for background processing
        self.last_processed_id = -1

        # Process and store the safe, absolute paths for the link file directories
        self.link_file_roots = {}
        if link_file_roots:
            for alias, path in link_file_roots.items():
                # Storing the absolute path is crucial for security checks
                self.link_file_roots[alias] = os.path.abspath(path)
                print(f"Registered link file alias '{alias}' -> '{self.link_file_roots[alias]}'")

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
        self._register_routes(wrapper=None)

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

    def register_router(self, app: Flask, wrapper=None) -> bool:
        if not self.app:
            self.app = app
            self.app.secret_key = os.urandom(24)  # Secret key for session management
            CORS(self.app)
            self._register_routes(wrapper)
            return True
        else:
            # Already registered
            return False

    def _register_routes(self, wrapper):
        def maybe_wrap(fn):
            return wrapper(fn) if wrapper else fn

        self.app.add_url_rule('/logger/log_viewer', 'log_viewer', maybe_wrap(self.log_viewer))
        self.app.add_url_rule('/logger/api/logs', 'get_logs', maybe_wrap(self.get_logs), methods=['GET'])
        self.app.add_url_rule('/logger/api/modules', 'get_module_hierarchy', maybe_wrap(self.get_module_hierarchy),
                              methods=['GET'])
        self.app.add_url_rule('/logger/api/stats', 'get_log_stats', maybe_wrap(self.get_log_stats), methods=['GET'])
        self.app.add_url_rule('/logger/api/stream', 'stream_logs', maybe_wrap(self.stream_logs))

        # Register the new route for serving linked files.
        # The <path:filepath> converter allows slashes in the filepath variable.
        self.app.add_url_rule(
            '/logger/link_file/<path:filepath>',
            'serve_link_file',
            maybe_wrap(self.serve_link_file),
            methods=['GET']
        )

        if self.logger_manager:
            self.app.add_url_rule('/logger/logger_config', 'logger_config', maybe_wrap(self.logger_config))
            self.app.add_url_rule('/logger/api/get_loggers', 'get_loggers', maybe_wrap(self.get_loggers), methods=['GET'])
            self.app.add_url_rule('/logger/api/config_logger', 'config_logger', maybe_wrap(self.config_logger), methods=['POST'])

    # ------------------------------------------ Web Service ------------------------------------------

    def log_viewer(self):
        return send_file(os.path.join(self_path, 'LoggerViewer.html'))

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
            start_log_id = max(0, start_log_id)

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
        last_log_id_arg = request.args.get('last_log_id')

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

    def serve_link_file(self, filepath: str):
        """
        Securely serves a file from one of the configured link_file_roots.

        This function prevents directory traversal attacks by checking if the requested
        path is within a registered safe directory.

        Args:
            filepath (str): The path provided in the URL, e.g., "appendix_a/file1.bin".

        Returns:
            A file response or a 404 error if the file is not found or not allowed.
        """
        # The filepath must contain a slash to separate the alias from the subpath.
        if '/' not in filepath:
            abort(404)

        # Split the path into the alias (e.g., "appendix_a") and the subpath (e.g., "file1.bin").
        alias, subpath = filepath.split('/', 1)

        # Look up the registered root directory for the given alias.
        root_directory = self.link_file_roots.get(alias)

        # If the alias is not configured, it's a "Not Found" error.
        if not root_directory:
            abort(404)

        try:
            # Use Flask's send_from_directory, which is the safest way to send files.
            # It automatically handles security checks to prevent access to files
            # outside of the specified `root_directory`.
            return send_from_directory(root_directory, subpath, as_attachment=True)
        except FileNotFoundError:
            abort(404)

    # --------------------------------- Logger Manager Related ---------------------------------

    def logger_config(self):
        return send_file(os.path.join(self_path, 'LoggerConfig.html'))

    def get_loggers(self):
        """Get all logger information"""
        try:
            loggers = self.logger_manager.get_all_loggers()
            return jsonify({'success': True, 'loggers': loggers})
        except Exception as e:
            print(str(e))
            print(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)})

    def config_logger(self):
        """Update logger configuration for one or multiple loggers.

        Supports two parameters:
        - 'name': Single logger name (for backward compatibility)
        - 'names': List of logger names
        At least one of these must be provided.
        """
        try:
            data = request.get_json()
            # Extract parameters
            logger_name = data.get('name')
            logger_names = data.get('names')
            level = data.get('level')
            enabled = data.get('enabled', True)

            # Validate at least one name parameter exists
            if not logger_name and not logger_names:
                return jsonify({
                    'success': False,
                    'error': 'Must provide either "name" or "names" parameter'
                })

            # Create combined list of names to process
            names_to_update = []
            if logger_names:
                if isinstance(logger_names, list):
                    names_to_update.extend(logger_names)
                else:
                    return jsonify({
                        'success': False,
                        'error': '"names" must be a list of strings'
                    })
            if logger_name:
                names_to_update.append(logger_name)

            # Process each logger
            success_count = 0
            for name in names_to_update:
                if not name:
                    continue  # Skip empty names
                if self.logger_manager.set_logger_level(name, level, enabled):
                    logger.info(f"Logger '{name}' updated: level={level}, enabled={enabled}")
                    success_count += 1

            # Return results
            total = len(names_to_update)
            if success_count == total:
                return jsonify({
                    'success': True,
                    'message': f'Successfully updated {success_count} loggers'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'Updated {success_count}/{total} loggers',
                    'updated_count': success_count,
                    'failed_count': total - success_count
                })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})


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
        cache_limit_count=args.cache_limit_count,
        with_logger_manager=True
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
