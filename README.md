# Technische Alternative C.M.I. Schema – Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

**Deutsch** · [English below](#english)

Liest und schreibt **alle Werte, die im Schema des C.M.I. (Technische Alternative) änderbar sind** – Sollwerte, Betriebsarten, Schaltzeiten, Wochentage – direkt aus Home Assistant. Ohne CoE, ohne Eingriff in die UVR-Programmierung und ohne Adressen von Hand suchen.

Die Integration benutzt dieselben Seiten wie die Weboberfläche des C.M.I. („Startseite Regelung“ / `schema.html`). Was dort klickbar ist, wird in Home Assistant zur Entität.

> Für Messwerte, Ein- und Ausgänge gibt es die Integration [ta_cmi](https://github.com/DeerMaximum/ta_cmi) (JSON-API, nur lesen). Diese Integration ergänzt sie um das **Schreiben**.

## Was wird angelegt?

| Im C.M.I.-Schema | In Home Assistant |
|---|---|
| Zahlenwert (z. B. `T.Raum Normal 22.0 °C`) | `number` mit Bereich und Schrittweite aus dem C.M.I. |
| Auswahl (z. B. Betriebsart *Zeit/Auto, Normal, Abgesenkt, Standby*) | `select` |
| Uhrzeit (z. B. Zeitprogramm `06:00`) | `time` |
| Ein/Aus-Taste (z. B. Wochentage *Mo … So*) | `switch` |
| angezeigte Messwerte (z. B. `RL Zirk. Ist: 20.7 °C`) | `sensor` (standardmäßig deaktiviert) |
| Statusbilder (Pumpe, Ventil, WP *Heizen*, *STOPP* …) und `ON`/`OFF`-Texte | `binary_sensor` (standardmäßig deaktiviert) |

Jede Schemaseite wird ein eigenes Gerät (Name = oberste Textzeile der Seite, z. B. „WZ-Küche“). Die Namen der Werte kommen aus dem Text, der im Schema in derselben Zeile links daneben steht (bei Statusbildern rechts daneben). Schaltzeiten bekommen zusätzlich die Überschrift darüber und „Beginn“/„Ende“, z. B. „Zeitprogramm 1 Zeitfenster 1 Beginn“; stehen sie ohne Zeilennummer untereinander, werden sie durchnummeriert („Zeitfenster 2 Beginn“). Wochentage heißen „Wochentag 1 Mo“ … „Wochentag 7 So“ (bzw. „Zeitprogramm 1 Wochentag 1 Mo“), damit Home Assistant sie von Montag bis Sonntag sortiert.

Nach einem Update liest die Integration das Schema automatisch neu ein, wenn sich die Erkennung geändert hat. Die angezeigten Namen werden dabei aktualisiert, die Entitäts-IDs bleiben (neu erstellen: *Einstellungen → Entitäten → auswählen → Entitäts-IDs neu erstellen*).

## Installation

### Marketplace (HACS)
Ab Home Assistant 2026.11 heißt HACS *Marketplace*.

1. Marketplace (bzw. HACS) → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/codo70/ha-ta-cmi-schema`, Typ *Integration*
2. „Technische Alternative C.M.I. Schema“ installieren, Home Assistant neu starten

### Manuell
Ordner `custom_components/ta_cmi_schema` nach `<config>/custom_components/` kopieren und neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → Technische Alternative C.M.I. Schema*

- **Host:** IP oder Name des C.M.I., z. B. `192.168.1.50`
- **Benutzername / Passwort:** Login des C.M.I.

Beim ersten Start werden alle Schemaseiten (1, 2, 3, … bis drei Seiten in Folge fehlen) eingelesen. Das dauert je nach Schema 10–60 Sekunden und wird danach zwischengespeichert.

### Optionen
- **Abfrageintervall** (Standard 60 s)
- **Nur diese Schemaseiten**, z. B. `3, 7, 20-28` (leer = alle)
- **Messwerte als Sensoren anlegen** (an/aus)
- **Dashboard „T.A. Schema“ in der Seitenleiste anzeigen** (an/aus)

### Schema geändert?
Nach Änderungen im TA Designer den Button **„Schema neu einlesen“** am C.M.I.-Gerät drücken (oder Aktion `ta_cmi_schema.rediscover`).

## Schema-Ansicht (Dashboard und Karte)
Die Schemaseiten erscheinen in Home Assistant so wie im C.M.I. – mit Hintergrundbild, Live-Werten, Statusbildern und Tasten:

- **Dashboard „T.A. Schema“** in der Seitenleiste: ein Reiter pro Schemaseite, wird automatisch angelegt.
- **Karte** für eigene Dashboards: *Karte hinzufügen → „T.A. C.M.I. Schema“* und die Seite auswählen, oder in YAML:
  ```yaml
  type: custom:ta-cmi-schema-card
  page: 5
  ```

Antippen funktioniert wie im C.M.I.: Werte öffnen den Home-Assistant-Dialog zum Ändern, Ein/Aus-Tasten schalten direkt, Navigationsflächen wechseln die Seite. Bilder und Werte holt die Integration selbst – der C.M.I.-Login bleibt im Server, die Ansicht funktioniert daher auch unterwegs in der App.

## Aktionen

```yaml
# beliebigen Wert über die Kurzadresse aus dem Schema schreiben
action: ta_cmi_schema.write_value
data:
  short_address: "10148110187"   # adresse="…" eines class="changex2"-Elements
  value: 21.5                     # Zahl | Index der Auswahl (0, 1, …) | Minuten bei Uhrzeiten
```

## So funktioniert es

| Anfrage | Inhalt |
|---|---|
| `schematic_files/<n>.cgi` | aktuelle Werte der Seite *n* (`<div id="posNN" class="changex2" adresse="…">`) |
| `schematic_files/<n>.html` | Titel und Positionen (daraus werden Beschriftungen ermittelt) |
| `INCLUDE/changerx2.cgi?sadrx2=<Kurzadresse>` | Änderungsdialog: Schreibadresse, Typ, min/max/Schritt bzw. Auswahlliste |
| `INCLUDE/change.cgi?changeadrx2=<Adresse>&changetox2=<Wert>` | schreibt den Wert |

Die 11-stellige **Kurzadresse** ist stabil. Die 14-stellige **Schreibadresse** wird vor jedem Schreiben frisch geholt, weil sie sich bei Auswahlwerten mit dem aktuellen Zustand ändert. Uhrzeiten werden in Minuten seit Mitternacht geschrieben (24:00 = 1440, in Home Assistant als 23:59:59 dargestellt).

## Hinweise
- Funktioniert nur, wenn im C.M.I. ein **Schema** (TA Designer) hinterlegt ist.
- Alle Anfragen laufen nacheinander, um den kleinen Webserver des C.M.I. nicht zu überlasten.
- Getestet mit C.M.I. (Webserver *Keil-EWEB/2.1*), UVR16x2 und RAS-Raumreglern.
- Inoffizielles Projekt, nicht von Technische Alternative.
- **Installation und Nutzung erfolgen auf eigenes Risiko.** Die Integration schreibt Werte direkt in die Heizungsregelung – Änderungen bitte prüfen. Es wird keine Haftung für Schäden oder Fehlfunktionen übernommen.

---

## English

Reads and writes **every value that can be changed in the C.M.I. schema** (Technische Alternative) – setpoints, operating modes, switching times, weekdays – from Home Assistant, without CoE and without looking up addresses manually.

The integration uses the same requests as the C.M.I. schema web page. Each schema page becomes a device; changeable numbers become `number`, selections `select`, clock times `time`, on/off buttons `switch`, displayed readings optional (disabled) `sensor` entities. Labels are taken from the text left of the value on the same row.

**Install:** add `https://github.com/codo70/ha-ta-cmi-schema` as a custom repository in the Marketplace (HACS) (type *Integration*), or copy `custom_components/ta_cmi_schema` manually. Then add the integration with host, user and password of the C.M.I.

**Options:** polling interval, page selection (`3, 7, 20-28`), sensors on/off. After changing the schema in TA Designer press **"Re-read schema"**.

**Schema view:** the sidebar dashboard "T.A. Schema" shows every schema page like the C.M.I. does (background, live values, status pictures, buttons). For your own dashboards use the card `type: custom:ta-cmi-schema-card` with `page: <n>`.

**Action:** `ta_cmi_schema.write_value` with `short_address` and `value`.

Unofficial project, not affiliated with Technische Alternative. MIT license.

**Install and use at your own risk.** The integration writes values directly to the heating controller – please double-check changes. No liability is accepted for any damage or malfunction.
