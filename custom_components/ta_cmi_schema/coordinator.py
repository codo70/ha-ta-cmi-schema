"""Discovery and polling of the C.M.I. schema pages."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CMIAuthError, CMIClient, CMIError, CMINotFound
from .const import (
    CONF_PAGES,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_MISSING_PAGES,
    MAX_PAGES,
    STORAGE_VERSION,
)
from .parser import (
    KIND_NUMBER,
    KIND_SELECT,
    KIND_TIME,
    PageLayout,
    SchemaElement,
    ROW_NUMBER,
    find_headline,
    find_label,
    find_label_pos,
    time_name,
    parse_layout,
    parse_number,
    parse_values,
)

_LOGGER = logging.getLogger(__name__)

KIND_SWITCH = "switch"
KIND_SENSOR = "sensor"


def parse_pages_option(value: str | None) -> list[int] | None:
    """``"3, 7, 20-28"`` -> [3, 7, 20, ..., 28]; empty -> None (all pages)."""
    if not value or not value.strip():
        return None
    pages: set[int] = set()
    for part in value.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = (int(x) for x in part.split("-", 1))
            pages.update(range(min(start, end), max(start, end) + 1))
        else:
            pages.add(int(part))
    return sorted(pages)


class CMISchemaCoordinator(DataUpdateCoordinator[dict[int, dict[str, SchemaElement]]]):
    """Polls all schema pages that contain entities."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: CMIClient) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.discovery: dict[str, Any] = {"pages": {}, "params": []}
        self.hub_device_id: str | None = None

    # ------------------------------------------------------------------ discovery

    async def async_load_discovery(self, force: bool = False) -> None:
        """Load the cached discovery or crawl the C.M.I. if there is none."""
        if not force and (cached := await self._store.async_load()):
            self.discovery = cached
            return
        self.discovery = await self._async_discover()
        await self._store.async_save(self.discovery)

    async def _async_discover(self) -> dict[str, Any]:
        wanted = parse_pages_option(self.config_entry.options.get(CONF_PAGES))
        with_sensors = self.config_entry.options.get(CONF_SENSORS, True)
        candidates = wanted or range(1, MAX_PAGES + 1)

        pages: dict[str, dict[str, Any]] = {}
        params: list[dict[str, Any]] = []
        missing = 0
        device_names: set[str] = set()
        seen_addresses: set[str] = set()

        for page in candidates:
            try:
                values = parse_values(await self.client.get_values(page))
            except CMINotFound:
                missing += 1
                if wanted is None and missing >= MAX_MISSING_PAGES:
                    break
                continue
            except CMIAuthError as err:
                raise ConfigEntryAuthFailed from err
            missing = 0
            if not values:
                continue

            try:
                layout = parse_layout(await self.client.get_layout(page))
            except CMIError:
                layout = PageLayout()

            device = find_headline(values, layout) or layout.title or f"Seite {page}"
            if device in device_names:
                device = f"{device} ({page})"
            device_names.add(device)
            pages[str(page)] = {"title": layout.title, "device": device}

            used_names: dict[str, int] = {}

            def unique(name: str) -> str:
                count = used_names.get(name, 0) + 1
                used_names[name] = count
                return name if count == 1 else f"{name} {count}"

            changers: dict[str, Any] = {}
            for pos, el in values.items():
                if not el.is_change or el.address in seen_addresses:
                    continue  # same value may be shown on several pages
                seen_addresses.add(el.address)
                try:
                    changer = await self.client.get_changer(el.address)
                except CMIError as err:
                    _LOGGER.warning("Skipping %s on page %s: %s", el.address, page, err)
                    continue
                if changer.kind not in (KIND_NUMBER, KIND_SELECT, KIND_TIME):
                    _LOGGER.debug("Unsupported value type %s on page %s", el.address, page)
                    continue
                changers[pos] = changer

            label_pos = {pos: find_label_pos(pos, values, layout) for pos in values}
            time_positions = {p for p, ch in changers.items() if ch.kind == KIND_TIME}

            for pos, el in values.items():
                if pos in changers:
                    changer = changers[pos]
                    inline_label, _ = el.split_label()
                    row = values[label_pos[pos]].text if label_pos[pos] else None
                    label = inline_label or row
                    if changer.kind == KIND_TIME:
                        name = time_name(
                            pos, values, layout, time_positions, label_pos, label
                        )
                    else:
                        name = label or f"Wert {pos[3:]}"
                    params.append(
                        {
                            "key": el.address,
                            "kind": changer.kind,
                            "page": page,
                            "pos": pos,
                            "address": el.address,
                            "name": unique(name),
                            "unit": changer.unit,
                            "min": changer.minimum,
                            "max": changer.maximum,
                            "step": changer.step,
                            "options": [list(o) for o in changer.options],
                        }
                    )
                elif el.is_button:
                    row = values[label_pos[pos]].text if label_pos[pos] else None
                    text = el.button_text or f"Taste {pos[3:]}"
                    if row and ROW_NUMBER.match(row):
                        name = f"{text} {row.rstrip('.')}"
                    else:
                        name = f"{row} {text}" if row else text
                    params.append(
                        {
                            "key": f"{page}_{pos}",
                            "kind": KIND_SWITCH,
                            "page": page,
                            "pos": pos,
                            "address": None,
                            "name": unique(name),
                        }
                    )
                elif with_sensors and not el.is_change and not el.is_link:
                    inline_label, value_text = el.split_label()
                    number = parse_number(value_text)
                    if number is None or number.unit is None:
                        continue
                    label = inline_label or find_label(pos, values, layout) or f"Messwert {pos[3:]}"
                    params.append(
                        {
                            "key": f"{page}_{pos}",
                            "kind": KIND_SENSOR,
                            "page": page,
                            "pos": pos,
                            "address": None,
                            "name": unique(label),
                            "unit": number.unit,
                        }
                    )

        _LOGGER.info(
            "C.M.I. discovery: %s pages, %s entities", len(pages), len(params)
        )
        return {"pages": pages, "params": params}

    # ------------------------------------------------------------------ polling

    @property
    def polled_pages(self) -> list[int]:
        return sorted({p["page"] for p in self.discovery["params"]})

    async def _async_update_data(self) -> dict[int, dict[str, SchemaElement]]:
        data: dict[int, dict[str, SchemaElement]] = dict(self.data or {})
        errors = 0
        for page in self.polled_pages:
            try:
                data[page] = parse_values(await self.client.get_values(page))
            except CMIAuthError as err:
                raise ConfigEntryAuthFailed from err
            except CMIError as err:
                errors += 1
                _LOGGER.debug("Page %s not updated: %s", page, err)
        if errors and errors == len(self.polled_pages):
            raise UpdateFailed("C.M.I. not reachable")
        return data

    async def async_refresh_page(self, page: int) -> None:
        """Re-read one page right after a write."""
        try:
            values = parse_values(await self.client.get_values(page))
        except CMIError as err:
            _LOGGER.debug("Page %s not refreshed: %s", page, err)
            return
        data = dict(self.data or {})
        data[page] = values
        self.async_set_updated_data(data)

    def element(self, param: dict[str, Any]) -> SchemaElement | None:
        page = (self.data or {}).get(param["page"])
        if not page:
            return None
        if param.get("address"):
            if (el := page.get(param["pos"])) and el.address == param["address"]:
                return el
            for el in page.values():
                if el.address == param["address"]:
                    return el
            return None
        return page.get(param["pos"])
