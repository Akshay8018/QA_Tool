from __future__ import annotations

from collections import Counter

from app.api.schemas import ExecutionResult, TestRunReport


class ReportGenerator:
    def generate(self, report: TestRunReport) -> dict:
        statuses = Counter(result.status for result in report.results)
        failed_steps = [r for r in report.results if r.status != "passed"]

        human_report = {
            "run_id": report.run_id,
            "summary": f"{statuses.get('passed', 0)} passed / {statuses.get('failed', 0)} failed",
            "root_cause_analysis": report.root_cause_analysis,
            "recommendations": report.recommendations,
            "failed_steps": [
                {
                    "step_id": f.step_id,
                    "details": f.details,
                    "root_cause": f.root_cause,
                }
                for f in failed_steps
            ],
        }
        return human_report

    def classify_failure(self, result: ExecutionResult) -> str:
        if "locator" in result.details.lower() or "not found" in result.details.lower():
            return "UI Change / Locator Drift"
        if "timeout" in result.details.lower():
            return "Performance/Timing Instability"
        return "Test Logic or Product Bug"
