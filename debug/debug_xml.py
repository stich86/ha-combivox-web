#!/usr/bin/env python3
"""
XML polling from alarm panel with change highlighting
"""

import requests
import time
import re
import argparse
from datetime import datetime

# Default configuration
DEFAULT_ENDPOINT = "http://192.168.1.125:80"
DEFAULT_POLL_INTERVAL = 3

# ANSI colors
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    BG_RED = '\033[101m'
    BG_GREEN = '\033[102m'
    BG_YELLOW = '\033[103m'

def extract_si_tag(xml_content):
    """Extract <si> tag content from XML"""
    match = re.search(r'<si>(.*?)</si>', xml_content, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def colorize_diff(old_str, new_str):
    """Color characters that changed between two strings"""
    if old_str is None:
        return new_str

    result = ""
    max_len = max(len(old_str), len(new_str))

    for i in range(max_len):
        old_char = old_str[i] if i < len(old_str) else ' '
        new_char = new_str[i] if i < len(new_str) else ' '

        if old_char != new_char:
            result += f"{Colors.BG_YELLOW}{Colors.RED}{Colors.BOLD}{new_char}{Colors.RESET}"
        else:
            result += new_char

    return result

def format_hex_string(hex_str, bytes_per_group=2):
    """Format hex string with spaces every N characters"""
    if not hex_str:
        return ""

    groups = []
    for i in range(0, len(hex_str), bytes_per_group):
        groups.append(hex_str[i:i+bytes_per_group])

    return ' '.join(groups)

def parse_gsm_data(si_value):
    """
    Parse GSM data from first bytes of <si> field.

    GSM data structure (skip first 2 bytes):
    - Byte 2 (position 4-5): Signal strength (0-5 bars)
    - Byte 5 (position 10-11): Operator code
    - Byte 6 (position 12-13): Status code
    """
    if len(si_value) < 16:  # Need at least 8 bytes (16 hex characters)
        return None

    try:
        # Skip first 2 bytes (4 characters), then extract:
        signal_hex = si_value[4:6]        # Byte 2 (position 4-5)
        operator_hex = si_value[10:12]    # Byte 5 (position 10-11)
        status_hex = si_value[12:14]      # Byte 6 (position 12-13)

        # Parse signal (0-5 bars to percentage)
        signal_bars = int(signal_hex, 16)
        if 0 <= signal_bars <= 5:
            signal_percent = signal_bars * 20  # 0→0%, 1→20%, ..., 5→100%
        else:
            signal_bars = 0
            signal_percent = 0

        # Parse operator
        operator_code = int(operator_hex, 16)
        operator_names = {
            0: "OTHER",
            1: "VODAFONE",
            2: "TIM",
            3: "WIND",
            4: "COMBIVOX"
        }
        operator_name = operator_names.get(operator_code, f"UNKNOWN({operator_code})")

        # Parse status
        status_code = int(status_hex, 16)
        status_names = {
            0x00: "OK",
            0x01: "NO_SIM",
            0x02: "SEARCHING"
        }
        status_name = status_names.get(status_code, f"UNKNOWN(0x{status_hex})")

        return {
            'signal_bars': signal_bars,
            'signal_percent': signal_percent,
            'operator_hex': operator_hex,
            'operator_code': operator_code,
            'operator_name': operator_name,
            'status_hex': status_hex,
            'status_code': status_code,
            'status_name': status_name
        }
    except Exception as e:
        return {'error': str(e)}

def parse_anomalies(si_value, marker_pos):
    """
    Parse anomalies from byte 171 after FFFFFF marker.

    Position: end of marker (pos_marker + 6) + 340 = pos_marker + 346
    """
    pos_start = marker_pos + 346
    pos_end = marker_pos + 348

    if len(si_value) < pos_end:
        return None

    try:
        anomalies_hex = si_value[pos_start:pos_end]
        anomalies_code = int(anomalies_hex, 16)

        anomalies_names = {
            0x00: "OK",
            0x40: "GSM_TROUBLE",
            0x01: "BUS_TROUBLE"
        }
        anomalies_name = anomalies_names.get(anomalies_code, f"UNKNOWN(0x{anomalies_hex})")

        return {
            'hex': anomalies_hex,
            'code': anomalies_code,
            'name': anomalies_name
        }
    except Exception as e:
        return {'error': str(e)}

def parse_domotic_modules(si_value):
    """
    Parse domotic module states (commands > 80) from end of string.

    Position: 484 chars from END of string, then 64 bytes (128 hex chars)
    Each MODULE has 2 CHANNELS, using 2 bytes (4 hex chars total)
    Byte 0 = Channel A, Byte 1 = Channel B
    Each channel: 00 = OFF, 07 = ON
    Each module generates 2 commands (e.g., module 1 = commands 145-146)
    """
    if len(si_value) < 484:  # Need at least 484 characters
        return None

    try:
        # Start 484 chars from end
        pos_start = len(si_value) - 484
        pos_end = pos_start + 128  # 64 bytes = 128 hex chars
        domotic_hex = si_value[pos_start:pos_end]

        # State mapping
        DOMOTIC_MODULE_HEX_TO_STATE = {
            "00": "off",
            "07": "on",
        }

        # Parse each module (2 bytes = 4 hex chars per module)
        active_modules = []
        num_modules = min(len(domotic_hex) // 4, 32)  # Max 32 modules

        for module_idx in range(num_modules):
            module_hex = domotic_hex[module_idx * 4:module_idx * 4 + 4]
            channel_a_hex = module_hex[0:2]  # First byte
            channel_b_hex = module_hex[2:4]  # Second byte

            # Calculate command IDs (starting from 145)
            command_id_a = 145 + module_idx * 2
            command_id_b = 145 + module_idx * 2 + 1

            # Parse states
            state_a = DOMOTIC_MODULE_HEX_TO_STATE.get(channel_a_hex, "unknown")
            state_b = DOMOTIC_MODULE_HEX_TO_STATE.get(channel_b_hex, "unknown")

            # Track active modules (at least one channel is not OFF)
            if module_hex != "0000":
                active_modules.append({
                    'module_num': module_idx + 1,
                    'command_a': command_id_a,
                    'state_a': state_a,
                    'hex_a': channel_a_hex,
                    'command_b': command_id_b,
                    'state_b': state_b,
                    'hex_b': channel_b_hex
                })

        return {
            'hex': domotic_hex,
            'pos_start': pos_start,
            'pos_end': pos_end,
            'num_modules': num_modules,
            'active_modules': active_modules
        }
    except Exception as e:
        return {'error': str(e)}

def parse_command_states(si_value):
    """
    Parse command switch states from end of string.

    Position: 520 chars (260 bytes) from END of string, then 10 bytes (20 hex chars)
    Each byte = 8 commands (1 bit per command), max 80 commands with 10 bytes

    Mapping: Byte X, bit Y = Command (X*8 + Y + 1)
    Example: Byte 0, bit 0 = Command 1, Byte 8, bit 5 = Command 70
    """
    if len(si_value) < 540:  # Need at least 520 + 20 characters
        return None

    try:
        # Start 520 chars from end
        pos_start = len(si_value) - 520
        pos_end = pos_start + 20  # 10 bytes = 20 hex chars
        command_states_hex = si_value[pos_start:pos_end]

        # Parse each byte
        command_states = {}
        for byte_idx in range(10):  # 10 bytes
            if byte_idx * 2 + 2 <= len(command_states_hex):
                byte_hex = command_states_hex[byte_idx * 2:byte_idx * 2 + 2]
                byte_val = int(byte_hex, 16)

                # Check each bit
                for bit_idx in range(8):
                    command_id = byte_idx * 8 + bit_idx + 1  # Convert to one-based ID
                    is_on = (byte_val >> bit_idx) & 1

                    if is_on:
                        command_states[command_id] = {
                            'byte_idx': byte_idx,
                            'bit_idx': bit_idx,
                            'byte_hex': byte_hex,
                            'byte_val': byte_val
                        }

        return {
            'hex': command_states_hex,
            'pos_start': pos_start,
            'pos_end': pos_end,
            'states': command_states
        }
    except Exception as e:
        return {'error': str(e)}

def print_analysis(si_value, prev_si):
    """Print detailed analysis with change highlighting"""
    timestamp = datetime.now().strftime("%H:%M:%S")

    print(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}[{timestamp}]{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}")

    # Raw string with colored diff
    print(f"\n{Colors.BOLD}RAW:{Colors.RESET}")
    colored_raw = colorize_diff(prev_si, si_value)
    print(colored_raw)

    # Formatted string (1 byte = 2 chars)
    print(f"\n{Colors.BOLD}FORMATTED (bytes):{Colors.RESET}")
    colored_formatted = colorize_diff(
        format_hex_string(prev_si) if prev_si else None,
        format_hex_string(si_value)
    )
    print(colored_formatted)

    # Length
    print(f"\n{Colors.BOLD}Length:{Colors.RESET} {len(si_value)} chars = {len(si_value)//2} bytes")

    # Changes detected
    if prev_si and prev_si != si_value:
        changes = []
        for i in range(0, min(len(prev_si), len(si_value)), 2):
            old_byte = prev_si[i:i+2] if i < len(prev_si) else None
            new_byte = si_value[i:i+2] if i < len(si_value) else None

            if old_byte != new_byte:
                byte_pos = i // 2
                changes.append({
                    'pos': i,
                    'byte_num': byte_pos,
                    'old': old_byte,
                    'new': new_byte
                })

        if changes:
            print(f"\n{Colors.BOLD}{Colors.RED}CHANGES DETECTED:{Colors.RESET}")
            for change in changes:
                old_bin = format(int(change['old'], 16), '08b') if change['old'] else 'N/A'
                new_bin = format(int(change['new'], 16), '08b') if change['new'] else 'N/A'

                print(f"  {Colors.YELLOW}Byte {change['byte_num']:3} (pos {change['pos']:3}):{Colors.RESET} "
                      f"{change['old']} → {Colors.GREEN}{change['new']}{Colors.RESET} "
                      f"({old_bin} → {new_bin})")

    # ========== GSM DATA (from first bytes) ==========
    print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}GSM DATA (first bytes):{Colors.RESET}")
    gsm_data = parse_gsm_data(si_value)
    if gsm_data and 'error' not in gsm_data:
        print(f"  {Colors.GREEN}Signal{Colors.RESET}: {gsm_data['signal_bars']} bars ({gsm_data['signal_percent']}%)")
        print(f"  {Colors.GREEN}Operator{Colors.RESET}: {gsm_data['operator_name']} (code {gsm_data['operator_code']}, hex {gsm_data['operator_hex']})")
        print(f"  {Colors.GREEN}Status{Colors.RESET}: {gsm_data['status_name']} (code {gsm_data['status_code']}, hex {gsm_data['status_hex']})")
    else:
        print(f"  {Colors.RED}GSM data not available{Colors.RESET}")

    # ========== FIND FFFFFF MARKER ==========
    # Find the FFFFFF marker using fixed offset from end
    print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}MARKER FFFFFF:{Colors.RESET}", end=" ")

    # Fixed offset from end: 1130 characters
    # - At 1124 chars from end: end of "extra characters"
    # - FFFFFF marker starts 6 characters BEFORE that point
    MARKER_OFFSET_FROM_END = 1130

    if len(si_value) < MARKER_OFFSET_FROM_END:
        print(f"{Colors.RED}STRING TOO SHORT{Colors.RESET}")
        print(f"  {Colors.YELLOW}Need {MARKER_OFFSET_FROM_END} chars, got {len(si_value)}{Colors.RESET}")
        return

    pos_marker = len(si_value) - MARKER_OFFSET_FROM_END

    # Validate that we found FFFFFF at expected position
    if si_value[pos_marker:pos_marker+6] != "FFFFFF":
        print(f"{Colors.YELLOW}VALIDATION WARNING{Colors.RESET}")
        print(f"  Expected FFFFFF at position {pos_marker} but found: {si_value[pos_marker:pos_marker+6]}")
        print(f"  {Colors.YELLOW}Continuing anyway...{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}FOUND{Colors.RESET} at fixed position {pos_marker} (byte {pos_marker//2})")

    print(f"  Marker: {si_value[pos_marker:pos_marker+6]}")
    print(f"  Next bytes: {si_value[pos_marker+6:pos_marker+10]}")
    print(f"  String length: {len(si_value)} chars")
    print(f"  Offset from end: {len(si_value) - pos_marker} chars")

    # ========== AREAS STATE ==========
    # Areas state = marker_pos - 12 : marker_pos - 8 (4 bytes before marker)
    if pos_marker >= 12:
        areas_start = pos_marker - 12
        areas_end = pos_marker - 8
        areas_hex = si_value[areas_start:areas_end]
        areas_int = int(areas_hex, 16)

        print(f"\n{Colors.GREEN}AREAS STATE{Colors.RESET} (pos {areas_start}-{areas_end}): {areas_hex}")
        print(f"  Binary: 0b{format(areas_int, '032b')}")

        # Show which areas are armed
        armed_areas = []
        for i in range(8):
            is_armed = bool(areas_int & (1 << i))
            status = f"{Colors.GREEN}ARMED{Colors.RESET}" if is_armed else "disarmed"
            print(f"    Area {i+1}: {status}")
            if is_armed:
                armed_areas.append(i + 1)

        if armed_areas:
            print(f"  → Armed areas: {', '.join(map(str, armed_areas))}")
        else:
            print(f"  → All areas disarmed")

    # ========== ALARM STATE ==========
    # Alarm state: marker_pos - 32 : marker_pos - 30 (16 bytes before marker)
    if pos_marker >= 32:
        alarm_start = pos_marker - 32
        alarm_end = pos_marker - 30
        alarm_hex = si_value[alarm_start:alarm_end]
        alarm_int = int(alarm_hex, 16)

        alarm_states = {
            0x08: "DISARMED_GSM_EXCLUDED",
            0x0C: "DISARMED",
            0x0D: "DISARMED_WITH_DELAY",
            0x0A: "ARMING",
            0x0E: "ARMING",
            0x8D: "PENDING",
            0x8C: "TRIGGERED",
            0x88: "TRIGGERED_GSM_EXCLUDED"
        }
        alarm_name = alarm_states.get(alarm_int, f"UNKNOWN(0x{alarm_hex})")

        print(f"\n{Colors.GREEN}ALARM STATE{Colors.RESET} (pos {alarm_start}-{alarm_end}): {alarm_hex} = 0b{format(alarm_int, '08b')}")
        print(f"  → {alarm_name}")

    # ========== ANOMALIES ==========
    print(f"\n{Colors.GREEN}ANOMALIES{Colors.RESET}", end=" ")
    anomalies_data = parse_anomalies(si_value, pos_marker)
    if anomalies_data and 'error' not in anomalies_data:
        print(f"(pos {pos_marker + 346}-{pos_marker + 348}): {anomalies_data['hex']}")
        print(f"  → {anomalies_data['name']}")
    else:
        print(f"{Colors.YELLOW}Not available{Colors.RESET}")

    # ========== ZONES DATA ==========
    # Zones start after marker (6 chars) + next bytes (4 chars) = marker_pos + 10
    zones_start = pos_marker + 10
    zones_end = zones_start + 80  # 40 bytes = 80 chars (320 zones max, 8 zones per byte)

    if zones_end <= len(si_value):
        zones_hex = si_value[zones_start:zones_end]
        print(f"\n{Colors.GREEN}ZONES DATA{Colors.RESET} (pos {zones_start}-{zones_end}):")
        print(f"  Length: {len(zones_hex)} chars = {len(zones_hex)//2} bytes (320 zones max)")
        print(f"  Preview: {zones_hex[:40]}...")

        # Count open zones
        open_zones = []
        for byte_idx in range(len(zones_hex) // 2):
            byte_val = int(zones_hex[byte_idx*2:byte_idx*2+2], 16)
            for bit_idx in range(8):
                zone_id = byte_idx * 8 + bit_idx + 1
                if zone_id > 320:
                    break
                if byte_val & (1 << bit_idx):
                    open_zones.append(zone_id)

        if open_zones:
            print(f"  {Colors.YELLOW}Open zones{Colors.RESET}: {', '.join(map(str, open_zones[:20]))}", end="")
            if len(open_zones) > 20:
                print(f" ... ({len(open_zones)} total)")
            else:
                print()
        else:
            print(f"  All zones closed")

    # ========== INCLUSION STATE ==========
    # After zones (40 bytes) + 2 bytes padding = 42 bytes after marker + 10 = marker + 94
    inclusion_start = zones_start + 80 + 4  # zones + padding
    inclusion_end = inclusion_start + 80  # 40 bytes

    if inclusion_end <= len(si_value):
        inclusion_hex = si_value[inclusion_start:inclusion_end]
        print(f"\n{Colors.GREEN}INCLUSION STATE{Colors.RESET} (pos {inclusion_start}-{inclusion_end}):")
        print(f"  Length: {len(inclusion_hex)} chars = {len(inclusion_hex)//2} bytes")

        # Count excluded zones
        excluded_zones = []
        for byte_idx in range(len(inclusion_hex) // 2):
            byte_val = int(inclusion_hex[byte_idx*2:byte_idx*2+2], 16)
            for bit_idx in range(8):
                zone_id = byte_idx * 8 + bit_idx + 1
                if zone_id > 320:
                    break
                if not (byte_val & (1 << bit_idx)):
                    excluded_zones.append(zone_id)

        if excluded_zones:
            print(f"  {Colors.YELLOW}Excluded zones{Colors.RESET}: {', '.join(map(str, excluded_zones[:20]))}", end="")
            if len(excluded_zones) > 20:
                print(f" ... ({len(excluded_zones)} total)")
            else:
                print()
        else:
            print(f"  All zones included")

    # ========== ALARM MEMORY ==========
    # From the END of string, skip 2 bytes (4 chars), read 40 bytes (80 chars)
    alarm_memory_end = len(si_value) - 4
    alarm_memory_start = alarm_memory_end - 80

    if alarm_memory_start >= 0:
        alarm_memory_hex = si_value[alarm_memory_start:alarm_memory_end]
        print(f"\n{Colors.GREEN}ALARM MEMORY{Colors.RESET} (pos {alarm_memory_start}-{alarm_memory_end}):")
        print(f"  Length: {len(alarm_memory_hex)} chars = {len(alarm_memory_hex)//2} bytes")

        # Count zones with alarm memory
        alarm_zones = []
        for byte_idx in range(len(alarm_memory_hex) // 2):
            byte_val = int(alarm_memory_hex[byte_idx*2:byte_idx*2+2], 16)
            for bit_idx in range(8):
                zone_id = byte_idx * 8 + bit_idx + 1
                if zone_id > 320:
                    break
                if byte_val & (1 << bit_idx):
                    alarm_zones.append(zone_id)

        if alarm_zones:
            print(f"  {Colors.RED}Zones with alarm memory{Colors.RESET}: {', '.join(map(str, alarm_zones[:20]))}", end="")
            if len(alarm_zones) > 20:
                print(f" ... ({len(alarm_zones)} total)")
            else:
                print()
        else:
            print(f"  No alarm memory")

    # ========== COMMAND STATES ==========
    print(f"\n{Colors.GREEN}COMMAND STATES{Colors.RESET}", end=" ")
    command_data = parse_command_states(si_value)
    if command_data and 'error' not in command_data:
        print(f"(pos {command_data['pos_start']}-{command_data['pos_end']}):")
        print(f"  Hex: {command_data['hex']}")
        print(f"  Length: 20 chars = 10 bytes (80 commands max)")

        if command_data['states']:
            print(f"  {Colors.YELLOW}Commands ON{Colors.RESET} ({len(command_data['states'])} total):")
            # Show first 20 commands with details
            sorted_commands = sorted(command_data['states'].items())
            for cmd_id, cmd_info in sorted_commands[:20]:
                byte_bin = format(cmd_info['byte_val'], '08b')
                print(f"    Command {cmd_id}: Byte {cmd_info['byte_idx']}, "
                      f"Bit {cmd_info['bit_idx']}, Hex {cmd_info['byte_hex']} (0b{byte_bin})")
            if len(sorted_commands) > 20:
                print(f"    ... and {len(sorted_commands) - 20} more")
        else:
            print(f"  All commands OFF")
    else:
        print(f"{Colors.YELLOW}Not available{Colors.RESET}")

    # ========== DOMOTIC MODULES ==========
    print(f"\n{Colors.GREEN}DOMOTIC MODULES{Colors.RESET}", end=" ")
    domotic_data = parse_domotic_modules(si_value)
    if domotic_data and 'error' not in domotic_data:
        print(f"(pos {domotic_data['pos_start']}-{domotic_data['pos_end']}):")
        print(f"  Hex: {domotic_data['hex']}")
        print(f"  Length: 128 chars = 64 bytes (32 modules max, 2 channels each)")

        if domotic_data['active_modules']:
            print(f"  {Colors.YELLOW}Active modules{Colors.RESET} ({len(domotic_data['active_modules'])} total):")
            for mod in domotic_data['active_modules'][:20]:
                print(f"    Module {mod['module_num']}: "
                      f"Command {mod['command_a']}={Colors.GREEN}{mod['state_a']}{Colors.RESET} ({mod['hex_a']}), "
                      f"Command {mod['command_b']}={Colors.GREEN}{mod['state_b']}{Colors.RESET} ({mod['hex_b']})")
            if len(domotic_data['active_modules']) > 20:
                print(f"    ... and {len(domotic_data['active_modules']) - 20} more")
            print(f"  Total modules parsed: {domotic_data['num_modules']} (commands 145-{145 + domotic_data['num_modules'] * 2 - 1})")
        else:
            print(f"  All modules OFF")
            print(f"  Total modules parsed: {domotic_data['num_modules']} (commands 145-{145 + domotic_data['num_modules'] * 2 - 1})")
    else:
        print(f"{Colors.YELLOW}Not available{Colors.RESET}")

def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='XML Poller - Alarm Panel Change Monitor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python3 debug_xml.py
  python3 debug_xml.py --ip 192.168.1.100
  python3 debug_xml.py --ip 192.168.1.100 --port 8080
  python3 debug_xml.py --endpoint http://192.168.1.100:8080/status9.xml
  python3 debug_xml.py --interval 5
        '''
    )

    parser.add_argument(
        '--ip',
        type=str,
        default='192.168.1.125',
        help='Panel IP address (default: 192.168.1.125)'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=80,
        help='Panel HTTP port (default: 80)'
    )

    parser.add_argument(
        '--endpoint',
        type=str,
        default=None,
        help='Full endpoint URL (overrides --ip and --port)'
    )

    parser.add_argument(
        '--interval',
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        help=f'Polling interval in seconds (default: {DEFAULT_POLL_INTERVAL})'
    )

    args = parser.parse_args()

    # Build endpoint
    if args.endpoint:
        endpoint = args.endpoint
    else:
        endpoint = f"http://{args.ip}:{args.port}/status9.xml"

    # Print header
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("="*80)
    print("XML POLLER - Alarm Panel Change Monitor")
    print("="*80)
    print(f"{Colors.RESET}")
    print(f"Endpoint: {Colors.GREEN}{endpoint}{Colors.RESET}")
    print(f"Interval: {Colors.GREEN}{args.interval}s{Colors.RESET}")
    print(f"\n{Colors.YELLOW}Press CTRL+C to stop{Colors.RESET}\n")

    previous_si = None
    error_count = 0

    try:
        while True:
            try:
                # HTTP request
                response = requests.get(endpoint, timeout=5)
                response.raise_for_status()

                # Extract <si> tag
                si_value = extract_si_tag(response.text)

                if si_value:
                    error_count = 0  # Reset errors

                    # Print only if changed or first time
                    if si_value != previous_si:
                        print_analysis(si_value, previous_si)
                        previous_si = si_value
                    else:
                        # Dot to indicate polling but no changes
                        print(".", end="", flush=True)
                else:
                    print(f"{Colors.RED}[ERROR] <si> tag not found in XML{Colors.RESET}")
                    error_count += 1

            except requests.exceptions.RequestException as e:
                error_count += 1
                print(f"\n{Colors.RED}[ERROR] Connection failed: {e}{Colors.RESET}")

                if error_count > 5:
                    print(f"{Colors.YELLOW}Too many consecutive errors. Check configuration...{Colors.RESET}")

            # Wait before next poll
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n{Colors.CYAN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}Polling stopped.{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")

if __name__ == "__main__":
    # Check if requests is installed
    try:
        import requests
    except ImportError:
        print("ERROR: The 'requests' module is not installed.")
        print("Install with: pip install requests")
        exit(1)

    main()
