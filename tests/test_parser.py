"""Parser tests with real responses of a C.M.I. (firmware with Keil-EWEB/2.1)."""

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"

# load parser.py standalone (it has no Home Assistant imports)
_spec = importlib.util.spec_from_file_location(
    "cmi_parser", ROOT / "custom_components" / "ta_cmi_schema" / "parser.py"
)
p = importlib.util.module_from_spec(_spec)
sys.modules["cmi_parser"] = p
_spec.loader.exec_module(p)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ValuesTest(unittest.TestCase):
    def test_page_with_labels_from_layout(self):
        values = p.parse_values(fixture("3.cgi"))
        layout = p.parse_layout(fixture("3.html"))
        self.assertEqual(layout.title, "Heizkreis Start")
        self.assertEqual(p.find_headline(values, layout), "Einstellungen FBH EG")
        changeable = {pos: el for pos, el in values.items() if el.is_change}
        self.assertEqual(set(changeable), {"pos1", "pos3", "pos5"})
        self.assertEqual(changeable["pos3"].address, "10148110187")
        self.assertEqual(p.find_label("pos1", values, layout), "Betrieb")
        self.assertEqual(p.find_label("pos3", values, layout), "T.Raum Normal")
        self.assertEqual(p.find_label("pos5", values, layout), "T.Raum Absenk")
        self.assertEqual(p.parse_number(changeable["pos3"].text).value, 22.0)
        self.assertEqual(p.parse_number(changeable["pos3"].text).unit, "°C")

    def test_inline_labels_times_and_buttons(self):
        values = p.parse_values(fixture("20.cgi"))
        self.assertEqual(values["pos18"].split_label(), ("RL Zirk.SOLL", "35.5 °C"))
        self.assertEqual(p.parse_number(values["pos19"].split_label()[1]).value, -5.0)
        self.assertEqual(values["pos7"].split_label(), (None, "06:00"))
        self.assertEqual(p.parse_time_minutes(values["pos7"].text), 360)
        self.assertIsNone(p.parse_number("06:00"))
        self.assertTrue(values["pos0"].is_button)
        self.assertEqual(values["pos0"].visible_state, 1)
        self.assertEqual(values["pos1"].visible_state, 0)
        self.assertEqual(values["pos1"].button_text, "Mo")
        self.assertTrue(values["pos21"].is_link)


class NamingTest(unittest.TestCase):
    def test_room_controller_headline(self):
        values = p.parse_values(fixture("21.cgi"))
        layout = p.parse_layout(fixture("21.html"))
        self.assertEqual(p.find_headline(values, layout), "WZ-Küche")
        self.assertEqual(p.find_label("pos4", values, layout), "T.Raum Normal")
        self.assertEqual(p.find_label("pos3", values, layout), "T.Raum Absenk")

    def test_time_program(self):
        values = p.parse_values(fixture("5.cgi"))
        layout = p.parse_layout(fixture("5.html"))
        self.assertEqual(p.find_headline(values, layout), "Zeitprog. FBH EG")
        label_pos = {pos: p.find_label_pos(pos, values, layout) for pos in values}
        times = {"pos32", "pos33", "pos38", "pos39"}

        def name(pos):
            lp = label_pos[pos]
            return p.time_name(pos, values, layout, times, label_pos, values[lp].text if lp else None)

        self.assertEqual(name("pos32"), "Zeitprogramm 1 Zeitfenster 1 von")
        self.assertEqual(name("pos33"), "Zeitprogramm 1 Zeitfenster 1 bis")
        self.assertEqual(name("pos38"), "Zeitprogramm 2 Zeitfenster 1 von")
        self.assertEqual(name("pos39"), "Zeitprogramm 2 Zeitfenster 1 bis")
        # weekday buttons: row label is the program number
        self.assertEqual(p.find_label("pos19", values, layout), "1")


class StartPageTest(unittest.TestCase):
    """Overview page with status pictures, controller clock and power in "KW"."""

    def setUp(self):
        self.values = p.parse_values(fixture("1.cgi"))
        self.layout = p.parse_layout(fixture("1.html"))

    def lamp(self, pos):
        return p.find_lamp_label(pos, self.values, self.layout)

    def test_status_pictures(self):
        lamps = {pos for pos, el in self.values.items() if el.is_lamp}
        self.assertEqual(
            lamps,
            {"pos16", "pos17", "pos38", "pos43", "pos46", "pos47", "pos52", "pos54"},
        )
        self.assertEqual(self.values["pos46"].visible_state, 1)
        self.assertEqual(self.values["pos47"].visible_state, 0)
        # label written right of the picture
        self.assertEqual(self.lamp("pos46"), "Heizen")
        self.assertEqual(self.lamp("pos47"), "Warmwasser")
        self.assertEqual(self.lamp("pos52"), "STOPP")
        self.assertEqual(self.lamp("pos54"), "PV-Betrieb")
        self.assertEqual(self.lamp("pos16"), "Keller-Lager")
        self.assertEqual(self.lamp("pos17"), "Büro")
        # label of a reading next to the picture
        self.assertEqual(self.lamp("pos43"), "Wohnen")
        self.assertEqual(self.lamp("pos38"), "Gäste SZ")

    def test_links_and_values_are_not_lamps(self):
        self.assertFalse(self.values["pos76"].is_lamp)
        self.assertFalse(self.values["pos67"].is_lamp)
        self.assertFalse(self.values["pos0"].is_lamp)

    def test_controller_clock(self):
        self.assertEqual(p.parse_time_minutes(self.values["pos67"].text), 19 * 60 + 21)
        self.assertIsNone(p.find_label("pos67", self.values, self.layout))

    def test_power_in_kw(self):
        self.assertEqual(p.parse_number(self.values["pos7"].text).unit, "KW")


class HeatPumpPageTest(unittest.TestCase):
    """Page 2: large fonts, heat pump status pictures, pumps as ON/OFF text."""

    def setUp(self):
        self.values = p.parse_values(fixture("2.cgi"))
        self.layout = p.parse_layout(fixture("2.html"))

    def test_heat_pump_status(self):
        lamp = lambda pos: p.find_lamp_label(pos, self.values, self.layout)  # noqa: E731
        self.assertEqual(lamp("pos41"), "Heizen")
        self.assertEqual(lamp("pos43"), "Warmwasser")
        self.assertEqual(lamp("pos45"), "PV-Überschuss")
        self.assertEqual(lamp("pos28"), "Wohnen")
        self.assertEqual(self.values["pos41"].visible_state, 1)

    def test_pump_text(self):
        for pos, label, state in (
            ("pos5", "Pumpe", False),
            ("pos15", "Zirkpu.", False),
            ("pos27", "Pu. Ofen", True),
        ):
            inline, value = self.values[pos].split_label()
            self.assertEqual(inline, label)
            self.assertIs(p.parse_on_off(value), state)

    def test_power_without_space(self):
        number = p.parse_number(self.values["pos36"].text)
        self.assertEqual((number.value, number.unit), (0.0, "KW"))


class LabelFilterTest(unittest.TestCase):
    def test_readings_are_not_labels(self):
        self.assertFalse(p._is_label_text("Außen: 5.8 °C"))
        self.assertFalse(p._is_label_text("22.0 °C"))
        self.assertFalse(p._is_label_text("06:00"))
        self.assertFalse(p._is_label_text("-"))
        self.assertTrue(p._is_label_text("T.Raum Normal"))
        self.assertTrue(p._is_label_text("1.", allow_row_number=True))

    def test_row_numbers_are_not_readings(self):
        self.assertIsNone(p.parse_number("1."))
        self.assertIsNone(p.parse_number("3."))
        self.assertEqual(p.parse_number("0 %").unit, "%")
        self.assertEqual(p.parse_number("2.5 kW").unit, "kW")


class ChangerTest(unittest.TestCase):
    def test_number(self):
        c = p.parse_changer(fixture("changer_number.html"))
        self.assertEqual(c.kind, p.KIND_NUMBER)
        self.assertEqual(c.write_address, "0100014811D101")
        self.assertEqual((c.minimum, c.maximum, c.step, c.unit), (0.0, 45.0, 0.1, "°C"))
        self.assertEqual(p.decimals_for_step(c.step), 1)

    def test_select(self):
        c = p.parse_changer(fixture("changer_select.html"))
        self.assertEqual(c.kind, p.KIND_SELECT)
        self.assertEqual(c.write_address, "010001483B1101")
        self.assertEqual(c.options[3], ("3", "Standby/Frostschutz"))
        self.assertEqual(c.selected, "1")

    def test_time(self):
        c = p.parse_changer(fixture("changer_time.html"))
        self.assertEqual(c.kind, p.KIND_TIME)
        self.assertEqual(c.write_address, "0100174848C13C")


class SchemaViewTest(unittest.TestCase):
    def test_pictures_links_and_page_css(self):
        values = p.parse_values(fixture("1.cgi"))
        self.assertEqual(
            values["pos16"].images,
            [
                {"name": "1_pos16_0.png", "bis": 0, "hide": True},
                {"name": "1_pos16_1.png", "bis": None, "hide": False},
            ],
        )
        self.assertEqual(values["pos76"].link_page, 3)
        layout = p.parse_layout(fixture("1.html"))
        self.assertEqual(layout.image, "1.png")
        self.assertEqual(layout.refresh, 60)
        self.assertIn("#pos16 img {height:20px; width:20px}", layout.css)

    def test_button_faces(self):
        values = p.parse_values(fixture("5.cgi"))
        self.assertEqual(values["pos19"].spans, [["v0", "Mo"], ["v1", "Mo"]])
        self.assertEqual(values["pos19"].button_text, "Mo")
        css = p.parse_layout(fixture("5.html")).css
        self.assertIn("#pos19.visible1 .v1 {", css)

    def test_css_is_sanitized(self):
        css = p.sanitize_css(
            "body{margin:0} #pos1{background:url(http://evil)} #pos2{color:red; behavior:x}"
            " .other{top:0} #pos3, .x{left:1px} /* #pos4{top:1px} */"
        )
        self.assertEqual(css, "#pos2 {color:red}\n#pos3 {left:1px}")

    def test_file_names(self):
        self.assertEqual(p.file_name("schematic_files/1_pos16_0.png"), "1_pos16_0.png")
        self.assertIsNone(p.file_name("../secret.png"))
        self.assertIsNone(p.file_name("http://x/y.png"))
        self.assertIsNone(p.file_name("schematic_files/1.cgi"))


if __name__ == "__main__":
    unittest.main()
