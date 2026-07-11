"""Smoke-test the real Tauri WebView over an explicitly enabled debug CDP port."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def connect_browser(playwright, endpoint: str, timeout_seconds: int = 45):
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return playwright.chromium.connect_over_cdp(endpoint)
        except Exception as exc:  # WebView2 may still be starting.
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"WebView2 CDP unavailable: {last_error}")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: tauri_webview_smoke.py <cdp-port> <screenshot-path>")

    port = int(sys.argv[1])
    screenshot = Path(sys.argv[2]).resolve()
    screenshot.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = connect_browser(playwright, f"http://127.0.0.1:{port}")
        if not browser.contexts or not browser.contexts[0].pages:
            raise RuntimeError("CDP connected but the Tauri WebView page is missing")

        page = browser.contexts[0].pages[0]
        console_errors: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[dict[str, str | None]] = []
        gateway_responses: list[dict[str, object]] = []
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type in ("error", "warning")
            else None,
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                {"url": request.url, "error": request.failure}
            ),
        )
        page.on(
            "response",
            lambda response: gateway_responses.append(
                {"url": response.url, "status": response.status}
            )
            if response.url.startswith("http://127.0.0.1:")
            else None,
        )

        page.wait_for_url("http://tauri.localhost/", timeout=30_000)
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
        page.locator(".brand").wait_for(state="visible", timeout=30_000)
        previous_onboarding = page.evaluate("localStorage.getItem('pm_onboarded')")
        page.evaluate("localStorage.setItem('pm_onboarded', '1')")
        page.reload(wait_until="domcontentloaded")
        page.locator(".brand").wait_for(state="visible", timeout=30_000)
        page.wait_for_timeout(1_000)

        page.get_by_role("button", name="设置").click()
        page.locator(".settings-modal").wait_for(state="visible", timeout=15_000)
        page.get_by_role("button", name="信任模式").click()
        page.locator(".trust-active").wait_for(state="visible", timeout=5_000)
        page.locator(".settings-modal button[aria-label='关闭']").click()
        page.locator(".settings-modal").wait_for(state="hidden", timeout=5_000)
        page.locator(".trust-active").click()
        page.locator(".trust-active").wait_for(state="hidden", timeout=5_000)
        page.locator(".statuschip").click()
        page.get_by_text("连接状态", exact=True).wait_for(state="visible", timeout=5_000)

        mcp_results = page.evaluate(
            """async names => {
                const session = await window.__TAURI_INTERNALS__.invoke('gateway_session');
                const results = [];
                for (const name of names) {
                    const response = await fetch(
                        `${session.baseUrl}/api/mcp/tools?name=${encodeURIComponent(name)}`,
                        {
                            headers: {
                                'X-Prism-Session': session.token,
                            },
                        },
                    );
                    const body = await response.json();
                    results.push({
                        name,
                        status: response.status,
                        count: body.count || 0,
                        error: body.error || null,
                    });
                }
                return results;
            }""",
            ["reaper", "music-perception"],
        )
        page.screenshot(path=str(screenshot))

        result = {
            "url": page.url,
            "title": page.title(),
            "brand": page.locator(".brand").inner_text(),
            "body_has_primary_prompt": "今天想创作点什么" in page.locator("body").inner_text(),
            "settings_opened": True,
            "trust_mode_toggled": True,
            "status_menu_opened": True,
            "mcp_results": mcp_results,
            "gateway_responses": gateway_responses,
            "console_errors": console_errors,
            "page_errors": page_errors,
            "failed_requests": failed_requests,
            "screenshot": str(screenshot),
        }

        if previous_onboarding is None:
            page.evaluate("localStorage.removeItem('pm_onboarded')")
        else:
            page.evaluate(
                "value => localStorage.setItem('pm_onboarded', value)", previous_onboarding
            )

        assert result["url"] == "http://tauri.localhost/", result
        assert result["title"] == "Prism Motif", result
        assert result["brand"] == "Prism Motif", result
        assert result["body_has_primary_prompt"], result
        assert gateway_responses, result
        assert all(item["status"] < 400 for item in gateway_responses), result
        assert all(item["status"] == 200 for item in mcp_results), result
        assert all(item["count"] > 0 for item in mcp_results), result
        assert not console_errors, result
        assert not page_errors, result
        unexpected_failures = [
            item for item in failed_requests if item["error"] != "net::ERR_ABORTED"
        ]
        assert not unexpected_failures, result

        print(json.dumps(result, ensure_ascii=False))
        page.locator(".wctl button[aria-label='关闭']").click()
        try:
            page.wait_for_timeout(500)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
