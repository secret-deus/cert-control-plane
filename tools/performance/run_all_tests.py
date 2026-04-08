#!/usr/bin/env python3
"""
Run all performance tests.

Usage:
    python run_all_tests.py [--duration DURATION] [--users USERS]

Examples:
    # Run all tests with default settings (5 min, 100 users)
    python run_all_tests.py

    # Run quick test (1 min, 50 users)
    python run_all_tests.py --duration 1m --users 50

    # Run stress test (10 min, 500 users)
    python run_all_tests.py --duration 10m --users 500
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_test(test_file: str, duration: str, users: int, host: str):
    """Run a single performance test."""
    print(f"\n{'='*60}")
    print(f"Running: {test_file}")
    print(f"Duration: {duration}, Users: {users}, Host: {host}")
    print(f"{'='*60}\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"results/{test_file.replace('.py', '')}_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "locust",
        "-f", test_file,
        "--headless",
        "--host", host,
        "--users", str(users),
        "--spawn-rate", str(users // 10),  # Spawn 10% of users per second
        "--run-time", duration,
        "--html", str(output_dir / "report.html"),
        "--csv", str(output_dir / "stats"),
        "--only-summary",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode != 0:
            print(f"⚠️  Test failed with return code {result.returncode}")
            return False

        print(f"✅ Test completed. Results saved to {output_dir}")
        return True

    except FileNotFoundError:
        print("❌ Error: locust not found. Install with: pip install locust")
        return False
    except Exception as e:
        print(f"❌ Error running test: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run Cert Control Plane performance tests"
    )
    parser.add_argument(
        "--duration",
        default="5m",
        help="Test duration (e.g., 1m, 5m, 10m)"
    )
    parser.add_argument(
        "--users",
        type=int,
        default=100,
        help="Number of concurrent users"
    )
    parser.add_argument(
        "--host",
        default="https://localhost:443",
        help="Target host URL"
    )
    parser.add_argument(
        "--test",
        choices=["heartbeat", "cert_sync", "all"],
        default="all",
        help="Which test to run"
    )

    args = parser.parse_args()

    tests = {
        "heartbeat": "heartbeat_test.py",
        "cert_sync": "cert_sync_test.py",
    }

    if args.test == "all":
        test_files = list(tests.values())
    else:
        test_files = [tests[args.test]]

    print(f"\n🚀 Starting performance tests")
    print(f"   Duration: {args.duration}")
    print(f"   Users: {args.users}")
    print(f"   Host: {args.host}")
    print(f"   Tests: {[t for t in test_files]}\n")

    results = {}
    for test_file in test_files:
        success = run_test(test_file, args.duration, args.users, args.host)
        results[test_file] = success

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    for test_file, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_file}: {status}")

    all_passed = all(results.values())
    if all_passed:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Check the results directory for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
