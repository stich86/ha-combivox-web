"""Buttons for Combivox Amica Web integration."""

import logging
from typing import Any, Dict

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import CombivoxWebClient
from .const import DOMAIN, DATA_COORDINATOR, DATA_CONFIG
from .coordinator import CombivoxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up buttons from a config entry."""
    _LOGGER.info("Setting up zone bypass and macro buttons")

    # Get coordinator and client
    coordinator: CombivoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    client: CombivoxWebClient = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]

    # Get device info for HA
    device_info = client.get_device_info_for_ha()

    # Get zones configuration
    zones_config = client.get_zones_config()

    # Get macros configuration
    macros_config = client.get_macros_config()

    # Get commands configuration
    commands_config = client.get_commands_config()

    entities = []

    # Create a button for each zone that has a name
    if zones_config:
        for zone in zones_config:
            zone_name = zone.get("zone_name")
            zone_id = zone.get("zone_id")

            # Only create buttons for zones with names
            if zone_name:
                entities.append(CombivoxZoneBypassButton(
                    coordinator,
                    client,
                    device_info,
                    zone_id,
                    zone_name
                ))

    _LOGGER.info("Adding %d zone bypass buttons", len(entities) - len(macros_config) if macros_config else len(entities))

    # Create a button for each macro that has a name
    if macros_config:
        for macro in macros_config:
            macro_name = macro.get("macro_name")
            macro_id = macro.get("macro_id")

            # Only create buttons for macros with names
            if macro_name:
                entities.append(CombivoxMacroButton(
                    coordinator,
                    client,
                    device_info,
                    macro_id,
                    macro_name
                ))

    _LOGGER.info("Adding %d macro (scenario) buttons", len(macros_config) if macros_config else 0)

    # Create a button for each command of type "button" (impulsivo)
    command_buttons_count = 0
    if commands_config:
        for command in commands_config:
            command_name = command.get("command_name")
            command_id = command.get("command_id")
            command_type = command.get("command_type")

            # Only create buttons for commands with type "button"
            if command_name and command_type == "button":
                entities.append(CombivoxCommandButton(
                    coordinator,
                    client,
                    device_info,
                    command_id,
                    command_name
                ))
                command_buttons_count += 1

    _LOGGER.info("Adding %d command buttons", command_buttons_count)

    # Add clear alarm memory button
    entities.append(CombivoxClearAlarmMemoryButton(
        coordinator,
        client,
        device_info
    ))

    _LOGGER.info("Adding %d total buttons", len(entities))

    async_add_entities(entities, update_before_add=True)


class CombivoxZoneBypassButton(CoordinatorEntity, ButtonEntity):
    """Button for zone bypass toggle."""

    def __init__(
        self,
        coordinator: CombivoxDataUpdateCoordinator,
        client: CombivoxWebClient,
        device_info: Dict[str, Any],
        zone_id: int,
        zone_name: str
    ):
        """Initialize the zone bypass button."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        self.zone_id = zone_id
        self.zone_name = zone_name

        # Create unique ID based on zone ID
        self._attr_unique_id = f"combivox_zone_{zone_id}_bypass"
        self._attr_name = f"{zone_name} - Bypass"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to HA."""
        await super().async_added_to_hass()
        # Register for coordinator updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def icon(self) -> str:
        """Return icon based on zone inclusion state."""
        zones = (self.coordinator.data or {}).get("zones", {})
        zone_data = zones.get(self.zone_id)

        if zone_data and zone_data.get("included", True):
            # Zone is included - show normal shield
            return "mdi:shield"
        else:
            # Zone is excluded/bypassed - show shield with slash
            return "mdi:shield-off"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    async def async_press(self, **kwargs: Any) -> None:
        """Press the button - toggle zone inclusion."""
        _LOGGER.info("Toggling zone %d (%s) bypass", self.zone_id, self.zone_name)

        success = await self.client.toggle_zone_inclusion(self.zone_id)
        if success:
            _LOGGER.info("Zone %d bypass toggled successfully", self.zone_id)
            # Refresh to get updated state
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to toggle zone %d bypass", self.zone_id)


class CombivoxMacroButton(CoordinatorEntity, ButtonEntity):
    """Button for executing macros (scenarios)."""

    def __init__(
        self,
        coordinator: CombivoxDataUpdateCoordinator,
        client: CombivoxWebClient,
        device_info: Dict[str, Any],
        macro_id: int,
        macro_name: str
    ):
        """Initialize the macro button."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        self.macro_id = macro_id
        self.macro_name = macro_name

        # Create unique ID based on macro ID
        self._attr_unique_id = f"combivox_macro_{macro_id}"
        self._attr_name = macro_name
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.CONFIG

        # Set icon for scenario
        self._attr_icon = "mdi:play-box-outline"

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Register update listener
        if self.coordinator:
            self.coordinator.async_add_listener(self._handle_coordinator_update)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    async def async_press(self, **kwargs: Any) -> None:
        """Press the button - execute the macro."""
        _LOGGER.info("Executing macro %d (%s)", self.macro_id, self.macro_name)

        success = await self.client.execute_macro(self.macro_id, self.macro_name)
        if success:
            _LOGGER.info("Macro %d (%s) executed successfully", self.macro_id, self.macro_name)
        else:
            _LOGGER.error("Failed to execute macro %d (%s)", self.macro_id, self.macro_name)


class CombivoxCommandButton(CoordinatorEntity, ButtonEntity):
    """Button for executing commands (type=button, impulsivo)."""

    def __init__(
        self,
        coordinator: CombivoxDataUpdateCoordinator,
        client: CombivoxWebClient,
        device_info: Dict[str, Any],
        command_id: int,
        command_name: str
    ):
        """Initialize the command button."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        self.command_id = command_id
        self.command_name = command_name

        # Create unique ID based on command ID
        self._attr_unique_id = f"combivox_command_{command_id}"
        self._attr_name = command_name
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.CONFIG

        # Set icon for command button
        self._attr_icon = "mdi:gesture-tap-button"

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Register update listener
        if self.coordinator:
            self.coordinator.async_add_listener(self._handle_coordinator_update)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    async def async_press(self, **kwargs: Any) -> None:
        """Press the button - execute the command (activate)."""
        _LOGGER.info("Executing command %d (%s)", self.command_id, self.command_name)

        success = await self.client.execute_command(self.command_id, activate=True)
        if success:
            _LOGGER.info("Command %d (%s) executed successfully", self.command_id, self.command_name)
        else:
            _LOGGER.error("Failed to execute command %d (%s)", self.command_id, self.command_name)


class CombivoxClearAlarmMemoryButton(CoordinatorEntity, ButtonEntity):
    """Button for clearing alarm memory."""

    def __init__(
        self,
        coordinator: CombivoxDataUpdateCoordinator,
        client: CombivoxWebClient,
        device_info: Dict[str, Any]
    ):
        """Initialize the clear alarm memory button."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client

        self._attr_unique_id = "combivox_clear_alarm_memory"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:delete-forever"
        self._attr_translation_key = "clear_alarm_memory"

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to HA."""
        await super().async_added_to_hass()
        # Register for coordinator updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    async def async_press(self, **kwargs: Any) -> None:
        """Press the button - clear alarm memory."""
        _LOGGER.info("Clearing alarm memory")

        success = await self.client.clear_alarm_memory()
        if success:
            _LOGGER.info("Alarm memory cleared successfully")
            # Refresh to get updated state
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to clear alarm memory")

