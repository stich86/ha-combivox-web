"""Services for Combivox Amica Web integration."""

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, DATA_CONFIG, DATA_COORDINATOR

_LOGGER = logging.getLogger(__name__)

# Service schemas
SERVICE_ARM_AREAS_SCHEMA = vol.Schema({
    vol.Required("areas"): vol.All(cv.ensure_list, [vol.In([1, 2, 3, 4, 5, 6, 7, 8])]),
    vol.Optional("mode", default="away"): vol.In(["away", "home", "night"]),
    vol.Optional("force", default=False): bool,
})


SERVICE_DISARM_AREAS_SCHEMA = vol.Schema({
    vol.Optional("areas", default=[1, 2, 3, 4, 5, 6, 7, 8]): vol.All(cv.ensure_list, [vol.In([1, 2, 3, 4, 5, 6, 7, 8])]),
})


async def setup_services(hass: HomeAssistant) -> None:
    """Set up the Combivox services."""

    async def arm_areas_handler(call: ServiceCall) -> ServiceResponse:
        """Handle arm areas service call."""
        areas: List[int] = call.data.get("areas", [])
        mode: str = call.data.get("mode", "away")
        force: bool = call.data.get("force", False)

        _LOGGER.info("Service arm_areas called: areas=%s, mode=%s, force=%s", areas, mode, force)

        # Get client from first entry
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            _LOGGER.error("No config entries found")
            return {"success": False}

        entry = next(iter(entries))
        client = hass.data[DOMAIN][entry.entry_id][DATA_CONFIG]

        # Call async arm_areas method
        success = await client.arm_areas(areas, mode=mode, force=force)

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
        areas: List[int] = call.data.get("areas", [1, 2, 3, 4, 5, 6, 7, 8])

        _LOGGER.info("Service disarm_areas called: areas=%s", areas)

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
