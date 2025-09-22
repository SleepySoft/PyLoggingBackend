# test_log_generator.py
"""
Main entry point for generating test logs across multiple modules.
This script creates structured JSON logs for testing the log viewer system.
"""
import logging
import time
import random
import threading
from pythonjsonlogger import jsonlogger
from datetime import datetime
import sys
import os


# Configure root logger with JSON formatting
def setup_logging():
    """Configure structured JSON logging for all modules"""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with JSON formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # JSON formatter with structured data
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(module)s %(funcName)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler for persistent logs
    file_handler = logging.FileHandler('application.log')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return root_logger


# Module 1: Authentication and User Management
def auth_module_test():
    """Test authentication module with various log levels"""
    auth_logger = logging.getLogger('auth')

    def simulate_login(user_id, success=True):
        """Simulate user login attempt"""
        if success:
            auth_logger.info(
                "User login successful",
                extra={
                    'user_id': user_id,
                    'ip_address': f'192.168.1.{random.randint(1, 255)}',
                    'session_id': f'sess_{random.randint(1000, 9999)}'
                }
            )
        else:
            auth_logger.warning(
                "User login failed",
                extra={
                    'user_id': user_id,
                    'reason': 'invalid_credentials',
                    'attempt_count': random.randint(1, 5)
                }
            )

    def simulate_logout(user_id):
        """Simulate user logout"""
        auth_logger.debug(
            "User logout processed",
            extra={
                'user_id': user_id,
                'session_duration': random.randint(10, 3600)
            }
        )

    # Generate auth logs
    for i in range(10):
        user_id = f"user_{random.randint(100, 999)}"
        success = random.random() > 0.3  # 70% success rate
        simulate_login(user_id, success)
        if success:
            time.sleep(0.1)
            simulate_logout(user_id)
        time.sleep(0.2)


# Module 2: Database Operations
def database_module_test():
    """Test database module with various operations"""
    db_logger = logging.getLogger('database')

    def simulate_query(query_type, duration_ms, success=True):
        """Simulate database query"""
        if success:
            db_logger.debug(
                "Database query executed",
                extra={
                    'query_type': query_type,
                    'duration_ms': duration_ms,
                    'rows_affected': random.randint(1, 100),
                    'connection_id': f"conn_{random.randint(1, 20)}"
                }
            )
        else:
            db_logger.error(
                "Database query failed",
                extra={
                    'query_type': query_type,
                    'duration_ms': duration_ms,
                    'error_code': f"ERR_{random.randint(100, 599)}",
                    'error_message': "Connection timeout or constraint violation"
                }
            )

    def simulate_transaction(operation_type):
        """Simulate database transaction"""
        db_logger.info(
            "Database transaction completed",
            extra={
                'operation': operation_type,
                'transaction_id': f"tx_{random.randint(10000, 99999)}",
                'isolation_level': 'READ_COMMITTED'
            }
        )

    # Generate database logs
    operations = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE']
    for i in range(15):
        op_type = random.choice(operations)
        duration = random.randint(10, 500)
        success = random.random() > 0.2  # 80% success rate

        simulate_query(op_type, duration, success)

        if random.random() > 0.7:  # 30% chance of transaction
            simulate_transaction(op_type)

        time.sleep(0.15)


# Module 3: Payment Processing
def payment_module_test():
    """Test payment processing module"""
    payment_logger = logging.getLogger('payment')
    transaction_logger = logging.getLogger('payment.transaction')
    fraud_logger = logging.getLogger('payment.fraud_detection')

    def simulate_payment(amount, currency='USD'):
        """Simulate payment processing"""
        transaction_id = f"pay_{random.randint(100000, 999999)}"

        transaction_logger.info(
            "Payment processing started",
            extra={
                'transaction_id': transaction_id,
                'amount': amount,
                'currency': currency,
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

        # Simulate processing
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

    # Generate payment logs
    for i in range(12):
        amount = round(random.uniform(10, 5000), 2)
        simulate_payment(amount)
        time.sleep(0.2)


# Module 4: System Operations
def system_module_test():
    """Test system-level operations and monitoring"""
    system_logger = logging.getLogger('system')
    performance_logger = logging.getLogger('system.performance')
    security_logger = logging.getLogger('system.security')

    def simulate_system_metrics():
        """Simulate system performance metrics"""
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

    def simulate_security_events():
        """Simulate security-related events"""
        events = ['login_attempt', 'access_denied', 'firewall_block', 'password_change']
        event_type = random.choice(events)

        security_logger.info(
            "Security event detected",
            extra={
                'event_type': event_type,
                'source_ip': f'203.0.113.{random.randint(1, 255)}',
                'user_agent': random.choice([
                    'Mozilla/5.0', 'Chrome/91.0', 'Safari/14.0', 'PostmanRuntime/7.28'
                ]),
                'severity': random.choice(['low', 'medium', 'high'])
            }
        )

    # Generate system logs
    for i in range(20):
        simulate_system_metrics()

        if random.random() > 0.7:  # 30% chance of security event
            simulate_security_events()

        time.sleep(0.1)


# Module 5: Background Tasks
def background_tasks_test():
    """Test background tasks and scheduled jobs"""
    task_logger = logging.getLogger('tasks')
    scheduler_logger = logging.getLogger('tasks.scheduler')
    worker_logger = logging.getLogger('tasks.worker')

    def simulate_scheduled_task(task_name):
        """Simulate scheduled task execution"""
        scheduler_logger.info(
            "Task scheduled for execution",
            extra={
                'task_name': task_name,
                'scheduled_time': datetime.now().isoformat(),
                'interval_minutes': random.randint(5, 60)
            }
        )

        # Simulate task execution
        execution_time = random.randint(100, 2000)
        worker_logger.debug(
            "Task execution started",
            extra={
                'task_name': task_name,
                'worker_id': f"worker_{random.randint(1, 8)}",
                'thread_id': threading.get_ident()
            }
        )

        time.sleep(0.05)

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

    # Generate task logs
    tasks = ['data_cleanup', 'report_generation', 'cache_refresh', 'email_notifications']
    for i in range(8):
        task_name = random.choice(tasks)
        simulate_scheduled_task(task_name)
        time.sleep(0.3)


# Main execution function
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

    end_time = time.time() + (duration_minutes * 60)

    try:
        while time.time() < end_time:
            # Run all modules in sequence
            auth_module_test()
            database_module_test()
            payment_module_test()
            system_module_test()
            background_tasks_test()

            # Log progress
            remaining = end_time - time.time()
            logger.debug(
                "Test cycle completed",
                extra={
                    'remaining_seconds': round(remaining, 2),
                    'cycles_completed': getattr(run_all_tests, 'cycle_count', 0) + 1
                }
            )
            run_all_tests.cycle_count = getattr(run_all_tests, 'cycle_count', 0) + 1

            time.sleep(1)  # Brief pause between cycles

    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.critical(
            "Test failed with error",
            extra={
                'error_type': type(e).__name__,
                'error_message': str(e),
                'test_status': 'aborted'
            }
        )
        raise

    logger.info(
        "Test completed successfully",
        extra={
            'test_id': 'log_generation_test_001',
            'total_cycles': getattr(run_all_tests, 'cycle_count', 0),
            'test_status': 'completed'
        }
    )


if __name__ == "__main__":
    # Set up logging
    setup_logging()

    # Parse command line arguments
    import argparse

    parser = argparse.ArgumentParser(description='Generate test logs for log viewer system')
    parser.add_argument(
        '--duration',
        type=int,
        default=5,
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

    # Run the tests
    run_all_tests(args.duration)
