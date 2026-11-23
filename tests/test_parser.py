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
