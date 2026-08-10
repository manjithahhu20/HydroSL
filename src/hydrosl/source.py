from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Optional

from .models import SheetSpec
from .sheets import PUBLISHED_WORKBOOK_URL


class SourceFetchError(RuntimeError):
    pass


class GoogleSheetsSource:
    """Fetch published sheets without requiring Google API credentials."""

    def __init__(
        self,
        workbook_url: str = PUBLISHED_WORKBOOK_URL,
        *,
        timeout: int = 60,
        retries: int = 3,
        user_agent: str = "HydroSL/0.1 (open hydrology data project)",
    ) -> None:
        self.workbook_url = workbook_url.rstrip("?")
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent

    def url_for(self, spec: SheetSpec) -> str:
        separator = "&" if "?" in self.workbook_url else "?"
        return f"{self.workbook_url}{separator}gid={spec.gid}&single=true&output=csv"

    def fetch(self, spec: SheetSpec) -> str:
        url = self.url_for(spec)
        last_error: Optional[Exception] = None
        for attempt in range(self.retries):
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "text/csv,text/plain,*/*",
                    "User-Agent": self.user_agent,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    content = response.read().decode("utf-8-sig")
                if content.lstrip().startswith("<!DOCTYPE html"):
                    raise SourceFetchError(
                        f"sheet {spec.name} returned HTML instead of CSV; it may no longer be published"
                    )
                return content
            except (urllib.error.URLError, TimeoutError, OSError, SourceFetchError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(2**attempt)
        raise SourceFetchError(f"could not fetch {spec.name} from {url}: {last_error}")
