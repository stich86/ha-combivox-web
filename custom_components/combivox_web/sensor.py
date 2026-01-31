"""Sensors for Combivox Amica Web integration."""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base import CombivoxWebClient
from .const import (
    DOMAIN, DATA_COORDINATOR, DATA_CONFIG,
    GSM_STATUS_HEX_TO_HA_STATE,
    GSM_OPERATOR_HEX_TO_NAME
)
from .coordinator import CombivoxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up sensors from a config entry."""
    _LOGGER.info("Setting up system sensors")

    # Get coordinator and client
    coordinator: CombivoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    client: CombivoxWebClient = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]

    # Get device info for HA
    device_info = client.get_device_info_for_ha()

    entities = []

    # Add system status sensor
    entities.append(CombivoxSystemStatusSensor(coordinator, device_info))

    # Add device info sensors
    if device_info:
        entities.append(CombivoxModelSensor(coordinator, device_info))
        entities.append(CombivoxFirmwareSensor(coordinator, device_info))
        entities.append(CombivoxWebVersionSensor(coordinator, device_info))
        entities.append(CombivoxDateTimeSensor(coordinator, device_info))

    # Add GSM sensors
    entities.append(CombivoxGSMStatusSensor(coordinator, device_info))
    entities.append(CombivoxGSMOperatorSensor(coordinator, device_info))
    entities.append(CombivoxGSMSignalSensor(coordinator, device_info))

    _LOGGER.info("Adding %d system sensors", len(entities))

    async_add_entities(entities, update_before_add=True)


class CombivoxSystemStatusSensor(SensorEntity):
    """Sensor for system alarm status."""

    def __init__(self, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the system status sensor."""
        self.coordinator = coordinator

        self._attr_unique_id = "combivox_system_status"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [
            "disarmed",
            "armed",
            "disarmed_gsm_excluded",
            "arming",
            "armed_with_delay",
            "pending",
            "triggered",
            "triggered_gsm_excluded",
            "unknown"
        ]
        self._attr_translation_key = "combivox_system_status"

    @property
    def native_value(self) -> str:
        """Return the system status."""
        return (self.coordinator.data or {}).get("state", "unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "status_hex": (self.coordinator.data or {}).get("status_hex", ""),
            "armed_areas": (self.coordinator.data or {}).get("armed_areas", []),
        }
        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()


class CombivoxModelSensor(SensorEntity):
    """Sensor for device model."""

    def __init__(self, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the model sensor."""
        self.coordinator = coordinator
        self._static_device_info = device_info  # Store static device info

        self._attr_unique_id = "combivox_model"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "combivox_model"

    @property
    def native_value(self) -> str:
        """Return the device model."""
        # Get model from static device info (parsed from /system/index.html during setup)
        return self._static_device_info.get("model", "Unknown")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable


class CombivoxFirmwareSensor(SensorEntity):
    """Sensor for device firmware version."""

    def __init__(self, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the firmware sensor."""
        self.coordinator = coordinator

        self._attr_unique_id = "combivox_firmware"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "combivox_firmware"

    @property
    def native_value(self) -> str:
        """Return the device firmware version."""
        # TODO: Parse from /system/index.html
        # For now return a placeholder
        return "Unknown (TODO: parse from /system/index.html)"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable


class CombivoxWebVersionSensor(SensorEntity):
    """Sensor for Web interface version."""

    def __init__(self, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the web version sensor."""
        self.coordinator = coordinator

        self._attr_unique_id = "combivox_web_version"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:web"
        self._attr_translation_key = "combivox_web_version"

    @property
    def native_value(self) -> str:
        """Return the web interface version."""
        # TODO: Parse from /system/index.html
        # For now return a placeholder
        return "Unknown (TODO: parse from /system/index.html)"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable


class CombivoxDateTimeSensor(SensorEntity):
    """Sensor for device date and time."""

    def __init__(self, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the datetime sensor."""
        self.coordinator = coordinator

        self._attr_unique_id = "combivox_datetime"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        # No device class - we'll show formatted string
        self._attr_icon = "mdi:clock"
        self._attr_translation_key = "combivox_datetime"

    @property
    def native_value(self) -> str | None:
        """Return the device date and time."""
        # Read from coordinator that has already done the parsing
        system_data = self.coordinator.data

        dt = system_data.get("datetime")

        if dt is None:
            return None

        # If it's a datetime object, format it as string
        if hasattr(dt, 'strftime'):
            # Format in readable way: DD/MM/YYYY HH:MM:SS
            return dt.strftime("%d/%m/%Y %H:%M:%S")

        # Otherwise return the value as is (already string?)
        return str(dt) if dt else None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable


class CombivoxGSMStatusSensor(SensorEntity):
    """Sensor for GSM status."""

    def __init__(self, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the GSM status sensor."""
        self.coordinator = coordinator

        self._attr_unique_id = "combivox_gsm_status"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:sim"
        self._attr_translation_key = "combivox_gsm_status"

    @property
    def native_value(self) -> str:
        """Return the GSM status."""
        system_data = self.coordinator.data or {}
        gsm_data = system_data.get("gsm", {})

        if not gsm_data:
            return "unknown"

        status_hex = gsm_data.get("status_hex", "").upper()
        return GSM_STATUS_HEX_TO_HA_STATE.get(status_hex, "unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        system_data = self.coordinator.data or {}
        gsm_data = system_data.get("gsm", {})
        return {
            "status_hex": gsm_data.get("status_hex", "")
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable


class CombivoxGSMOperatorSensor(SensorEntity):
    """Sensor for GSM operator."""

    def __init__(self, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the GSM operator sensor."""
        self.coordinator = coordinator

        self._attr_unique_id = "combivox_gsm_operator"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:signal"
        self._attr_translation_key = "combivox_gsm_operator"

    @property
    def native_value(self) -> str:
        """Return the GSM operator."""
        system_data = self.coordinator.data or {}
        gsm_data = system_data.get("gsm", {})

        if not gsm_data:
            return "unknown"

        operator_hex = gsm_data.get("operator_hex", "").upper()
        return GSM_OPERATOR_HEX_TO_NAME.get(operator_hex, "unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        system_data = self.coordinator.data or {}
        gsm_data = system_data.get("gsm", {})
        return {
            "operator_hex": gsm_data.get("operator_hex", "")
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable


class CombivoxGSMSignalSensor(SensorEntity):
    """Sensor for GSM signal strength."""

    def __init__(self, coordinator: CombivoxDataUpdateCoordinator, device_info: Dict[str, Any]):
        """Initialize the GSM signal sensor."""
        self.coordinator = coordinator

        self._attr_unique_id = "combivox_gsm_signal"
        self._attr_has_entity_name = True
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:signal"
        self._attr_translation_key = "combivox_gsm_signal"

    @property
    def native_value(self) -> int | None:
        """Return the GSM signal strength in percentage."""
        system_data = self.coordinator.data or {}
        gsm_data = system_data.get("gsm", {})

        if not gsm_data:
            return None

        return gsm_data.get("signal_percent")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        system_data = self.coordinator.data or {}
        gsm_data = system_data.get("gsm", {})
        return {
            "signal_bars": gsm_data.get("signal_bars", 0)
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self.coordinator._panel_unavailable
