"""Binary sensors for Combivox Amica Web integration."""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base import CombivoxWebClient
from .const import DOMAIN, DATA_COORDINATOR, DATA_CONFIG
from .coordinator import CombivoxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up binary sensors from a config entry."""
    _LOGGER.info("Setting up binary sensors")

    # Get coordinator and client
    coordinator: CombivoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    client: CombivoxWebClient = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]

    # Get device info for HA
    device_info = client.get_device_info_for_ha()

    entities = []

    # Add zone sensors
    zones_config = client.get_zones_config()
    for zone_config in zones_config:
        zone_id = zone_config.get("zone_id")
        zone_name = zone_config.get("zone_name", f"Zone {zone_id}")

        entity = CombivoxZoneBinarySensor(
            zone_id=zone_id,
            zone_name=zone_name,
            coordinator=coordinator,
            device_info=device_info,
        )
        entities.append(entity)
        _LOGGER.debug("Added zone sensor: %s (ID: %d)", zone_name, zone_id)

    # Add area sensors
    areas_config = client.get_areas_config()
    for area_config in areas_config:
        area_id = area_config.get("area_id")
        area_name = area_config.get("area_name", f"Area {area_id}")

        entity = CombivoxAreaBinarySensor(
            area_id=area_id,
            area_name=area_name,
            coordinator=coordinator,
            device_info=device_info,
        )
        entities.append(entity)
        _LOGGER.debug("Added area sensor: %s (ID: %d)", area_name, area_id)

    _LOGGER.info("Adding %d binary sensors (%d zones, %d areas)",
                 len(entities), len(zones_config), len(areas_config))

    async_add_entities(entities, update_before_add=True)


class CombivoxZoneBinarySensor(BinarySensorEntity):
    """Binary sensor for a Combivox zone."""

    def __init__(self, zone_id: int, zone_name: str, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the zone sensor."""
        self.zone_id = zone_id
        self.zone_name = zone_name
        self.coordinator = coordinator

        # All zones are motion sensors
        self._attr_device_class = BinarySensorDeviceClass.MOTION
        self._attr_device_info = device_info

        self._attr_unique_id = f"combivox_zone_{zone_id}"
        self._attr_name = zone_name
        self._attr_has_entity_name = True

    @property
    def is_on(self) -> bool:
        """Return True if the zone is open (triggered)."""
        zones_data = (self.coordinator.data or {}).get("zones", {})
        zone_data = zones_data.get(self.zone_id, {})
        return zone_data.get("open", False)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        zones_data = (self.coordinator.data or {}).get("zones", {})
        zone_data = zones_data.get(self.zone_id, {})

        attrs = {
            "zone_id": self.zone_id,
            "alarm_memory": zone_data.get("alarm_memory", False),
            "included": zone_data.get("included", False),
        }

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()


class CombivoxAreaBinarySensor(BinarySensorEntity):
    """Binary sensor for a Combivox area."""

    def __init__(self, area_id: int, area_name: str, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the area sensor."""
        self.area_id = area_id
        self.area_name = area_name
        self.coordinator = coordinator

        # No device_class - use custom icon only for visual indication
        self._attr_device_info = device_info

        self._attr_unique_id = f"combivox_area_{area_id}"
        self._attr_name = area_name
        self._attr_has_entity_name = True

    @property
    def is_on(self) -> bool:
        """Return True if the area is armed."""
        areas_data = (self.coordinator.data or {}).get("areas", {})
        area_data = areas_data.get(self.area_id, {})
        status = area_data.get("status", "disarmed")
        return status == "armed"

    @property
    def icon(self) -> str:
        """Return dynamic icon based on armed state."""
        areas_data = (self.coordinator.data or {}).get("areas", {})
        area_data = areas_data.get(self.area_id, {})
        status = area_data.get("status", "disarmed")

        if status == "armed":
            return "mdi:shield-lock"   # Armed: shield locked
        else:
            return "mdi:shield-home"   # Disarmed: shield home

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        areas_data = (self.coordinator.data or {}).get("areas", {})
        area_data = areas_data.get(self.area_id, {})

        attrs = {
            "area_id": self.area_id,
            "status": area_data.get("status", "disarmed"),
        }

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()
