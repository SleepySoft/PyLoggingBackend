import os
import time
import json
import itertools
import threading
from collections import deque
from typing import List, Dict, Any, Deque, Tuple, Optional


class LogSession:
    """Represents a client session for reading log entries"""

    def __init__(self, start_index: int, generation: int):
        self.start_entry_index = start_index
        self.current_entry_offset = 0
        self.generation = generation

    def advance_offset(self, delta: int):
        """Advance the read offset by specified delta"""
        self.current_entry_offset += delta

    def reset(self, new_index: int, new_generation: int):
        """Reset session to new starting position"""
        self.start_entry_index = new_index
        self.current_entry_offset = 0
        self.generation = new_generation

    def end_position(self) -> int:
        """Calculate current end position of the session"""
        return self.start_entry_index + self.current_entry_offset


class LogFileWrapper:
    """
    Monitors, analyzes and caches log file content with rotation handling.
    Provides indexed access to log entries with session-based reading.
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
        self.last_entry_index = -1
        self.file_position = 0
        self.generation = 0
        self.lock = threading.RLock()
        self._monitor_running = True
        self._file_id: Optional[Tuple[int, int]] = None  # (dev, inode)
        self._no_changes_count = 0
        self._sleep_duration = 0.1

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
        """Append multiple log entries to cache"""
        if not lines:
            return

        entries = []
        for line in lines:
            try:
                # Try to parse as JSON, fallback to raw text
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    entries.append({"raw": line, "timestamp": time.time()})
            except Exception as e:
                print(f"Error processing log line: {e}")

        with self.lock:
            self.log_entries.extend(entries)
            self.last_entry_index += len(entries)

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
            self.generation += 1
            self.log_entries.clear()
            self.last_entry_index = -1
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
                        self.generation += 1
                        self.log_entries.clear()
                        self.last_entry_index = -1
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

    def stop_monitoring(self) -> None:
        """Stop monitoring thread gracefully"""
        self._monitor_running = False
        try:
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                print("Warning: Monitor thread did not terminate")
        except Exception as e:
            print(f"Error stopping monitoring thread: {e}")

    def get_start_session(self) -> LogSession:
        """Create new session for reading logs"""
        with self.lock:
            return LogSession(
                start_index=self.last_entry_index,
                generation=self.generation
            )

    def has_updates(self, session: LogSession) -> bool:
        """Check if new entries exist since session creation"""
        with self.lock:
            return self.last_entry_index > session.end_position()

    def get_historical_logs(self, session: LogSession, offset: int, count: int) -> List[Dict[str, Any]]:
        """Get historical log entries relative to session start"""
        self._recover_session(session)
        requested_index = session.start_entry_index + offset + 1

        with self.lock:
            if not self.log_entries:
                return []

            # Calculate valid range
            oldest_index = max(0, self.last_entry_index - len(self.log_entries) + 1)
            if requested_index < oldest_index or requested_index > self.last_entry_index:
                return []

            # Convert to deque index
            entries_index = requested_index - oldest_index
            return self._get_logs_by_index(entries_index, count)

    def get_realtime_logs(self, session: LogSession, count: int) -> List[Dict[str, Any]]:
        """Get new log entries since last read in session"""
        self._recover_session(session)
        current_read_position = session.end_position()

        with self.lock:
            if not self.log_entries or current_read_position >= self.last_entry_index:
                return []

            # Calculate valid range
            oldest_index = max(0, self.last_entry_index - len(self.log_entries) + 1)
            new_entries_count = min(
                count,
                self.last_entry_index - current_read_position,
                len(self.log_entries) - (current_read_position - oldest_index)
            )

            if new_entries_count <= 0:
                return []

            # Get entries and update session
            entries_index = current_read_position - oldest_index
            result = self._get_logs_by_index(entries_index, new_entries_count)
            session.advance_offset(new_entries_count)
            return result

    def _get_logs_by_index(self, start_index: int, count: int = 100) -> List[Dict[str, Any]]:
        """Retrieve log entries by deque index"""
        with self.lock:
            if not self.log_entries:
                return []

            end_index = min(len(self.log_entries), start_index + count)
            return list(itertools.islice(self.log_entries, start_index, end_index))

    def _recover_session(self, session: LogSession) -> None:
        """Reset session if file rotation occurred"""
        with self.lock:
            if session.generation != self.generation:
                session.reset(
                    new_index=self.last_entry_index,
                    new_generation=self.generation
                )


# ----------------------------------------------------------------------------------------------------------------------

# import time
# import logging
# import random
# import os
#
# # Configure logging to display messages
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s',
#     handlers=[logging.StreamHandler()]
# )
#
#
# def simulate_log_writer(log_file_path: str):
#     """Simulate a process that writes logs to a file"""
#     if not os.path.exists(log_file_path):
#         open(log_file_path, 'w').close()  # Create empty file
#
#     while True:
#         try:
#             with open(log_file_path, 'a', encoding='utf-8') as f:
#                 for _ in range(random.randint(1, 5)):
#                     log_entry = {
#                         "timestamp": time.time(),
#                         "level": random.choice(["INFO", "WARN", "ERROR"]),
#                         "message": f"Log event {random.randint(1000, 9999)}"
#                     }
#                     f.write(json.dumps(log_entry) + "\n")
#                     logging.info(f"Wrote log: {log_entry['message']}")
#         except Exception as e:
#             logging.error(f"Log writer error: {e}")
#
#         time.sleep(random.uniform(0.5, 2.0))


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

    # # Start log writer simulation in a separate thread
    # writer_thread = threading.Thread(
    #     target=simulate_log_writer,
    #     args=(LOG_FILE,),
    #     daemon=True
    # )
    # writer_thread.start()
    #
    # logging.info(f"Starting log monitor for file: {LOG_FILE}")

    # Create log monitor instance
    log_monitor = LogFileWrapper(LOG_FILE, limit=1000)

    try:
        # Create a session for reading logs
        session = log_monitor.get_start_session()
        # logging.info(f"Created new log session starting at index {session.start_entry_index}")

        logs = log_monitor.get_historical_logs(session, -1000, 1000)
        for log in logs:
            print_log(log)

        # Main monitoring loop
        while True:
            # Check for new logs
            new_logs = log_monitor.get_realtime_logs(session, count=100)

            if new_logs:
                # print(f"Found {len(new_logs)} new log entries:")
                for i, log in enumerate(new_logs):
                    print_log(log)

            # Wait before next check
            time.sleep(MONITOR_INTERVAL)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        log_monitor.stop_monitoring()
        print("Log monitoring stopped")


if __name__ == "__main__":
    main()
