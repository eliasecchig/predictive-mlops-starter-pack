"""Verify local setup is correct before running pipelines.

This script checks:
- Python version
- Required dependencies
- GCP authentication
- Project ID configuration
- Required GCP APIs
- BigQuery dataset and tables
"""

import os
import subprocess
import sys
from importlib.metadata import version

REQUIRED_PYTHON = (3, 11)
MAX_PYTHON = (3, 14)  # Exclusive upper bound
REQUIRED_APIS = [
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
]


def check_python_version():
    """Check Python version is 3.11-3.13."""
    if sys.version_info < REQUIRED_PYTHON:
        print(f"❌ Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ required")
        print(f"   Current: {sys.version_info.major}.{sys.version_info.minor}")
        return False
    if sys.version_info >= MAX_PYTHON:
        print(f"❌ Python {MAX_PYTHON[0]}.{MAX_PYTHON[1]} not yet supported")
        print(f"   Current: {sys.version_info.major}.{sys.version_info.minor}")
        print(f"   Supported: 3.11, 3.12, 3.13")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def check_dependencies():
    """Check required Python packages are installed."""
    required = ["google-cloud-bigquery", "google-cloud-aiplatform", "pandas", "xgboost", "kfp"]
    missing = []
    for pkg in required:
        try:
            v = version(pkg)
            print(f"✅ {pkg}=={v}")
        except Exception:
            print(f"❌ {pkg} not installed")
            missing.append(pkg)
    return len(missing) == 0


def check_gcloud():
    """Check gcloud CLI is installed and authenticated."""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
            capture_output=True,
            text=True,
            check=True,
        )
        account = result.stdout.strip()
        if account:
            print(f"✅ Authenticated as: {account}")
            return True
        else:
            print("❌ Not authenticated to gcloud")
            print("   Run: gcloud auth login")
            print("   And: gcloud auth application-default login")
            return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ gcloud CLI not found or not in PATH")
        print("   Install: https://cloud.google.com/sdk/docs/install")
        return False


def check_project_id():
    """Check PROJECT_ID is set."""
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                check=True,
            )
            project_id = result.stdout.strip()
        except subprocess.CalledProcessError:
            pass

    if project_id and project_id != "(unset)":
        print(f"✅ PROJECT_ID: {project_id}")
        return True, project_id
    else:
        print("❌ PROJECT_ID not set")
        print("   Run: export PROJECT_ID=your-project-id")
        print("   And: gcloud config set project $PROJECT_ID")
        return False, None


def check_apis(project_id):
    """Check required GCP APIs are enabled."""
    if not project_id:
        return False

    all_enabled = True
    for api in REQUIRED_APIS:
        try:
            result = subprocess.run(
                ["gcloud", "services", "list", "--enabled", f"--filter=name:{api}", "--format=value(name)"],
                capture_output=True,
                text=True,
                check=True,
            )
            if api in result.stdout:
                print(f"✅ {api} enabled")
            else:
                print(f"❌ {api} not enabled")
                all_enabled = False
        except subprocess.CalledProcessError:
            print(f"❌ Failed to check {api}")
            all_enabled = False

    if not all_enabled:
        print("\nTo enable APIs:")
        print(f"  gcloud services enable {' '.join(REQUIRED_APIS)}")

    return all_enabled


def check_bigquery_data(project_id):
    """Check BigQuery dataset and tables exist."""
    if not project_id:
        return False

    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=project_id)

        # Check dataset
        try:
            client.get_dataset(f"{project_id}.fraud_detection")
            print("✅ BigQuery dataset: fraud_detection")
        except Exception:
            print("❌ BigQuery dataset 'fraud_detection' not found")
            print("   Run: make setup-data")
            return False

        # Check tables
        tables_ok = True
        for table in ["tx", "txlabels"]:
            try:
                table_ref = f"{project_id}.fraud_detection.{table}"
                t = client.get_table(table_ref)
                print(f"✅ BigQuery table: {table} ({t.num_rows:,} rows)")
            except Exception:
                print(f"❌ BigQuery table '{table}' not found")
                tables_ok = False

        if not tables_ok:
            print("   Run: make setup-data")
        return tables_ok

    except Exception as e:
        print(f"❌ Failed to check BigQuery: {e}")
        return False


def main():
    """Run all checks."""
    print("=" * 60)
    print("Verifying Local Setup")
    print("=" * 60)
    print()

    checks = [
        ("Python version", check_python_version()),
        ("Dependencies", check_dependencies()),
        ("gcloud CLI", check_gcloud()),
    ]

    project_ok, project_id = check_project_id()
    checks.append(("PROJECT_ID", project_ok))

    if project_ok:
        checks.append(("GCP APIs", check_apis(project_id)))
        checks.append(("BigQuery data", check_bigquery_data(project_id)))

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    all_ok = all(result for _, result in checks)

    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {check_name}")

    print()

    if all_ok:
        print("✅ All checks passed! You're ready to run:")
        print("   make run-training-local")
        print("   make run-scoring-local")
        return 0
    else:
        print("❌ Some checks failed. Fix the issues above and try again.")
        print()
        print("For help, see:")
        print("  - SETUP.md for installation instructions")
        print("  - TROUBLESHOOTING.md for common issues")
        return 1


if __name__ == "__main__":
    sys.exit(main())
