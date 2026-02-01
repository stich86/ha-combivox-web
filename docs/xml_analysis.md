# XML Analysis - status9.xml Structure

This document contains the analysis of the `/status9.xml` endpoint response structure from Combivox alarm panels.

**Authentication Required:** This endpoint requires an authentication cookie to access.

## Overview

The `<si>` field in `status9.xml` contains multiple pieces of data encoded as a hexadecimal string. This document maps each byte position to its meaning based on analysis and testing.

**Numbering Convention:** This document uses **0-based indexing** (standard in programming):
- Byte 0 = 1st byte
- Byte 1 = 2nd byte
- Byte 9 = 10th byte
- etc.

⚠️ **Important:** The `FFFFFF` marker position is **dynamic** and varies depending on:
- Whether the panel has 16 extra bytes for operator name (AmicaWeb Plus/SmartWeb)
- Panel configuration
- Other factors

Therefore, positions after the first bytes are expressed as **offsets from the marker**.

## Data Structure

The hexadecimal string structure:

```
<header_fixed><optional_operator_name><marker><zones_data><inclusion><anomalies><alarm_memory>
```

Example with `|` separators (not in actual data):

```
03|16|00|FFFF|FF|05|091DFF|00|<variable>|FFFFFF|0101|<zones>|0000|<inclusion>|40|<alarm_memory>
```

## Fixed Header Section (First 10 bytes, BEFORE variable section)

These bytes are always at the same position at the start of the string:

| Byte | Hex Example | Description | Notes |
|------|-------------|-------------|-------|
| 0 | `03` | Unknown | Purpose not yet identified |
| 1 | `16` | Unknown | Purpose not yet identified |
| 2 | `00` | **Signal Strength** | 00-05 (5 bars = 100%) |
| 3-4 | `FFFF` | Padding | Always `FFFF` |
| 5 | `FF` | **SIM Operator** | See operator codes below |
| 6 | `05` | **GSM Status** | See status codes below |
| 7 | `09` | **SIM Expiry Month** | 01-0C (1-12 decimal) |
| 8 | `1D` | **SIM Expiry Day** | 01-1F (1-31 decimal) |
| 9 | `FF` | **SIM Expiry Year** | `FF` = not set |

**Note:** 1 byte = 2 hexadecimal characters (0-255 decimal)

## Variable Section (Operator Name)

On **AmicaWeb Plus** and **SmartWeb** interfaces only:
- **16 additional bytes** (bytes 10-25) containing the **GSM operator name in hexadecimal**
- This section contains **ONLY the operator name encoded in hex**, NOT the network type
- This section is **NOT present** on base AmicaWeb
- This causes the `FFFFFF` marker position to shift by 16 bytes

**Example:**
- AmicaWeb base: marker starts at byte ~108
- AmicaWeb Plus/SmartWeb: marker starts at byte ~124 (108 + 16)

## Dynamic Marker

The `FFFFFF` marker (3 bytes = 6 hex characters) is always followed by `0000` or `0101`.

**Finding the marker:** Search for `FFFFFF` (6 chars) followed by `0000` or `0101`.

**Example:**
```
...FF|FFFFFF|0101|...
     ^marker  ^suffix
```

## Data Relative to Marker (Byte Offsets)

All data after the fixed header is accessed as **byte offsets from the marker position**.

### Visual Overview

```
[16 bytes BEFORE marker] <-- [FFFFFF marker] --> [173+ bytes AFTER marker]

BEFORE the marker (going backward 16 bytes):
  16th back: Alarm State (0C=disarmed, 8C=triggered)
  15th back: Padding
  14th back: Programming Status (04=free, 84=programming)
  13th back: Programming Flag
  12th back: Unknown
  11th back: Arming Timer (seconds in hex, e.g. 1E = 30s)
  10th-6th back: Unknown (5 bytes)
  5th back: Areas State (8 areas bitmask)
  4th-2nd back: Unknown (3 bytes)

AFTER the marker (going forward from FFFFFF):
  1st-3rd bytes: FFFFFF marker (3 bytes)
  4th-5th bytes: Padding (2 bytes)
  6th-45th bytes: Zone Status (40 bytes, zones 1-8 start at byte 6)
  46th-47th bytes: Padding FF (2 bytes)
  48th-87th bytes: Zone Inclusion (40 bytes)
  88th-89th bytes: Padding FF (2 bytes)
  90th-173rd bytes: Unknown data (84 bytes)
  174th byte: Anomalies (00=OK, 40=GSM, 01=Bus)
  Last 40 bytes: Alarm Memory (320 zones max)
```

### BEFORE the Marker (Going backward from FFFFFF)

| Byte going BACK from marker | Description |
|---------------------------|-------------|
| **16th byte back** | **Alarm State** (0C=disarmed, 8C=triggered) |
| 15th byte back | Padding |
| 14th byte back | **Programming Status** (04=free, 84=programming) |
| 13th byte back | **Programming Flag** (changes when programming) |
| 12th byte back | ❓ Unknown |
| 11th byte back | **Arming Timer** (seconds in hex, e.g., 1E = 30 seconds) |
| 10th byte back | ❓ Unknown |
| 9th byte back | ❓ Unknown |
| 8th byte back | ❓ Unknown |
| 7th byte back | ❓ Unknown |
| 6th byte back | ❓ Unknown |
| **5th byte back** | **Areas State** (8 areas bitmask, which areas are armed) |
| 4th byte back | ❓ Unknown |
| 3rd byte back | ❓ Unknown |
| 2nd byte back | ❓ Unknown |

### AFTER the Marker (Going forward from FFFFFF)

| Byte going FORWARD from marker | Length | Description |
|------------------------------|--------|-------------|
| **1st-3rd bytes** | 3 bytes | **Marker** (`FFFFFF`) |
| 4th-5th bytes | 2 bytes | Padding |
| **6th-45th bytes** | 40 bytes | **Zone Status** (320 zones max, zones 1-8 in 6th byte) |
| 46th-47th bytes | 2 bytes | Padding (`FF`) |
| 48th-87th bytes | 40 bytes | **Zone Inclusion** (320 zones max, which zones are active) |
| 88th-89th bytes | 2 bytes | Padding (`FF`) |
| 90th-173rd bytes | 84 bytes | ❓ Unknown data |
| **174th byte** | 1 byte | **Anomalies** (00=OK, 40=GSM trouble, 01=Bus trouble) |
| Last 40 bytes (from end) | 40 bytes | **Alarm Memory** (320 zones max, which zones have alarm) |

## Code Tables

### Signal Strength (Byte 2)

| Value | Bars | Percentage | Description |
|-------|------|------------|-------------|
| `00` | 0 | 0% | No signal |
| `01` | 1 | 20% | Very weak |
| `02` | 2 | 40% | Weak |
| `03` | 3 | 60% | Fair |
| `04` | 4 | 80% | Good |
| `05` | 5 | 100% | Excellent |
| `FF` | - | Unknown | Not available |

### GSM Operator Codes (Byte 5)

| Value | Operator | Description |
|-------|----------|-------------|
| `00` | Other | Alternative operator |
| `01` | Vodafone | Vodafone network |
| `02` | TIM | Telecom Italia Mobile |
| `03` | WIND | WIND / WINDTRE |
| `04` | Combivox | Combivox operator |
| `FF` | Unknown | Not detected / invalid |

### GSM Status Codes (Byte 6)

| Value | Status | Description |
|-------|--------|-------------|
| `00` | OK | GSM connected and working |
| `04` | Searching | Searching for GSM network |
| `05` | No SIM | No SIM card detected |
| Other | Unknown | Invalid status |

### Alarm State (marker - 16, 16 bytes BEFORE marker)

| Value | State | Description |
|-------|-------|-------------|
| `08` | Disarmed (GSM Excluded) | System disarmed, GSM excluded |
| `0C` | Disarmed | System fully disarmed |
| `0D` | Disarmed with Delay | Disarmed but with delay enabled |
| `0E` | Arming | Exit delay active |
| `8D` | Pending | Entry delay / pre-alarm |
| `8C` | Triggered | **ALARM!** System in alarm |
| `88` | Triggered (GSM Excluded) | **ALARM!** Alarm with GSM excluded |

### Programming Status (marker - 14, 14 bytes BEFORE marker)

Indicates whether a programmer is connected to the panel.

| Value | Status | Description |
|-------|--------|-------------|
| `04` | Free | No programmer connected |
| `84` | Programming | Programmer connected and in use |

### Programming Flag (marker - 13, 13 bytes BEFORE marker)

This byte changes when programming operations are performed on the panel.

### Arming Timer (marker - 11, 11 bytes BEFORE marker)

Contains the arming delay (exit delay) timer value in **seconds**, expressed as hexadecimal.

**Examples:**
- `1E` = 30 seconds
- `3C` = 60 seconds (1 minute)
- `78` = 120 seconds (2 minutes)

### Areas State (marker - 5, 5 bytes BEFORE marker)

The areas state is a **single byte bitmask** where each bit represents one of 8 areas (which areas are currently armed):

| Bit | Area | Description |
|-----|------|-------------|
| 0 | Area 1 | Armed if set |
| 1 | Area 2 | Armed if set |
| 2 | Area 3 | Armed if set |
| 3 | Area 4 | Armed if set |
| 4 | Area 5 | Armed if set |
| 5 | Area 6 | Armed if set |
| 6 | Area 7 | Armed if set |
| 7 | Area 8 | Armed if set |

**Common Examples:**
- `01` (binary `00000001`) = Only Area 1 armed
- `02` (binary `00000010`) = Only Area 2 armed
- `0C` (binary `00001100`) = Areas 3 and 4 armed (bits 2 + 3)
- `FF` (binary `11111111`) = All 8 areas armed

**How to calculate:**
- Each bit represents an area: bit 0 = Area 1, bit 1 = Area 2, etc.
- To arm multiple areas, sum the corresponding bit values
- Example: Areas 1, 3, 5 = bits 0, 2, 4 = 1 + 4 + 16 = `11` (hex)

### Zone Status (marker + 5 to marker + 44, 40 bytes AFTER marker)

Zone status starts **2 bytes after the FFFFFF marker** (zones 1-8 are in the 3rd byte after marker).

Each byte contains **8 zones** (1 bit per zone):

- **`0`** = Zone closed / normal
- **`1`** = Zone open / triggered

**Format:**
- Byte 0 (marker + 5): Zones 1-8
- Byte 1 (marker + 6): Zones 9-16
- Byte 2 (marker + 7): Zones 17-24
- ...
- Byte 39 (marker + 44): Zones 313-320

**Maximum:** 320 zones (40 bytes × 8 zones per byte)

### Zone Inclusion (marker + 47 to marker + 86, 40 bytes AFTER marker)

Each byte contains **8 zones** (1 bit per zone):

- **`1`** = Zone included (active/monitored)
- **`0`** = Zone excluded (bypassed)

**Format:** Same as zone status (8 zones per byte, 320 max)

### Anomalies (marker + 173, 173 bytes AFTER marker)

This is the **85th byte after zone inclusion** (84 bytes of unknown data + 1 byte for anomalies).

| Value | Anomaly | Description |
|-------|---------|-------------|
| `00` | OK | No anomalies |
| `01` | Bus Trouble | Bus communication fault (panel tamper) |
| `40` | GSM Trouble | GSM communication fault |
| Other | Unknown | Invalid code |

### Alarm Memory (End - 40 to End - 1, 40 bytes from END)

Each byte contains **8 zones** (1 bit per zone):

- **`0`** = No alarm memory
- **`1`** = Zone has alarm memory

**Format:** Same as zone status (8 zones per byte, 320 max)

**Position:** Calculated from the END of the string, backward (not from marker)!

## Extended GSM Information (AmicaWeb Plus/SmartWeb Only)

On AmicaWeb Plus and SmartWeb interfaces, **16 additional bytes** are present between the SIM expiry date and the `FFFFFF` marker containing the operator name encoded in hexadecimal.

This feature is **NOT available** on base AmicaWeb interface.

**Important:** The network type (4G/3G/2G) is **NOT** in these 16 bytes - it's in a different location that has not yet been identified.

### Operator Name Encoding

The 16 bytes contain the operator name (e.g., "Vodafone", "TIM", "WIND") encoded as hexadecimal characters.

**Research Needed:** The exact encoding format and the location of network type information (4G/3G/2G) are not yet fully understood.

## Example Observations

### Network Loss Detection

When network connection is lost:

**Byte 212** (hex position 424):
- `00` → `01` (00000000 → 00000001)
- Indicates network absence

**Byte 205** (hex position 410):
- `00` → `40` (00000000 → 01000000)
- Indicates searching for network (with SIM inserted)

## Implementation Notes

### Finding the Marker in Code

```python
# Search for FFFFFF (3 bytes) followed by 0000 or 0101
# si_value is a hex string (2 chars per byte)
for i in range(len(si_value) - 10):
    if si_value[i:i+6] == "FFFFFF":  # 3 bytes = 6 hex chars
        next_bytes = si_value[i+6:i+10]
        if next_bytes in ["0000", "0101"]:
            marker_pos = i  # Position in hex chars (divide by 2 for bytes)
            break
```

### Parsing Zone Data

```python
# Zone status starts at marker + 5 bytes (marker + 10 hex chars)
zones_start = marker_pos + 10  # +5 bytes = +10 hex chars
zones_end = zones_start + 80    # 40 bytes = 80 hex chars

zones_hex = si_value[zones_start:zones_end]

# Each byte represents 8 zones (1 bit per zone)
for byte_idx in range(40):  # 40 bytes
    byte_val = int(zones_hex[byte_idx*2:byte_idx*2+2], 16)
    for bit_idx in range(8):
        zone_id = byte_idx * 8 + bit_idx + 1
        is_open = bool(byte_val & (1 << bit_idx))
        print(f"Zone {zone_id}: {'Open' if is_open else 'Closed'}")
```

### Parsing Areas State

```python
# Areas state is at marker - 1 byte (marker - 2 hex chars)
areas_start = marker_pos - 2  # -1 byte = -2 hex chars
areas_hex = si_value[areas_start:areas_start+2]
areas_int = int(areas_hex, 16)

# Check each area (bit 0-7, 8 areas total)
for i in range(8):
    is_armed = bool(areas_int & (1 << i))
    print(f"Area {i+1}: {'Armed' if is_armed else 'Disarmed'}")
```

## Unknown Sections

The following sections are not yet fully understood:

| Position | Length | Description | Status |
|----------|--------|-------------|--------|
| 0-1 | 2 bytes | Unknown data | ❓ Needs research |
| marker - 12 | 1 byte | Unknown data | ❓ Between timer and ? |
| marker - 10 | 1 byte | Unknown data | ❓ Between timer and ? |
| marker - 9 | 1 byte | Unknown data | ❓ Between timer and ? |
| marker - 8 | 1 byte | Unknown data | ❓ Between timer and ? |
| marker - 7 | 1 byte | Unknown data | ❓ Between timer and ? |
| marker - 6 | 1 byte | Unknown data | ❓ Between timer and ? |
| marker - 4 | 1 byte | Unknown data | ❓ Between timer and areas |
| marker - 3 | 1 byte | Unknown data | ❓ Between timer and areas |
| marker - 2 | 1 byte | Unknown data | ❓ Between timer and areas |
| marker + 3 to marker + 4 | 2 bytes | Padding | ❓ Purpose? |
| marker + 89 to marker + 172 | 84 bytes | Unknown data | ❓ Between inclusion padding and anomalies |
| Various positions after marker | Multiple bytes | Unused/reserved | ❓ Purpose unknown |

## Testing Notes

- Always verify changes with real hardware
- Test different SIM operators (Vodafone, TIM, WIND)
- Test alarm scenarios to verify memory bytes
- Test zone bypass to verify inclusion bytes
- Monitor anomalies byte by inducing faults
- Compare outputs from different panel models
- Document the complete `<si>` hex dump for each test

## Research Needed

If you can help identify unknown byte meanings:

1. **Compare `<si>` outputs** from different panel states
2. **Test different panel configurations** and document changes
3. **Document which bytes change** for each action performed
4. **Report findings** in GitHub issues with:
   - Panel model and firmware version
   - Web interface type (AmicaWeb/AmicaWeb Plus/SmartWeb)
   - Complete `<si>` hex dump
   - Description of action performed
   - Expected vs actual result

## Tools

### Debug Script

Use `debug/debug_xml.py` to analyze the XML structure in real-time:

```bash
cd debug
python3 debug_xml.py --ip 192.168.1.125
```

This script:
- Continuously polls `/status9.xml`
- Highlights byte changes in real-time
- Parses all known sections
- Shows positions relative to the marker
- Displays armed areas, open zones, excluded zones, alarm memory

⚠️ **Important:** This script does NOT support authentication. You must disable the PIN code requirement in your panel's web interface to use it.

## See Also

- [Debug Tool Documentation](todo.md#debug-tools) - How to use `debug_xml.py` script
- [Entity Documentation](entities.md) - How data is exposed in Home Assistant
- [TODO & Improvements](todo.md) - Implementation status and future plans
- [Authentication Documentation](authentication.md) - How panel authentication works
