# Entities Documentation

The integration creates multiple Home Assistant entities automatically based on your panel configuration.

> **Important:** Only zones, areas, and macros with **configured names** in the panel are created as entities.

## Entity ID Naming Convention

All entity IDs use a prefix based on the **integration name** you choose during setup in Home Assistant.

**Default prefix:** `combivox_alarm_` (if you keep the default name "Combivox Alarm")

**Custom prefix:** The prefix changes if you customize the integration name during setup.

**Examples:**
- Default name → `sensor.combivox_alarm_model`
- Custom name "Casa Allarme" → `sensor.casa_allarme_model`
- Custom name "Alarm" → `sensor.alarm_model`

> **Note:** In this document, we use the default prefix `combivox_alarm_` for all entity ID examples. Your actual entity IDs may differ based on your integration name.

## Alarm Control Panel

### `alarm_control_panel.combivox_alarm`

The main alarm control panel entity.

**Supported States:**
- `disarmed` - Panel is disarmed
- `arming` - Panel is arming (exit delay active)
- `armed_away` - Away mode armed
- `armed_home` - Home mode armed
- `armed_night` - Night mode armed
- `triggered` - ALARM! The panel has detected an alarm
- `pending` - Pre-alarm state

**Configuration:**
- **Arm Away:** Arms areas configured in "Areas for Away Mode"
- **Arm Home:** Arms areas configured in "Areas for Home Mode"
- **Arm Night:** Arms areas configured in "Areas for Night Mode"
- **Disarm:** Disarms areas configured in "Areas for Disarm Mode" (or all areas if empty)

---

## System Sensors

### `sensor.combivox_alarm_ystem_status`
Current alarm state of the panel.

**States:** `disarmed`, `arming`, `armed_away`, `armed_home`, `armed_night`, `triggered`, `pending`

**Attributes:**
- `alarm_hex` - Raw hex code from panel (e.g., `0C`, `8C`)

### `sensor.combivox_alarm_model`
Device model and web interface type.

**States:** Example: `Amica 64 LTE + AmicaWeb Plus`

**Attributes:**
- `model_raw` - Raw model name from panel
- `web_interface` - Web interface type (AmicaWeb, AmicaWeb Plus, SmartWeb)

### `sensor.combivox_alarm_datetime`
Panel date and time.

**Attributes:**
- `datetime` - ISO 8601 formatted datetime with timezone

### `sensor.combivox_alarm_gsm_status`
GSM connection status.

**States:**
- `ok` - GSM connected and working
- `no_sim` - No SIM card detected
- `searching` - Searching for GSM network
- `unknown` - Status unknown

**Attributes:**
- `gsm_hex` - Raw hex status code from panel

### `sensor.combivox_alarm_gsm_operator`
GSM operator name.

**States:** `vodafone`, `tim`, `wind`, `combivox`, `other`, `unknown`

**Attributes:**
- `operator_hex` - Raw hex operator code

### `sensor.combivox_alarm_gsm_signal`
GSM signal strength as percentage.

**States:** `0` to `100` (percentage)

**Attributes:**
- `signal_bars` - Signal strength in bars (0-5)

### `sensor.combivox_alarm_anomalies`
System anomalies/trouble status.

**States:**
- `ok` - No anomalies
- `gsm_trouble` - GSM communication fault
- `bus_trouble` - Bus communication fault
- `unknown` - Unknown status

**Attributes:**
- `anomalies_hex` - Raw hex code (for debugging)

---

## Diagnostic Buttons

### `button.combivox_alarm_clear_alarm_memory`
Clears alarm memory from the panel.

**Action:** Press the button to clear all alarm memory entries

**Category:** DIAGNOSTIC

---

## Zone Binary Sensors

For each zone with a configured name, the integration creates:

### `binary_sensor.combivox_alarm_<zone_name>`

Zone open/closed status sensor.

**States:**
- `on` - Zone is open (triggered)
- `off` - Zone is closed (normal)

**Device Class:** Automatically detected (window, door, motion, smoke, etc.)

**Attributes:**
- `zone_id` - Zone number (1-64, depending on panel model)
- `alarm` - True if zone is currently in alarm state
- `alarm_memory` - True if zone has alarm memory (past alarm)
- `included` - True if zone is included (not bypassed/excluded)

**Example entity IDs:**
- `binary_sensor.portoncino`
- `binary_sensor.sala`
- `binary_sensor.finestra_camera`

---

## Zone Bypass Buttons

For each zone with a configured name, the integration creates:

### `button.combivox_alarm_<zone_name>_bypass`

Toggle zone inclusion/exclusion (bypass).

**Action:** Press to toggle zone between included and excluded states

**Icon:**
- `mdi:shield` - Zone is included (active)
- `mdi:shield-off` - Zone is excluded (bypassed)

**Category:** CONFIG

**Example entity IDs:**
- `button.portoncino_bypass`
- `button.sala_bypass`

---

## Area Binary Sensors

For each area with a configured name, the integration creates:

### `binary_sensor.combivox_alarm_<area_name>`

Area armed/disarmed status sensor.

**States:**
- `on` - Area is armed
- `off` - Area is disarmed

**Icon:**
- `mdi:shield-lock` - Area is armed
- `mdi:shield-home` - Area is disarmed

**Attributes:**
- `area_id` - Area number (1-8)
- `status` - Text status: "armed" or "disarmed"

**Example entity IDs:**
- `binary_sensor.casa_mamma`
- `binary_sensor.garage`

---

## Macro/Scenario Buttons

For each macro/scenario with a configured name, the integration creates:

### `button.combivox_alarm_<macro_name>`

Execute a macro/scenario on the panel.

**Action:** Press to execute the macro

**Icon:** `mdi:play-box-outline`

**Category:** CONFIG

**Example entity IDs:**
- `button.uscita`
- `button.presto_notturno`

> **Note:** Macros must have names configured in the panel to appear as buttons.
