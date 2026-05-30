"""Browser-based login utility using Playwright (optional dependency)."""
from __future__ import annotations

import asyncio


async def browser_login(
    login_url: str,
    cookie_domains: list[str],
    headless: bool = False,
    wait_for_login_indicator: str | None = None,
    timeout: int = 120,
) -> dict[str, str]:
    """Open a browser for manual login and extract cookies after authentication.

    Args:
        login_url: The URL to navigate to for login.
        cookie_domains: Domains to capture cookies from.
        headless: Run browser in headless mode (mostly for testing).
        wait_for_login_indicator: CSS selector that indicates successful login.
        timeout: Max seconds to wait for login completion.

    Returns:
        Dictionary of cookie name -> value for the specified domains.

    Raises:
        ImportError: If playwright is not installed.
        TimeoutError: If login is not completed within timeout.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError(
            "playwright is required for browser login. "
            "Install it with: pip install 'junk-detector[crawler-auth]'"
        )

    cookies_result: dict[str, str] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto(login_url, wait_until="domcontentloaded")

            initial_url = page.url

            # Wait for login completion
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            while True:
                elapsed = loop.time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(
                        f"Login timed out after {timeout}s. "
                        "Please complete login within the timeout period."
                    )

                # Check if login indicator appeared
                if wait_for_login_indicator:
                    try:
                        element = await page.query_selector(wait_for_login_indicator)
                        if element:
                            break
                    except Exception:
                        pass

                # Check if URL changed (navigated away from login)
                if page.url != initial_url and "login" not in page.url.lower():
                    break

                await asyncio.sleep(0.5)

            # Extract cookies for the specified domains
            all_cookies = await context.cookies()
            for cookie in all_cookies:
                domain = cookie.get("domain", "").lstrip(".")
                if any(domain == d or domain.endswith("." + d) for d in cookie_domains):
                    cookies_result[cookie["name"]] = cookie["value"]
        finally:
            await browser.close()

    return cookies_result
