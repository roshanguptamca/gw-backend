"""
SecureWise CI/CD pipeline example generation.

The generated examples intentionally reference environment variable names only;
they never embed token values or deployment secrets.
"""

from __future__ import annotations


def generate_github_actions_workflow(
    *,
    python_version: str = "3.11",
    output_dir: str = "securewise-report",
    fail_on: str = "high",
) -> str:
    return f"""name: SecureWise Scan

on:
  push:
  pull_request:

jobs:
  securewise:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "{python_version}"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Prepare database
        run: python manage.py migrate --noinput

      - name: Run SecureWise local scan
        run: python -m apps.securewise.cli scan --path . --output {output_dir} --fail-on {fail_on}

      - name: Upload SecureWise reports
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: securewise-report
          path: {output_dir}/
"""


def generate_jenkinsfile(*, output_dir: str = "securewise-report", fail_on: str = "high") -> str:
    return f"""pipeline {{
  agent any
  stages {{
    stage('Install dependencies') {{
      steps {{
        sh 'python3 -m venv .venv'
        sh '. .venv/bin/activate && python -m pip install --upgrade pip'
        sh '. .venv/bin/activate && pip install -r requirements.txt'
      }}
    }}
    stage('Prepare database') {{
      steps {{
        sh '. .venv/bin/activate && python manage.py migrate --noinput'
      }}
    }}
    stage('SecureWise scan') {{
      steps {{
        sh '. .venv/bin/activate && python -m apps.securewise.cli scan --path . --output {output_dir} --fail-on {fail_on}'
      }}
      post {{
        always {{
          archiveArtifacts artifacts: '{output_dir}/**', fingerprint: true
        }}
      }}
    }}
  }}
}}
"""
