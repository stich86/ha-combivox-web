"""Switches for Combivox Amica Web integration."""

import logging
from typing import Any, Dict

from homeassistant.components.switch import SwitchEntity
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
    """Set up switches from a config entry."""
    _LOGGER.info("Setting up command switches")

    # Get coordinator and client
    coordinator: CombivoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    client: CombivoxWebClient = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]

    # Get device info for HA
    device_info = client.get_device_info_for_ha()

    # Get commands configuration
    commands_config = client.get_commands_config()

    entities = []

    # Create a switch for each command of type "switch" (bistabile)
    if commands_config:
        for command in commands_config:
            command_name = command.get("command_name")
            command_id = command.get("command_id")
            command_type = command.get("command_type")

            # Only create switches for commands with type "switch"
            if command_name and command_type == "switch":
                entities.append(CombivoxCommandSwitch(
                    coordinator,
                    client,
                    device_info,
                    command_id,
                    command_name
                ))

    _LOGGER.info("Adding %d command switches", len(entities))
    async_add_entities(entities, update_before_add=True)


class CombivoxCommandSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for executing commands (type=switch, bistabile)."""

    def __init__(
        self,
        coordinator: CombivoxDataUpdateCoordinator,
        client: CombivoxWebClient,
        device_info: Dict[str, Any],
        command_id: int,
        command_name: str
    ):
        """Initialize the command switch."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        self.command_id = command_id
        self.command_name = command_name

        # Optimistic state (will be updated when we parse the XML byte)
        # TODO: Parse switch state from XML byte to track actual state
        self._attr_is_on = False

        # Create unique ID based on command ID
        self._attr_unique_id = f"combivox_switch_{command_id}"
        self._attr_name = command_name
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.CONFIG

        # Set icon for switch
        self._attr_icon = "mdi:toggle-switch"

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Register update listener
        if self.coordinator:
            self.coordinator.async_add_listener(self._handle_coordinator_update)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # TODO: Parse switch state from XML byte to track actual state
        # The XML contains the state of each switch (on/off) in a specific byte position
        # Need to identify which byte contains the switch states and parse it
        # For now, using optimistic mode (state updates only when we change it)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.info("Turning on command switch %d (%s)", self.command_id, self.command_name)

        success = await self.client.execute_command(self.command_id, activate=True)
        if success:
            self._attr_is_on = True
            _LOGGER.info("Command switch %d (%s) turned on successfully", self.command_id, self.command_name)
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on command switch %d (%s)", self.command_id, self.command_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.info("Turning off command switch %d (%s)", self.command_id, self.command_name)

        success = await self.client.execute_command(self.command_id, activate=False)
        if success:
            self._attr_is_on = False
            _LOGGER.info("Command switch %d (%s) turned off successfully", self.command_id, self.command_name)
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off command switch %d (%s)", self.command_id, self.command_name)
