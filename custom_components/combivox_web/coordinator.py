"""Data update coordinator for Combivox Amica Web."""

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval

from .base import CombivoxWebClient
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class CombivoxDataUpdateCoordinator(DataUpdateCoordinator):
    """Unified data update coordinator for polling all panel data."""

    def __init__(self, hass: HomeAssistant, client: CombivoxWebClient, scan_interval: int = None):
        """Initialize coordinator."""
        self.client = client
        self._custom_interval = None
        self._custom_unsub = None
        self._is_polling = False
        self._consecutive_failures = 0  # Track consecutive failures
        self._max_consecutive_failures = 2  # Mark unavailable after 2 failures
        self._panel_unavailable = False  # Custom flag - more reliable than last_update_success

        if scan_interval is None:
            scan_interval = DEFAULT_SCAN_INTERVAL

        _LOGGER.debug("Initializing coordinator with scan_interval: %d seconds", scan_interval)

        # DON'T pass update_interval to parent - we'll manage our own timer
        super().__init__(
            hass,
            _LOGGER,
            name="Combivox Data",
            update_interval=None,  # Disable automatic polling
        )

        # Start our custom polling
        self._start_custom_polling(scan_interval)

        _LOGGER.debug("Coordinator initialized with custom polling every %s seconds", scan_interval)

    def _start_custom_polling(self, interval: int) -> None:
        """Start custom polling with specified interval."""
        # Cancel existing timer if any
        if self._custom_unsub:
            self._custom_unsub()
            self._custom_unsub = None

        self._custom_interval = interval

        # Create a new timer that calls _async_refresh (bypasses debouncer) every N seconds
        @callback
        def _refresh_callback(now):
            """Refresh callback."""
            # Use _async_refresh_log instead of async_refresh to bypass debouncer
            self.hass.async_create_task(self._async_refresh_log())

        self._custom_unsub = async_track_time_interval(
            self.hass,
            _refresh_callback,
            timedelta(seconds=interval)
        )

        _LOGGER.debug("Custom polling timer started - interval: %s seconds", interval)

    async def _async_refresh_log(self) -> None:
        """Refresh data with logging (bypasses debouncer)."""
        # If already polling, skip this update (our own debouncer)
        if self._is_polling:
            _LOGGER.debug("Already polling, skipping this refresh")
            return

        _LOGGER.debug("Starting refresh")
        try:
            await self._async_refresh()
        except Exception as err:
            _LOGGER.error("Error refreshing data: %s", err)
            raise

    async def update_scan_interval(self, scan_interval: int) -> None:
        """Update the polling interval and restart the refresh timer."""
        _LOGGER.debug("Changing scan interval from %s to %s seconds", self._custom_interval, scan_interval)

        # Restart custom polling with new interval
        self._start_custom_polling(scan_interval)

        # Do an immediate refresh
        await self.async_refresh()

        _LOGGER.debug("Scan interval updated to %s seconds", scan_interval)

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and cancel timers."""
        if self._custom_unsub:
            self._custom_unsub()
            self._custom_unsub = None
        await super().async_shutdown()

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch all data from the device with a single HTTP request."""
        # Prevent concurrent polls (avoid spam when panel is down)
        if self._is_polling:
            _LOGGER.debug("Already polling, skipping this update")
            return self.data if self.data else {"state": "unknown", "zones": {}, "areas": {}}

        self._is_polling = True
        try:
            status = await self.client.get_status()

            if status:
                # Success - reset failure counter and unavailable flag
                if self._panel_unavailable:
                    _LOGGER.info("Connection recovered - entities will become available")
                elif self._consecutive_failures > 0:
                    _LOGGER.debug("Connection recovered after %d failures", self._consecutive_failures)

                self._consecutive_failures = 0
                self._panel_unavailable = False

                zones = status.get("zones", {})
                areas = status.get("areas", {})

                _LOGGER.debug("Updated data: %d zones, %d areas, state=%s",
                             len(zones), len(areas), status.get("state", "unknown"))

                return status
            else:
                # Failure - increment counter
                self._consecutive_failures += 1
                _LOGGER.warning("No data received from panel (failure %d/%d)",
                               self._consecutive_failures, self._max_consecutive_failures)

                if self._consecutive_failures >= self._max_consecutive_failures:
                    # Mark as unavailable and raise exception
                    _LOGGER.error("Panel unavailable after %d consecutive failures - marking entities unavailable",
                                self._consecutive_failures)
                    self._panel_unavailable = True
                    from .exceptions import CombivoxConnectionError
                    raise CombivoxConnectionError(f"Panel unavailable after {self._consecutive_failures} consecutive failures")
                else:
                    # Return last known data but don't mark as unavailable yet
                    return self.data if self.data else {"state": "unknown", "zones": {}, "areas": {}}

        except CombivoxConnectionError:
            # Re-raise our connection error to mark entities unavailable
            raise
        except Exception as e:
            # Log error but don't raise - track consecutive failures instead
            self._consecutive_failures += 1
            _LOGGER.error("Error updating data (failure %d/%d): %s",
                        self._consecutive_failures, self._max_consecutive_failures, e)

            if self._consecutive_failures >= self._max_consecutive_failures:
                # Mark as unavailable and raise exception
                _LOGGER.error("Panel unavailable after %d consecutive failures - marking entities unavailable",
                            self._consecutive_failures)
                self._panel_unavailable = True
                from .exceptions import CombivoxConnectionError
                raise CombivoxConnectionError(f"Panel unavailable after {self._consecutive_failures} consecutive failures")
            else:
                return self.data if self.data else {"state": "unknown", "zones": {}, "areas": {}}

        finally:
            self._is_polling = False