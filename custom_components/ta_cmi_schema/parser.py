"""Parser for the C.M.I. schema web interface (no Home Assistant imports).

The C.M.I. "schema" pages are made of three kinds of resources:

* ``schematic_files/<n>.cgi``  - current values of page ``n`` as flat ``<div id="posNN">``
* ``schematic_files/<n>.html`` - title and absolute CSS positions of every ``posNN``
* ``INCLUDE/changerx2.cgi?sadrx2=<short address>`` - edit dialog of one value
  (real write address, type, range, options)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re

CLASS_CHANGE = "changex2"
CLASS_BUTTON = "buttonx2"
CLASS_TASTER = "taster"
CLASS_LINK = "durchsichtig"

KIND_NUMBER = "number"
KIND_SELECT = "select"
KIND_TIME = "time"
KIND_UNSUPPORTED = "unsupported"

_WS = re.compile(r"\s+")
_NUMBER_VALUE = re.compile(r"^(-?\d+(?:[.,]\d+)?)\s*(.*)$")
_TIME_VALUE = re.compile(r"^(\d{1,2}):(\d{2})$")
_INLINE_LABEL = re.compile(r"^(.*?\S)\s*:\s+(\S.*)$")


def _clean(text: str) -> str:
    return _WS.sub(" ", unescape(text)).strip()


@dataclass
class SchemaElement:
    """One ``<div id="posNN">`` of a schema page."""

    pos: str
    classes: list[str] = field(default_factory=list)
    address: str | None = None
    changefrom: str | None = None
    chunks: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return _clean(" ".join(self.chunks))

    @property
    def is_change(self) -> bool:
        return CLASS_CHANGE in self.classes and bool(self.address)

    @property
    def is_button(self) -> bool:
        return CLASS_BUTTON in self.classes and bool(self.address)

    @property
    def is_link(self) -> bool:
        return CLASS_LINK in self.classes

    @property
    def visible_state(self) -> int | None:
        """Value of the ``visibleN`` class (buttons: 1 = on, 0 = off, <0 = hidden/locked)."""
        for cls in self.classes:
            if cls.startswith("visible"):
                try:
                    return int(cls[7:])
                except ValueError:
                    return None
        return None

    @property
    def button_text(self) -> str:
        return _clean(self.chunks[0]) if self.chunks else ""

    def split_label(self) -> tuple[str | None, str]:
        """Split ``"RL Zirk.SOLL: 35.5 °C"`` into (``"RL Zirk.SOLL"``, ``"35.5 °C"``)."""
        text = self.text
        match = _INLINE_LABEL.match(text)
        if match and not _TIME_VALUE.match(text):
            return match.group(1), match.group(2)
        return None, text


class _ValuesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[SchemaElement] = []
        self._current: SchemaElement | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag != "div" and self._current is None:
            return
        if self._current is None:
            attr = dict(attrs)
            pos = attr.get("id") or ""
            if not pos.startswith("pos"):
                return
            self._current = SchemaElement(
                pos=pos,
                classes=(attr.get("class") or "").split(),
                address=(attr.get("adresse") or "").strip() or None,
                changefrom=(attr.get("changefrom") or "").strip() or None,
            )
            self._depth = 1
        elif tag == "div":
            self._depth += 1

    def handle_endtag(self, tag):
        if self._current is not None and tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.elements.append(self._current)
                self._current = None

    def handle_data(self, data):
        if self._current is not None and data.strip():
            self._current.chunks.append(data)


def parse_values(html: str) -> dict[str, SchemaElement]:
    """Parse a ``schematic_files/<n>.cgi`` response."""
    parser = _ValuesParser()
    parser.feed(html)
    parser.close()
    return {el.pos: el for el in parser.elements}


@dataclass
class PositionInfo:
    top: float
    x: float
    font_size: float = 0
    bold: bool = False


@dataclass
class PageLayout:
    title: str | None = None
    width: float = 0
    positions: dict[str, PositionInfo] = field(default_factory=dict)


_TITLE = re.compile(r"""titel\s*=\s*["']([^"']*)["']""")
_WIDTH = re.compile(r"#values\s*\{[^}]*?width\s*:\s*(\d+)")
_RULE = re.compile(r"((?:#pos\d+[^{,]*,?\s*)+)\{([^}]*)\}")
_PROP = re.compile(r"([a-z-]+)\s*:\s*([^;]+)")


def parse_layout(html: str) -> PageLayout:
    """Parse a ``schematic_files/<n>.html`` file (title + CSS positions)."""
    layout = PageLayout()
    if match := _TITLE.search(html):
        layout.title = _clean(match.group(1)) or None
    if match := _WIDTH.search(html):
        layout.width = float(match.group(1))
    props: dict[str, dict[str, str]] = {}
    for selectors, body in _RULE.findall(html):
        for pos in re.findall(r"#(pos\d+)(?![\w ])", selectors):
            props.setdefault(pos, {}).update(
                {k.strip(): v.strip() for k, v in _PROP.findall(body)}
            )
    for pos, prop in props.items():
        if "top" not in prop:
            continue
        top = _px(prop["top"])
        if "left" in prop:
            x = _px(prop["left"])
        elif "right" in prop and layout.width:
            x = layout.width - _px(prop["right"])
        else:
            continue
        layout.positions[pos] = PositionInfo(
            top=top,
            x=x,
            font_size=_px(prop.get("font-size", "0")),
            bold="bold" in prop.get("font-weight", ""),
        )
    return layout


def _px(value: str) -> float:
    match = re.match(r"\s*(-?\d+(?:\.\d+)?)", value)
    return float(match.group(1)) if match else 0.0


def _is_label_text(text: str) -> bool:
    if not text or text in {"-", "--", "?"}:
        return False
    if _TIME_VALUE.match(text):
        return False
    return not _NUMBER_VALUE.match(text)


def find_label(
    pos: str, elements: dict[str, SchemaElement], layout: PageLayout
) -> str | None:
    """Find the descriptive text written on the same row, left of ``pos``."""
    own = layout.positions.get(pos)
    if own is None:
        return None
    tolerance = max(15.0, own.font_size * 0.6)
    best: tuple[float, str] | None = None
    for other_pos, other in elements.items():
        if other_pos == pos or other.is_change or other.is_button or other.is_link:
            continue
        info = layout.positions.get(other_pos)
        if info is None or abs(info.top - own.top) > tolerance:
            continue
        text = other.text
        if not _is_label_text(text):
            continue
        distance = own.x - info.x
        if distance <= 0:
            continue
        if best is None or distance < best[0]:
            best = (distance, text)
    return best[1] if best else None


def find_headline(elements: dict[str, SchemaElement], layout: PageLayout) -> str | None:
    """Return the bold, biggest texts at the top of the page (e.g. "Einstellungen FBH EG")."""
    candidates = []
    for pos, el in elements.items():
        info = layout.positions.get(pos)
        if info is None or not info.bold or el.is_change or el.is_button:
            continue
        if _is_label_text(el.text):
            candidates.append((info, el.text))
    if not candidates:
        return None
    biggest = max(info.font_size for info, _ in candidates)
    top_row = min(info.top for info, _ in candidates if info.font_size == biggest)
    parts = [
        (info.x, text)
        for info, text in candidates
        if info.font_size == biggest and abs(info.top - top_row) <= 15
    ]
    return " ".join(text for _, text in sorted(parts))


@dataclass
class NumberValue:
    value: float
    unit: str | None


def parse_number(text: str) -> NumberValue | None:
    if _TIME_VALUE.match(text.strip()):
        return None
    match = _NUMBER_VALUE.match(text.strip())
    if not match:
        return None
    unit = match.group(2).strip() or None
    if unit and _NUMBER_VALUE.match(unit):
        return None
    return NumberValue(float(match.group(1).replace(",", ".")), unit)


def parse_time_minutes(text: str) -> int | None:
    match = _TIME_VALUE.match(text.strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


@dataclass
class Changer:
    """Parsed ``changerx2.cgi`` dialog."""

    write_address: str | None
    kind: str
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    unit: str | None = None
    options: list[tuple[str, str]] = field(default_factory=list)  # (value, label)
    selected: str | None = None


_HIDDEN_ADR = re.compile(r'value="([0-9A-Fa-f]+)"\s+name="changeadrx2"')
_OPTION = re.compile(r"<option([^>]*)>([^<]*)</option>", re.IGNORECASE)
_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_RANGE = re.compile(r"(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*([^<\d][^<]*)?<br")


def _input_attrs(html: str, element_id: str) -> dict[str, str]:
    for tag in re.findall(r"<input[^>]*>", html, re.IGNORECASE):
        attrs = dict(_ATTR.findall(tag.replace('"value', '" value')))
        if attrs.get("id") == element_id:
            return attrs
    return {}


def parse_changer(html: str) -> Changer:
    adr = _HIDDEN_ADR.search(html)
    write_address = adr.group(1) if adr else None

    if "<select" in html.lower():
        options = []
        selected = None
        for attrs_raw, label in _OPTION.findall(html):
            attrs = dict(_ATTR.findall(attrs_raw))
            value = attrs.get("value", str(len(options)))
            options.append((value, _clean(label)))
            if "selected" in attrs_raw:
                selected = value
        return Changer(write_address, KIND_SELECT, options=options, selected=selected)

    if 'id="changetotime' in html:
        ids = set(re.findall(r'id="changetotime(\w)"', html))
        if ids == {"h", "m"}:
            return Changer(write_address, KIND_TIME, minimum=0, maximum=1440, step=1)
        return Changer(write_address, KIND_UNSUPPORTED)

    if 'id="changetodate' in html:
        return Changer(write_address, KIND_UNSUPPORTED)

    attrs = _input_attrs(html, "changeto")
    if attrs:
        unit = None
        if rng := _RANGE.search(html):
            unit = (rng.group(3) or "").strip() or None
        return Changer(
            write_address,
            KIND_NUMBER,
            minimum=_float(attrs.get("min")),
            maximum=_float(attrs.get("max")),
            step=_float(attrs.get("step")) or 1.0,
            unit=unit,
        )
    return Changer(write_address, KIND_UNSUPPORTED)


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def decimals_for_step(step: float | None) -> int:
    if not step:
        return 0
    text = f"{step:.6f}".rstrip("0")
    return len(text.split(".")[1]) if "." in text else 0
