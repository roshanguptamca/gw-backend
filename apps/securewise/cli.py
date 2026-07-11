"""
SecureWise command line interface.

Usage:
  python -m apps.securewise.cli scan --path .
"""

from __future__ import annotations

import argparse
import sys

from apps.securewise.services.local_scan import LocalScanError, run_local_scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="securewise", description="SecureWise developer tooling")
    subcommands = parser.add_subparsers(dest="command", required=True)

    scan = subcommands.add_parser("scan", help="Scan a local repository path")
    scan.add_argument("--path", required=True, help="Repository path to scan, for example '.'")
    scan.add_argument("--output", default="securewise-report", help="Directory for JSON and HTML reports")
    scan.add_argument(
        "--scan-type",
        default="full",
        choices=["sast", "sca", "secrets", "iac", "container", "api", "dast", "full"],
        help="Scan type to run",
    )
    scan.add_argument(
        "--fail-on",
        default="high",
        choices=["critical", "high", "medium", "low", "info"],
        help="Exit non-zero when findings at or above this severity are found",
    )
    scan.add_argument("--target-url", default="", help="Optional live target URL for DAST")
    scan.add_argument("--docker-image", default="", help="Optional Docker image reference for container scanning")
    scan.add_argument("--api-spec-url", default="", help="Optional API spec URL for API scanning metadata")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        try:
            report = run_local_scan(
                args.path,
                output_dir=args.output,
                scan_type=args.scan_type,
                fail_on=args.fail_on,
                target_url=args.target_url,
                docker_image=args.docker_image,
                api_spec_url=args.api_spec_url,
            )
        except LocalScanError as exc:
            print(f"SecureWise scan failed [{exc.code}]: {exc}", file=sys.stderr)
            return 2

        artifacts = report.get("artifacts", {})
        discovery = report.get("discovery_summary", {})
        print(f"SecureWise scan complete: {report['summary']['total_findings']} finding(s)")
        print(
            "Discovery: "
            f"type={discovery.get('project_type', 'unknown')}, "
            f"framework={discovery.get('framework') or 'n/a'}, "
            f"runtime={discovery.get('requires_runtime', False)}, "
            f"auto_run={discovery.get('can_auto_run', False)}"
        )
        if report.get("summary", {}).get("warnings"):
            print("Warnings:")
            for warning in report["summary"]["warnings"]:
                print(f"  - {warning}")
        if report.get("scan", {}).get("engines"):
            print(f"Engines: {', '.join(report['scan']['engines'])}")
        print(f"JSON report: {artifacts.get('json', '')}")
        print(f"HTML report: {artifacts.get('html', '')}")
        if not report.get("scan", {}).get("quality_gate_passed"):
            print(f"Quality gate failed at threshold: {args.fail_on}", file=sys.stderr)
            return 1
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
