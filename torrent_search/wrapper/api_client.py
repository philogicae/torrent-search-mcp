import logging
from asyncio import Task, create_task, shield
from contextlib import suppress
from os import getenv
from sys import argv
from typing import Any, ClassVar

from aiocache import cached

from .models import Cache, Torrent
from .scraper import WEBSITES, search_torrents
from .scraper import popular_torrents as scrape_popular_torrents

logger = logging.getLogger("Torrent Search")


SOURCES: list[str] = list(WEBSITES.keys())
EXCLUDE_SOURCES: list[str] = []
_excluded_env = getenv("EXCLUDE_SOURCES")
if _excluded_env:
    EXCLUDE_SOURCES = [s.strip() for s in _excluded_env.split(",") if s.strip()]
    SOURCES = [s for s in SOURCES if s not in set(EXCLUDE_SOURCES)]

# Scraping keys -> domains shown to users. Data keeps flowing through the
# original mirrors/APIs; only the displayed names are normalized.
SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "apibay.org": "thepiratebay.org",
    "yts.mx": "yts.vg",
}


def display_source(name: str) -> str:
    """Public domain for a scraping key (unchanged when not aliased)."""
    return SOURCE_DISPLAY_NAMES.get(name, name)


def displayed_sources(names: list[str]) -> list[str]:
    """Display names for scraping keys, deduplicated in order."""
    seen: list[str] = []
    for name in names:
        shown = display_source(name)
        if shown not in seen:
            seen.append(shown)
    return seen


def key_builder(fn: Any, *args: Any, **kwargs: Any) -> str:
    """Build the aiocache key.

    aiocache calls ``key_builder(fn, *call_args)``; for the decorated bound
    method ``args[0]`` is ``self``, so real arguments start at ``args[1]``.
    The query is lowercased to match ``search_torrents``' normalization and
    avoid duplicate cache entries that only differ by case.
    """
    call_args = args[1:]
    query = (
        str(call_args[0]).lower() if call_args else str(kwargs.get("query", "")).lower()
    )
    limit = (
        call_args[1]
        if len(call_args) > 1
        else next(
            (
                kwargs[name]
                for name in ("limit", "max_items", "per_source")
                if name in kwargs
            ),
            10,
        )
    )
    return str({"fn": getattr(fn, "__qualname__", ""), "query": query, "limit": limit})


class TorrentSearchApi:
    """A client for searching torrents."""

    CACHE: Cache = Cache()
    _inflight: ClassVar[dict[str, Task[Any]]] = {}

    async def _single_flight(self, key: str, factory: Any) -> Any:
        """Coalesce concurrent identical cold misses into one task."""
        while True:
            existing = self._inflight.get(key)
            if existing is None:
                break
            return await shield(existing)
        task = create_task(factory())
        self._inflight[key] = task
        try:
            return await task
        finally:
            self._inflight.pop(key, task)

    def available_sources(self) -> list[str]:
        """Get the list of available torrent sources (display domains)."""
        return displayed_sources(SOURCES)

    @cached(ttl=120, key_builder=key_builder)  # 2min
    async def search_torrents(
        self,
        query: str,
        max_items: int = 20,
    ) -> list[Torrent]:
        """
        Search for torrents on available sources.

        Args:
            query: Search query.
            max_items: Maximum number of items to return.

        Returns:
            A list of torrent results.
        """
        query = query.lower()
        found_torrents = await self._single_flight(
            f"search:{query}:{max_items}",
            lambda: search_torrents(query, SOURCES),
        )

        found_torrents = sorted(
            found_torrents,
            key=lambda torrent: torrent.seeders + torrent.leechers,
            reverse=True,
        )[:max_items]

        for torrent in found_torrents:
            torrent.source = display_source(torrent.source or "")
            torrent.prepend_info(query, max_items)

        self.CACHE.clean()  # Clean cache routine
        self.CACHE.update(found_torrents)
        return found_torrents

    @cached(ttl=120, key_builder=key_builder)  # 2min
    async def popular_torrents(self, per_source: int | None = 20) -> list[Torrent]:
        """
        Get the most popular torrents per source with a top listing.

        Args:
            per_source: Optional maximum number of results kept per source
                (best first). None keeps everything the source returned.

        Returns:
            A list of torrent results ranked by seeders + leechers.
        """
        found_torrents = await self._single_flight(
            f"popular:{per_source}",
            lambda: scrape_popular_torrents(per_source=per_source),
        )

        for torrent in found_torrents:
            torrent.source = display_source(torrent.source or "")
            # Empty query marker: ids stay decodable but are not re-searchable
            torrent.prepend_info("", per_source or 0)

        self.CACHE.clean()  # Clean cache routine
        self.CACHE.update(found_torrents)
        return found_torrents

    async def get_torrent(self, torrent_id: str) -> str | None:
        """
        Get the magnet link for a previously found torrent.

        Args:
            torrent_id: The ID of the torrent.

        Returns:
            The magnet link as a string, else None.
        """
        found_torrent: Torrent | None = self.CACHE.get(torrent_id)

        query, max_items = "", 10
        with suppress(Exception):
            query, max_items = Torrent.extract_info(torrent_id)[:2]
        if not query and not found_torrent:
            # Garbage ids, or popular-listing ids whose cache entry expired
            # (they carry no query marker and cannot be re-searched).
            logger.warning("Invalid torrent ID: %s", torrent_id)
            return None

        if not found_torrent:  # Missing or uncached
            torrents: list[Torrent] = await self.search_torrents(query, max_items)
            found_torrent = next(
                (torrent for torrent in torrents if torrent.id == torrent_id), None
            )

        self.CACHE.clean()  # Clean cache routine

        if found_torrent and found_torrent.magnet_link:
            return found_torrent.magnet_link
        return None

    async def cli(self, query: str | None = None) -> None:
        """
        Command line interface for the API.
        """
        query = query or (argv[1] if len(argv) > 1 else None)
        if query:
            found_torrents: list[Torrent] = await self.search_torrents(
                query, max_items=100
            )
            if found_torrents:
                found_sources = set()
                for t in found_torrents:
                    found_sources.add(t.source)
                    print(
                        f"{t.id} ({t.seeders}|{t.leechers}|{t.downloads}) - {t.filename}"
                    )
                print(f"Fetching: {found_torrents[0].id}")
                print(f"Result: {await self.get_torrent(found_torrents[0].id)}")
                print(
                    f"Found Sources (Excluded: {EXCLUDE_SOURCES}): {found_sources} | Found Torrents: {len(found_torrents)}"
                )
            else:
                print("No torrents found")
        else:
            print("Please provide a search query.")
