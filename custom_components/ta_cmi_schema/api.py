"""Async client for the C.M.I. schema web interface."""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

from .parser import Changer, parse_changer

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


class CMIError(Exception):
    """Generic C.M.I. communication error."""


class CMIAuthError(CMIError):
    """Wrong user name or password."""


class CMINotFound(CMIError):
    """Requested page does not exist."""


class CMIClient:
    """Talks to the C.M.I. exactly like its own schema web page does.

    The C.M.I. web server is small; all requests are serialized with a lock.
    """

    def __init__(
        self, session: aiohttp.ClientSession, host: str, username: str, password: str
    ) -> None:
        host = host.strip().rstrip("/")
        self._base = host if host.startswith(("http://", "https://")) else f"http://{host}"
        self._auth = aiohttp.BasicAuth(username, password)
        self._session = session
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return self._base

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        raw, _ = await self._request(path, params, headers)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")

    async def _request(
        self,
        path: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, str]:
        url = f"{self._base}/{path}"
        async with self._lock:
            last_err: Exception | None = None
            for attempt in range(2):
                try:
                    async with self._session.get(
                        url,
                        params=params,
                        headers=headers,
                        auth=self._auth,
                        timeout=REQUEST_TIMEOUT,
                    ) as resp:
                        if resp.status == 401:
                            raise CMIAuthError("Authentication failed")
                        if resp.status == 404:
                            raise CMINotFound(path)
                        if resp.status >= 400:
                            raise CMIError(f"HTTP {resp.status} for {path}")
                        raw = await resp.read()
                        content_type = resp.content_type
                except (CMIAuthError, CMINotFound):
                    raise
                except (aiohttp.ClientError, asyncio.TimeoutError, CMIError) as err:
                    last_err = err
                    _LOGGER.debug("Request %s failed (attempt %s): %s", path, attempt + 1, err)
                    await asyncio.sleep(1)
                    continue
                return raw, content_type
            raise CMIError(f"Cannot reach C.M.I. ({path}): {last_err}") from last_err

    async def get_values(self, page: int) -> str:
        """Current values of a schema page (``schematic_files/<page>.cgi``)."""
        return await self._get(f"schematic_files/{page}.cgi")

    async def get_layout(self, page: int) -> str:
        """Title and layout of a schema page (``schematic_files/<page>.html``)."""
        return await self._get(f"schematic_files/{page}.html")

    async def get_file(self, name: str) -> tuple[bytes, str]:
        """A picture of the schema (``schematic_files/<name>``) and its content type."""
        return await self._request(f"schematic_files/{name}")

    async def get_changer(self, short_address: str) -> Changer:
        """Edit dialog of a value: write address, range, options."""
        html = await self._get("INCLUDE/changerx2.cgi", params={"sadrx2": short_address})
        return parse_changer(html)

    async def change(self, write_address: str, value: str | int | float) -> None:
        """Write a value to a (14 character) write address."""
        await self._get(
            "INCLUDE/change.cgi",
            params={
                "changeadrx2": write_address,
                "changetox2": str(value),
                "_": str(int(time.time() * 1000)),
            },
            headers={
                "Referer": f"{self._base}/schema.html",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

    async def write(self, short_address: str, value: str | int | float) -> None:
        """Write a value by its short address (fetches the current write address first).

        The write address of selections changes with the current value, so it is
        always fetched fresh right before writing.
        """
        changer = await self.get_changer(short_address)
        if not changer.write_address or len(changer.write_address) != 14:
            raise CMIError(f"No write address for {short_address}")
        _LOGGER.debug("Write %s (%s) = %s", short_address, changer.write_address, value)
        await self.change(changer.write_address, value)
