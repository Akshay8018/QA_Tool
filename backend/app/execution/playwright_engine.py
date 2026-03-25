from __future__ import annotations

import asyncio
import os
from typing import Any

from app.api.schemas import ExecutionResult, Step
from app.execution.base import BaseExecutionEngine


class PlaywrightExecutionEngine(BaseExecutionEngine):
    def __init__(self, max_heal_attempts: int = 3, watch_execution: bool = False) -> None:
        self.max_heal_attempts = max_heal_attempts
        self.watch_execution = watch_execution
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None
        self._startup_error: str | None = None

    async def start_session(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError:
            self._startup_error = "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            return

        try:
            self._playwright = await async_playwright().start()
            launch_opts = {"headless": not self.watch_execution}
            if self.watch_execution:
                launch_opts["channel"] = "chrome"
                launch_opts["slow_mo"] = 200
                launch_opts["args"] = ["--start-maximized"]
            try:
                self._browser = await self._playwright.chromium.launch(**launch_opts)
            except Exception:
                # Fallback to explicit Chrome path, then bundled Chromium.
                launch_opts.pop("channel", None)
                chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                if self.watch_execution and os.path.exists(chrome_path):
                    try:
                        self._browser = await self._playwright.chromium.launch(executable_path=chrome_path, **launch_opts)
                    except Exception as inner_exc:
                        _ = inner_exc
                        self._browser = await self._playwright.chromium.launch(**launch_opts)
                else:
                    self._browser = await self._playwright.chromium.launch(**launch_opts)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()
            self._startup_error = None
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            if "Executable doesn't exist" in message or "browserType.launch" in message:
                message = (
                    f"{message}. Browser binaries may be missing. "
                    "Run: python -m playwright install chromium"
                )
            self._startup_error = f"Playwright startup failed: {message}"

    async def close_session(self) -> None:
        if self.watch_execution and self._page is not None:
            # Keep the window visible briefly so users can observe final state.
            await self._page.wait_for_timeout(2000)
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None

    async def execute_step(self, step: Step) -> ExecutionResult:
        if self._startup_error:
            return ExecutionResult(
                step_id=step.id,
                status="failed",
                details=self._startup_error,
                locator_used=step.target,
                root_cause="Execution engine initialization error",
            )
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError:
            return ExecutionResult(
                step_id=step.id,
                status="failed",
                details="Playwright is not installed in backend environment. Run: pip install playwright && playwright install chromium",
                locator_used=step.target,
                root_cause="Execution dependency missing",
            )

        page = self._page
        if page is None:
            # Fallback for non-session usage.
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                local_context = await browser.new_context()
                page = await local_context.new_page()
                result = await self._execute_step_with_page(page, step)
                await local_context.close()
                await browser.close()
                return result

        return await self._execute_step_with_page(page, step)

    async def _execute_step_with_page(self, page: Any, step: Step) -> ExecutionResult:
        if step.action == "goto":
            try:
                await page.goto(step.target or "about:blank", wait_until="domcontentloaded", timeout=20000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    # Some apps keep long-running connections; DOM-ready is enough to proceed.
                    pass
                return ExecutionResult(step_id=step.id, status="passed", details=f"Navigated to {step.target}", locator_used=step.target)
            except Exception as exc:
                return ExecutionResult(
                    step_id=step.id,
                    status="failed",
                    details=f"Navigation failed: {exc}",
                    locator_used=step.target,
                    root_cause="Navigation or network issue",
                )

        alternate_locators = self._candidate_locators(step)
        locators = [l for l in alternate_locators if l]
        if not locators:
            return ExecutionResult(
                step_id=step.id,
                status="failed",
                details="No locator candidate available for this step",
                locator_used=step.target,
                root_cause="Invalid step definition",
            )

        for attempt in range(self.max_heal_attempts):
            try:
                await asyncio.sleep(0.15 if self.watch_execution else 0.05)
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                chosen = locators[min(attempt, len(locators) - 1)]
                timeout = 4000 + (attempt * 2000)
                locator = page.locator(chosen).first

                if step.action == "click":
                    await locator.wait_for(state="visible", timeout=timeout)
                    await locator.click(timeout=timeout)
                elif step.action == "type":
                    await locator.wait_for(state="visible", timeout=timeout)
                    await locator.fill(step.value or "", timeout=timeout)
                elif step.action == "assert_text":
                    await page.wait_for_timeout(800)
                    body_text = await page.locator(step.target or "body").inner_text(timeout=timeout)
                    if (step.assertion or "").lower() not in body_text.lower():
                        raise ValueError(f"Assertion text not found: {step.assertion}")
                else:
                    return ExecutionResult(step_id=step.id, status="failed", details=f"Unknown action {step.action}", locator_used=chosen)

                return ExecutionResult(
                    step_id=step.id,
                    status="passed",
                    details="Step executed",
                    locator_used=chosen,
                    retries=attempt,
                )
            except Exception as exc:
                if attempt == self.max_heal_attempts - 1:
                    return ExecutionResult(
                        step_id=step.id,
                        status="failed",
                        details=f"Execution failed after healing attempts: {exc}",
                        locator_used=locators[min(attempt, len(locators) - 1)] if locators else step.target,
                        retries=self.max_heal_attempts,
                        root_cause="Locator instability or dynamic UI drift",
                    )
        return ExecutionResult(step_id=step.id, status="failed", details="Unexpected execution fallthrough", locator_used=step.target)

    def _candidate_locators(self, step: Step) -> list[str | None]:
        if step.action == "type":
            return [
                step.target,
                "css=input[type='email']",
                "css=input[name*='user']",
                "css=input[id*='user']",
                "css=input[type='password']" if "password" in (step.target or "").lower() else None,
            ]
        if step.action == "click":
            return [
                step.target,
                "css=button[type='submit']",
                "text=Login",
                "text=Sign in",
                "xpath=//button[contains(., 'Login') or contains(., 'Sign in')]",
            ]
        if step.action == "assert_text":
            return [step.target or "body"]
        return [step.target]
