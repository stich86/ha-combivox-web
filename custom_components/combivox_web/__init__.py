"""The Combivox Amica Web integration."""

import logging
import voluptuous as vol
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
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
    DATA_CONFIG,
    CONF_IP_ADDRESS,
    CONF_PORT,
    CONF_CODE,
    CONF_AREAS_AWAY,
    CONF_AREAS_HOME,
    CONF_AREAS_NIGHT,
    CONF_AREAS_CUSTOM_BYPASS,
    CONF_AREAS_DISARM,
    CONF_ARM_MODE_AWAY,
    CONF_ARM_MODE_HOME,
    CONF_ARM_MODE_NIGHT,
    CONF_ENABLE_CUSTOM_BYPASS,
    CONF_ARM_MODE_CUSTOM_BYPASS,
    CONF_MACRO_AWAY,
    CONF_MACRO_HOME,
    CONF_MACRO_NIGHT,
    CONF_MACRO_CUSTOM_BYPASS,
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

    # Migration: previous versions saved the changed PIN in the options,
    # where it was ignored (the client always used entry.data). If present
    # and different, promote it to the connection data (single source of truth).
    options_code = entry.options.get(CONF_CODE)
    if options_code and options_code != code:
        _LOGGER.info("Found PIN stored in options by a previous version - migrating it to entry data")
        code = options_code
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_CODE: code},
            options={k: v for k, v in entry.options.items() if k != CONF_CODE},
        )

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
        if not client.is_config_loaded():
            # Raise ConfigEntryNotReady instead of failing the setup for good:
            # HA will retry automatically, so the integration recovers by itself
            # as soon as the panel accepts the (possibly fixed) PIN.
            raise ConfigEntryNotReady("Cannot connect to Combivox panel and no cached configuration available")
        _LOGGER.warning("Failed to connect to Combivox panel - using cached configuration, entities will be unavailable until connection succeeds")
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

    # Register the options update listener exactly once per entry: it must
    # survive reloads. Unloading removes nothing, but a reload re-runs setup:
    # registering unconditionally would add a duplicate listener on every
    # reload, while deregistering on unload would leave a window (between
    # unload and setup completion) where a saved PIN would be ignored.
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(f"{entry.entry_id}_update_listener_registered"):
        entry.add_update_listener(options_update_listener)
        domain_data[f"{entry.entry_id}_update_listener_registered"] = True

    # Store coordinator and client
    domain_data[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_CONFIG: client,
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
        CONF_AREAS_AWAY, CONF_AREAS_HOME, CONF_AREAS_NIGHT, CONF_AREAS_CUSTOM_BYPASS, CONF_AREAS_DISARM,
        CONF_MACRO_AWAY, CONF_MACRO_HOME, CONF_MACRO_NIGHT, CONF_MACRO_CUSTOM_BYPASS, CONF_MACRO_DISARM,
        CONF_ARM_MODE_AWAY, CONF_ARM_MODE_HOME, CONF_ARM_MODE_NIGHT, CONF_ARM_MODE_CUSTOM_BYPASS,
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
        "areas_custom_bypass": config_entry.options.get(CONF_AREAS_CUSTOM_BYPASS, []),
        "areas_disarm": config_entry.options.get(CONF_AREAS_DISARM, []),
        "macro_away": config_entry.options.get(CONF_MACRO_AWAY, ""),
        "macro_home": config_entry.options.get(CONF_MACRO_HOME, ""),
        "macro_night": config_entry.options.get(CONF_MACRO_NIGHT, ""),
        "macro_custom_bypass": config_entry.options.get(CONF_MACRO_CUSTOM_BYPASS, ""),
        "macro_disarm": config_entry.options.get(CONF_MACRO_DISARM, ""),
        "arm_mode_away": config_entry.options.get(CONF_ARM_MODE_AWAY, "normal"),
        "arm_mode_home": config_entry.options.get(CONF_ARM_MODE_HOME, "normal"),
        "arm_mode_night": config_entry.options.get(CONF_ARM_MODE_NIGHT, "normal"),
        "arm_mode_custom_bypass": config_entry.options.get(CONF_ARM_MODE_CUSTOM_BYPASS, "normal"),
        "scan_interval": new_scan_interval,
        "enable_bypass": config_entry.options.get(CONF_ENABLE_CUSTOM_BYPASS, False),
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
            "areas_custom_bypass": [],
            "areas_disarm": [],
            "macro_away": "",
            "macro_home": "",
            "macro_night": "",
            "macro_custom_bypass": "",
            "macro_disarm": "",
            "arm_mode_away": "normal",
            "arm_mode_home": "normal",
            "arm_mode_night": "normal",
            "arm_mode_custom_bypass": "normal",
            "enable_bypass": False,
        }


    return {
        "areas_away": alarm_panel.areas_away or [],
        "areas_home": alarm_panel.areas_home or [],
        "areas_night": alarm_panel.areas_night or [],
        "areas_custom_bypass": alarm_panel.areas_custom_bypass or [],
        "areas_disarm": alarm_panel.areas_disarm or [],
        "macro_away": alarm_panel.macro_away or "",
        "macro_home": alarm_panel.macro_home or "",
        "macro_night": alarm_panel.macro_night or "",
        "macro_custom_bypass": alarm_panel.macro_custom_bypass or "",
        "macro_disarm": alarm_panel.macro_disarm or "",
        "arm_mode_away": alarm_panel.arm_mode_away,
        "arm_mode_home": alarm_panel.arm_mode_home,
        "arm_mode_night": alarm_panel.arm_mode_night,
        "arm_mode_custom_bypass": alarm_panel.arm_mode_custom_bypass,
        "enable_bypass": alarm_panel.enable_bypass,
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
        new_config.get("areas_custom_bypass", []) != current_config.get("areas_custom_bypass", []) or
        new_config.get("areas_disarm", []) != current_config.get("areas_disarm", [])
    )

    # Check macros
    macros_changed = (
        new_config["macro_away"] != current_config["macro_away"] or
        new_config["macro_home"] != current_config["macro_home"] or
        new_config["macro_night"] != current_config["macro_night"] or
        new_config["macro_custom_bypass"] != current_config["macro_custom_bypass"] or
        new_config["macro_disarm"] != current_config["macro_disarm"]
    )

    # Check arm modes
    arm_modes_changed = (
        new_config["arm_mode_away"] != current_config["arm_mode_away"] or
        new_config["arm_mode_home"] != current_config["arm_mode_home"] or
        new_config["arm_mode_night"] != current_config["arm_mode_night"] or
        new_config["arm_mode_custom_bypass"] != current_config["arm_mode_custom_bypass"]
    )

    # Check scan interval
    scan_interval_changed = (current_interval is not None and
                            current_interval != new_config["scan_interval"])

    # Check enable bypass checkbox
    enable_bypass_changed = new_config["enable_bypass"] != current_config["enable_bypass"]

    return {
        "areas": areas_changed,
        "macros": macros_changed,
        "arm_modes": arm_modes_changed,
        "scan_interval": scan_interval_changed,
        "enable_bypass": enable_bypass_changed,
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

    if changes["enable_bypass"]:
        _LOGGER.info("Custom bypass option changed - updating alarm panel entity features to: %s", new_config["enable_bypass"])
        try:
            if alarm_panel:
                alarm_panel.update_enable_bypass(new_config["enable_bypass"])
                _LOGGER.info("Alarm panel custom bypass feature updated successfully")
            else:
                _LOGGER.warning("Alarm panel entity not found, cannot update custom bypass feature")
        except Exception as e:
            _LOGGER.error("Error updating alarm panel entity custom bypass feature: %s", e)

    # Update areas dynamically (no reload needed)
    if changes["areas"]:
        _LOGGER.info("Areas configuration changed - updating alarm panel entity")
        _LOGGER.info("Areas to update - away: %s, home: %s, night: %s, custom_bypass: %s, disarm: %s",
                    new_config.get("areas_away", []),
                    new_config.get("areas_home", []),
                    new_config.get("areas_night", []),
                    new_config.get("areas_custom_bypass", []),
                    new_config.get("areas_disarm", []))
        try:
            if alarm_panel:
                alarm_panel.update_areas(
                    new_config.get("areas_away", []),
                    new_config.get("areas_home", []),
                    new_config.get("areas_night", []),
                    new_config.get("areas_custom_bypass", []),
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
                    new_config["macro_custom_bypass"],
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
                    new_config["arm_mode_night"],
                    new_config["arm_mode_custom_bypass"]
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


def _get_entry_client(hass: HomeAssistant, entry: ConfigEntry):
    """Return the live client for the entry, or None if the entry is not loaded."""
    return hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get(DATA_CONFIG)


async def _handle_pin_change(hass: HomeAssistant, config_entry: ConfigEntry,
                             recheck: bool = False) -> bool:
    """Reload the entry when its PIN differs from the one the client is using.

    A reload rebuilds the client (and its authenticated session) from the
    current entry data. Returns True if a reload was scheduled.

    A reload can take tens of seconds when authentication keeps failing, and
    this listener fires twice per save (data + options update). If a reload
    is already in flight we must not just drop the request: schedule a
    re-check when it completes, so a PIN saved during that window is applied.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    reload_task_key = f"{config_entry.entry_id}_pin_reload_task"

    running_task = domain_data.get(reload_task_key)
    if running_task is not None and not running_task.done():
        running_task.add_done_callback(
            lambda _task: hass.async_create_task(
                _handle_pin_change(hass, config_entry, recheck=True)
            )
        )
        return False

    new_code = config_entry.data.get(CONF_CODE)
    client = _get_entry_client(hass, config_entry)

    if not new_code or (client is not None and new_code == client.code):
        return False

    if client is None:
        if recheck:
            # Re-check after our own reload found no client: the entry is not
            # loaded and HA is retrying the setup by itself (already using
            # the new PIN) - reloading again here would just loop.
            return False
        # Fresh save on an entry that is not loaded (setup previously failed,
        # e.g. a wrong PIN): no client to compare against, but the entry data
        # just changed - reload to retry the setup with the new PIN.
        _LOGGER.info("PIN changed while entry is not loaded - reloading config entry to apply the new code")
    else:
        _LOGGER.info("PIN changed - reloading config entry to apply the new code")

    reload_task = hass.async_create_task(
        hass.config_entries.async_reload(config_entry.entry_id)
    )
    domain_data[reload_task_key] = reload_task
    reload_task.add_done_callback(
        lambda _task: domain_data.pop(reload_task_key, None)
    )
    return True


async def options_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""
    # If the PIN changed, the client must be rebuilt from the new entry data.
    # When a reload gets scheduled there is no point in applying the other
    # option changes: the reload will rebuild coordinator and entities.
    if await _handle_pin_change(hass, config_entry):
        return

    # Get coordinator (required for scan interval updates)
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {}).get(DATA_COORDINATOR)
    if not coordinator:
        # Normal while a reload is in flight or the setup is failing/retrying
        _LOGGER.debug("Entry not loaded - skipping options update")
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
        await client.close()
        _LOGGER.info("Client closed successfully")
    except Exception as e:
        _LOGGER.error("Error closing client: %s", e)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # The update listener is intentionally kept registered across reloads
        # (see async_setup_entry); hass.data[DOMAIN] keeps the per-entry flags.
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Clean up entity registry - remove all entities for this integration
        from homeassistant.helpers import entity_registry as er
        entity_reg = er.async_get(hass)
        entity_reg.async_clear_config_entry(entry)

        _LOGGER.info("Cleared all entities from registry for config entry %s", entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Cleanup when the config entry is removed.

    The cached panel configuration is intentionally kept across reloads:
    deleting it on unload would leave the integration without its fallback
    (e.g. after saving a wrong PIN, setup would fail hard with no retry).
    """
    # Drop the per-entry listener flag: the entry (and its listener) is gone.
    hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_update_listener_registered", None)

    ip_address = entry.data.get(CONF_IP_ADDRESS)
    port = entry.data.get(CONF_PORT, 80)

    if not ip_address:
        return

    config_file_path = hass.config.path(f"combivox_web/config_{ip_address}_{port}.json")

    import os
    try:
        if os.path.exists(config_file_path):
            os.remove(config_file_path)
            _LOGGER.info("Deleted cached config file: %s", config_file_path)
        else:
            _LOGGER.debug("Config file not found (already deleted): %s", config_file_path)
    except Exception as e:
        _LOGGER.error("Error deleting config file %s: %s", config_file_path, e)
