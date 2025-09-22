import traceback

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import os
import time
import json
import threading
from collections import defaultdict
from pathlib import Path

from LoggerViewerTemplate import LOGGER_VIEWER

app = Flask(__name__)
CORS(app)

# Configuration
LOG_FILE = "application.log"
MAX_LINES = 1000
CHUNK_SIZE = 100
LOG_CACHE = []
LOG_CACHE_LOCK = threading.Lock()
FILE_POSITION = 0
MODULE_HIERARCHY = defaultdict(set)


def monitor_log_file():
    """Background thread to monitor log file for changes"""
    global FILE_POSITION, LOG_CACHE, MODULE_HIERARCHY

    while True:
        try:
            with open(LOG_FILE, 'r') as f:
                f.seek(FILE_POSITION)
                new_lines = f.readlines()

                if new_lines:
                    with LOG_CACHE_LOCK:
                        for line in new_lines:
                            try:
                                log_entry = json.loads(line.strip())
                                LOG_CACHE.append(log_entry)

                                # Update module hierarchy
                                if 'module' in log_entry:
                                    module_parts = log_entry['module'].split('.')
                                    for i in range(1, len(module_parts) + 1):
                                        parent = '.'.join(module_parts[:i - 1]) if i > 1 else 'root'
                                        child = '.'.join(module_parts[:i])
                                        MODULE_HIERARCHY[parent].add(child)

                            except json.JSONDecodeError:
                                continue

                        # if len(LOG_CACHE) > MAX_LINES:
                        #     LOG_CACHE = LOG_CACHE[-MAX_LINES:]

                    FILE_POSITION = f.tell()

                time.sleep(0.5)
        except FileNotFoundError:
            time.sleep(5)
        except Exception as e:
            print(f"Error in log monitoring: {e}")
            time.sleep(5)


@app.route('/log_viewer', methods=['GET'])
def log_viewer() -> str:
    return LOGGER_VIEWER


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get logs with filtering and pagination"""
    try:
        start = int(request.args.get('start', 0))
        limit = int(request.args.get('limit', CHUNK_SIZE))
        level_filter = request.args.getlist('level[]')
        module_filter = request.args.getlist('module[]')

        with LOG_CACHE_LOCK:
            filtered_logs = LOG_CACHE

            # Apply level filter (multiple levels)
            if level_filter:
                filtered_logs = [log for log in filtered_logs
                                 if log.get('levelname', '').upper() in [l.upper() for l in level_filter]]

            # Apply module filter
            if module_filter:
                filtered_logs = [log for log in filtered_logs
                                 if any(log.get('module', '').startswith(m) for m in module_filter)]

            # Reverse order (newest first for display)
            filtered_logs.reverse()

            # Apply pagination
            end_index = min(start + limit, len(filtered_logs))
            result_logs = filtered_logs[start:end_index]

            return jsonify({
                'logs': result_logs,
                'total': len(filtered_logs),
                'start': start,
                'limit': limit,
                'hasMore': end_index < len(filtered_logs)
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/modules', methods=['GET'])
def get_module_hierarchy():
    """Get the module hierarchy for tree display"""
    with LOG_CACHE_LOCK:
        return jsonify({
            'hierarchy': {k: list(v) for k, v in MODULE_HIERARCHY.items()}
        })


@app.route('/api/stats', methods=['GET'])
def get_log_stats():
    """Get statistics about logs"""
    with LOG_CACHE_LOCK:
        level_counts = defaultdict(int)
        module_counts = defaultdict(int)

        for log in LOG_CACHE:
            level_counts[log.get('levelname', 'UNKNOWN')] += 1
            if 'module' in log:
                module_counts[log['module']] += 1

        return jsonify({
            'totalEntries': len(LOG_CACHE),
            'levelCounts': dict(level_counts),
            'moduleCounts': dict(module_counts)
        })


@app.route('/api/stream')
def stream_logs():
    """Server-sent events for real-time log updates"""

    def event_stream():
        last_count = len(LOG_CACHE)
        last_heartbeat = time.time()

        while True:
            current_time = time.time()
            # 每15秒发送一次心跳
            if current_time - last_heartbeat >= 15:
                yield ": heartbeat\n\n"  # SSE心跳（空注释行）
                last_heartbeat = current_time

            with LOG_CACHE_LOCK:
                current_count = len(LOG_CACHE)
                if current_count > last_count:
                    new_logs = LOG_CACHE[last_count:]
                    for log in new_logs:
                        yield f"data: {json.dumps(log)}\n\n"
                    last_count = current_count

            time.sleep(0.5)

    return Response(event_stream(), mimetype='text/event-stream')


if __name__ == '__main__':
    try:
        # Start log monitoring thread
        monitor_thread = threading.Thread(target=monitor_log_file, daemon=True)
        monitor_thread.start()

        app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
    except Exception as e:
        print(str(e))
        print(traceback.format_exc())
    finally:
        pass
