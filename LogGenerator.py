# test_log_generator.py
"""
Main entry point for generating test logs across multiple modules.
This script creates structured JSON logs for testing the log viewer system.
"""
import time
import random
import logging
import argparse
import threading
from datetime import datetime


if __name__ == '__main__':
    from LogUtility import setup_logging
else:
    from .LogUtility import setup_logging


class LogGenerator:
    """Base class for log generators"""

    def __init__(self, stop_event):
        self.stop_event = stop_event
        self.logger = logging.getLogger(self.module_name)

    def run(self):
        """Main execution loop for the generator"""
        while not self.stop_event.is_set():
            self.generate_logs()
            time.sleep(random.uniform(0.1, 0.5))


class AuthGenerator(LogGenerator):
    """Authentication and User Management logs"""
    module_name = 'auth'

    def generate_logs(self):
        user_id = f"user_{random.randint(100, 999)}"
        success = random.random() > 0.3  # 70% success rate

        if success:
            self.logger.info(
                "User login successful",
                extra={
                    'user_id': user_id,
                    'ip_address': f'192.168.1.{random.randint(1, 255)}',
                    'session_id': f'sess_{random.randint(1000, 9999)}'
                }
            )
            time.sleep(0.1)
            self.logger.debug(
                "User logout processed",
                extra={
                    'user_id': user_id,
                    'session_duration': random.randint(10, 3600)
                }
            )
        else:
            self.logger.warning(
                "User login failed",
                extra={
                    'user_id': user_id,
                    'reason': 'invalid_credentials',
                    'attempt_count': random.randint(1, 5)
                }
            )


class DatabaseGenerator(LogGenerator):
    """Database Operations logs"""
    module_name = 'database'

    def generate_logs(self):
        operations = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE']
        op_type = random.choice(operations)
        duration = random.randint(10, 500)
        success = random.random() > 0.2  # 80% success rate

        if success:
            self.logger.debug(
                "Database query executed",
                extra={
                    'query_type': op_type,
                    'duration_ms': duration,
                    'rows_affected': random.randint(1, 100),
                    'connection_id': f"conn_{random.randint(1, 20)}"
                }
            )
        else:
            self.logger.error(
                "Database query failed",
                extra={
                    'query_type': op_type,
                    'duration_ms': duration,
                    'error_code': f"ERR_{random.randint(100, 599)}",
                    'error_message': "Connection timeout or constraint violation"
                }
            )

        if random.random() > 0.7:  # 30% chance of transaction
            self.logger.info(
                "Database transaction completed",
                extra={
                    'operation': op_type,
                    'transaction_id': f"tx_{random.randint(10000, 99999)}",
                    'isolation_level': 'READ_COMMITTED'
                }
            )


class PaymentGenerator(LogGenerator):
    """Payment Processing logs"""
    module_name = 'payment'

    def generate_logs(self):
        transaction_logger = logging.getLogger('payment.transaction')
        fraud_logger = logging.getLogger('payment.fraud_detection')

        amount = round(random.uniform(10, 5000), 2)
        transaction_id = f"pay_{random.randint(100000, 999999)}"

        transaction_logger.info(
            "Payment processing started",
            extra={
                'transaction_id': transaction_id,
                'amount': amount,
                'currency': 'USD',
                'payment_method': random.choice(['credit_card', 'paypal', 'bank_transfer'])
            }
        )

        # Simulate fraud check
        if amount > 1000:
            fraud_logger.warning(
                "High value transaction - fraud check required",
                extra={
                    'transaction_id': transaction_id,
                    'risk_score': random.randint(30, 95),
                    'amount': amount
                }
            )

        time.sleep(0.1)

        if random.random() > 0.1:  # 90% success rate
            transaction_logger.info(
                "Payment processed successfully",
                extra={
                    'transaction_id': transaction_id,
                    'status': 'completed',
                    'processing_time_ms': random.randint(50, 300)
                }
            )
        else:
            transaction_logger.error(
                "Payment processing failed",
                extra={
                    'transaction_id': transaction_id,
                    'status': 'failed',
                    'error_reason': random.choice([
                        'insufficient_funds',
                        'card_declined',
                        'network_error'
                    ])
                }
            )


class SystemGenerator(LogGenerator):
    """System Operations logs"""
    module_name = 'system'

    def generate_logs(self):
        performance_logger = logging.getLogger('system.performance')
        security_logger = logging.getLogger('system.security')

        cpu_usage = random.randint(10, 95)
        memory_usage = random.randint(200, 800)

        performance_logger.debug(
            "System metrics collected",
            extra={
                'cpu_usage_percent': cpu_usage,
                'memory_usage_mb': memory_usage,
                'disk_io_mb': random.randint(5, 50),
                'network_io_mb': random.randint(1, 20)
            }
        )

        if cpu_usage > 80:
            performance_logger.warning(
                "High CPU usage detected",
                extra={
                    'cpu_usage_percent': cpu_usage,
                    'threshold': 80,
                    'process_count': random.randint(50, 200)
                }
            )

        if random.random() > 0.7:  # 30% chance of security event
            events = ['login_attempt', 'access_denied', 'firewall_block', 'password_change']
            security_logger.info(
                "Security event detected",
                extra={
                    'event_type': random.choice(events),
                    'source_ip': f'203.0.113.{random.randint(1, 255)}',
                    'user_agent': random.choice([
                        'Mozilla/5.0', 'Chrome/91.0', 'Safari/14.0', 'PostmanRuntime/7.28'
                    ]),
                    'severity': random.choice(['low', 'medium', 'high'])
                }
            )


class TaskGenerator(LogGenerator):
    """Background Tasks logs"""
    module_name = 'tasks'

    def generate_logs(self):
        scheduler_logger = logging.getLogger('tasks.scheduler')
        worker_logger = logging.getLogger('tasks.worker')

        tasks = ['data_cleanup', 'report_generation', 'cache_refresh', 'email_notifications']
        task_name = random.choice(tasks)

        scheduler_logger.info(
            "Task scheduled for execution",
            extra={
                'task_name': task_name,
                'scheduled_time': datetime.now().isoformat(),
                'interval_minutes': random.randint(5, 60)
            }
        )

        worker_logger.debug(
            "Task execution started",
            extra={
                'task_name': task_name,
                'worker_id': f"worker_{random.randint(1, 8)}",
                'thread_id': threading.get_ident()
            }
        )

        time.sleep(0.05)
        execution_time = random.randint(100, 2000)

        if random.random() > 0.15:  # 85% success rate
            worker_logger.info(
                "Task completed successfully",
                extra={
                    'task_name': task_name,
                    'execution_time_ms': execution_time,
                    'result_count': random.randint(1, 1000)
                }
            )
        else:
            worker_logger.error(
                "Task execution failed",
                extra={
                    'task_name': task_name,
                    'execution_time_ms': execution_time,
                    'error_message': 'Task timeout or resource unavailable'
                }
            )


class LongMessageGenerator(LogGenerator):
    """Generates logs with extremely long messages to test UI wrapping/scrolling."""
    module_name = 'stress.long_message'

    _LOREM = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt "
        "ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation "
        "ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
        "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur "
        "sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id "
        "est laborum. "
    )

    def generate_logs(self):
        style = random.choice(['paragraph', 'url', 'base64', 'json_blob', 'chinese_long'])
        extra = {'msg_style': style, 'seq': random.randint(1, 999999)}

        if style == 'paragraph':
            repeat = random.randint(10, 80)
            msg = f"[PARAGRAPH] {' '.join([self._LOREM] * repeat)}"
            self.logger.info(msg, extra=extra)

        elif style == 'url':
            # Very long URL-like string without spaces
            path_len = random.randint(200, 2000)
            segments = ''.join(random.choices(
                'abcdefghijklmnopqrstuvwxyz0123456789-_/=&?',
                k=path_len
            ))
            msg = f"[LONG_URL] https://api.example.com/v1/resource{segments}"
            self.logger.warning(msg, extra=extra)

        elif style == 'base64':
            # Simulate a huge base64 payload
            payload_len = random.randint(300, 3000)
            b64 = ''.join(random.choices(
                'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=',
                k=payload_len
            ))
            msg = f"[BASE64] data:image/png;base64,{b64}"
            self.logger.debug(msg, extra=extra)

        elif style == 'json_blob':
            # Large flattened JSON-like text
            pairs = [f'"k{i}":"{random.randint(1000,9999)}"' for i in range(random.randint(50, 300))]
            msg = f"[JSON_BLOB] {{{','.join(pairs)}}}"
            self.logger.info(msg, extra=extra)

        elif style == 'chinese_long':
            # Long mixed Chinese-English sentence without natural word breaks
            chars = (
                "这是一段非常长的中文日志内容用于测试日志查看器在显示超长文本时的表现情况"
                "系统需要能够正确处理不换行或自动换行的场景同时保持可读性"
                "The system should handle long mixed CJK and ASCII content gracefully "
            )
            msg = f"[CHINESE_LONG] {chars * random.randint(5, 30)}"
            self.logger.error(msg, extra=extra)


class LargePayloadGenerator(LogGenerator):
    """Generates logs with a large number of extra fields."""
    module_name = 'stress.large_payload'

    def generate_logs(self):
        field_count = random.randint(20, 120)
        extra = {'field_count': field_count}

        for i in range(field_count):
            key = f"field_{i:03d}"
            val_type = random.choice(['int', 'float', 'str', 'bool', 'uuid'])
            if val_type == 'int':
                extra[key] = random.randint(0, 999999)
            elif val_type == 'float':
                extra[key] = round(random.uniform(0, 10000), 4)
            elif val_type == 'str':
                extra[key] = ''.join(random.choices('abcdef0123456789', k=16))
            elif val_type == 'bool':
                extra[key] = random.choice([True, False])
            else:
                extra[key] = (
                    f"{random.randint(0,255):02x}{random.randint(0,255):02x}"
                    f"-{random.randint(0,65535):04x}"
                )

        msg = f"Bulk payload with {field_count} fields"
        level = random.choice([logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR])
        self.logger.log(level, msg, extra=extra)


class StackTraceGenerator(LogGenerator):
    """Simulates multi-line stack-trace style log messages."""
    module_name = 'stress.stacktrace'

    _TEMPLATES = [
        (
            "Traceback (most recent call last):\n"
            '  File "/app/src/handlers.py", line 142, in process_request\n'
            "    result = await db.fetch(query, params)\n"
            '  File "/app/src/db.py", line 88, in fetch\n'
            "    cursor.execute(sql, bindings)\n"
            "psycopg2.OperationalError: connection to server at \"10.0.1.15\" failed: Connection refused\n"
            "\tIs the server running on that host and accepting TCP/IP connections?"
        ),
        (
            "UnhandledPromiseRejectionWarning: Error: Request timeout after 30000ms\n"
            "    at ClientRequest.<anonymous> (/app/node_modules/got/dist/source/core/index.js:956:65)\n"
            "    at Object.onceWrapper (events.js:420:28)\n"
            "    at ClientRequest.emit (events.js:314:20)\n"
            "    at ClientRequest.EventEmitter.emit (domain.js:483:12)\n"
            "    at TLSSocket.socketErrorListener (_http_client.js:427:9)"
        ),
        (
            "java.net.SocketTimeoutException: Read timed out\n"
            "\tat java.base/java.net.SocketInputStream.socketRead0(Native Method)\n"
            "\tat java.base/java.net.SocketInputStream.socketRead(SocketInputStream.java:115)\n"
            "\tat java.base/java.net.SocketInputStream.read(SocketInputStream.java:168)\n"
            "\tat java.base/java.io.BufferedInputStream.fill(BufferedInputStream.java:252)\n"
            "\tat java.base/java.io.BufferedInputStream.read1(BufferedInputStream.java:292)"
        ),
    ]

    def generate_logs(self):
        template = random.choice(self._TEMPLATES)
        # Occasionally append a huge repeating suffix to make it extra long
        if random.random() > 0.7:
            suffix = "\n... repeated frames ...\n" * random.randint(10, 50)
            template = template + suffix

        level = random.choice([logging.WARNING, logging.ERROR, logging.CRITICAL])
        self.logger.log(
            level,
            template,
            extra={
                'trace_id': f"trace_{random.randint(100000, 999999)}",
                'service': random.choice(['api-gateway', 'worker', 'scheduler', 'ingestor'])
            }
        )


class MixedFormatGenerator(LogGenerator):
    """Generates logs with special characters, unicode, emojis, and mixed languages."""
    module_name = 'stress.mixed_format'

    _SPECIAL_MSGS = [
        "User input: <script>alert('xss')</script> — sanitization test",
        "Path traversal attempt: ../../../etc/passwd blocked",
        "Binary marker: \x00\x01\x02\x03 EOF sequence detected",
        "Currency: €100.50, ¥12000, £80.00, ₹5000 processed",
        "Math: ∫f(x)dx ≈ Σᵢ₌₁ⁿ f(xᵢ)Δx — approximation OK",
        "Emojis: 🚀🌟🔥💻🐛✅❌⚠️🛡️📊 in log message",
        "RTL test: مرحبا بالعالم mixed with ASCII text",
        "Zero-width: a\u200Bb\u200Cc\u200Dd joiner test",
        "Tabs:\tcol1\tcol2\tcol3\tcol4\tcol5 end",
        "URL-encoded: %3Cbody%20onload%3D%22hack%28%29%22%3E",
    ]

    def generate_logs(self):
        msg = random.choice(self._SPECIAL_MSGS)
        if random.random() > 0.5:
            # Occasionally combine multiple special messages into one mega-line
            msg = " | ".join(random.sample(self._SPECIAL_MSGS, k=random.randint(2, 5)))

        self.logger.info(
            msg,
            extra={
                'format_type': 'special',
                'unicode_test': True,
                'payload_hash': ''.join(random.choices('abcdef0123456789', k=32))
            }
        )


class BurstGenerator(LogGenerator):
    """Emits short bursts of many log lines to stress the viewer."""
    module_name = 'stress.burst'

    def generate_logs(self):
        burst_size = random.randint(20, 200)
        event_id = f"burst_{random.randint(1000, 9999)}"
        for i in range(burst_size):
            self.logger.debug(
                f"Burst event {event_id} step {i + 1}/{burst_size}",
                extra={
                    'burst_id': event_id,
                    'step': i + 1,
                    'total': burst_size,
                    'batch_tag': f"batch_{datetime.now().strftime('%H%M%S')}"
                }
            )


def run_all_tests(duration_minutes=5):
    """
    Run all test modules for specified duration.

    Args:
        duration_minutes (int): How long to run the tests in minutes
    """
    logger = logging.getLogger('main')
    logger.info(
        "Starting log generation test",
        extra={
            'test_id': 'log_generation_test_001',
            'duration_minutes': duration_minutes,
            'modules': [
                'auth', 'database', 'payment', 'system', 'tasks',
                'stress.long_message', 'stress.large_payload', 'stress.stacktrace',
                'stress.mixed_format', 'stress.burst'
            ]
        }
    )

    stop_event = threading.Event()
    generators = [
        AuthGenerator(stop_event),
        DatabaseGenerator(stop_event),
        PaymentGenerator(stop_event),
        SystemGenerator(stop_event),
        TaskGenerator(stop_event),
        LongMessageGenerator(stop_event),
        LargePayloadGenerator(stop_event),
        StackTraceGenerator(stop_event),
        MixedFormatGenerator(stop_event),
        BurstGenerator(stop_event),
    ]

    # Start all generators in separate threads
    threads = []
    for generator in generators:
        thread = threading.Thread(target=generator.run)
        thread.daemon = True
        thread.start()
        threads.append(thread)

    # Run for specified duration
    try:
        time.sleep(duration_minutes * 60)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        stop_event.set()
        logger.info(
            "Test completed",
            extra={
                'test_id': 'log_generation_test_001',
                'test_status': 'completed' if not stop_event.is_set() else 'interrupted'
            }
        )

    # Wait for threads to finish
    for thread in threads:
        thread.join(timeout=1.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate test logs for log viewer system')
    parser.add_argument(
        '--duration',
        type=int,
        default=10000,
        help='Duration to run tests in minutes (default: 5)'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default='application.log',
        help='Log file path (default: application.log)'
    )

    args = parser.parse_args()

    print(f"Starting log generation test for {args.duration} minutes...")
    print(f"Logs will be saved to: {args.log_file}")
    print("Press Ctrl+C to stop early")
    print("-" * 50)

    # Set up logging
    setup_logging(args.log_file)

    # Run the tests
    run_all_tests(args.duration)
