# Combivox Amica Web Integration for Home Assistant

Home Assistant integration for Combivox alarm panels (Amica/Elisa) via AmicaWeb/AmicaWeb Plus/SmartWeb HTTP/XML interface.

## Features

- **Real-time Status Monitoring**: Polls alarm status every 5 seconds (configurable 3-30 seconds)
- **Zone Binary Sensors**: Open/closed status with alarm memory attribute
- **Area Binary Sensors**: Armed/disarmed status with dynamic icons
- **Alarm Control Panel**: Arm Away/Home/Night and Disarm with configurable modes
- **Zone Bypass Buttons**: Toggle zone inclusion/exclusion
- **Macro/Scenario Buttons**: Execute panel macros and scenarios
- **System Sensors**: Device model, IP address, alarm state, date/time, gsm status
- **Label Caching**: Saves zone/area names to JSON file for fast loading
- **Smart Polling**: Single unified coordinator for efficient updates
- **Automatic Recovery**: Handles temporary network issues and session expiration with automatic retry
  - Entities become unavailable during outages (no stale data)
  - Automatically reconnects when panel comes back online

## Requirements

- Home Assistant 2025.11 or later
- Combivox alarm panel (Amica/Elisa series)
- AmicaWeb/AmicaWeb Plus/SmartWeb module enabled
- HTTP access to the alarm panel (default port 80)

## Installation

### Method 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots menu → "Custom repositories"
4. Add this repository URL
5. Click "Download" on the Combivox Amica Web integration
6. Restart Home Assistant

### Method 2: Manual Installation

1. Copy the `custom_components/combivox_web` directory to your Home Assistant configuration directory
2. Restart Home Assistant

## Configuration

### Initial Setup

1. In Home Assistant, go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Combivox Amica Web"
4. Enter the following information:
   - **IP Address**: The IP address of your alarm panel (e.g., `192.168.1.125`)
   - **Port**: HTTP port (default: `80`)
   - **Master PIN Code**: Your master PIN code (if less than 6 digits, two zeros are appended to the end, e.g., `1234` → `123400`)
   - **Technical PIN Code**: Technical PIN code (default: `000000`, if less than 6 digits, two zeros are appended)

### Options Configuration

After initial setup, you can configure:

#### Basic Settings
- **Scan Interval**: Polling interval in seconds (1-300, default: 5)
- **Code**: User code for arm/disarm from UI (optional)
- **Technician Code**: Technician code (optional)

#### Area Configuration
- **Areas for Away Mode**: Multi-select of area names for away arming
- **Areas for Home Mode**: Multi-select of area names for home arming
- **Areas for Night Mode**: Multi-select of area names for night arming
- **Areas for Disarm Mode**: Multi-select of area names for selective disarming

#### Disarm Behavior

The integration supports **selective disarming** - you can choose which areas to disarm:

- **If areas are selected**: Only the selected areas will be disarmed
- **If no areas selected**: ALL areas will be disarmed (complete disarm)
- **If scenario is configured**: The scenario will be executed instead (areas have priority if both are configured)

This allows you to, for example, keep the perimeter armed while disarming only interior areas.

#### Arm Modes
For each arm type (Away/Home/Night):
- **Normal**: Arming with exit delay (standard mode)
- **Immediate**: Arming without exit delay
- **Forced**: Bypass open zones and arm anyway with delay

#### Macro/Scenario Configuration
- **Scenario for Away**: Macro to execute when arming away
- **Scenario for Home**: Macro to execute when arming home
- **Scenario for Night**: Macro to execute when arming night
- **Scenario for Disarm**: Macro to execute when disarming

**Note**: Areas have priority over scenarios when both are configured.

## Entities Created

### Alarm Control Panel
- `alarm_control_panel.combivox_alarm`: Main alarm control panel

### System Sensors
- `sensor.combivox_system_status`: Current alarm state
- `sensor.combivox_model`: Device model name
- `sensor.combivox_datetime`: Panel date and time

### Zone Binary Sensors
For each zone with a configured name:
- `binary_sensor.<zone_name>`: Zone open/closed status
  - **Device Class**: Automatically detected (window, motion, smoke, etc.)
  - **Attributes**:
    - `zone_id`: Zone number
    - `alarm`: True if zone is in alarm state
    - `alarm_memory`: True if zone has alarm memory
    - `included`: True if zone is included (not excluded)

### Zone Bypass Buttons
For each zone with a configured name:
- `button.<zone_name>_bypass`: Toggle zone inclusion/exclusion
  - **Icon**: `mdi:shield` (included) or `mdi:shield-off` (excluded)
  - **Category**: Config

### Area Binary Sensors
For each area with a configured name:
- `binary_sensor.<area_name>`: Area armed/disarmed status
  - **Icon**: `mdi:shield-lock` (armed) or `mdi:shield-home` (disarmed)
  - **Attributes**:
    - `area_id`: Area number
    - `status`: "armed" or "disarmed"

### Macro/Scenario Buttons
For each macro with a configured name:
- `button.<macro_name>`: Execute macro/scenario
  - **Icon**: `mdi:play-box-outline`
  - **Category**: Config

## Alarm States

The panel supports the following alarm states (still working in progress to understand other states):

| Hex | State | Description |
|-----|-------|-------------|
| `08` | `disarmed_gsm_excluded` | Disarmed, GSM excluded |
| `0C` | `disarmed` | Disarmed |
| `0D` | `disarmed_with_delay` | Disarmed with delay |
| `0E` | `arming` | Arming with delay |
| `8D` | `pending` | Pre-alarm |
| `8C` | `triggered` | **ALARM!** |
| `88` | `triggered_gsm_excluded` | **ALARM!** (GSM excluded) |

## How the Integration Works

The integration communicates directly with your Combivox panel via HTTP:

1. **Authentication**: Uses Combivox's dynamic password authentication system
2. **Status Polling**: Polls panel status at configured interval (default: 5 seconds)
3. **Configuration Download**: Downloads zone/area names from panel once during setup
4. **Command Execution**: Sends arm/disarm/bypass commands to panel
5. **Entity Creation**: Creates Home Assistant entities for all configured zones/areas/macros

Only zones, areas, and macros with **configured names** in the panel are created as entities.

## Enabling Debug Logging

To enable detailed logging for troubleshooting:

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.combivox_web: debug
```

### What You'll See

**DEBUG logs include**:
- HTTP commands (URL, payload, response)
- XML parsing details
- Zone/area status updates
- Authentication steps

**INFO logs include**:
- Connection status
- Configuration loaded
- Areas armed/disarmed
- Panel state changes
- Alarm memory warnings

## Troubleshooting

### "Failed to connect" Error

- Verify the alarm panel IP address is correct
- Check that Home Assistant can reach the panel (ping test from HA host)
- Ensure HTTP port is correct (default: 80, but may vary)
- Verify the panel's web interface is accessible from a browser

### "Invalid authentication" Error

- Verify your Master PIN code is correct
- Check that Technical PIN code matches your panel settings
- Ensure the panel's web interface is accessible
- Try accessing the panel's web interface from a browser

### Zones/Areas Not Showing

Only zones/areas with **configured names** in the panel are created as entities:

1. Check that zones/areas have names in the panel configuration
2. Check the cached config file at `/config/combivox_web/config_IP_PORT.json`
3. Check logs for "Loaded configuration: X zones, Y areas"
4. Enable debug logging and check Home Assistant logs for parsing errors

### Areas Not Arming Correctly

1. Verify area assignments in integration options
2. Check logs for "Areas armed:" or "Areas disarmed:"
3. Enable debug logging and verify the HTTP response
4. Check if areas are properly named in the panel

### High CPU Usage

- Increase the poll interval in integration options
- Default is 5 seconds; try 10-30 seconds
- Minimum recommended: 3 seconds

### Macros/Scenarios Not Showing

Only macros with **configured names** are created as buttons:

1. Check if macros were downloaded: "Loaded X macros (scenarios)" in logs
2. Check cached config: `/config/combivox_web/config_IP_PORT.json` for "macros" section
3. Enable debug logging and look for "Parsed macro X: name" messages
4. Verify macros have names in the panel configuration

### Options Not Saving/Loading

1. Check if "OPTIONS UPDATE LISTENER CALLED" appears in logs
2. Verify areas are read from integration options (not data)
3. If areas changed, integration should reload automatically
4. If scan interval changed, check "polling interval updated" log

## Device Info

All entities are grouped under a single device with:
- **Identifiers**: `combivox_web` + `IP:PORT`
- **Name**: Combivox Amica 64 GSM
- **Manufacturer**: Combivox
- **Model**: Amica 64 GSM
- **Software Version**: Auto-detected from panel

## TODO

- **Extract panel info from technical configuration page**: Retrieve additional panel information (firmware version, web version) from the technical configuration page using the technician code
- **GSM status monitoring**: Add sensors for GSM status (registered, operator name, signal strength)
- **Trouble status detection**: Investigate and implement trouble status detection (determine if there's a specific bit mapping for this)
- **Complete alarm state mapping**: Continue reverse-engineering and mapping all possible alarm states
- **Single area arming**: Add buttons/switches to arm individual areas without using the main alarm panel (implement custom services)

## Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/stich86/ha-combivox-web/issues)
