from __future__ import annotations

import argparse, asyncio
import zendriver, json
import colorama

from typing import Optional, Tuple
from enum import Enum
from typing import Any, Iterable, List
from datetime import datetime

from selenium_authenticated_proxy import SeleniumAuthenticatedProxy
from zendriver.cdp.network import T_JSON_DICT, Cookie
from zendriver.core.element import Element

colorama.init(autoreset=True)


class Logger:
    """
    A logger for the CloudflareSolver class.
    """

    prefix = f"{colorama.Style.BRIGHT}{colorama.Fore.MAGENTA}CAPTCHASOLVER.AI {colorama.Fore.RESET}>"

    def __init__(self) -> None:
        pass

    def debug(self, message: str) -> None:
        """
        Log a debug message.
        """
        print(
            f"{self.prefix}{colorama.Style.DIM}{colorama.Fore.CYAN} [DEBUG] {colorama.Fore.RESET}{message}"
        )

    def info(self, message: str) -> None:
        """
        Log an info message.
        """
        print(
            f"{self.prefix}{colorama.Style.NORMAL}{colorama.Fore.GREEN} [INFO] {colorama.Fore.RESET}{message}"
        )

    def warning(self, message: str) -> None:
        """
        Log a warning message.
        """
        print(
            f"{self.prefix}{colorama.Style.NORMAL}{colorama.Fore.YELLOW} [WARNING] {colorama.Fore.RESET}{message}"
        )

    def error(self, message: str) -> None:
        """
        Log an error message.
        """
        print(
            f"{self.prefix}{colorama.Style.BRIGHT}{colorama.Fore.RED} [ERROR] {colorama.Fore.RESET}{message}"
        )


logger = Logger()


class ChallengePlatform(Enum):
    """Cloudflare challenge platform types."""

    JAVASCRIPT = "non-interactive"
    MANAGED = "managed"
    INTERACTIVE = "interactive"
    INVISIBLE = "invisible"


class CloudflareSolver:
    """
    A class for solving Cloudflare challenges with Zendriver.
    """

    def __init__(
        self,
        *,
        user_agent: Optional[str],
        timeout: float,
        http2: bool,
        http3: bool,
        headless: bool,
        proxy: Optional[str],
    ) -> None:
        config = zendriver.Config(headless=headless)
        if user_agent is not None:
            config.add_argument(f"--user-agent={user_agent}")
        if not http2:
            config.add_argument("--disable-http2")
        if not http3:
            config.add_argument("--disable-quic")
        auth_proxy = SeleniumAuthenticatedProxy(proxy)
        auth_proxy.enrich_chrome_options(config)
        self.driver = zendriver.Browser(config)
        self._timeout = timeout

    async def __aenter__(self) -> "CloudflareSolver":
        await self.driver.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.driver.stop()

    @staticmethod
    def _format_cookies(cookies: Iterable[Cookie]) -> List[T_JSON_DICT]:
        return [cookie.to_json() for cookie in cookies]

    @staticmethod
    def extract_clearance_cookie(
        cookies: Iterable[T_JSON_DICT],
    ) -> Optional[T_JSON_DICT]:
        for cookie in cookies:
            if cookie["name"] == "cf_clearance":
                return cookie
        return None

    async def get_cookies(self) -> List[T_JSON_DICT]:
        return self._format_cookies(await self.driver.cookies.get_all())

    async def detect_challenge(self) -> Optional[ChallengePlatform]:
        html = await self.driver.main_tab.get_content()
        for platform in ChallengePlatform:
            if f"cType: '{platform.value}'" in html:
                return platform

        return ChallengePlatform.INVISIBLE

    async def solve_challenge(self) -> None:
        start_timestamp = datetime.now()
        while (
            self.extract_clearance_cookie(await self.get_cookies()) is None
            and await self.detect_challenge() is not None
            and (datetime.now() - start_timestamp).seconds < self._timeout
        ):
            widget_input = await self.driver.main_tab.find("input")
            if widget_input.parent is None or not widget_input.parent.shadow_roots:
                await asyncio.sleep(0.1)
                continue
            challenge = Element(
                widget_input.parent.shadow_roots[0],
                self.driver.main_tab,
                widget_input.parent.tree,
            )
            challenge = challenge.children[0]
            if isinstance(
                challenge, Element
            ) and "display: none;" not in challenge.attrs.get("style", ""):
                try:
                    await challenge.mouse_click()
                except Exception:
                    continue
            await asyncio.sleep(0.5)


async def get_cf_clearance(
    url: str,
    timeout: float = 30,
    proxy: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Retrieve the Cloudflare clearance cookie from the specified URL.

    Args:
        url: The URL to scrape the cf_clearance cookie from.
        timeout: The timeout in seconds for solving challenges (default: 30).
        proxy: The proxy server URL to use (default: None).
        user_agent: The user agent string to use (default: None).

    Returns:
        Tuple[bool, Optional[str]]: (True, cf_clearance) if successful, (False, None) otherwise.
    """
    challenge_messages = {
        ChallengePlatform.JAVASCRIPT: "Solving Cloudflare challenge [JavaScript]...",
        ChallengePlatform.MANAGED: "Solving Cloudflare challenge [Managed]...",
        ChallengePlatform.INTERACTIVE: "Solving Cloudflare challenge [Interactive]...",
        ChallengePlatform.INVISIBLE: "Solving Cloudflare challenge ['Invisible']...",
    }

    async with CloudflareSolver(
        user_agent=user_agent,
        timeout=timeout,
        http2=False,
        http3=False,
        headless=True,
        proxy=proxy,
    ) as solver:
        logger.info(f"Routing to {url}")
        try:
            await solver.driver.get(url)
        except asyncio.TimeoutError as err:
            logger.error(f"Connection to {url} timed out: {err}")
            return False, None

        all_cookies = await solver.get_cookies()
        clearance_cookie = solver.extract_clearance_cookie(all_cookies)

        if clearance_cookie is None:
            challenge_platform = await solver.detect_challenge()
            if challenge_platform is None:
                logger.error("No Cloudflare challenge detected.")
                return False, None
            logger.info(f"{challenge_messages[challenge_platform]}")
            try:
                await solver.solve_challenge()
            except asyncio.TimeoutError:
                pass
            all_cookies = await solver.get_cookies()
            clearance_cookie = solver.extract_clearance_cookie(all_cookies)

        if clearance_cookie is None:
            logger.error("Failed to retrieve a Cloudflare clearance cookie.")
            return False, None

        cf_clearance = clearance_cookie["value"]
        return True, cf_clearance


async def main(
    url: str,
    timeout: Optional[float] = 30,
    proxy: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    try:
        success, cf_clearance = await get_cf_clearance(
            url=url,
            timeout=timeout,
            proxy=proxy,
            user_agent=user_agent,
        )

        if success:
            logger.info(f"cf_clearance: {cf_clearance}")

        else:
            logger.error("Failed to retrieve cf_clearance.")

        return cf_clearance
    except:
        return main(url, timeout, proxy, user_agent)


if __name__ == "__main__":
    asyncio.run(main("https://grok.com/"))


# ORIGINAL IS FROM https://github.com/Xewdy444/CF-Clearance-Scraper/blob/zendriver/main.py
