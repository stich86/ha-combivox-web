"""Alarm control panel for Combivox Amica Web integration."""

import logging
import asyncio
from typing import Any, Dict, Optional, List

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base import CombivoxWebClient
from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    DATA_CONFIG,
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
    ALARM_HEX_TO_HA_STATE,
)
from .coordinator import CombivoxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up alarm control panel from a config entry."""
    _LOGGER.info("Setting up alarm control panel")

    # Get coordinator and client
    coordinator: CombivoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    client: CombivoxWebClient = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]

    # Get device info for HA
    device_info = client.get_device_info_for_ha()

    # Get area mappings from options (not data!)
    areas_away = entry.options.get(CONF_AREAS_AWAY, [])
    areas_home = entry.options.get(CONF_AREAS_HOME, [])
    areas_night = entry.options.get(CONF_AREAS_NIGHT, [])
    areas_disarm = entry.options.get(CONF_AREAS_DISARM, [])

    # Get macro mappings from options
    macro_away = entry.options.get(CONF_MACRO_AWAY, "")
    macro_home = entry.options.get(CONF_MACRO_HOME, "")
    macro_night = entry.options.get(CONF_MACRO_NIGHT, "")
    macro_disarm = entry.options.get(CONF_MACRO_DISARM, "")

    # Get arm mode mappings from options
    arm_mode_away = entry.options.get(CONF_ARM_MODE_AWAY, "normal")
    arm_mode_home = entry.options.get(CONF_ARM_MODE_HOME, "normal")
    arm_mode_night = entry.options.get(CONF_ARM_MODE_NIGHT, "normal")

    _LOGGER.info("Alarm panel loading - arm modes: away=%s, home=%s, night=%s",
                arm_mode_away, arm_mode_home, arm_mode_night)

    entity = CombivoxAlarmControlPanel(
        client=client,
        coordinator=coordinator,
        device_info=device_info,
        areas_away=areas_away,
        areas_home=areas_home,
        areas_night=areas_night,
        areas_disarm=areas_disarm,
        macro_away=macro_away,
        macro_home=macro_home,
        macro_night=macro_night,
        macro_disarm=macro_disarm,
        arm_mode_away=arm_mode_away,
        arm_mode_home=arm_mode_home,
        arm_mode_night=arm_mode_night,
    )

    async_add_entities([entity], update_before_add=True)

    # Store entity reference for dynamic updates
    hass.data[DOMAIN][entry.entry_id]["alarm_panel_entity"] = entity

    _LOGGER.info("Alarm control panel added")


class CombivoxAlarmControlPanel(AlarmControlPanelEntity):
    """Alarm control panel for Combivox."""

    def __init__(
        self,
        client: CombivoxWebClient,
        coordinator: CombivoxDataUpdateCoordinator,
        device_info: Dict[str, Any],
        areas_away: List[int],
        areas_home: List[int],
        areas_night: List[int],
        areas_disarm: List[int],
        macro_away: str = "",
        macro_home: str = "",
        macro_night: str = "",
        macro_disarm: str = "",
        arm_mode_away: str = "normal",
        arm_mode_home: str = "normal",
        arm_mode_night: str = "normal",
    ):
        """Initialize the alarm control panel."""
        self.client = client
        self.coordinator = coordinator

        # Store area mappings for each arm mode (NO DEFAULTS - use exactly what's configured)
        # Empty list = no areas configured for this mode
        self.areas_away = areas_away if areas_away else []
        self.areas_home = areas_home if areas_home else []
        self.areas_night = areas_night if areas_night else []
        self.areas_disarm = areas_disarm if areas_disarm else []

        # Store macro mappings for each arm/disarm action
        self.macro_away = macro_away
        self.macro_home = macro_home
        self.macro_night = macro_night
        self.macro_disarm = macro_disarm

        # Store arm mode for each arm action
        self.arm_mode_away = arm_mode_away
        self.arm_mode_home = arm_mode_home
        self.arm_mode_night = arm_mode_night

        self._attr_unique_id = "combivox_alarm_panel"
        self._attr_translation_key = "combivox_alarm_panel"
        self._attr_device_info = device_info
        self._attr_code_format = CodeFormat.NUMBER
        self._attr_supported_features = (
            AlarmControlPanelEntityFeature.ARM_HOME
            | AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.ARM_NIGHT
        )

        _LOGGER.debug("Alarm panel initialized - arm modes: away=%s, home=%s, night=%s",
                     self.arm_mode_away, self.arm_mode_home, self.arm_mode_night)

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

    def update_areas(self, areas_away: List[int], areas_home: List[int], areas_night: List[int], areas_disarm: List[int]) -> None:
        """Update the area mappings dynamically."""
        # NO DEFAULTS - use exactly what's configured
        self.areas_away = areas_away if areas_away else []
        self.areas_home = areas_home if areas_home else []
        self.areas_night = areas_night if areas_night else []
        self.areas_disarm = areas_disarm if areas_disarm else []
        _LOGGER.info("Alarm panel areas UPDATED - away: %s, home: %s, night: %s, disarm: %s",
                     self.areas_away or "(none)", self.areas_home or "(none)",
                     self.areas_night or "(none)", self.areas_disarm or "(none)")

    def update_macros(self, macro_away: str, macro_home: str, macro_night: str, macro_disarm: str) -> None:
        """Update the macro mappings dynamically."""
        self.macro_away = macro_away
        self.macro_home = macro_home
        self.macro_night = macro_night
        self.macro_disarm = macro_disarm
        _LOGGER.debug("Alarm panel macros updated - away: %s, home: %s, night: %s, disarm: %s",
                     self.macro_away or "(none)", self.macro_home or "(none)",
                     self.macro_night or "(none)", self.macro_disarm or "(none)")

    def update_arm_modes(self, arm_mode_away: str, arm_mode_home: str, arm_mode_night: str) -> None:
        """Update the arm mode configurations dynamically."""
        self.arm_mode_away = arm_mode_away
        self.arm_mode_home = arm_mode_home
        self.arm_mode_night = arm_mode_night
        _LOGGER.debug("Alarm panel arm modes updated - away: %s, home: %s, night: %s",
                     self.arm_mode_away, self.arm_mode_home, self.arm_mode_night)

    @property
    def state(self) -> str:
        """Return the state of the alarm."""
        # First check alarm state (triggered/pending/arming)
        alarm_hex = (self.coordinator.data or {}).get("alarm_hex", "")

        # Check priority alarm states from hex mapping
        if alarm_hex in ALARM_HEX_TO_HA_STATE:
            return ALARM_HEX_TO_HA_STATE[alarm_hex]

        # Determine mode from armed areas
        mode = self._determine_current_mode()

        # If no area armed → disarmed
        if mode == "unknown":
            return "disarmed"

        # Return armed_{mode} state
        return f"armed_{mode}"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        armed_areas = (self.coordinator.data or {}).get("armed_areas", [])
        current_mode = self._determine_current_mode()

        attrs = {
            "armed_areas": armed_areas,
            "status_hex": (self.coordinator.data or {}).get("status_hex", ""),
            "alarm_hex": (self.coordinator.data or {}).get("alarm_hex", ""),
            "alarm_state": (self.coordinator.data or {}).get("alarm_state", ""),
            "areas_away_mode": self.areas_away,
            "areas_home_mode": self.areas_home,
            "areas_night_mode": self.areas_night,
            "areas_disarm_mode": self.areas_disarm,
            "arm_mode_away": self.arm_mode_away,
            "arm_mode_home": self.arm_mode_home,
            "arm_mode_night": self.arm_mode_night,
            "current_mode": current_mode,
        }
        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    def _determine_current_mode(self) -> str:
        """Determine current mode from armed areas.

        Returns:
            Mode string: "away", "home", "night", or "custom_bypass"
        """
        armed_areas = (self.coordinator.data or {}).get("armed_areas", [])

        # If no area armed → no mode
        if not armed_areas:
            return "unknown"

        # Compare with configuration to determine mode
        if set(armed_areas) == set(self.areas_away):
            return "away"
        elif set(armed_areas) == set(self.areas_home):
            return "home"
        elif set(armed_areas) == set(self.areas_night):
            return "night"
        else:
            # Non-standard configuration
            return "custom_bypass"

    async def _execute_macro_if_configured(self, macro_id: str) -> bool:
        """Execute a macro if configured."""
        if not macro_id:
            return False

        try:
            # Convert macro_id to int
            macro_id_int = int(macro_id)

            # Get macros config from client
            macros_config = self.client.get_macros_config()

            # Find macro name for logging
            macro_name = "Unknown"
            for macro in macros_config:
                if macro.get("macro_id") == macro_id_int:
                    macro_name = macro.get("macro_name", "Unknown")
                    break

            _LOGGER.info("Executing macro %s: %s", macro_id, macro_name)

            # Execute the macro
            success = await self.client.execute_macro(macro_id_int, macro_name)

            if success:
                _LOGGER.info("Macro %s (%s) executed successfully", macro_id, macro_name)
            else:
                _LOGGER.error("Failed to execute macro %s (%s)", macro_id, macro_name)

            return success

        except Exception as e:
            _LOGGER.error("Error executing macro %s: %s", macro_id, e)
            return False

    def _determine_arm_strategy(self, macro: str, areas: List[int], mode: str) -> Dict[str, Any]:
        """Determine arm strategy based on macro/areas configuration.

        Args:
            macro: Macro ID string
            areas: List of area IDs
            mode: Arm mode (away/home/night) for logging

        Returns:
            Dict with 'type' ('areas' or 'macro') and 'data' (areas list or macro ID)
        """
        if macro and areas:
            _LOGGER.warning("Arm %s - BOTH scenario (macro=%s) and areas (%s) configured. Using AREAS (priority).",
                          mode, macro, areas)
            return {"type": "areas", "data": areas}
        elif macro:
            return {"type": "macro", "data": macro}
        else:
            return {"type": "areas", "data": areas}

    async def _execute_arm_strategy(self, strategy: Dict[str, Any], mode: str, arm_mode: str) -> bool:
        """Execute arm strategy and refresh state.

        Args:
            strategy: Dict from _determine_arm_strategy with 'type' and 'data'
            mode: Arm mode (away/home/night)
            arm_mode: Arm mode type (normal/immediate/forced)

        Returns:
            bool: True if successful, False otherwise
        """
        if strategy["type"] == "areas":
            areas = strategy["data"]
            _LOGGER.info("Arm %s - areas: %s, mode: %s", mode, areas, arm_mode)
            success = await self.client.arm_areas(areas, mode=mode, arm_mode=arm_mode)
        else:  # macro
            macro = strategy["data"]
            _LOGGER.info("Arm %s - using scenario (macro): %s", mode, macro)
            success = await self._execute_macro_if_configured(macro)

        if success:
            # Wait for command to take effect
            await asyncio.sleep(2)
            # Refresh coordinator to get new state
            await self.coordinator.async_refresh()
        else:
            _LOGGER.error("Failed to arm %s", mode)

        return success

    async def _arm_with_mode(self, mode: str, areas: List[int], macro_id: str, arm_mode: str) -> None:
        """Generic arm method with macro/areas priority logic.

        Args:
            mode: Arm mode (away/home/night)
            areas: List of area IDs for this mode
            macro_id: Macro ID for this mode
            arm_mode: Arm mode type (normal/immediate/forced)
        """
        _LOGGER.debug("Arm %s - macro_%s='%s', areas_%s=%s, arm_mode=%s",
                     mode, mode, macro_id, mode, areas, arm_mode)

        # Determine strategy (areas vs macro)
        strategy = self._determine_arm_strategy(macro_id, areas, mode)

        # Check if we have something to execute
        if strategy["type"] == "areas" and not strategy["data"]:
            # No areas and no macro configured
            _LOGGER.error("Arm %s - FAILED: No scenario or areas configured for %s mode! "
                         "Please configure at least one in integration options.",
                         mode.capitalize(), mode.capitalize())
            return

        # Execute the determined strategy
        await self._execute_arm_strategy(strategy, mode, arm_mode)

    async def async_alarm_arm_away(self, code: Optional[str] = None) -> None:
        """Send arm away command."""
        await self._arm_with_mode("away", self.areas_away, self.macro_away, self.arm_mode_away)

    async def async_alarm_arm_home(self, code: Optional[str] = None) -> None:
        """Send arm home command."""
        await self._arm_with_mode("home", self.areas_home, self.macro_home, self.arm_mode_home)

    async def async_alarm_arm_night(self, code: Optional[str] = None) -> None:
        """Send arm night command."""
        await self._arm_with_mode("night", self.areas_night, self.macro_night, self.arm_mode_night)

    async def async_alarm_disarm(self, code: Optional[str] = None) -> None:
        """Send disarm command."""
        _LOGGER.debug("Disarm called - macro_disarm='%s', areas_disarm=%s (type: %s)",
                     self.macro_disarm, self.areas_disarm, type(self.areas_disarm))

        # Use same strategy as arm: macro priority, then areas
        if self.macro_disarm and self.areas_disarm:
            _LOGGER.warning("Disarm - BOTH scenario (macro=%s) and areas (%s) configured. Using AREAS (priority).",
                          self.macro_disarm, self.areas_disarm)

        if self.macro_disarm and not self.areas_disarm:
            # Only macro configured, use it
            _LOGGER.info("Disarm - using scenario (macro): %s", self.macro_disarm)
            success = await self._execute_macro_if_configured(self.macro_disarm)
        elif self.areas_disarm:
            # Areas configured, disarm only selected areas
            _LOGGER.info("Disarm areas: %s", self.areas_disarm)
            success = await self.client.disarm_areas(self.areas_disarm)
        else:
            # Neither macro nor areas configured, disarm all areas as fallback
            areas_config = self.client.get_areas_config()
            all_areas = [area["area_id"] for area in areas_config] if areas_config else list(range(1, 9))
            _LOGGER.info("Disarm all areas (no areas configured): %s", all_areas)
            success = await self.client.disarm_areas(all_areas)

        if success:
            # Wait for command to take effect
            await asyncio.sleep(2)
            # Refresh coordinator to get new state
            await self.coordinator.async_refresh()
        else:
            _LOGGER.error("Failed to disarm")
