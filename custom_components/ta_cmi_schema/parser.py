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
_LINK_TARGET = re.compile(r"schema\.html#(\d+)")
_FILE_NAME = re.compile(r"^[\w.-]+\.(?:png|gif|jpe?g|bmp|svg)$", re.IGNORECASE)


def _clean(text: str) -> str:
    return _WS.sub(" ", unescape(text)).strip()


@dataclass
class SchemaElement:
    """One ``<div id="posNN">`` of a schema page."""

    pos: str
    classes: list[str] = field(default_factory=list)
    address: str | None = None
    changefrom: str | None = None
    onclick: str | None = None
    chunks: list[str] = field(default_factory=list)
    # status pictures: {"name": "1_pos16_0.png", "bis": 0 | None, "hide": bool}
    images: list[dict] = field(default_factory=list)
    # button faces: [("v0", "Mo"), ("v1", "Mo")]
    spans: list[list[str]] = field(default_factory=list)

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
    def is_taster(self) -> bool:
        """Push button: 1 while pressed, 0 when released."""
        return CLASS_TASTER in self.classes and bool(self.address)

    @property
    def is_link(self) -> bool:
        return CLASS_LINK in self.classes

    @property
    def is_lamp(self) -> bool:
        """Status picture (pump, valve, "Heizen", ...) switched by ``visibleN``."""
        return (
            not self.address
            and not self.is_link
            and not self.chunks
            and self.visible_state is not None
        )

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
    def link_page(self) -> int | None:
        """Target page of a transparent navigation area (``schema.html#2``)."""
        if self.onclick and (match := _LINK_TARGET.search(self.onclick)):
            return int(match.group(1))
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
        self._spans: list[str | None] = []  # open <span> classes (v0/v1 or None)

    def handle_starttag(self, tag, attrs):
        if tag != "div" and self._current is None:
            return
        attr = dict(attrs)
        if self._current is None:
            pos = attr.get("id") or ""
            if not pos.startswith("pos"):
                return
            self._current = SchemaElement(
                pos=pos,
                classes=(attr.get("class") or "").split(),
                address=(attr.get("adresse") or "").strip() or None,
                changefrom=(attr.get("changefrom") or "").strip() or None,
                onclick=attr.get("onclick"),
            )
            self._depth = 1
            self._spans = []
        elif tag == "div":
            self._depth += 1
        elif tag == "img":
            name = file_name(attr.get("src"))
            if name:
                try:
                    bis = int(attr["bis"]) if attr.get("bis") is not None else None
                except ValueError:
                    bis = None
                self._current.images.append(
                    {"name": name, "bis": bis, "hide": "hide" in (attr.get("class") or "").split()}
                )
        elif tag == "span":
            cls = next(
                (c for c in (attr.get("class") or "").split() if c in ("v0", "v1")), None
            )
            self._spans.append(cls)
            if cls:
                self._current.spans.append([cls, ""])

    def handle_endtag(self, tag):
        if self._current is None:
            return
        if tag == "span" and self._spans:
            self._spans.pop()
        elif tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.elements.append(self._current)
                self._current = None

    def handle_data(self, data):
        if self._current is not None and data.strip():
            self._current.chunks.append(data)
            if any(self._spans) and self._current.spans:
                face = self._current.spans[-1]
                face[1] = _clean(f"{face[1]} {data}")


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
    height: float = 0

    @property
    def center_y(self) -> float:
        return self.top + (self.height or self.font_size * 1.2) / 2


@dataclass
class PageLayout:
    title: str | None = None
    width: float = 0
    height: float = 0
    positions: dict[str, PositionInfo] = field(default_factory=dict)
    image: str | None = None  # background picture in schematic_files/
    background: str | None = None  # page background colour
    refresh: int | None = None  # seconds, like the C.M.I. page
    css: str = ""  # sanitized page stylesheet (#values / #posNN rules only)


_TITLE = re.compile(r"""titel\s*=\s*["']([^"']*)["']""")
_IMAGE = re.compile(r"""\bimage\s*=\s*["']([^"']*)["']""")
_REFRESH = re.compile(r"\brefreshtime\s*=\s*(\d+)")
_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_CSS_SELECTOR = re.compile(r"^#(?:pos\d+|values)(?:[.#]?[\w-]+|[\s>]+[.#]?[\w-]+)*$")
_BODY_BG = re.compile(r"body\s*\{[^}]*?background(?:-color)?\s*:\s*([#\w(),. ]+)")
_UNSAFE_CSS = re.compile(r"url\s*\(|expression|@|\\|behavior|binding|javascript", re.IGNORECASE)
_WIDTH = re.compile(r"#values\s*\{[^}]*?width\s*:\s*(\d+)")
_HEIGHT = re.compile(r"#values\s*\{[^}]*?height\s*:\s*(\d+)")
_ROW_NUMBER = re.compile(r"^\d{1,2}\.?$")
ROW_NUMBER = _ROW_NUMBER
# weekday button text -> position in the week (names are sorted alphabetically in HA)
WEEKDAYS = {
    day: i % 7 + 1
    for i, day in enumerate(
        ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    )
}
_RULE = re.compile(r"((?:#pos\d+[^{,]*,?\s*)+)\{([^}]*)\}")
_PROP = re.compile(r"([a-z-]+)\s*:\s*([^;]+)")


def parse_layout(html: str) -> PageLayout:
    """Parse a ``schematic_files/<n>.html`` file (title + CSS positions)."""
    layout = PageLayout()
    if match := _TITLE.search(html):
        layout.title = _clean(match.group(1)) or None
    if match := _IMAGE.search(html):
        layout.image = file_name(match.group(1))
    if match := _REFRESH.search(html):
        layout.refresh = int(match.group(1))
    if match := _BODY_BG.search(html):
        layout.background = match.group(1).strip()
    layout.css = sanitize_css(" ".join(_STYLE.findall(html)))
    if match := _WIDTH.search(html):
        layout.width = float(match.group(1))
    if match := _HEIGHT.search(html):
        layout.height = float(match.group(1))
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
            height=_px(prop.get("height", "0")),
        )
    return layout


def file_name(src: str | None) -> str | None:
    """``schematic_files/1_pos16_0.png`` -> ``1_pos16_0.png`` (pictures of the C.M.I. only)."""
    if not src:
        return None
    src = src.strip()
    if src.startswith("schematic_files/"):
        src = src[len("schematic_files/") :]
    return src if _FILE_NAME.match(src) else None


def sanitize_css(css: str) -> str:
    """Keep only the ``#values`` / ``#posNN`` rules of a schema page.

    The page CSS is shown inside Home Assistant, so nothing that could load
    external resources or escape the schema view is passed on.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    rules = []
    for selectors, body in _CSS_RULE.findall(css):
        kept = [
            s.strip()
            for s in selectors.split(",")
            if _CSS_SELECTOR.match(_WS.sub(" ", s.strip()))
        ]
        if not kept:
            continue
        decls = [
            d.strip()
            for d in body.split(";")
            if ":" in d and not _UNSAFE_CSS.search(d)
        ]
        if decls:
            rules.append(f"{', '.join(kept)} {{{'; '.join(decls)}}}")
    return "\n".join(rules)


def _px(value: str) -> float:
    match = re.match(r"\s*(-?\d+(?:\.\d+)?)", value)
    return float(match.group(1)) if match else 0.0


def _is_label_text(text: str, allow_row_number: bool = False) -> bool:
    if not text or text in {"-", "--", "?"}:
        return False
    if allow_row_number and _ROW_NUMBER.match(text):
        return True
    if _TIME_VALUE.match(text):
        return False
    if _NUMBER_VALUE.match(text):
        return False
    # "Außen: 5.8 °C" is a reading with its own label, not a label for something else
    inline = _INLINE_LABEL.match(text)
    if inline and (_NUMBER_VALUE.match(inline.group(2)) or _TIME_VALUE.match(inline.group(2))):
        return False
    return True


def _same_row(a: PositionInfo, b: PositionInfo) -> bool:
    tolerance = max(15.0, a.font_size * 0.6, b.font_size * 0.6)
    return abs(a.center_y - b.center_y) <= tolerance


def find_label_pos(
    pos: str, elements: dict[str, SchemaElement], layout: PageLayout
) -> str | None:
    """Position of the descriptive text on the same row, left of ``pos``."""
    own = layout.positions.get(pos)
    if own is None:
        return None
    best: tuple[float, str] | None = None
    for other_pos, other in elements.items():
        if other_pos == pos or other.is_change or other.is_button or other.is_link:
            continue
        info = layout.positions.get(other_pos)
        if info is None or not _same_row(own, info):
            continue
        if not _is_label_text(other.text, allow_row_number=True):
            continue
        distance = own.x - info.x
        if distance <= 0:
            continue
        if best is None or distance < best[0]:
            best = (distance, other_pos)
    return best[1] if best else None


def find_lamp_label(
    pos: str, elements: dict[str, SchemaElement], layout: PageLayout
) -> str | None:
    """Text next to a status picture; TA writes it right of the picture.

    A reading such as "Wohnen: 20.7 °C" next to it lends its label ("Wohnen").
    """
    own = layout.positions.get(pos)
    if own is None:
        return None
    best: tuple[float, str] | None = None
    for other_pos, other in elements.items():
        if other_pos == pos or other.is_change or other.is_button or other.is_link:
            continue
        info = layout.positions.get(other_pos)
        if info is None or abs(info.top - own.top) > max(12.0, info.font_size * 0.6):
            continue
        inline, _ = other.split_label()
        text = inline or (other.text if _is_label_text(other.text) else None)
        if not text:
            continue
        distance = info.x - own.x
        if distance <= 0:
            distance = -distance + 100  # left of the picture: only if nothing right
        if distance > 160:
            continue
        if best is None or distance < best[0]:
            best = (distance, text)
    return best[1] if best else None


def find_label(
    pos: str, elements: dict[str, SchemaElement], layout: PageLayout
) -> str | None:
    """Descriptive text written on the same row, left of ``pos``."""
    label_pos = find_label_pos(pos, elements, layout)
    return elements[label_pos].text if label_pos else None


def find_section(
    pos: str, elements: dict[str, SchemaElement], layout: PageLayout
) -> str | None:
    """Bold heading above ``pos`` in the same column, e.g. "Zeitprogramm 1".

    Short numbers on the heading row right of it (until the next heading) are
    appended, because TA pages often write "Zeitprogramm" and "1" separately.
    """
    own = layout.positions.get(pos)
    if own is None:
        return None
    best: tuple[tuple[float, float], str] | None = None
    for other_pos, other in elements.items():
        info = layout.positions.get(other_pos)
        if (
            info is None
            or not info.bold
            or other.is_change
            or other.is_button
            or other.is_link
            or not _is_label_text(other.text)
        ):
            continue
        above = own.top - info.top
        if info.top <= (layout.height or 816) * 0.15:
            continue  # page headline, not a section
        if above <= 20 or above > 350 or info.x > own.x + 40:
            continue
        key = (above, own.x - info.x)
        if best is None or key < best[0]:
            best = (key, other_pos)
    if best is None:
        return None
    head = layout.positions[best[1]]
    row = []
    for other_pos, other in elements.items():
        info = layout.positions.get(other_pos)
        if info is None or other.is_change or other.is_button or other.is_link:
            continue
        if not _same_row(head, info) or info.x < head.x:
            continue
        if other_pos == best[1] or _ROW_NUMBER.match(other.text):
            row.append((info.x, other_pos, other.text))
        elif _is_label_text(other.text):
            row.append((info.x, other_pos, None))  # next heading -> stop
    parts = []
    for _, other_pos, text in sorted(row):
        if text is None:
            break
        parts.append(text)
    return " ".join(parts) or None


def time_name(
    pos: str,
    elements: dict[str, SchemaElement],
    layout: PageLayout,
    time_positions: set[str],
    label_pos: dict[str, str | None],
    label: str | None,
) -> str:
    """Name a switching time, e.g. "Zeitprogramm 1 1. von"."""
    section = find_section(label_pos.get(pos) or pos, elements, layout)
    own = layout.positions.get(pos)
    siblings = sorted(
        (layout.positions[p].x, p)
        for p in time_positions
        if own is not None
        and p in layout.positions
        and label_pos.get(p) == label_pos.get(pos)
        and abs(layout.positions[p].top - own.top) <= 20
    )
    suffix = None
    if len(siblings) == 2:
        # "Beginn"/"Ende" (not "von"/"bis") so both sort in the right order
        suffix = "Beginn" if siblings[0][1] == pos else "Ende"
    elif len(siblings) > 2:
        suffix = str([p for _, p in siblings].index(pos) + 1)
    if label and _ROW_NUMBER.match(label):
        # rows "1.", "2.", "3." of a time program are its time windows
        label = f"Zeitfenster {label.rstrip('.')}"
    elif not label and own is not None:
        # unlabeled rows "06:00 - 07:00" below each other: number them
        rows: list[float] = []
        for p in time_positions:
            info = layout.positions.get(p)
            if (
                info is None
                or label_pos.get(p) is not None
                or find_section(p, elements, layout) != section
            ):
                continue
            if not any(abs(info.top - top) <= 20 for top in rows):
                rows.append(info.top)
        rows.sort()
        if len(rows) > 1:
            index = next(i for i, top in enumerate(rows) if abs(own.top - top) <= 20)
            label = f"Zeitfenster {index + 1}"
    return " ".join(part for part in (section, label, suffix) if part) or f"Schaltzeit {pos[3:]}"


def find_headline(elements: dict[str, SchemaElement], layout: PageLayout) -> str | None:
    """Texts in the topmost row of the page (e.g. "Einstellungen FBH EG")."""
    limit = (layout.height or 816) * 0.15
    candidates = []
    for pos, el in elements.items():
        info = layout.positions.get(pos)
        if info is None or info.top > limit or el.is_change or el.is_button or el.is_link:
            continue
        if _is_label_text(el.text):
            candidates.append((info, el.text))
    if not candidates:
        return None
    top_row = min(info.top for info, _ in candidates)
    parts = [(info.x, text) for info, text in candidates if info.top - top_row <= 20]
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
    if unit and not re.search(r"[^\W\d_]|[°%]", unit):
        return None  # "1." is a row number, not a reading with unit "."
    return NumberValue(float(match.group(1).replace(",", ".")), unit)


def parse_on_off(text: str) -> bool | None:
    """``"ON"`` / ``"OFF"`` (pump outputs shown as text)."""
    value = text.strip(" :").upper()  # "Zirkpu.: : OFF" leaves ": OFF"
    if value in ("ON", "EIN"):
        return True
    if value in ("OFF", "AUS"):
        return False
    return None


def parse_time_minutes(text: str) -> int | None:
    text = text.strip()
    if text.endswith("Uhr"):
        text = text[:-3].strip()  # "19:21 Uhr"
    match = _TIME_VALUE.match(text)
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
