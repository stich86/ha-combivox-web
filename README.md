# Combivox Alarm Web Integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/stich86/ha-combivox-web)](https://github.com/stich86/ha-combivox-web/releases)
[![License](https://img.shields.io/github/license/stich86/ha-combivox-web)](LICENSE)

Home Assistant integration for Combivox alarm panels (Amica/Elisa series) via AmicaWeb/AmicaWeb Plus/SmartWeb HTTP/XML interface.

**This integration will set up the following platforms:**

| Platform | Description |
|----------|-------------|
| `alarm_control_panel` | Main alarm panel with arm/disarm functionality |
| `binary_sensor` | Zone sensors (open/closed) and area sensors (armed/disarmed) |
| `sensor` | System status (model, alarm state, GSM info, date/time, anomalies) |
| `button` | Zone bypass toggles, macro/scenario execution, clear alarm memory |

## Features

- **Real-time Status Monitoring**: Polls alarm status every 5 seconds (configurable 3-300 seconds)
- **Zone Binary Sensors**: Open/closed status with alarm memory and inclusion attributes
- **Area Binary Sensors**: Armed/disarmed status with dynamic icons
- **Alarm Control Panel**: Arm Away/Home/Night and Disarm with configurable arm modes
- **Zone Bypass Buttons**: Toggle zone inclusion/exclusion
- **Macro/Scenario Buttons**: Execute panel macros and scenarios
- **System Sensors**: Device model, alarm state, GSM status (signal, operator), anomalies
- **Label Caching**: Saves zone/area/macro names to JSON file for fast loading
- **Smart Polling**: Single unified coordinator for efficient updates
- **Automatic Recovery**: Handles network issues and session expiration with automatic retry
  - Entities become unavailable during outages (no stale data)
  - Automatically reconnects when panel comes back online

## Requirements

- Home Assistant 2025.11 or later
- Combivox alarm panel (Amica/Elisa series) with AmicaWeb/AmicaWeb Plus/SmartWeb module enabled (not tested with SmartWeb Video Plus)
- HTTP access to the alarm panel (default port 80)

## Installation

### Method 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots menu → "Custom repositories"
4. Add this repository URL: `https://github.com/stich86/ha-combivox-web`
5. Click "Download" on the Combivox Alarm Web integration
6. Restart Home Assistant

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=combivox_web)

### Method 2: Manual Installation

1. Using the tool of choice, open the directory (folder) for your HA configuration (where you find `configuration.yaml`)
2. If you do not have a `custom_components` directory (folder) there, create it
3. In the `custom_components` directory (folder), create a new folder called `combivox_web`
4. Download all the files from the `custom_components/combivox_web/` directory in this repository
5. Place the files you downloaded in the new directory you created
6. Restart Home Assistant

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=combivox_web)

## Configuration

### Initial Setup

After installation, add the integration:

1. In Home Assistant, go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Combivox Alarm Web"
4. Enter the following information:
   - **IP Address**: The IP address of your alarm panel (e.g., `192.168.1.125`)
   - **Port**: HTTP port (default: `80`)
   - **Master PIN Code**: Your master PIN code
     - If less than 6 digits, two zeros are appended to the end
     - Example: `1234` → `123400`

### Options Configuration

After initial setup, click **Configure** on the integration to access advanced options:

#### Basic Settings
- **Scan Interval**: Polling interval in seconds (1-300, default: 5)
- **Code**: User code for arm/disarm from UI (optional)

#### Area Configuration
- **Areas for Away Mode**: Multi-select of area names for away arming
- **Areas for Home Mode**: Multi-select of area names for home arming
- **Areas for Night Mode**: Multi-select of area names for night arming
- **Areas for Disarm Mode**: Multi-select of area names for selective disarming

#### Disarm Behavior

The integration supports **selective disarming**:

- **If areas are selected**: Only the selected areas will be disarmed
- **If no areas selected**: ALL areas will be disarmed (complete disarm)
- **If scenario is configured**: The scenario will be executed instead

This allows you to keep the perimeter armed while disarming only interior areas.

#### Arm Modes

For each arm type (Away/Home/Night):
- **Normal**: Arming with exit delay (standard mode)
- **Immediate**: Arming without exit delay
- **Forced**: Bypass open zones and arm with delay

#### Macro/Scenario Configuration
- **Scenario for Away**: Macro to execute when arming away
- **Scenario for Home**: Macro to execute when arming home
- **Scenario for Night**: Macro to execute when arming night
- **Scenario for Disarm**: Macro to execute when disarming

**Note**: Areas have priority over scenarios when both are configured.

## Documentation

For detailed documentation, see:

- **[Services Documentation](docs/services.md)** - Using arm/disarm services
- **[Entities Documentation](docs/entities.md)** - All created entities and their attributes
- **[Authentication Documentation](docs/authentication.md)** - How authentication works
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions
- **[Supported Models](docs/supported-models.md)** - Compatibility table and reporting

## Download Diagnostics

The integration supports downloading diagnostic data:

1. Go to **Settings** → **Devices & Services**
2. Find **Combivox Alarm Web** integration
3. Click the three dots menu (⋮)
4. Select **Download Diagnostics**

A JSON file will be downloaded with comprehensive diagnostic information (connection, state, configuration, device info, live panel data).

## Support

For issues, questions, or contributions:
- **GitHub Issues**: [Create an issue](https://github.com/stich86/ha-combivox-web/issues)
- **Supported Models**: Help us improve - report your panel model in [Supported Models](docs/supported-models.md)

## Documentation

- [Entities Reference](docs/entities.md) - Complete list of all entities and their attributes
- [Services](docs/services.md) - Custom services for arm/disarm areas
- [Authentication](docs/authentication.md) - How authentication works
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [Supported Models](docs/supported-models.md) - Tested and compatible panel models
- [TODO & Improvements](docs/todo.md) - XML byte mapping status and planned improvements
