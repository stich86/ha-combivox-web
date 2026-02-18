"""XML Parser for Combivox Amica Web."""

import xml.etree.ElementTree as ET
import logging
import datetime
from typing import Dict, List, Optional, Any

from .const import ALARM_HEX_TO_AP_STATE

_LOGGER = logging.getLogger(__name__)


def parse_gsm_block(si: str, marker_pos: int) -> Optional[Dict[str, Any]]:
    """
    Parse the GSM block (7 bytes) in the <si> field.

    GSM block structure (14 hex characters = 7 bytes):
    - Byte 0 (f[0]): Raw signal (bars = f0 + 3, range 0-5)
    - Byte 1 (f[1]): Credit € (integer part)
    - Byte 2 (f[2]): Credit cents (if >99 = N/A)
    - Byte 3 (f[3]): Network status (0=OTHER,1=VODAFONE,2=TIM,3=WIND,>4=N/A)
    - Byte 4 (f[4]): GSM bitfield (bit 0=excluded, bit 2=searching)
    - Byte 5 (f[5]): Expiry month (1-12)
    - Byte 6 (f[6]): Expiry day (1-31)

    IMPORTANT: The GSM block starts IMMEDIATELY AFTER the FFFFFFFF marker
    So position: marker_pos + 8 (8 characters = "FFFFFFFF")

    Args:
        si: Complete hex string of the <si> field
        marker_pos: Position of the FFFFFFFF marker in the buffer

    Returns:
        Dict with complete GSM status or None if error
    """
    try:
        # The GSM block starts immediately after FFFFFFFF
        gsm_start = marker_pos + 8

        if gsm_start + 14 > len(si):  # 7 bytes = 14 hex characters
            _LOGGER.warning("Buffer <si> too short for GSM parsing")
            return None

        # Extract the 7 bytes of the GSM block
        gsm_bytes = []
        for i in range(7):
            byte_hex = si[gsm_start + (i * 2): gsm_start + (i * 2) + 2]
            gsm_bytes.append(int(byte_hex, 16))

        # Parsing (from deobfuscated JS + real XML analysis)
        signal_raw = gsm_bytes[0]              # Raw signal (f[0])
        signal_bars = signal_raw + 3            # Conversion: bars = f0 + 3
        credit_eur = gsm_bytes[1]               # Credit € (f[1])
        credit_cents_raw = gsm_bytes[2]         # Credit cents (f[2], >99 = N/A)
        network_status_code = gsm_bytes[3]      # Network status (f[3])
        gsm_bitfield = gsm_bytes[4]             # GSM bitfield (f[4])
        expiry_month = gsm_bytes[5]             # Expiry month (f[5])
        expiry_day = gsm_bytes[6]               # Expiry day (f[6])

        # Decode network status (JS: if (f[3] > 4) f[3] = 4)
        if network_status_code > 4:
            network_status_code = 4

        # Network states map from JS: ["ALTRO", "VODAFONE", "TIM", "WIND", "N/D"][f[3]]
        network_states = {
            0: "altro",           # OTHER
            1: "vodafone",        # VODAFONE
            2: "tim",             # TIM
            3: "wind",            # WIND
            4: "not_available"    # N/D (when > 4)
        }
        network_state = network_states.get(network_status_code, "not_available")

        # Decode expiry date (JS: if (f[6] < 32) && (f[5] < 13))
        credit_available = (credit_cents_raw <= 99)  # JS: if (f[2] <= 99)

        # Format expiry date if valid
        expiry_date = None
        if (expiry_day < 32) and (expiry_month < 13) and (expiry_day > 0) and (expiry_month > 0):
            # Months in Italian
            months_it = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                         "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
            expiry_date = f"{expiry_day} {months_it[expiry_month]}"

        # Decode GSM bitfield (JS: if (f[4] & 1) ... else if (f[4] & 4) ...)
        gsm_excluded = (gsm_bitfield & (1 << 0)) != 0   # bit 0: "SIM EXCLUDED"
        gsm_searching = (gsm_bitfield & (1 << 2)) != 0   # bit 2: "SEARCHING..."

        # GSM operational: OK if not excluded, not searching, and network status = 0 (OTHER/registered)
        gsm_operational = (
            not gsm_excluded and
            not gsm_searching and
            network_status_code == 0
        )

        return {
            "signal_raw": signal_raw,             # Raw signal value
            "signal_bars": signal_bars,           # 0-5 (f0 + 3)
            "credit_eur": credit_eur if credit_available else None,
            "credit_cents": credit_cents_raw if credit_available else None,
            "credit_available": credit_available,
            "network_status_code": network_status_code,
            "network_state": network_state,       # altro/vodafone/tim/wind/not_available
            "gsm_excluded": gsm_excluded,
            "gsm_searching": gsm_searching,
            "gsm_operational": gsm_operational,
            "expiry_month": expiry_month,
            "expiry_day": expiry_day,
            "expiry_date": expiry_date,
            "bitfield_raw": gsm_bitfield,
            "bitfield_hex": f"{gsm_bitfield:02X}"
        }

    except (ValueError, IndexError) as e:
        _LOGGER.error("Error parsing GSM block: %s", e)
        return None


def parse_datetime(cd_hex: str) -> Optional[datetime.datetime]:
    """
    Parse the <cd> field (current date/time) from status.xml

    Args:
        cd_hex: Hex string of the cd field (12 characters = 6 bytes)

    Returns:
        Timezone-aware datetime object or None if error

    Format: DD MM YY HH MM SS (6 bytes in hex)
    Example: "17011A08331D" → 23/01/26 08:51:29
    """
    try:
        if len(cd_hex) != 12:
            _LOGGER.warning("Invalid cd field length: %s (expected 12 characters)", cd_hex)
            return None

        # Split into 6 values of 2 characters each
        gg = int(cd_hex[0:2], 16)
        mm = int(cd_hex[2:4], 16)
        aa = int(cd_hex[4:6], 16)
        hh = int(cd_hex[6:8], 16)
        min = int(cd_hex[8:10], 16)
        ss = int(cd_hex[10:12], 16)

        # Create datetime object (year 2000 + yy)
        # Note: we assume year 2000-2155 (BCD standard)
        year = 2000 + aa if aa < 100 else aa
        try:
            # Create timezone-aware datetime using local timezone
            dt = datetime.datetime(year, mm, gg, hh, min, ss)
            # Add local timezone for HA
            import time as time_module
            tz_offset = datetime.timedelta(seconds=-time_module.timezone)
            if time_module.daylight:
                tz_offset = datetime.timedelta(seconds=-time_module.altzone)
            dt = dt.replace(tzinfo=datetime.timezone(tz_offset))
            return dt
        except ValueError as e:
            _LOGGER.warning("Invalid date/time: %s (error: %s)", cd_hex, e)
            return None
    except Exception as e:
        _LOGGER.error("Error parsing datetime: %s", e)
        return None


class CombivoxXMLParser:
    """Parser for Combivox Amica XML."""

    @staticmethod
    def parse_status_xml(
        xml_content: str,
        zones_config: List[Dict[str, Any]] = None,
        max_aree: int = 8,
        zone_ids: List[int] = None
    ) -> Dict[str, Any]:
        """
        Parse the status XML and extract:
        - Panel state (hex)
        - Current date/time
        - Areas state (armed/disarmed)
        - Zones state (open/closed, alarm, armed)

        IMPORTANT: Structure after FFFFFF marker (3 FF bytes):
        ...4 byte areas state|2 byte variable|FFFFFF marker|2 byte data|zones...
                            marker_pos-6      marker_pos    marker_pos+6

        - Variable byte (FF/1F/3F): marker_pos-2 : marker_pos
        - FFFFFF marker: marker_pos : marker_pos+6
        - 2 "system data" bytes: marker_pos+6 : marker_pos+8
        - Zones start: marker_pos+8

        Areas state: 4 bytes BEFORE the variable byte (marker_pos-10:marker_pos-6)

        Args:
            xml_content: Status XML content
            zones_config: List of zone config with zone_id, zone_name, areas
            max_aree: Maximum number of areas (detected from labelAree.xml)
            zone_ids: List of active zone IDs (from numZoneProg.xml), if None uses zones_config

        Returns:
            Dict with:
                - datetime: current date/time
                - status_hex: status hex code
                - state: decoded state (disarmed, armed)
                - armed_areas: list of armed area IDs
                - zones: dict {zone_id: {"open": bool, "alarm": bool, "armed": bool}}
                - areas: dict {area_id: {"status": "armed"|"disarmed"}}
        """
        try:
            root = ET.fromstring(xml_content)

            # Parse <cd> field (date/time)
            cd = root.find('cd')
            datetime_obj = None
            if cd is not None and cd.text:
                cd_hex = cd.text.strip()
                datetime_obj = parse_datetime(cd_hex)
                if datetime_obj:
                    _LOGGER.debug("Panel datetime: %s", datetime_obj.isoformat())
                else:
                    _LOGGER.warning("Failed to parse datetime from hex: %s", cd_hex)
            else:
                _LOGGER.debug("Datetime field not found or empty in XML")

            # Parse <si> field (status data)
            si_element = root.find('si')
            if si_element is None or not si_element.text:
                _LOGGER.error("Status field <si> not found or empty in XML")
                return {}
            si = si_element.text

            # Find FFFFFF marker position using fixed offset from end
            # IMPORTANT: The marker is always at a fixed position from the end
            # - At 1124 chars from end: end of "extra characters" section
            # - FFFFFF marker starts 6 characters BEFORE that point
            # - Therefore: marker starts at len(si) - 1124 - 6 = len(si) - 1130

            MARKER_OFFSET_FROM_END = 1130  # 1124 + 6 (marker itself)

            if len(si) < MARKER_OFFSET_FROM_END:
                _LOGGER.error("String too short for fixed marker position (len=%d, need %d)",
                             len(si), MARKER_OFFSET_FROM_END)
                return {}

            # Calculate marker position directly from end
            marker_pos = len(si) - MARKER_OFFSET_FROM_END

            # Validate that we found FFFFFF at expected position
            if si[marker_pos:marker_pos + 6] != "FFFFFF":
                _LOGGER.warning("Expected FFFFFF at fixed position %d but found: %s (continuing anyway)",
                               marker_pos, si[marker_pos:marker_pos + 6])
            else:
                _LOGGER.debug("Found FFFFFF marker at fixed position: %d (len=%d)",
                             marker_pos, len(si))

            # Parse GSM data from bytes 3, 6, 7 (0-indexed, after skipping first 2 bytes)
            # Byte 2 (3°): Signal strength (0-5 bars)
            # Byte 5 (6°): Operator code
            # Byte 6 (7°): Status code
            gsm_data = {}
            if len(si) >= 16:  # Need at least 8 bytes (16 hex characters)
                try:
                    # Skip first 2 bytes (4 characters), then extract:
                    signal_hex = si[4:6]        # Byte 2 (position 4-5)
                    operator_hex = si[10:12]    # Byte 5 (position 10-11)
                    status_hex = si[12:14]      # Byte 6 (position 12-13)

                    # Parse signal (0-5 bars to percentage: linear 0-100%)
                    signal_bars = int(signal_hex, 16)
                    if 0 <= signal_bars <= 5:
                        signal_percent = signal_bars * 20  # 0→0%, 1→20%, ..., 5→100%
                    else:
                        signal_bars = 0
                        signal_percent = 0

                    gsm_data = {
                        "signal_bars": signal_bars,
                        "signal_percent": signal_percent,
                        "operator_hex": operator_hex,
                        "status_hex": status_hex
                    }
                    _LOGGER.debug("GSM data: signal=%d bars (%d%%), operator=%s, status=%s",
                                 signal_bars, signal_percent, operator_hex, status_hex)
                except (ValueError, IndexError) as e:
                    _LOGGER.warning("Failed to parse GSM data: %s", e)
                    gsm_data = {}
            else:
                _LOGGER.debug("Buffer too short for GSM parsing (len=%d)", len(si))
                gsm_data = {}

            # Parse anomalies data from byte 171 after FFFFFF marker
            # Byte 171 (0-indexed from after marker): anomalies status
            # There are 340 chars (170 bytes) before, byte is at positions 340-341 (0-indexed after marker)
            anomalies_data = {}
            if len(si) >= marker_pos + 346 + 2:  # Need marker (6) + 340 + 2 (byte) = 348 chars
                try:
                    # Position: marker_pos + 6 (end of FFFFFF) + 340 = marker_pos + 346
                    pos_start = marker_pos + 346
                    pos_end = marker_pos + 348
                    anomalies_hex = si[pos_start:pos_end]
                    anomalies_data = {
                        "anomalies_hex": anomalies_hex
                    }
                    _LOGGER.debug("Anomalies data: pos_start=%d pos_end=%d hex=%s", pos_start, pos_end, anomalies_hex)
                except (ValueError, IndexError) as e:
                    _LOGGER.warning("Failed to parse anomalies data: %s", e)
                    anomalies_data = {}
            else:
                _LOGGER.debug("Buffer too short for anomalies parsing (len=%d)", len(si))
                anomalies_data = {}

            # Extract areas hex state
            # CORRECT STRUCTURE (based on user analysis):
            # Position 42 (byte 54): AREAS STATE (4 bytes)
            # Position 53 (byte 106): FF/3F (variable)
            # Position 54 (byte 108): FFFFFF marker
            #
            # Areas state = marker_pos - 12 : marker_pos - 8

            if marker_pos >= 12:
                status_hex = si[marker_pos - 12:marker_pos - 8]
                _LOGGER.debug("Areas status: pos_start=%d pos_end=%d value=%s", marker_pos - 12, marker_pos - 8, status_hex)
            else:
                _LOGGER.warning("Marker FFFFFF too close to start to extract areas status")
                status_hex = "00"

            # ========== ALARM STATE ==========
            # 16 bytes (32 characters) before the marker - inclusive!
            alarm_state = None
            alarm_hex = None
            if marker_pos >= 32:
                alarm_hex = si[marker_pos - 32:marker_pos - 30]

                # Use match/case for clean state determination (Python 3.10+)
                match alarm_hex:
                    case key if key in ALARM_HEX_TO_AP_STATE:
                        state = ALARM_HEX_TO_AP_STATE[key]
                        alarm_state = state  # For logging
                        _LOGGER.debug("Panel state changed: pos_start=%d pos_end=%d hex=%s state=%s", marker_pos - 32, marker_pos - 30, alarm_hex, alarm_state)
                    case _:
                        state = f"sconosciuto_{alarm_hex}"
                        _LOGGER.warning("Unknown panel state: %s (hex value: %s)", alarm_hex, alarm_hex)
            else:
                # Fallback: use areas state if no alarm state available
                status_int = int(status_hex, 16)
                state = "disarmed" if status_hex == "00" else "armed"
                alarm_hex = None

            # Calculate status_int for armed areas (if not already calculated)
            if 'status_int' not in locals():
                status_int = int(status_hex, 16)

            # Determine which areas are armed (bitwise, dynamic based on model)
            armed_areas = []
            for i in range(max_aree):
                if status_int & (1 << i):
                    armed_areas.append(i + 1)

            # Build areas dict
            areas = {}
            for i in range(1, max_aree + 1):
                areas[i] = {
                    "area_id": i,
                    "status": "armed" if i in armed_areas else "disarmed"
                }

            # Parse zones (CORRECT APPROACH based on user analysis)
            # Zones start AFTER the FFFFFF marker (6 characters) + 2 "system data" bytes (4 characters) = +10 characters
            # Each zone has an offset of 16: eff_id = zone_id + 16
            # Then calculate position normally: (eff_id-1)//8
            #
            # NOTE: Zones are 40 bytes (320 zones max), 8 zones per byte
            start_z = marker_pos + 10  # AFTER marker (6) + 2 "system data" bytes (4)

            # INCLUSION STATE: after zones (40 bytes = 80 characters) + padding (2 bytes = 4 characters)
            inclusion_start = start_z + 80 + 4

            # ALARM MEMORY: from the END of the string, skip 2 bytes (4 characters), read 40 bytes (80 characters)
            alarm_memory_end = len(si) - 4  # 2 bytes before the end
            alarm_memory_start = alarm_memory_end - 80  # 40 bytes back

            zones = {}

            _LOGGER.debug("Zone parsing: marker_pos=%d, start_z=%d, inclusion_start=%d, alarm_memory_start=%d, alarm_memory_end=%d",
                         marker_pos, start_z, inclusion_start, alarm_memory_start, alarm_memory_end)

            # Create zone -> areas mapping from configuration
            zone_to_areas = {}
            if zones_config:
                for zone_cfg in zones_config:
                    zid = zone_cfg.get("zone_id")
                    zone_areas = zone_cfg.get("areas", [])
                    zone_to_areas[zid] = zone_areas

            # Parse all configured zones (supports 64/128/320 models)
            # Use zone_ids from numZoneProg.xml or extract from zones_config
            if zone_ids:
                # Zone IDs already provided from numZoneProg.xml
                pass
            elif zones_config:
                # Extract zone_ids from configuration
                zone_ids = [zc.get("zone_id") for zc in zones_config]
            else:
                # Fallback: calculate max zones based on XML length
                max_zones = min(199, (len(si) - start_z) // 2)  # MAX_ZONE from Costanti_Amica64.cs
                zone_ids = range(1, max_zones + 1)

            for zid in zone_ids:
                eff_id = zid

                # Calculate position based on eff_id
                byte_index = (eff_id - 1) // 8
                bit_index = (eff_id - 1) % 8

                # Verify there are enough bytes
                if start_z + (byte_index * 2) + 2 > len(si):
                    break

                # Read the byte
                val_hex = si[start_z + (byte_index * 2): start_z + (byte_index * 2) + 2]
                try:
                    val = int(val_hex, 16)

                    # Bit 0: open/closed
                    is_open = (val & (1 << bit_index)) != 0

                    # ========== INCLUSION STATE ==========
                    # Read inclusion byte (same logic as zones)
                    is_included = True  # Default: included
                    if inclusion_start + (byte_index * 2) + 2 <= len(si):
                        inc_val_hex = si[inclusion_start + (byte_index * 2): inclusion_start + (byte_index * 2) + 2]
                        inc_val = int(inc_val_hex, 16)
                        # FF = included, bit at 0 = excluded
                        is_included = (inc_val & (1 << bit_index)) != 0

                    # ========== ALARM MEMORY ==========
                    # Read alarm memory byte (same logic as zones)
                    has_alarm_memory = False
                    if alarm_memory_start + (byte_index * 2) + 2 <= len(si):
                        mem_val_hex = si[alarm_memory_start + (byte_index * 2): alarm_memory_start + (byte_index * 2) + 2]
                        mem_val = int(mem_val_hex, 16)
                        # Bit at 1 = alarm memory present
                        has_alarm_memory = (mem_val & (1 << bit_index)) != 0
                        _LOGGER.debug("Zone %d: alarm memory byte=%s bit=%d val=%d -> %s",
                                     zid, mem_val_hex, bit_index, mem_val, has_alarm_memory)

                    # NOTE: The "armed" state for zones has been removed - it doesn't exist
                    zones[zid] = {
                        "zone_id": zid,
                        "open": is_open,
                        "alarm_memory": has_alarm_memory,
                        "included": is_included
                    }
                except ValueError:
                    _LOGGER.warning("Failed to parse byte for zone %d: %s", zid, val_hex)
                    continue

            # Log zones in alarm memory
            zones_with_alarm = [zid for zid, zdata in zones.items() if zdata.get("alarm_memory", False)]
            if zones_with_alarm:
                zone_names = []
                if zones_config:
                    for zid in zones_with_alarm:
                        zone = next((z for z in zones_config if z["zone_id"] == zid), None)
                        if zone:
                            zone_names.append(zone.get("zone_name", f"Zone {zid}"))
                        else:
                            zone_names.append(f"Zone {zid}")
                _LOGGER.debug("Alarm memory: zones %s - %s", zones_with_alarm, zone_names)

            # Parse command switch states from end of string
            # Structure: 520 chars (260 bytes) from end, then 10 bytes (20 hex chars) of command states
            # Each byte represents 8 commands (1 bit per command), max 80 commands with 10 bytes
            command_states = {}
            if len(si) >= 520:  # Need at least 520 characters
                try:
                    # Get the 10 bytes of command states (20 hex characters)
                    # They start 520 chars from end, so from position len(si)-520
                    pos_start = len(si) - 520
                    pos_end = pos_start + 20
                    command_states_hex = si[pos_start:pos_end]

                    _LOGGER.debug("Command states hex (20 chars): %s", command_states_hex)
                    _LOGGER.debug("Command states position: %d to %d (section len=%d)", pos_start, pos_end, pos_end - pos_start)

                    # Parse each byte (2 hex chars) and extract bit states
                    active_commands = []
                    for byte_idx in range(10):  # 10 bytes
                        if byte_idx * 2 + 2 <= len(command_states_hex):
                            byte_hex = command_states_hex[byte_idx * 2:byte_idx * 2 + 2]
                            byte_val = int(byte_hex, 16)

                            # Check each bit (8 commands per byte)
                            for bit_idx in range(8):
                                # Commands are zero-based in the panel
                                # Byte 0, bit 0 = Command 1, Byte 0, bit 1 = Command 2, etc.
                                command_id = byte_idx * 8 + bit_idx + 1  # Convert to one-based ID
                                is_on = (byte_val >> bit_idx) & 1  # Check if bit is set

                                if is_on:
                                    command_states[command_id] = True
                                    active_commands.append(command_id)

                    # Log in compressed format (like domotic modules)
                    if active_commands:
                        _LOGGER.debug("Active commands: %s", active_commands)
                        _LOGGER.debug("Parsed 10 command bytes with %d active (commands 1-80)",
                                     len(active_commands))
                    else:
                        _LOGGER.debug("Parsed 10 command bytes, all OFF (commands 1-80)")
                except (ValueError, IndexError) as e:
                    _LOGGER.warning("Failed to parse command states: %s", e)
                    command_states = {}
            else:
                _LOGGER.debug("Buffer too short for command states parsing (len=%d)", len(si))

            # Parse domotic module states (commands > 80) from end of string
            # Structure: 484 chars from end, then 64 bytes (128 hex chars) of domotic module states
            # Each MODULE has 2 CHANNELS, using 2 bytes (4 hex chars total)
            # Byte 0 = Channel A, Byte 1 = Channel B
            # Each channel: 00 = OFF, 07 = ON
            # Each module generates 2 commands (e.g., module 0 = commands 81-82)
            if len(si) >= 484:  # Need at least 484 characters
                try:
                    # Get the 64 bytes (128 hex characters) of domotic module states
                    # They start 484 chars from end, so from position len(si)-484
                    pos_start = len(si) - 484
                    pos_end = pos_start + 128  # 64 bytes = 128 hex chars
                    domotic_states_hex = si[pos_start:pos_end]

                    _LOGGER.debug("Domotic modules hex (128 chars): %s", domotic_states_hex)
                    _LOGGER.debug("Domotic modules position: %d to %d (section len=%d)", pos_start, pos_end, pos_end - pos_start)

                    # Import constants
                    from .const import DOMOTIC_MODULE_HEX_TO_STATE, DOMOTIC_MODULE_FIRST_COMMAND_ID

                    # Track active modules for compressed logging
                    active_modules = []

                    # Parse each module (2 bytes = 4 hex chars per module)
                    num_modules = min(len(domotic_states_hex) // 4, 32)  # Max 32 modules
                    for module_idx in range(num_modules):
                        # Extract 2 bytes (4 hex chars) for this module
                        module_hex = domotic_states_hex[module_idx * 4:module_idx * 4 + 4]

                        # Each module has 2 channels, each is 1 byte (2 hex chars)
                        channel_a_hex = module_hex[0:2]  # First byte = channel A
                        channel_b_hex = module_hex[2:4]  # Second byte = channel B

                        # Calculate command IDs using configurable first ID
                        # Module 1 = commands FIRST_ID,FIRST_ID+1, module 2 = FIRST_ID+2,FIRST_ID+3, etc.
                        command_id_a = DOMOTIC_MODULE_FIRST_COMMAND_ID + module_idx * 2     # Channel A
                        command_id_b = DOMOTIC_MODULE_FIRST_COMMAND_ID + module_idx * 2 + 1 # Channel B

                        # Parse channel A
                        state_a = DOMOTIC_MODULE_HEX_TO_STATE.get(channel_a_hex, "unknown")
                        command_states[command_id_a] = (state_a == "on")

                        # Parse channel B
                        state_b = DOMOTIC_MODULE_HEX_TO_STATE.get(channel_b_hex, "unknown")
                        command_states[command_id_b] = (state_b == "on")

                        # Track active modules (at least one channel is ON or has non-standard state)
                        if module_hex != "0000":
                            active_modules.append((module_idx + 1, command_id_a, state_a, channel_a_hex,
                                                  command_id_b, state_b, channel_b_hex))

                    # Log only active modules
                    if active_modules:
                        for mod_num, cmd_a, state_a, hex_a, cmd_b, state_b, hex_b in active_modules:
                            _LOGGER.debug("Domotic Module %d: Command %d=%s (%s), Command %d=%s (%s)",
                                         mod_num, cmd_a, state_a, hex_a, cmd_b, state_b, hex_b)
                        _LOGGER.debug("Parsed %d domotic modules with %d active (commands %d-%d)",
                                     num_modules, len(active_modules), DOMOTIC_MODULE_FIRST_COMMAND_ID,
                                     DOMOTIC_MODULE_FIRST_COMMAND_ID + num_modules * 2 - 1)
                    else:
                        _LOGGER.debug("Parsed %d domotic modules, all OFF (commands %d-%d)",
                                     num_modules, DOMOTIC_MODULE_FIRST_COMMAND_ID,
                                     DOMOTIC_MODULE_FIRST_COMMAND_ID + num_modules * 2 - 1)
                except (ValueError, IndexError) as e:
                    _LOGGER.warning("Failed to parse domotic module states: %s", e)
            else:
                _LOGGER.debug("Buffer too short for domotic module parsing (len=%d)", len(si))

            return {
                "datetime": datetime_obj,
                "gsm": gsm_data,
                "anomalies": anomalies_data,
                "status_hex": status_hex,
                "state": state,
                "armed_areas": armed_areas,
                "areas": areas,
                "zones": zones,
                "alarm_state": alarm_state,
                "alarm_hex": alarm_hex,
                "command_states": command_states
            }

        except Exception as e:
            _LOGGER.error("Error parsing status.xml: %s", e)
            return {}

    @staticmethod
    def parse_zone_labels(xml_content: str, zone_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Parse the labelZone XML and extract zone names.

        Args:
            xml_content: XML content from labelZone.xml
            zone_ids: List of zone IDs (for correct mapping)

        Returns:
            List of dict: [{"zone_id": 1, "zone_name": "Porta"}, ...]
        """
        try:
            root = ET.fromstring(xml_content)

            # NOTE: The root is already 'response', text is directly in root.text
            if root.text is None:
                return []

            # Labels are separated by |
            labels_hex = root.text.strip()
            labels = labels_hex.split('|')

            zones = []
            for idx, label_hex in enumerate(labels):
                if label_hex and idx < len(zone_ids):
                    try:
                        name = bytes.fromhex(label_hex).decode('utf-8')
                        zones.append({
                            "zone_id": zone_ids[idx],
                            "zone_name": name
                        })
                    except ValueError:
                        _LOGGER.warning("Unable to decode zone label %d", zone_ids[idx] if idx < len(zone_ids) else idx)
                        continue

            return zones

        except Exception as e:
            _LOGGER.error("Error parsing labelZone.xml: %s", e)
            return []

    @staticmethod
    def parse_zone_ids(xml_content: str) -> List[int]:
        """
        Parse the numZoneProg XML and extract zone IDs.

        Returns:
            List of zone IDs: [2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 17]
        """
        try:
            root = ET.fromstring(xml_content)

            # Extract zone numbers from tags c0, c1, c2, ...
            zone_ids = []
            for i in range(100):  # Max 100 zones
                tag = root.find(f'c{i}')
                if tag is not None and tag.text:
                    try:
                        zone_id = int(tag.text.strip())
                        zone_ids.append(zone_id)
                    except ValueError:
                        continue

            _LOGGER.info("Found %d zones: %s", len(zone_ids), zone_ids)
            return zone_ids

        except Exception as e:
            _LOGGER.error("Error parsing numZoneProg.xml: %s", e)
            return []

    @staticmethod
    def parse_area_labels(xml_content: str) -> List[Dict[str, Any]]:
        """
        Parse the labelAree XML and extract area names.

        Returns:
            List of dict: [{"area_id": 1, "area_name": "Casa"}, ...]
        """
        try:
            root = ET.fromstring(xml_content)

            areas = []
            for i in range(1, 9):  # 8 areas
                area_tag = root.find(f'a{i}')
                if area_tag is not None and area_tag.text:
                    try:
                        name = bytes.fromhex(area_tag.text).decode('utf-8')
                        # Ignore areas with empty name
                        if name.strip():  # Only if name is not empty
                            areas.append({
                                "area_id": i,
                                "area_name": name
                            })
                    except ValueError:
                        _LOGGER.warning("Unable to decode area label %d", i)
                        continue

            return areas

        except Exception as e:
            _LOGGER.error("Error parsing labelAree.xml: %s", e)
            return []

    @staticmethod
    def parse_macro_ids(xml_content: str) -> List[int]:
        """
        Parse the numMacro XML and extract macro IDs.

        Returns:
            List of macro IDs: [1, 2, 3, 5, 8, ...]
        """
        try:
            root = ET.fromstring(xml_content)

            # Extract macro numbers from tags c0, c1, c2, ...
            macro_ids = []
            for i in range(100):  # Max 100 macros
                tag = root.find(f'c{i}')
                if tag is not None and tag.text:
                    try:
                        macro_id = int(tag.text.strip())
                        macro_ids.append(macro_id)
                    except ValueError:
                        continue

            _LOGGER.debug("Found %d macros: %s", len(macro_ids), macro_ids)
            return macro_ids

        except Exception as e:
            _LOGGER.error("Error parsing numMacro.xml: %s", e)
            return []

    @staticmethod
    def parse_macro_labels(xml_content: str, macro_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Parse the macro labels response and extract macro names.

        The XML response has tags like <m1>, <m2>, <m3>, etc. with hex-encoded names.
        Format: <mID>HEX_NAME~number~number</mID>

        Args:
            xml_content: XML content from macro labels request
            macro_ids: List of macro IDs

        Returns:
            List of dict: [{"macro_id": 1, "macro_name": "Uscita Totale"}, ...]
        """
        try:
            root = ET.fromstring(xml_content)

            macros = []

            _LOGGER.debug("Starting to parse macro labels from XML...")

            # Parse all m* tags (m1, m2, m3, ...)
            for macro_tag in root.iter():
                if macro_tag.tag.startswith('m') and macro_tag.tag[1:].isdigit():
                    macro_id = int(macro_tag.tag[1:])
                    _LOGGER.debug("Found tag <%s> with text: %s", macro_tag.tag,
                                 macro_tag.text[:50] if macro_tag.text else "None")

                    if macro_tag.text and macro_tag.text.strip():
                        try:
                            # Extract only the hex part before the first ~
                            # Format: HEX_NAME~number~number
                            hex_text = macro_tag.text.strip()
                            tilde_pos = hex_text.find('~')
                            if tilde_pos > 0:
                                hex_name = hex_text[:tilde_pos]
                            else:
                                hex_name = hex_text

                            # Decode hex to string
                            name = bytes.fromhex(hex_name).decode('utf-8')

                            macros.append({
                                "macro_id": macro_id,
                                "macro_name": name
                            })

                            _LOGGER.debug("Parsed macro %d: %s", macro_id, name)
                        except ValueError as e:
                            _LOGGER.warning("Unable to decode macro label %d: %s (text: %s)",
                                         macro_id, e, macro_tag.text[:50])
                            continue

            _LOGGER.debug("Loaded %d macros (scenarios)", len(macros))
            return macros

        except Exception as e:
            _LOGGER.error("Error parsing macro labels: %s", e)
            return []

    @staticmethod
    def parse_command_ids(xml_content: str) -> List[int]:
        """
        Parse the numComandiProg XML and extract command IDs.

        Returns:
            List of command IDs: [1, 2, 3, 5, 8, ...]
        """
        try:
            root = ET.fromstring(xml_content)

            # Extract command numbers from tags c0, c1, c2, ...
            command_ids = []
            for i in range(100):  # Max 100 commands
                tag = root.find(f'c{i}')
                if tag is not None and tag.text:
                    try:
                        command_id = int(tag.text.strip())
                        command_ids.append(command_id)
                    except ValueError:
                        continue

            _LOGGER.debug("Found %d commands: %s", len(command_ids), command_ids)
            return command_ids

        except Exception as e:
            _LOGGER.error("Error parsing numComandiProg.xml: %s", e)
            return []

    @staticmethod
    def parse_command_labels(xml_content: str, command_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Parse the command labels response and extract command names and types.

        The XML response has a <response> tag with pipe-separated hex-encoded commands.
        Format: <response>HEX_NAME1~type1|HEX_NAME2~type2|HEX_NAME3~type3|...</response>
        Type can be: 2 (impulsivo/button) or 6 (bistabile/switch)

        Args:
            xml_content: XML content from command labels request
            command_ids: List of command IDs (in order)

        Returns:
            List of dict: [{"command_id": 1, "command_name": "Luci Sala", "command_type": "button"}, ...]
        """
        try:
            root = ET.fromstring(xml_content)

            # The <response> tag IS the root element in this XML format
            if root.tag != 'response':
                _LOGGER.warning("Unexpected root tag: %s (expected 'response')", root.tag)

            if not root.text:
                _LOGGER.warning("Response tag has no text content")
                return []

            # Get the pipe-separated content from root
            content = root.text.strip()

            # Split by pipe to get individual commands
            command_parts = content.split('|')

            commands = []

            # Parse each command part (index + 1 = command_id)
            for idx, part in enumerate(command_parts):
                if not part.strip():
                    continue

                command_id = command_ids[idx] if idx < len(command_ids) else idx + 1

                # Split by tilde to get hex_name and type
                tilde_pos = part.find('~')
                if tilde_pos > 0:
                    hex_name = part[:tilde_pos]
                    type_str = part[tilde_pos + 1:]
                else:
                    hex_name = part
                    type_str = ""

                _LOGGER.debug("Command %d - hex_name: %s, type_str: %s", command_id, hex_name, type_str)

                try:
                    # Decode hex to string
                    name = bytes.fromhex(hex_name).decode('utf-8')

                    # All commands are switches (the type after tilde is only for web UI display)
                    command_type = "switch"

                    commands.append({
                        "command_id": command_id,
                        "command_name": name,
                        "command_type": command_type
                    })

                    _LOGGER.debug("Parsed command %d: %s (type: %s)", command_id, name, command_type)
                except ValueError as e:
                    _LOGGER.warning("Unable to decode command label %d: %s (hex: %s)",
                                 command_id, e, hex_name[:50])
                    continue

            _LOGGER.debug("Loaded %d commands", len(commands))
            return commands

        except Exception as e:
            _LOGGER.error("Error parsing command labels: %s", e)
            return []

    @staticmethod
    def parse_prog_state_labels(xml_content: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Parse the labelProgStato XML and extract zone and area names.

        This file contains ALL names in one place, much cleaner!

        XML structure:
        - <a1>...</a1> = Area 1 (hex to decode)
        - <a2>...</a2> = Area 2
        - <z1>...</z1> = Zone 1 (hex to decode)
        - <z2>...</z2> = Zone 2
        - Empty tag = non-existent zone/area or without name

        Args:
            xml_content: XML content from labelProgStato.xml

        Returns:
            Dict with two keys:
            {
                "areas": [{"area_id": 1, "area_name": "Casa Mamma"}, ...],
                "zones": [{"zone_id": 1, "zone_name": "Portoncino"}, ...]
            }
        """
        try:
            root = ET.fromstring(xml_content)

            areas = []
            zones = []

            # Parse areas (a1, a2, a3, ...)
            # NOTE: Use iter to find all 'a*' tags, don't stop at first None
            for area_tag in root.iter():
                if area_tag.tag.startswith('a') and area_tag.tag[1:].isdigit():
                    area_id = int(area_tag.tag[1:])
                    if area_tag.text and area_tag.text.strip():
                        try:
                            name = bytes.fromhex(area_tag.text.strip()).decode('utf-8')
                            if name.strip():  # Only if name is not empty (filter out unconfigured areas)
                                areas.append({
                                    "area_id": area_id,
                                    "area_name": name
                                })
                        except ValueError:
                            _LOGGER.warning("Unable to decode area hex %d", area_id)

            # Parse zones (z1, z2, z3, ...)
            # NOTE: Use iter to find all 'z*' tags, don't stop at first None
            for zone_tag in root.iter():
                if zone_tag.tag.startswith('z') and zone_tag.tag[1:].isdigit():
                    zone_id = int(zone_tag.tag[1:])
                    if zone_tag.text and zone_tag.text.strip():
                        try:
                            name = bytes.fromhex(zone_tag.text.strip()).decode('utf-8')
                            if name.strip():  # Only if name is not empty
                                zones.append({
                                    "zone_id": zone_id,
                                    "zone_name": name
                                })
                        except ValueError:
                            _LOGGER.warning("Unable to decode zone hex %d", zone_id)

            _LOGGER.info("Parsing labelProgStato.xml: %d areas, %d zones found",
                       len(areas), len(zones))

            return {
                "areas": areas,
                "zones": zones
            }

        except Exception as e:
            _LOGGER.error("Error parsing labelProgStato.xml: %s", e)
            return {"areas": [], "zones": []}
