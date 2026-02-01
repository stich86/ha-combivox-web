"""Services for Combivox Amica Web integration."""

import logging
from typing import Dict, List, Union

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, DATA_CONFIG, DATA_COORDINATOR

_LOGGER = logging.getLogger(__name__)

# Service schemas - accept both strings and ints for areas
SERVICE_ARM_AREAS_SCHEMA = vol.Schema({
    vol.Required("areas"): vol.All(cv.ensure_list),
    vol.Optional("arm_mode", default="normal"): vol.In(["normal", "immediate", "forced"]),
})

SERVICE_DISARM_AREAS_SCHEMA = vol.Schema({
    vol.Optional("areas", default=[1, 2, 3, 4, 5, 6, 7, 8]): vol.All(cv.ensure_list),
})


def _convert_areas_to_ints(areas: List[Union[str, int]]) -> List[int]:
    """Convert area values to integers (handles both string and int inputs)."""
    result = []
    for area in areas:
        if isinstance(area, str):
            # Handle comma-separated string (e.g., "1,2,3,4,5,6,7,8")
            if ',' in area:
                result.extend([int(x.strip()) for x in area.split(',')])
            else:
                result.append(int(area))
        elif isinstance(area, int):
            result.append(area)
        else:
            # Try to convert to int
            result.append(int(area))
    return result


async def setup_services(hass: HomeAssistant) -> None:
    """Set up the Combivox services."""

    async def arm_areas_handler(call: ServiceCall) -> ServiceResponse:
        """Handle arm areas service call."""
        areas_input: List[Union[str, int]] = call.data.get("areas", [])
        arm_mode: str = call.data.get("arm_mode", "normal")

        # Convert areas to integers (handles both string and int inputs from UI)
        areas = _convert_areas_to_ints(areas_input)

        _LOGGER.info("Service arm_areas called: areas=%s, arm_mode=%s", areas, arm_mode)

        # Get client from first entry
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            _LOGGER.error("No config entries found")
            return {"success": False}

        entry = next(iter(entries))
        client = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]

        # Call async arm_areas method
        # mode parameter is only used for logging, arm_mode determines the actual behavior
        success = await client.arm_areas(areas, mode="service", arm_mode=arm_mode)

        if success:
            # Refresh coordinator
            coordinator = hass.data[DOMAIN][entry.entry_id].get(DATA_COORDINATOR)
            if coordinator:
                await coordinator.async_request_refresh()

            _LOGGER.info("Service arm_areas completed successfully")
            return {"success": True}
        else:
            _LOGGER.error("Service arm_areas failed")
            return {"success": False}

    async def disarm_areas_handler(call: ServiceCall) -> ServiceResponse:
        """Handle disarm areas service call."""
        areas_input = call.data.get("areas")

        # Handle different input formats
        if areas_input is None:
            # No areas provided - disarm all
            areas = [1, 2, 3, 4, 5, 6, 7, 8]
        elif isinstance(areas_input, str):
            # String input - could be "1,2,3" or just "2"
            if ',' in areas_input:
                areas = [int(x.strip()) for x in areas_input.split(',')]
            else:
                areas = [int(areas_input)]
        elif isinstance(areas_input, list):
            if len(areas_input) == 0:
                # Empty list - disarm all
                areas = [1, 2, 3, 4, 5, 6, 7, 8]
            else:
                # List input - convert to ints
                areas = _convert_areas_to_ints(areas_input)
        else:
            # Fallback
            areas = [1, 2, 3, 4, 5, 6, 7, 8]

        _LOGGER.info("Service disarm_areas called: areas=%s (input=%s)", areas, areas_input)

        # Get client from first entry
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            _LOGGER.error("No config entries found")
            return {"success": False}

        entry = next(iter(entries))
        client = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]

        # Call async disarm_areas method
        success = await client.disarm_areas(areas)

        if success:
            # Refresh coordinator
            coordinator = hass.data[DOMAIN][entry.entry_id].get(DATA_COORDINATOR)
            if coordinator:
                await coordinator.async_request_refresh()

            _LOGGER.info("Service disarm_areas completed successfully")
            return {"success": True}
        else:
            _LOGGER.error("Service disarm_areas failed")
            return {"success": False}

    # Register services
    hass.services.async_register(
        DOMAIN,
        "arm_areas",
        arm_areas_handler,
        schema=SERVICE_ARM_AREAS_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        "disarm_areas",
        disarm_areas_handler,
        schema=SERVICE_DISARM_AREAS_SCHEMA
    )

    _LOGGER.info("Combivox services registered")
