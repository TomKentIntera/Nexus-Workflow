#!/usr/bin/env python
"""
Utility script for running Cypress tests from n8n.

This script can execute Cypress tests and return results in JSON format
so n8n workflows can process the test outcomes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Cypress tests")
    parser.add_argument(
        "--spec",
        help="Path to specific test file to run (relative to cypress project root)",
    )
    parser.add_argument(
        "--browser",
        default="electron",
        choices=["electron", "chrome", "chromium", "firefox", "edge"],
        help="Browser to run tests in",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run in headless mode (default: True)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run in headed mode (overrides --headless)",
    )
    parser.add_argument(
        "--project",
        help="Path to Cypress project directory (default: current directory)",
    )
    parser.add_argument(
        "--config",
        help="Path to cypress.config.js or JSON config file",
    )
    parser.add_argument(
        "--env",
        help="JSON string of environment variables to pass to Cypress",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save test results and screenshots/videos",
    )
    parser.add_argument(
        "--reporter",
        default="json",
        choices=["json", "junit", "spec", "mochawesome"],
        help="Test reporter format (default: json)",
    )
    parser.add_argument(
        "--reporter-options",
        help="JSON string of reporter options (e.g., '{\"mochaFile\": \"results.xml\"}')",
    )
    return parser.parse_args()


def _build_cypress_command(args: argparse.Namespace) -> list[str]:
    """Build the Cypress run command."""
    cmd = ["npx", "cypress", "run"]
    
    if args.spec:
        cmd.extend(["--spec", args.spec])
    
    if args.browser:
        cmd.extend(["--browser", args.browser])
    
    if args.headed:
        cmd.append("--headed")
    elif args.headless:
        cmd.append("--headless")
    
    if args.project:
        cmd.extend(["--project", args.project])
    
    if args.config:
        cmd.extend(["--config-file", args.config])
    
    if args.env:
        try:
            env_dict = json.loads(args.env)
            env_string = ",".join([f"{k}={v}" for k, v in env_dict.items()])
            cmd.extend(["--env", env_string])
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON in --env: {args.env}", file=sys.stderr)
    
    if args.output_dir:
        cmd.extend(["--config", f"screenshotsFolder={args.output_dir}/screenshots"])
        cmd.extend(["--config", f"videosFolder={args.output_dir}/videos"])
    
    # Reporter configuration
    if args.reporter == "json":
        cmd.extend(["--reporter", "json"])
        if args.output_dir:
            cmd.extend(["--reporter-options", f'{{"output": "{args.output_dir}/results.json"}}'])
    elif args.reporter == "junit":
        cmd.extend(["--reporter", "junit"])
        reporter_opts = json.loads(args.reporter_options) if args.reporter_options else {}
        if "mochaFile" not in reporter_opts and args.output_dir:
            reporter_opts["mochaFile"] = f"{args.output_dir}/results.xml"
        if reporter_opts:
            cmd.extend(["--reporter-options", json.dumps(reporter_opts)])
    elif args.reporter == "mochawesome":
        cmd.extend(["--reporter", "mochawesome"])
        reporter_opts = json.loads(args.reporter_options) if args.reporter_options else {}
        if "reportDir" not in reporter_opts and args.output_dir:
            reporter_opts["reportDir"] = args.output_dir
        if reporter_opts:
            cmd.extend(["--reporter-options", json.dumps(reporter_opts)])
    
    return cmd


def _load_test_results(output_dir: Optional[str]) -> Dict[str, Any]:
    """Load test results from output directory."""
    results: Dict[str, Any] = {}
    
    if not output_dir:
        return results
    
    output_path = Path(output_dir)
    
    # Load JSON results if available
    json_results = output_path / "results.json"
    if json_results.exists():
        try:
            with open(json_results, "r") as f:
                results["json"] = json.load(f)
        except Exception as e:
            results["json_error"] = str(e)
    
    # Check for screenshots
    screenshots_dir = output_path / "screenshots"
    if screenshots_dir.exists():
        results["screenshots"] = [str(p) for p in screenshots_dir.rglob("*.png")]
    
    # Check for videos
    videos_dir = output_path / "videos"
    if videos_dir.exists():
        results["videos"] = [str(p) for p in videos_dir.rglob("*.mp4")]
    
    return results


def main() -> None:
    args = parse_args()
    
    # Determine working directory
    cwd = Path(args.project) if args.project else Path.cwd()
    if not cwd.exists():
        print(f"Error: Project directory does not exist: {cwd}", file=sys.stderr)
        sys.exit(1)
    
    # Create output directory if specified
    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build and execute Cypress command
    cmd = _build_cypress_command(args)
    
    print(f"Running Cypress command: {' '.join(cmd)}", file=sys.stderr)
    print(f"Working directory: {cwd}", file=sys.stderr)
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )
        
        output: Dict[str, Any] = {
            "exit_code": result.returncode,
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join(cmd),
        }
        
        # Load test results if available
        if output_dir:
            test_results = _load_test_results(str(output_dir))
            output["results"] = test_results
        
        # Print JSON output for n8n to consume
        print(json.dumps(output, indent=2))
        
        # Exit with Cypress exit code
        sys.exit(result.returncode)
        
    except subprocess.TimeoutExpired:
        output = {
            "exit_code": 124,
            "success": False,
            "error": "Test execution timed out after 10 minutes",
            "command": " ".join(cmd),
        }
        print(json.dumps(output, indent=2), file=sys.stderr)
        sys.exit(124)
    except Exception as e:
        output = {
            "exit_code": 1,
            "success": False,
            "error": str(e),
            "command": " ".join(cmd),
        }
        print(json.dumps(output, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

