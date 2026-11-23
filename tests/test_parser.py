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

        self.assertEqual(name("pos32"), "Zeitprogramm 1 1. von")
        self.assertEqual(name("pos33"), "Zeitprogramm 1 1. bis")
        self.assertEqual(name("pos38"), "Zeitprogramm 2 1. von")
        self.assertEqual(name("pos39"), "Zeitprogramm 2 1. bis")
        # weekday buttons: row label is the program number
        self.assertEqual(p.find_label("pos19", values, layout), "1")


class LabelFilterTest(unittest.TestCase):
    def test_readings_are_not_labels(self):
        self.assertFalse(p._is_label_text("Außen: 5.8 °C"))
        self.assertFalse(p._is_label_text("22.0 °C"))
        self.assertFalse(p._is_label_text("06:00"))
        self.assertFalse(p._is_label_text("-"))
        self.assertTrue(p._is_label_text("T.Raum Normal"))
        self.assertTrue(p._is_label_text("1.", allow_row_number=True))


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


if __name__ == "__main__":
    unittest.main()
