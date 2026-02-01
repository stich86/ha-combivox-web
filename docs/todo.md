# TODO & Improvements

This document tracks future improvements and pending tasks for the Combivox Web integration.

## XML Byte Mapping Status

This section tracks the mapping of bytes from the `/status9.xml` response from the panel.

### Status Field (`<si>`)

The `<si>` field contains a hexadecimal string with multiple pieces of data.

#### ✅ Fully Implemented

| Data | Position | Bytes | Status | Notes |
|------|----------|-------|--------|-------|
| **Areas State** | Before FFFFFF marker | 4 bytes | ✅ Implemented | Armed/disarmed status of 8 areas |
| **Alarm State** | After FFFFFF + 2 bytes | 1 byte | ✅ Implemented | Panel state (disarmed/arming/triggered/etc.) |
| **Zones Status** | After FFFFFF + 10 bytes | 40 bytes | ✅ Implemented | Open/closed status of 320 zones (8 zones per byte) |
| **Zones Inclusion** | After zones data + 2 bytes padding | 40 bytes | ✅ Implemented | Included/excluded status of 320 zones |
| **Alarm Memory** | End of string - 4 bytes | 40 bytes | ✅ Implemented | Alarm memory for all zones |
| **GSM Signal** | GSM block, byte 0 | 1 byte | ✅ Implemented | Signal strength (0-5 bars → 0-100%) |
| **GSM Operator** | GSM block, byte 3 | 1 byte | ✅ Implemented | Operator code (Vodafone/TIM/Wind/Other) |
| **GSM Status** | GSM block, byte 4 | 1 byte | ✅ Implemented | GSM status (ok/searching/no_sim) |
| **Anomalies** | After FFFFFF + 346 bytes | 1 byte | ✅ Implemented | System anomalies (GSM/Bus trouble) |
| **Panel DateTime** | `<dt>` field | 6 bytes | ✅ Implemented | Panel date and time |

#### ⚠️ Partially Implemented

| Data | Position | Bytes | Status | Notes |
|------|----------|-------|--------|-------|
| **GSM Credit** | GSM block, bytes 1-2 | 2 bytes | ⚠️ Parsed, not exposed | Credit amount (€ + cents) - parsed but not shown as sensor |
| **GSM Expiry** | GSM block, bytes 5-6 | 2 bytes | ⚠️ Parsed, not exposed | SIM expiry date (month/day) - parsed but not shown as sensor |

#### ❓ Unknown / Not Mapped

| Data | Position | Bytes | Status | Notes |
|------|----------|-------|--------|-------|
| **System Data Bytes** | After FFFFFF marker + 2 bytes | 2 bytes | ❓ Unknown | Two bytes between FFFFFF and zones - purpose unknown |
| **Other `<si>` bytes** | Various | Multiple | ❓ Unknown | Many bytes before/after known sections - purpose unknown |
| **`<cd>` Field** | Separate field | 6 bytes | ❓ Unknown | Appears to be date-related - format similar to datetime |

### Other XML Files

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `/status9.xml` | Main status polling | ⚠️ Partially implemented | Main sections parsed (areas, zones, alarm, GSM, anomalies) - many bytes still unknown |
| `/labelProgStato.xml` | Zone/area names | ✅ Fully implemented | Names downloaded and cached |
| `/numMacro.xml` | Macro/scenario IDs | ✅ Fully implemented | Parsed on startup |
| `/labelMacro.xml` | Macro/scenario names | ✅ Fully implemented | Parsed on startup |
| `/jscript9.js` | Panel variant info | ✅ Fully implemented | Model and web interface type |
| `/insAree.xml` | Arm/disarm commands | ✅ Fully implemented | All arm modes supported |
| `/execBypass.xml` | Zone bypass toggle | ✅ Fully implemented | Toggle zone inclusion |
| `/execChangeImp.xml` | Macro execution | ✅ Fully implemented | Execute scenarios |
| `/execDelMem.xml` | Clear alarm memory | ✅ Fully implemented | Clear alarm memory |
| `/numTrouble.xml` | Active anomaly ID | ✅ Fully implemented | Used in diagnostics |
| `/labelMem.xml` | Alarm memory info | ✅ Fully implemented | Used in diagnostics |

## Future Improvements

### High Priority

#### GSM Credit and Expiry Sensors

**Status:** Parsed in `xml_parser.py` but not exposed as entities

The GSM block contains additional data that could be useful:

- **GSM Credit** (bytes 1-2):
  - Byte 1: Credit in Euro (integer part)
  - Byte 2: Credit in cents (if >99 means N/A)
  - Could be exposed as `sensor.combivox_gsm_credit` with value in EUR

- **GSM SIM Expiry** (bytes 5-6):
  - Byte 5: Expiry month (1-12)
  - Byte 6: Expiry day (1-31)
  - Could be exposed as `sensor.combivox_gsm_sim_expiry` as a date sensor

**Implementation:**
1. Add sensors in `sensor.py`
2. Return parsed data from `xml_parser.py`
3. Add translations to `en.json` and `it.json`

### Medium Priority

#### System Events Logging

The panel may support event history retrieval (similar to alarm memory). This could be exposed as:

- `sensor.combivox_last_event` - Most recent system event
- Event history could be shown in Home Assistant logbook

**Research needed:**
- Find XML endpoint for event history
- Parse event format
- Determine how to best present in HA

#### Zone Tamper Detection

If the panel reports tamper status separately from open/closed state:

- Add `tamper` attribute to zone binary sensors
- Could trigger different automations (tamper vs normal alarm)

**Research needed:**
- Check if tamper is reported separately in status XML
- Map tamper bytes if available

### Low Priority

#### Panel Configuration Export

Export full panel configuration for backup/restore:

- Download zone/area/macro configuration
- Export as JSON for user backup
- Potential restore functionality (risky - needs careful implementation)

#### Firmware Update Detection

Monitor panel firmware version and notify on updates:

- Current firmware version shown in diagnostics
- Could check against latest version online
- Notify user when update available

#### Advanced Troubleshooting

Add more detailed diagnostics for troubleshooting:

- Network latency monitoring
- Request/response timing metrics
- Authentication failure reasons
- Cookie expiry tracking

## Research Needed

### Debug Tools

A Python debug script is available to help analyze the XML byte structure:

#### `debug/debug_xml.py`

This script continuously polls the panel's `/status9.xml` endpoint and highlights byte changes in real-time:

**Features:**
- **Continuous polling** with configurable interval (default: 3 seconds)
- **Change detection** with color-coded diff output (yellow background for changed bytes)
- **Byte-level analysis** showing exactly which bytes changed with binary representation
- **Complete parsing of all known sections**:
  - **GSM data** (from first bytes): Signal, operator, status
  - **Areas state**: Shows which of 8 areas are armed/disarmed with bitmask
  - **Alarm state**: Panel status (disarmed/arming/triggered/etc.)
  - **Anomalies**: System trouble status (GSM/Bus)
  - **Zones data**: Lists all open zones (up to 320 zones)
  - **Inclusion state**: Lists all excluded/bypassed zones
  - **Alarm memory**: Lists zones with alarm memory
- **Raw and formatted** output (hex string with byte grouping)

**Usage:**
```bash
cd debug
python3 debug_xml.py                    # Use default IP (192.168.1.125:80)
python3 debug_xml.py --ip 192.168.1.100  # Specify IP address
python3 debug_xml.py --ip 192.168.1.100 --port 8080  # Specify IP and port
python3 debug_xml.py --endpoint http://192.168.1.100:8080/status9.xml  # Full URL
python3 debug_xml.py --interval 5  # Custom polling interval
```

**Command-line Arguments:**
- `--ip IP`: Panel IP address (default: 192.168.1.125)
- `--port PORT`: HTTP port (default: 80)
- `--endpoint URL`: Full endpoint URL (overrides --ip and --port)
- `--interval SECONDS`: Polling interval in seconds (default: 3)

> **⚠️ Important:** This script does not support authentication. You must **disable the PIN code requirement** in your panel's web interface settings to use it, or the endpoint will return the login page instead of the XML data.

**How to use for research:**

1. **Start the script**: It will begin polling your panel
2. **Perform actions**: Open/close zones, arm/disarm areas, trigger alarms
3. **Watch for changes**: The script highlights exactly which bytes change
4. **Document findings**: Note which byte positions change for each action
5. **Report results**: Create GitHub issues with your discoveries

**Output example:**
```
[14:32:15]
================================================================================
RAW: 000000...FFFFFF...

FORMATTED (bytes):
00 00 00 00 14 00 00 00 20 00 00 00 ...

Length: 320 chars = 160 bytes

CHANGES DETECTED:
  Byte  44 (pos  88): 00 → 01 (00000000 → 00000001)
  Byte 108 (pos 216): 3F → FF (00111111 → 11111111)

================================================================================
GSM DATA (first bytes):
  Signal: 3 bars (60%)
  Operator: VODAFONE (code 1, hex 01)
  Status: OK (code 0, hex 00)

================================================================================
MARKER FFFFFFFF: position 216 (byte 108)

AREAS STATE (pos 204-212): 0000000C
  Binary: 0b00000000000000000000000000001100
    Area 1: disarmed
    Area 2: disarmed
    Area 3: disarmed
    Area 4: ARMED
    Area 5: ARMED
    Area 6: disarmed
    Area 7: disarmed
    Area 8: disarmed
  → Armed areas: 4, 5

ALARM STATE (pos 200-202): 0C = 0b00001100
  → DISARMED

ANOMALIES (pos 562-564): 00
  → OK

ZONES DATA (pos 226-306):
  Length: 80 chars = 40 bytes (320 zones max)
  Preview: 0000000000000000000000000000000000000000...
  All zones closed

INCLUSION STATE (pos 310-390):
  Length: 80 chars = 40 bytes
  All zones included

ALARM MEMORY (pos 570-650):
  Length: 80 chars = 40 bytes
  No alarm memory
```

**Requirements:**
- Python 3.6+
- `requests` library: `pip install requests`

**Technical Details:**

The script parses the `<si>` field from `/status9.xml` using the same structure as the integration:

**First Bytes (0-15):**
- **Bytes 0-1**: Unknown/reserved
- **Byte 2** (pos 4-5): Signal strength (0-5 bars, linear to percentage)
- **Bytes 3-4**: Unknown
- **Byte 5** (pos 10-11): GSM operator code (0=OTHER, 1=VODAFONE, 2=TIM, 3=WIND, 4=COMBIVOX)
- **Byte 6** (pos 12-13): GSM status code (0x00=OK, 0x01=NO_SIM, 0x02=SEARCHING)

**Around FFFFFF Marker:**
- **Alarm State**: marker_pos - 32 : marker_pos - 30 (16 bytes before marker)
  - States: 0x08=DISARMED_GSM_EXCLUDED, 0x0C=DISARMED, 0x0D=DISARMED_WITH_DELAY, 0x0E=ARMING, 0x8D=PENDING, 0x8C=TRIGGERED, 0x88=TRIGGERED_GSM_EXCLUDED
- **Areas State**: marker_pos - 12 : marker_pos - 8 (4 bytes, 8 areas bitmask)
- **Variable Byte**: marker_pos - 2 : marker_pos (FF, 1F, 3F, etc.)
- **FFFFFFF Marker**: marker_pos : marker_pos + 6 (6 characters = 3 bytes, MUST be followed by 0000 or 0101)
- **Next Bytes**: marker_pos + 6 : marker_pos + 10 (4 characters = 2 bytes, these are the 0000/0101 bytes)

**After Marker:**
- **Zones Data**: marker_pos + 10 : marker_pos + 90 (40 bytes, 320 zones max, 8 zones per byte)
- **Inclusion State**: After zones + 2 bytes padding (40 bytes)
- **Anomalies**: marker_pos + 346 : marker_pos + 348 (byte 171 after end of marker)
  - Codes: 0x00=OK, 0x40=GSM_TROUBLE, 0x01=BUS_TROUBLE
- **Alarm Memory**: End of string - 4 bytes : End - 84 bytes (40 bytes from end)

This tool is invaluable for mapping unknown bytes and understanding how the panel represents different states.

### Unknown Bytes in `<si>` Field

Several sections of the `<si>` field are not yet understood:

1. **Bytes before areas state**: What data is contained here?
2. **System data bytes** (2 bytes after FFFFFF marker): What do these represent?
3. **Bytes after alarm memory**: Is there more data after the alarm memory section?

**How to help:**
- Compare `<si>` output from different panel states
- Test different panel configurations
- Document which bytes change when different actions occur
- Report findings in GitHub issues

### Other XML Endpoints

The panel may have additional undocumented XML endpoints:

**Potential endpoints to explore:**
- Event history log
- Zone configuration details
- Area configuration details
- System diagnostics (fault and anomalies)

**How to explore:**
- Use browser developer tools while using panel web interface
- Look for XML requests in Network tab
- Test endpoints found in JavaScript files
- Document discovered endpoints

## Contributing

Want to help implement these improvements?

1. **Research unknown bytes**: Use the integration with debug logging enabled and compare `<si>` outputs
2. **Test on different panels**: If you have a different model, report which features work
3. **Implement sensors**: GSM credit and expiry are ready to be implemented
4. **Find new XML endpoints**: Explore the panel web interface to find undocumented features
5. **Report your findings**: Create GitHub issues with your discoveries

## Documentation Improvements

- [ ] Add more screenshots to README
- [ ] Document advanced automation examples
- [ ] Translate documentation to more languages

## Testing

- [ ] Test on Amica series panels
- [ ] Test on Elisa series panels
- [ ] Test with 32+ zones
- [ ] Test with all 8 areas configured
- [ ] Test rapid arm/disarm cycles
