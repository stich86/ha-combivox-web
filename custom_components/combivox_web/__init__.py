"""The Combivox Amica Web integration."""

import logging
import voluptuous as vol
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform, CONF_IP_ADDRESS

from .base import CombivoxWebClient

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.info("Migrating config entry from version %s", config_entry.version)

    if config_entry.version < 1:
        from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL

        if CONF_SCAN_INTERVAL not in config_entry.options:
            new_options = dict(config_entry.options)
            new_options[CONF_SCAN_INTERVAL] = DEFAULT_SCAN_INTERVAL
            _LOGGER.info("Adding scan_interval=%s to options", DEFAULT_SCAN_INTERVAL)

            hass.config_entries.async_update_entry(
                config_entry,
                options=new_options,
                version=1
            )

            _LOGGER.info("Migration completed: Please reload the integration to apply changes")
        else:
            hass.config_entries.async_update_entry(config_entry, version=1)

    return True


from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    DATA_UPDATE_LISTENER,
    DATA_CONFIG,
    CONF_IP_ADDRESS,
    CONF_PORT,
    CONF_CODE,
    CONF_AREAS_AWAY,
    CONF_AREAS_HOME,
    CONF_AREAS_NIGHT,
    CONF_AREAS_DISARM,
    CONF_ARM_MODE_AWAY,
    CONF_ARM_MODE_HOME,
    CONF_ARM_MODE_NIGHT,
    CONF_MACRO_AWAY,
    CONF_MACRO_HOME,
    CONF_MACRO_NIGHT,
    CONF_MACRO_DISARM,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.ALARM_CONTROL_PANEL,
    Platform.BUTTON,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Combivox Amica Web from a config entry."""
    _LOGGER.info("Setting up Combivox Amica Web integration")

    # Get configuration
    ip_address = entry.data.get(CONF_IP_ADDRESS)
    port = entry.data.get(CONF_PORT, 80)
    code = entry.data.get(CONF_CODE)

    if not ip_address or not code:
        _LOGGER.error("Missing required configuration: ip_address or code")
        return False

    # Create config file path
    config_file_path = hass.config.path(f"combivox_web/config_{ip_address}_{port}.json")

    # Create client with reduced timeout for faster failure detection
    client = CombivoxWebClient(
        ip_address=ip_address,
        code=code,
        port=port,
        config_file_path=config_file_path,
        timeout=3,
    )

    # Connect to panel (async) - but allow setup to continue if cache is available
    connected = await client.connect()

    if not connected:
        _LOGGER.warning("Failed to connect to Combivox panel - will retry automatically")
        if not client.is_config_loaded():
            _LOGGER.error("No cached configuration available - cannot setup integration")
            return False
        _LOGGER.info("Using cached configuration - entities will be created but unavailable until connection succeeds")
    else:
        _LOGGER.info("Successfully connected to Combivox panel")

    # Get polling interval - check options first, then data, then default
    # This ensures we always have a value even on first setup
    scan_interval = None
    
    # Priority 1: Check options (user may have changed it)
    if CONF_SCAN_INTERVAL in entry.options:
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL)
        _LOGGER.info("Found scan_interval in options: %s", scan_interval)
    
    # Priority 2: Check data (from previous setup or migration)
    elif CONF_SCAN_INTERVAL in entry.data:
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL)
        _LOGGER.info("Found scan_interval in data: %s", scan_interval)
    
    # Priority 3: Use default
    else:
        scan_interval = DEFAULT_SCAN_INTERVAL
        _LOGGER.info("Using DEFAULT_SCAN_INTERVAL: %s", scan_interval)
    
    # Force cast to int in case it's stored as string
    try:
        scan_interval = int(scan_interval)
    except (ValueError, TypeError) as e:
        _LOGGER.warning("Invalid scan_interval value '%s' (%s), using default %s",
                       scan_interval, e, DEFAULT_SCAN_INTERVAL)
        scan_interval = DEFAULT_SCAN_INTERVAL

    _LOGGER.info("Setting up coordinator with scan_interval: %d seconds", scan_interval)

    # Import coordinator
    from .coordinator import CombivoxDataUpdateCoordinator

    # Create single coordinator with unified polling
    coordinator = CombivoxDataUpdateCoordinator(
        hass=hass,
        client=client,
        scan_interval=scan_interval
    )

    # Preload data
    await coordinator.async_config_entry_first_refresh()

    # Register update listener for options changes
    update_listener = entry.add_update_listener(options_update_listener)

    # Store coordinator and client
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_CONFIG: client,
        DATA_UPDATE_LISTENER: update_listener,
    }

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup services
    from . import services
    await services.setup_services(hass)

    return True


def _get_alarm_panel_entity(hass: HomeAssistant, config_entry: ConfigEntry):
    """Get alarm panel entity from hass.data.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Alarm panel entity or None
    """
    return hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {}).get("alarm_panel_entity")


def _extract_new_config(config_entry: ConfigEntry) -> Dict[str, Any]:
    """Extract new configuration from options.

    Args:
        config_entry: Configuration entry with updated options

    Returns:
        Dict with all new configuration values
    """
    from .const import (
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL,
        CONF_AREAS_AWAY, CONF_AREAS_HOME, CONF_AREAS_NIGHT, CONF_AREAS_DISARM,
        CONF_MACRO_AWAY, CONF_MACRO_HOME, CONF_MACRO_NIGHT, CONF_MACRO_DISARM,
        CONF_ARM_MODE_AWAY, CONF_ARM_MODE_HOME, CONF_ARM_MODE_NIGHT,
    )

    # Extract scan interval and convert to int
    new_scan_interval_raw = config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    try:
        new_scan_interval = int(new_scan_interval_raw)
    except (ValueError, TypeError):
        _LOGGER.warning("Invalid scan_interval in options: %s, using default", new_scan_interval_raw)
        new_scan_interval = DEFAULT_SCAN_INTERVAL

    return {
        "areas_away": config_entry.options.get(CONF_AREAS_AWAY, []),
        "areas_home": config_entry.options.get(CONF_AREAS_HOME, []),
        "areas_night": config_entry.options.get(CONF_AREAS_NIGHT, []),
        "areas_disarm": config_entry.options.get(CONF_AREAS_DISARM, []),
        "macro_away": config_entry.options.get(CONF_MACRO_AWAY, ""),
        "macro_home": config_entry.options.get(CONF_MACRO_HOME, ""),
        "macro_night": config_entry.options.get(CONF_MACRO_NIGHT, ""),
        "macro_disarm": config_entry.options.get(CONF_MACRO_DISARM, ""),
        "arm_mode_away": config_entry.options.get(CONF_ARM_MODE_AWAY, "normal"),
        "arm_mode_home": config_entry.options.get(CONF_ARM_MODE_HOME, "normal"),
        "arm_mode_night": config_entry.options.get(CONF_ARM_MODE_NIGHT, "normal"),
        "scan_interval": new_scan_interval,
    }


def _get_current_config(alarm_panel) -> Dict[str, Any]:
    """Get current configuration from alarm panel entity.

    Args:
        alarm_panel: Alarm panel entity (can be None)

    Returns:
        Dict with all current configuration values
    """
    if not alarm_panel:
        # Fallback defaults if entity not found
        return {
            "areas_away": [],
            "areas_home": [],
            "areas_night": [],
            "areas_disarm": [],
            "macro_away": "",
            "macro_home": "",
            "macro_night": "",
            "macro_disarm": "",
            "arm_mode_away": "normal",
            "arm_mode_home": "normal",
            "arm_mode_night": "normal",
        }

    return {
        "areas_away": alarm_panel.areas_away or [],
        "areas_home": alarm_panel.areas_home or [],
        "areas_night": alarm_panel.areas_night or [],
        "areas_disarm": alarm_panel.areas_disarm or [],
        "macro_away": alarm_panel.macro_away or "",
        "macro_home": alarm_panel.macro_home or "",
        "macro_night": alarm_panel.macro_night or "",
        "macro_disarm": alarm_panel.macro_disarm or "",
        "arm_mode_away": alarm_panel.arm_mode_away,
        "arm_mode_home": alarm_panel.arm_mode_home,
        "arm_mode_night": alarm_panel.arm_mode_night,
    }


def _detect_changes(new_config: Dict[str, Any], current_config: Dict[str, Any],
                   current_interval: Optional[int]) -> Dict[str, Any]:
    """Detect which configuration values changed.

    Args:
        new_config: New configuration from options
        current_config: Current configuration from entity
        current_interval: Current scan interval from coordinator

    Returns:
        Dict with boolean flags for each change type
    """
    # Check areas
    areas_changed = (
        new_config.get("areas_away", []) != current_config.get("areas_away", []) or
        new_config.get("areas_home", []) != current_config.get("areas_home", []) or
        new_config.get("areas_night", []) != current_config.get("areas_night", []) or
        new_config.get("areas_disarm", []) != current_config.get("areas_disarm", [])
    )

    # Check macros
    macros_changed = (
        new_config["macro_away"] != current_config["macro_away"] or
        new_config["macro_home"] != current_config["macro_home"] or
        new_config["macro_night"] != current_config["macro_night"] or
        new_config["macro_disarm"] != current_config["macro_disarm"]
    )

    # Check arm modes
    arm_modes_changed = (
        new_config["arm_mode_away"] != current_config["arm_mode_away"] or
        new_config["arm_mode_home"] != current_config["arm_mode_home"] or
        new_config["arm_mode_night"] != current_config["arm_mode_night"]
    )

    # Check scan interval
    scan_interval_changed = (current_interval is not None and
                            current_interval != new_config["scan_interval"])

    return {
        "areas": areas_changed,
        "macros": macros_changed,
        "arm_modes": arm_modes_changed,
        "scan_interval": scan_interval_changed,
    }


async def _apply_changes(hass: HomeAssistant, config_entry: ConfigEntry,
                        changes: Dict[str, Any], new_config: Dict[str, Any],
                        current_interval: Optional[int]) -> None:
    """Apply detected configuration changes.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry
        changes: Dict with boolean flags for each change type
        new_config: New configuration values
        current_interval: Current scan interval for logging
    """
    alarm_panel = _get_alarm_panel_entity(hass, config_entry)
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {}).get(DATA_COORDINATOR)

    # Update areas dynamically (no reload needed)
    if changes["areas"]:
        _LOGGER.info("Areas configuration changed - updating alarm panel entity")
        _LOGGER.info("Areas to update - away: %s, home: %s, night: %s, disarm: %s",
                    new_config.get("areas_away", []),
                    new_config.get("areas_home", []),
                    new_config.get("areas_night", []),
                    new_config.get("areas_disarm", []))
        try:
            if alarm_panel:
                alarm_panel.update_areas(
                    new_config.get("areas_away", []),
                    new_config.get("areas_home", []),
                    new_config.get("areas_night", []),
                    new_config.get("areas_disarm", [])
                )
                _LOGGER.info("Alarm panel areas updated successfully")
            else:
                _LOGGER.warning("Alarm panel entity not found, cannot update areas")
        except Exception as e:
            _LOGGER.error("Error updating alarm panel entity areas: %s", e)
    else:
        _LOGGER.debug("Areas configuration NOT changed - skipping update")

    # Update macros dynamically (no reload needed)
    if changes["macros"]:
        _LOGGER.debug("Macros configuration changed - updating alarm panel entity")
        try:
            if alarm_panel:
                alarm_panel.update_macros(
                    new_config["macro_away"],
                    new_config["macro_home"],
                    new_config["macro_night"],
                    new_config["macro_disarm"]
                )
                _LOGGER.debug("Alarm panel macros updated successfully")
            else:
                _LOGGER.warning("Alarm panel entity not found, cannot update macros")
        except Exception as e:
            _LOGGER.error("Error updating alarm panel entity macros: %s", e)

    # Update arm modes dynamically (no reload needed)
    if changes["arm_modes"]:
        _LOGGER.debug("Arm modes configuration changed - updating alarm panel entity")
        try:
            if alarm_panel:
                alarm_panel.update_arm_modes(
                    new_config["arm_mode_away"],
                    new_config["arm_mode_home"],
                    new_config["arm_mode_night"]
                )
                _LOGGER.debug("Alarm panel arm modes updated successfully")
            else:
                _LOGGER.warning("Alarm panel entity not found, cannot update arm modes")
        except Exception as e:
            _LOGGER.error("Error updating alarm panel entity arm modes: %s", e)

    # Update scan_interval dynamically (no reload needed)
    if changes["scan_interval"] and coordinator:
        _LOGGER.debug("Scan interval CHANGED from %s to %s seconds - calling update_scan_interval()",
                    current_interval, new_config["scan_interval"])

        try:
            await coordinator.update_scan_interval(new_config["scan_interval"])
            _LOGGER.debug("Coordinator scan interval updated successfully to %s seconds",
                         new_config["scan_interval"])
        except Exception as e:
            _LOGGER.error("Error updating scan interval: %s", e)
            import traceback
            traceback.print_exc()
    else:
        _LOGGER.debug("Scan interval NOT changed (%s == %s), skipping update",
                    current_interval, new_config["scan_interval"])


async def options_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""
    # Get coordinator (required for scan interval updates)
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {}).get(DATA_COORDINATOR)
    if not coordinator:
        _LOGGER.error("Coordinator not found in hass.data!")
        return

    # Extract new configuration from options
    new_config = _extract_new_config(config_entry)

    # Get current configuration from alarm panel entity
    alarm_panel = _get_alarm_panel_entity(hass, config_entry)
    current_config = _get_current_config(alarm_panel)

    # Get current scan interval from coordinator
    current_interval = coordinator._custom_interval

    # Detect what changed
    changes = _detect_changes(new_config, current_config, current_interval)

    # Apply all detected changes
    await _apply_changes(hass, config_entry, changes, new_config, current_interval)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.info("Unloading Combivox Amica Web integration")

    # Shutdown coordinator first (stop polling)
    try:
        coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
        await coordinator.async_shutdown()
        _LOGGER.info("Coordinator shutdown complete")
    except Exception as e:
        _LOGGER.error("Error shutting down coordinator: %s", e)

    # Close client (cleanup HTTP session and cookies)
    try:
        client = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]
        config_file_path = client.get_config_file_path()
        await client.close()
        _LOGGER.info("Client closed successfully")
    except Exception as e:
        _LOGGER.error("Error closing client: %s", e)
        config_file_path = None

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Remove update listener
        hass.data[DOMAIN][entry.entry_id][DATA_UPDATE_LISTENER]()
        hass.data[DOMAIN].pop(entry.entry_id)

        # Cleanup if no more entries
        if not hass.data.get(DOMAIN):
            del hass.data[DOMAIN]

        # Clean up entity registry - remove all entities for this integration
        from homeassistant.helpers import entity_registry as er
        entity_reg = er.async_get(hass)
        entity_reg.async_clear_config_entry(entry)

        _LOGGER.info("Cleared all entities from registry for config entry %s", entry.entry_id)

        # Delete cached config file
        if config_file_path:
            import os
            try:
                if os.path.exists(config_file_path):
                    os.remove(config_file_path)
                    _LOGGER.info("Deleted cached config file: %s", config_file_path)
                else:
                    _LOGGER.debug("Config file not found (already deleted): %s", config_file_path)
            except Exception as e:
                _LOGGER.error("Error deleting config file %s: %s", config_file_path, e)

    return unload_ok
