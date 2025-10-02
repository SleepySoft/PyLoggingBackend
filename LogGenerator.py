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
            'modules': ['auth', 'database', 'payment', 'system', 'tasks']
        }
    )

    stop_event = threading.Event()
    generators = [
        AuthGenerator(stop_event),
        DatabaseGenerator(stop_event),
        PaymentGenerator(stop_event),
        SystemGenerator(stop_event),
        TaskGenerator(stop_event)
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
