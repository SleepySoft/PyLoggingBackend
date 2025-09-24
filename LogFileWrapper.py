import os
import time
import json
import itertools
import threading
from collections import deque, defaultdict
from typing import List, Dict, Any, Deque, Tuple, Optional, Callable


class LogFileWrapper:
    """
    Monitors, analyzes and caches log file content with rotation handling.
    Provides indexed access to log entries using _id field.
    """

    def __init__(self, file_path: str, limit: int = 10000):
        """
        Initialize the LogFileWrapper with a file to monitor.

        Args:
            file_path: Path to the log file to monitor
            limit: Maximum number of log entries to keep in cache
        """
        self.file_path = file_path
        self.limit = limit
        self.log_entries: Deque[Dict[str, Any]] = deque(maxlen=limit)
        self.next_id = 0  # Next available _id for new log entries
        self.file_position = 0
        self.lock = threading.RLock()
        self._monitor_running = True
        self._file_id: Optional[Tuple[int, int]] = None  # (dev, inode)
        self._no_changes_count = 0
        self._sleep_duration = 0.1

        self.module_hierarchy = defaultdict(set)
        self.seen_modules = set()

        # Initialize with existing file content
        self._load_initial_entries()

        # Start file monitoring thread
        self.monitor_thread = threading.Thread(
            target=self._monitor_file,
            daemon=True
        )
        self.monitor_thread.start()

    def __del__(self):
        """Ensure clean shutdown"""
        self.stop_monitoring()

    def _load_initial_entries(self) -> None:
        """Load initial entries from log file if exists"""
        if not os.path.exists(self.file_path):
            return

        try:
            # Capture file identity for rotation detection
            self._update_file_id()

            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                if self.limit > 0:
                    # Efficiently read last 'limit' lines
                    last_lines = deque(f, maxlen=self.limit)
                else:
                    last_lines = list(f)

                self._append_log_entries([line.strip() for line in last_lines])
                self.file_position = f.tell()
        except Exception as e:
            print(f"Initial load error: {e}")

    def _update_file_id(self) -> None:
        """Update file identity tracking"""
        try:
            stat = os.stat(self.file_path)
            self._file_id = (stat.st_dev, stat.st_ino)
        except FileNotFoundError:
            self._file_id = None

    def _append_log_entries(self, lines: List[str]) -> None:
        """Append multiple log entries to cache with _id"""
        if not lines:
            return

        entries = []
        for line in lines:
            try:
                # Try to parse as JSON, fallback to raw text
                try:
                    entry = json.loads(line)
                    module = entry.get('module', '')
                    name = entry.get('name', '')
                    if module:
                        self._update_module_hierarchy(module + '.' + name)
                except json.JSONDecodeError:
                    entry = {"raw": line, "timestamp": time.time()}

                # Add unique _id to each entry
                entry['_id'] = self.next_id
                self.next_id += 1
                entries.append(entry)
            except Exception as e:
                print(f"Error processing log line: {e}")

        with self.lock:
            self.log_entries.extend(entries)

    def _check_rotation(self) -> bool:
        """Check if file rotation has occurred"""
        if not os.path.exists(self.file_path):
            return True

        try:
            current_stat = os.stat(self.file_path)
            current_id = (current_stat.st_dev, current_stat.st_ino)
            return self._file_id != current_id
        except FileNotFoundError:
            return True

    def _handle_rotation(self) -> None:
        """Handle file rotation scenario"""
        with self.lock:
            self.log_entries.clear()
            self.file_position = 0
            self._update_file_id()

    def _monitor_file(self) -> None:
        """Monitor log file for changes and rotations"""
        while self._monitor_running:
            try:
                # Reset backoff if changes detected
                if self._no_changes_count > 0:
                    self._sleep_duration = 0.1
                    self._no_changes_count = 0

                # Handle file disappearance
                if not os.path.exists(self.file_path):
                    with self.lock:
                        self.log_entries.clear()
                        self.file_position = 0
                        self._file_id = None
                    time.sleep(5)
                    continue

                # Check for file rotation
                if self._check_rotation():
                    self._handle_rotation()
                    # Reload from new file
                    self._load_initial_entries()
                    continue

                current_size = os.path.getsize(self.file_path)

                # Handle file truncation
                if current_size < self.file_position:
                    self._handle_rotation()
                    self._load_initial_entries()
                # Read new content if file has grown
                elif current_size > self.file_position:
                    with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(self.file_position)
                        new_lines = f.readlines()

                        if new_lines:
                            self._append_log_entries([line.strip() for line in new_lines])
                            with self.lock:
                                self.file_position = f.tell()
                else:
                    # Exponential backoff when no changes
                    self._no_changes_count += 1
                    self._sleep_duration = min(self._sleep_duration * 1.5, 10.0)

                time.sleep(self._sleep_duration)
            except Exception as e:
                print(f"File monitoring error: {e}")
                time.sleep(5)

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

    def get_module_hierarchy(self) -> dict:
        with self.lock:
            return self.module_hierarchy.copy()

    def stop_monitoring(self) -> None:
        """Stop monitoring thread gracefully"""
        self._monitor_running = False
        try:
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                print("Warning: Monitor thread did not terminate")
        except Exception as e:
            print(f"Error stopping monitoring thread: {e}")

    def get_logs(self, start_id: int, count: int,
                 filter_func: Optional[Callable[[Dict], bool]] = None) -> List[Dict[str, Any]]:
        """
        Retrieve log entries starting from specified _id

        Args:
            start_id: Minimum _id to return (inclusive)
            count: Maximum number of entries to return
            filter_func: Optional filter function to apply to entries

        Returns:
            List of log entries matching criteria
        """
        with self.lock:
            if not self.log_entries:
                return []

            # Find starting position in deque
            start_index = 0
            for i, entry in enumerate(self.log_entries):
                if entry['_id'] >= start_id:
                    start_index = i
                    break
            else:
                return []  # No entries match start_id

            # Collect matching entries
            result = []
            for entry in itertools.islice(self.log_entries, start_index, None):
                if len(result) >= count:
                    break
                if filter_func is None or filter_func(entry):
                    result.append(entry)
            return result

    def get_total_count(self, filter_func: Optional[Callable[[Dict], bool]] = None) -> int:
        """
        Get total number of log entries matching filter

        Args:
            filter_func: Optional filter function to apply

        Returns:
            Count of matching entries
        """
        with self.lock:
            if filter_func is None:
                return len(self.log_entries)
            return sum(1 for entry in self.log_entries if filter_func(entry))

    def check_updates(self, current_id: int) -> Dict[str, Any]:
        """
        Check if new logs are available since specified _id

        Args:
            current_id: Last known _id by client

        Returns:
            Dictionary with update information:
            {
                'has_updates': bool,
                'new_count': int,
                'min_id': int,
                'max_id': int
            }
        """
        with self.lock:
            if not self.log_entries:
                return {
                    'has_updates': False,
                    'new_count': 0,
                    'min_id': 0,
                    'max_id': 0
                }

            min_id = self.log_entries[0]['_id']
            max_id = self.log_entries[-1]['_id']
            new_count = max(0, max_id - max(min_id - 1, current_id))

            return {
                'has_updates': new_count > 0,
                'new_count': new_count,
                'min_id': min_id,
                'max_id': max_id
            }


# ----------------------------------------------------------------------------------------------------------------------

def print_log(log):
    if "message" in log:
        log_msg = f"{log.get('asctime', '')} [{log.get('levelname', 'UNKNOWN')}] {log['message']}"
    else:
        log_msg = log.get("raw", str(log))
    print(log_msg)


def main():
    # Configuration
    LOG_FILE = "application.log"
    MONITOR_INTERVAL = 0.1  # Check for new logs every second

    # Create log monitor instance
    log_monitor = LogFileWrapper(LOG_FILE, limit=1000)

    try:
        # Get initial logs
        current_id = -1
        logs = log_monitor.get_logs(start_id=0, count=1000)
        for log in logs:
            print_log(log)
            current_id = max(current_id, log['_id'])

        # Main monitoring loop
        while True:
            # Check for updates
            update_info = log_monitor.check_updates(current_id)

            if update_info['has_updates']:
                # Get new logs since last known id
                new_logs = log_monitor.get_logs(
                    start_id=current_id + 1,
                    count=update_info['new_count']
                )

                for log in new_logs:
                    print_log(log)
                    current_id = max(current_id, log['_id'])

            # Wait before next check
            time.sleep(MONITOR_INTERVAL)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        log_monitor.stop_monitoring()
        print("Log monitoring stopped")


if __name__ == "__main__":
    main()
