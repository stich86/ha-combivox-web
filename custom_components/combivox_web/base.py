"""Base client for Combivox Amica Web integration."""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Any

import aiohttp

from .auth import CombivoxAuth
from .const import (
    STATUS_URL,
    LABELZONE_URL,
    LABELAREA_URL,
    INSAREA_URL,
    NUMMACRO_URL,
    EXECCHANGEIMP_URL,
    CONF_IP_ADDRESS,
    CONF_PORT,
    CONF_CODE,
    PERMMANUAL,
    MODEL_PATTERN,
    VERSION_PATTERN,
    SERIAL_NUMBER_PATTERN,
    FIRMWARE_FULL_PATTERN,
    FIRMWARE_FALLBACK_PATTERN,
    AMICAWEB_VERSION_PATTERN,
    MACRO_SUCCESS_CODE,
)
from .xml_parser import CombivoxXMLParser

_LOGGER = logging.getLogger(__name__)


class CombivoxWebClient:
    """HTTP client for Combivox Amica."""

    def __init__(
        self,
        ip_address: str,
        code: str,
        port: int = 80,
        config_file_path: Optional[str] = None,
        timeout: int = 10,
        tech_code: Optional[str] = None
    ):
        """
        Initialize the client.

        Args:
            ip_address: Panel IP address
            code: User code
            port: HTTP port
            config_file_path: JSON config file path
            timeout: HTTP request timeout
            tech_code: Technical code for system info access
        """
        self.ip_address = ip_address
        self.code = code
        self.port = port
        self.timeout = timeout
        self.tech_code = tech_code or "000000"
        self.base_url = f"http://{ip_address}:{port}"

        # Config file path
        self._config_file_path = config_file_path

        # Authentication
        self._auth = CombivoxAuth(ip_address, code, port, timeout)

        # XML Parser
        self._parser = CombivoxXMLParser()

        # Data cache
        self._zones_config: List[Dict[str, Any]] = []
        self._areas_config: List[Dict[str, Any]] = []
        self._area_name_map: Dict[int, str] = {}  # Cache for area_id -> area_name lookup
        self._macros_config: List[Dict[str, Any]] = []
        self._zone_ids: List[int] = []  # Active zone IDs from numZoneProg.xml
        self._device_info: Optional[Dict[str, Any]] = None

    def is_config_loaded(self) -> bool:
        """
        Check if configuration (zones/areas/macros) has been loaded.

        Returns:
            True if at least one of zones, areas, or macros config is loaded
        """
        return bool(self._zones_config or self._areas_config or self._macros_config)

    async def connect(self) -> bool:
        """
        Connect to the panel and download configuration.

        Returns:
            True if connection successful OR if cached configuration is available
        """
        try:
            _LOGGER.info("Connecting to Combivox panel at %s:%s", self.ip_address, self.port)

            if not await self._authenticate_and_download_config():
                return False

            # Try to fetch system info and initial status, but don't fail if offline
            # (we might have cached config)
            try:
                await self._fetch_system_info()
            except Exception as e:
                _LOGGER.warning("Could not fetch system info (panel may be offline): %s", e)

            try:
                await self._fetch_initial_status()
            except Exception as e:
                _LOGGER.warning("Could not fetch initial status (panel may be offline): %s", e)

            # If we have config (cached or fresh), connection is successful enough
            return self.is_config_loaded()

        except Exception as e:
            _LOGGER.error("Connection failed: %s", e)
            # Even on exception, check if we have cached config
            return self.is_config_loaded()

    async def _authenticate_and_download_config(self) -> bool:
        """
        Authenticate and download zones/areas/macros configuration.

        This method:
        1. Loads config from file if path provided
        2. Authenticates with the panel
        3. Downloads zones and areas configuration
        4. Downloads macros configuration
        5. Saves configuration to file if path provided

        Returns:
            True if authentication and config download successful, or if cached config is available
        """
        # Try to load config from file first
        has_cached_config = False
        if self._config_file_path:
            if await self._load_config_from_file():
                has_cached_config = bool(self._zones_config or self._areas_config or self._macros_config)
                if has_cached_config:
                    _LOGGER.info("Loaded cached configuration: %d zones, %d areas, %d macros",
                               len(self._zones_config), len(self._areas_config), len(self._macros_config))

        # Authenticate and download labels
        if not await self._auth.authenticate():
            _LOGGER.warning("Authentication failed - panel may be offline")
            # If we have cached config, we can still work
            return has_cached_config

        # Download zones and areas configuration from labelProgStato.xml (much cleaner!)
        prog_state = await self._download_prog_state_config()
        if prog_state:
            self._zones_config = prog_state.get("zones", [])
            self._zone_ids = [z["zone_id"] for z in self._zones_config]
            self._areas_config = prog_state.get("areas", [])
            self._area_name_map = {area["area_id"]: area["area_name"] for area in self._areas_config}
            _LOGGER.info("Loaded configuration: %d zones, %d areas",
                       len(self._zones_config), len(self._areas_config))

        # Download macros configuration (scenarios)
        macros_config = await self._download_macros_config()
        if macros_config:
            self._macros_config = macros_config
            _LOGGER.info("Loaded %d macros (scenarios)", len(self._macros_config))

        # Save to file if path provided
        if self._config_file_path and (prog_state or macros_config):
            await self._save_config_to_file()

        return True

    async def _fetch_system_info(self) -> None:
        """
        Fetch system information (firmware, model).

        Updates the _device_info attribute with model, firmware versions,
        and other system details from the panel.
        """
        system_info = await self._fetch_system_info_internal()
        if system_info:
            self._device_info = system_info
            _LOGGER.info("System info fetched: model=%s", system_info.get("model"))

    async def _fetch_initial_status(self) -> None:
        """
        Fetch initial alarm status.

        Gets the current device status and merges it with device info,
        adding IP address, port, and current state.
        """
        status = await self.get_status()
        if status:
            # Merge system_info with status info
            if not self._device_info:
                self._device_info = {}

            self._device_info.update({
                "ip_address": self.ip_address,
                "port": self.port,
                "state": status.get("state", "unknown")
            })

            _LOGGER.debug("Connected: model=%s, state=%s",
                       self._device_info.get("model", "Amica 64 GSM"),
                       self._device_info.get("state"))

    async def _download_prog_state_config(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """
        Download zones and areas configuration from labelProgStato.xml.

        This file contains ALL names in one place, much cleaner!

        NOTE: We must first trigger the XML generation by calling reqProg.cgi?req=255
        and waiting a couple of seconds for the file to be populated.

        Returns:
            Dict with {"zones": [...], "areas": [...]} or None if error
        """
        try:
            if not self._auth.is_authenticated():
                _LOGGER.error("Not authenticated, cannot download configuration")
                return None

            session = self._auth.get_session()
            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            # Step 1: Trigger data population (id=9 for general data)
            # This is required to populate the data before downloading
            trigger_url = f"{self.base_url}/reqProg.cgi?id=9"

            # Add Referer header as required by the panel
            headers_with_referer = headers.copy()
            headers_with_referer["Referer"] = f"{self.base_url}/index.htm?id=6"

            _LOGGER.debug("Triggering data population: URL=%s, Referer=%s",
                         trigger_url, headers_with_referer.get("Referer"))

            try:
                async with session.get(trigger_url, headers=headers_with_referer, timeout=self.timeout) as response:
                    if response.status == 200:
                        _LOGGER.debug("Data population triggered successfully")
                    else:
                        _LOGGER.warning("Trigger request returned status %d (continuing anyway)", response.status)
            except Exception as e:
                _LOGGER.warning("Failed to trigger data population: %s (continuing anyway)", e)

            # Step 2: Wait 2 seconds for data to be populated
            await asyncio.sleep(2)

            # Step 3: Download the actual XML file
            url = f"{self.base_url}/labelProgStato.xml"
            _LOGGER.debug("Downloading labelProgStato.xml: URL=%s, cookie=%s",
                         url, cookie)

            # Try multiple times to download (panel takes time to respond)
            max_retries = 5
            text = None

            for attempt in range(1, max_retries + 1):
                _LOGGER.debug("Downloading labelProgStato.xml (attempt %d/%d)", attempt, max_retries)

                async with session.get(url, headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        text = await response.text()
                        _LOGGER.info("Downloaded labelProgStato.xml successfully on attempt %d (%d bytes)", attempt, len(text))
                        break
                    else:
                        _LOGGER.warning("Attempt %d failed: status %d", attempt, response.status)
                        if attempt < max_retries:
                            await asyncio.sleep(1)  # Wait 1 second between retries

            if text is None:
                _LOGGER.error("Failed to download labelProgStato.xml after %d attempts", max_retries)
                return None

            _LOGGER.debug("labelProgStato.xml content (first 500 chars): %s", text[:500])

            # Parse zones and areas from XML file
            prog_state = self._parser.parse_prog_state_labels(text)

            if prog_state and (prog_state.get("zones") or prog_state.get("areas")):
                return prog_state
            else:
                _LOGGER.warning("No zones or areas found in labelProgStato.xml")
                return None

        except Exception as e:
            _LOGGER.error("Error downloading labelProgStato.xml configuration: %s", e)
            return None

    async def _download_macros_config(self) -> Optional[List[Dict[str, Any]]]:
        """
        Download macros (scenarios) configuration.

        Process:
        1. GET numMacro.xml to get macro IDs
        2. GET with payload comandi=id1;id2;etc to get macro labels
        3. Parse labels and return list of macros

        Returns:
            List of macro configs: [{"macro_id": 1, "macro_name": "Uscita"}, ...]
        """
        try:
            if not self._auth.is_authenticated():
                _LOGGER.error("Not authenticated, cannot download macros configuration")
                return None

            session = self._auth.get_session()
            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            # Step 1: Download numMacro.xml to get macro IDs
            url = f"{self.base_url}{NUMMACRO_URL}"
            _LOGGER.debug("Downloading numMacro.xml: URL=%s", url)

            async with session.get(url, headers=headers, timeout=self.timeout) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to download numMacro.xml: status %d", response.status)
                    return None

                text = await response.text()
                _LOGGER.debug("Downloaded numMacro.xml successfully (%d bytes)", len(text))

            # Parse macro IDs
            macro_ids = self._parser.parse_macro_ids(text)
            if not macro_ids:
                _LOGGER.info("No macros found in numMacro.xml")
                return []

            _LOGGER.debug("Found %d macro IDs: %s", len(macro_ids), macro_ids)

            # Step 2: Download macro labels using the IDs
            # Build comandi parameter with macro IDs
            comandi_param = ";".join(str(m_id) for m_id in macro_ids) + ";"
            labels_url = f"{self.base_url}/labelMacro.xml"

            # Build POST payload
            payload = f"comandi={comandi_param}"

            # Add Referer header as required by the panel
            headers_with_referer = headers.copy()
            headers_with_referer["Referer"] = f"{self.base_url}/index.htm?id=2"

            # TEMPORARY TEST: Try multiple times to download labels (panel takes time to respond)
            max_retries = 10
            text = None

            for attempt in range(1, max_retries + 1):
                _LOGGER.debug("Downloading macro labels (attempt %d/%d): URL=%s, Referer=%s, cookie=%s, payload=%s",
                             attempt, max_retries, labels_url, headers_with_referer.get("Referer"),
                             cookie, payload)

                async with session.post(labels_url, headers=headers_with_referer, data=payload, timeout=self.timeout) as response:
                    if response.status == 200:
                        text = await response.text()
                        _LOGGER.info("Downloaded macro labels successfully on attempt %d (%d bytes)", attempt, len(text))
                        break
                    else:
                        _LOGGER.warning("Attempt %d failed: status %d", attempt, response.status)
                        if attempt < max_retries:
                            await asyncio.sleep(1)  # Wait 1 second between retries

            if text is None:
                _LOGGER.warning("Failed to download macro labels after %d attempts (using IDs only)", max_retries)
                # Return macros without names
                return [{"macro_id": m_id, "macro_name": f"Macro {m_id}"} for m_id in macro_ids]

            _LOGGER.debug("Macro labels downloaded successfully (%d bytes)", len(text))

            # Step 3: Parse macro labels
            macros = self._parser.parse_macro_labels(text, macro_ids)

            if macros:
                _LOGGER.debug("Parsed %d macro labels", len(macros))
                return macros
            else:
                _LOGGER.warning("Failed to parse macro labels, using IDs only")
                return [{"macro_id": m_id, "macro_name": f"Macro {m_id}"} for m_id in macro_ids]

        except Exception as e:
            _LOGGER.error("Error downloading macros configuration: %s", e)
            return None

    async def _load_config_from_file(self) -> bool:
        """Load zones, areas and macros configuration from JSON file."""
        try:
            if not self._config_file_path or not os.path.exists(self._config_file_path):
                return False

            import asyncio
            loop = asyncio.get_event_loop()
            config = await loop.run_in_executor(None, lambda: json.load(open(self._config_file_path, 'r', encoding='utf-8')))

            if 'zones' in config:
                self._zones_config = config['zones']
                _LOGGER.info("Loaded %d zones from cache file", len(self._zones_config))

            if 'areas' in config:
                self._areas_config = config['areas']
                self._area_name_map = {area["area_id"]: area["area_name"] for area in self._areas_config}
                _LOGGER.info("Loaded %d areas from cache file", len(self._areas_config))

            if 'macros' in config:
                self._macros_config = config['macros']
                _LOGGER.info("Loaded %d macros from cache file", len(self._macros_config))

            return True

        except Exception as e:
            _LOGGER.warning("Failed to load config from file: %s", e)
            return False

    async def _save_config_to_file(self) -> bool:
        """Save zones, areas and macros configuration to JSON file."""
        try:
            if not self._config_file_path:
                return False

            # Ensure directory exists
            os.makedirs(os.path.dirname(self._config_file_path), exist_ok=True)

            config = {
                "zones": self._zones_config,
                "areas": self._areas_config,
                "macros": self._macros_config,
            }

            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: json.dump(config, open(self._config_file_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2))

            _LOGGER.debug("Saved configuration to cache file: %s", self._config_file_path)
            return True

        except Exception as e:
            _LOGGER.error("Failed to save configuration to file: %s", e)
            return False

    async def get_status(self, retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """
        Get the current panel status with automatic retry and reauthentication.

        Args:
            retry_count: Current retry attempt (used internally for recursion)

        Returns:
            Dict with complete status or None if error after all retries
        """
        max_retries = 1  # Reduced from 3 to avoid long blocking during polling
        base_delay = 1  # seconds

        try:
            url = f"{self.base_url}{STATUS_URL}"

            # NOTE: status9.xml requires cookie for some panels
            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            session = self._auth.get_session()

            # If no session or not authenticated, try to authenticate first
            if not session or not self._auth.is_authenticated():
                _LOGGER.warning("No authenticated session, attempting authentication...")
                if not await self._auth.authenticate():
                    _LOGGER.error("Authentication failed for status request")
                    # Fall back to unauthenticated request
                    return await self._get_status_unauthenticated(url, headers)

            # Try authenticated request
            try:
                async with session.get(url, headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        text = await response.text()

                        # Check if response is HTML (session expired) instead of XML
                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' in content_type or text.strip().startswith('<!DOCTYPE') or text.strip().startswith('<html'):
                            _LOGGER.warning("Received HTML instead of XML (session expired), attempting reauthentication...")
                            if retry_count < max_retries:
                                if await self._auth.authenticate():
                                    return await self.get_status(retry_count + 1)
                            _LOGGER.error("Reauthentication failed after HTML response")
                            return None

                        # Try to parse XML
                        try:
                            return self._parse_status_response(text)
                        except Exception as parse_error:
                            # XML parse error - might be session expired with weird response
                            _LOGGER.warning("XML parse error: %s. Response might be HTML, trying reauthentication...", parse_error)
                            if retry_count < max_retries:
                                # Check if response looks like HTML
                                if '<html' in text.lower() or '<body' in text.lower() or 'login' in text.lower():
                                    if await self._auth.authenticate():
                                        return await self.get_status(retry_count + 1)
                                # Retry with backoff anyway
                                delay = base_delay * (2 ** retry_count)
                                _LOGGER.warning("Retrying after parse error in %ds...", delay)
                                await asyncio.sleep(delay)
                                return await self.get_status(retry_count + 1)
                            _LOGGER.error("XML parse error after %d retries: %s", max_retries, parse_error)
                            return None
                    elif response.status == 401 or response.status == 403:
                        # Authentication error - try to reauthenticate
                        _LOGGER.warning("Authentication error (HTTP %d), attempting reauthentication...",
                                     response.status)
                        if retry_count < max_retries:
                            await asyncio.sleep(base_delay * (2 ** retry_count))  # Exponential backoff
                            if await self._auth.authenticate():
                                return await self.get_status(retry_count + 1)
                        _LOGGER.error("Reauthentication failed after %d attempts", retry_count + 1)
                        return None
                    elif response.status >= 500:
                        # Server error - retry with backoff
                        if retry_count < max_retries:
                            delay = base_delay * (2 ** retry_count)
                            _LOGGER.warning("Server error HTTP %d, retrying in %ds (attempt %d/%d)",
                                         response.status, delay, retry_count + 1, max_retries)
                            await asyncio.sleep(delay)
                            return await self.get_status(retry_count + 1)
                        _LOGGER.error("Server error after %d retries", max_retries)
                        return None
                    else:
                        _LOGGER.error("Failed to get status: HTTP %d", response.status)
                        return None
            except aiohttp.ClientError as e:
                # Network error - retry with backoff
                if retry_count < max_retries:
                    delay = base_delay * (2 ** retry_count)
                    _LOGGER.warning("Network error '%s', retrying in %ds (attempt %d/%d)",
                                 e, delay, retry_count + 1, max_retries)
                    await asyncio.sleep(delay)
                    return await self.get_status(retry_count + 1)
                _LOGGER.error("Network error after %d retries: %s", max_retries, e)
                return None

        except asyncio.TimeoutError:
            # Timeout - retry with backoff
            if retry_count < max_retries:
                delay = base_delay * (2 ** retry_count)
                _LOGGER.warning("Timeout, retrying in %ds (attempt %d/%d)",
                             delay, retry_count + 1, max_retries)
                await asyncio.sleep(delay)
                return await self.get_status(retry_count + 1)
            _LOGGER.error("Timeout after %d retries", max_retries)
            return None

        except Exception as e:
            _LOGGER.error("Unexpected error reading status: %s", e)
            return None

    async def _get_status_unauthenticated(self, url: str, headers: dict) -> Optional[Dict[str, Any]]:
        """
        Get status without authentication (fallback).

        Args:
            url: Status URL
            headers: HTTP headers

        Returns:
            Dict with status or None
        """
        try:
            async with aiohttp.ClientSession() as temp_session:
                async with temp_session.get(url, headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        text = await response.text()
                        return self._parse_status_response(text)
                    else:
                        _LOGGER.warning("Unauthenticated status request failed: HTTP %d", response.status)
                        return None
        except Exception as e:
            _LOGGER.warning("Unauthenticated status request error: %s", e)
            return None

    def _parse_status_response(self, xml_text: str) -> Optional[Dict[str, Any]]:
        """Parse XML status response."""
        # Calculate max_areas dynamically from configured areas
        max_aree = len(self._areas_config) if self._areas_config else 8

        return self._parser.parse_status_xml(
            xml_text,
            zones_config=self._zones_config,
            max_aree=max_aree,
            zone_ids=self._zone_ids  # Pass zone_ids from numZoneProg.xml
        )

    async def arm_areas(self, areas: List[int], mode: str = "away", arm_mode: str = "normal") -> bool:
        """
        Arm the specified areas.

        Args:
            areas: List of area IDs to arm
            mode: Mode ("away", "night", "home")
            arm_mode: Arm mode ("normal", "immediate", "forced")
                     - normal: fIns=0 (con ritardo)
                     - immediate: fIns=2 (stay, no ritardo su zone con ritardo)
                     - forced: fIns=1 (forzato, aree aperte)

        Returns:
            True if command sent successfully
        """
        try:
            # Reauthenticate if not authenticated
            if not self._auth.is_authenticated():
                _LOGGER.warning("Not authenticated, attempting reauthentication...")
                if not await self._auth.authenticate():
                    _LOGGER.error("Reauthentication failed")
                    return False
                _LOGGER.info("Reauthentication successful")

            # Calculate max_areas dynamically
            max_aree = len(self._areas_config) if self._areas_config else 8

            # Calculate bIns0 value based on areas (BITMASK)
            # bit 0 = area 1, bit 1 = area 2, bit 2 = area 3, etc.
            # Example: areas [1,2,3] = bIns0 = 1|2|4 = 7
            bIns0 = 0
            for area in areas:
                if 1 <= area <= max_aree:
                    bIns0 |= (1 << (area - 1))

            # Map arm_mode to fIns value
            # fIns=0 normale (ritardo)
            # fIns=1 forzato (aree aperte)
            # fIns=2 stay (no ritardo su zone con ritardo)
            arm_mode_map = {
                "normal": 0,
                "immediate": 2,   # stay mode
                "forced": 1
            }
            fIns = arm_mode_map.get(arm_mode, 0)

            session = self._auth.get_session()
            url = f"{self.base_url}{INSAREA_URL}"

            # Build raw payload: bIns0=7&idc=49&fIns=0
            payload = f"bIns0={bIns0}&idc=49&fIns={fIns}"

            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            _LOGGER.debug("Arm command: URL=%s, cookie=%s, payload=%s",
                         url, cookie, payload)

            async with session.post(url, headers=headers, data=payload, timeout=self.timeout) as response:
                response_text = await response.text()

                _LOGGER.debug("Arm command response: status=%d, body=%s",
                             response.status, response_text)

                if response.status == 200:
                    # Build area names list for logging (O(1) lookup using cache)
                    area_names = [
                        f"{area_id}({self._area_name_map.get(area_id, area_id)})"
                        for area_id in areas
                    ]

                    # Map mode to display name
                    mode_display = mode.capitalize() if mode else "Unknown"

                    _LOGGER.info("Areas armed (%s, %s): %s",
                               mode_display, arm_mode, ", ".join(area_names))
                    return True
                else:
                    _LOGGER.error("Arm command failed: HTTP %d, response=%s, payload=%s",
                                response.status, response_text, payload)
                    return False

        except Exception as e:
            _LOGGER.error("Arm command error: %s", e)
            return False

    async def disarm_areas(self, areas: List[int]) -> bool:
        """
        Disarm the specified areas.

        Args:
            areas: List of area IDs to disarm
                   If empty, disarm ALL areas
                   If specified, disarm only those areas (keeping others armed)

        Returns:
            True if command sent successfully
        """
        try:
            # Reauthenticate if not authenticated
            if not self._auth.is_authenticated():
                _LOGGER.warning("Not authenticated, attempting reauthentication...")
                if not await self._auth.authenticate():
                    _LOGGER.error("Reauthentication failed")
                    return False
                _LOGGER.info("Reauthentication successful")

            # Get current status to see which areas are armed
            status_data = await self.get_status()

            if not status_data:
                _LOGGER.warning("Could not get current status, defaulting to disarm all")
                bIns0 = 0
            else:
                currently_armed = status_data.get("armed_areas", [])

                if not areas:
                    # No areas specified → disarm ALL
                    bIns0 = 0
                    _LOGGER.info("Disarming ALL areas (no specific areas selected)")
                else:
                    # Selective disarm: remove specified areas from currently armed
                    remaining_armed = [area for area in currently_armed if area not in areas]

                    # Calculate bitmask of remaining armed areas
                    bIns0 = 0
                    for area_id in remaining_armed:
                        if 1 <= area_id <= 32:
                            bIns0 |= (1 << (area_id - 1))

                    _LOGGER.debug("Selective disarm - currently armed: %s, disarming: %s, remaining armed: %s (bitmask: %d)",
                                currently_armed, areas, remaining_armed, bIns0)

            session = self._auth.get_session()
            url = f"{self.base_url}{INSAREA_URL}"

            # Build raw payload: bIns0=BITMASK&idc=49&fIns=0&sDis=0
            payload = f"bIns0={bIns0}&idc=49&fIns=0"

            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            _LOGGER.debug("Disarm command: URL=%s, cookie=%s, payload=%s",
                         url, cookie, payload)

            async with session.post(url, headers=headers, data=payload, timeout=self.timeout) as response:
                response_text = await response.text()

                _LOGGER.debug("Disarm command response: status=%d, body=%s",
                             response.status, response_text)

                if response.status == 200:
                    # Build area names list for logging (O(1) lookup using cache)
                    area_names = [
                        f"{area_id}({self._area_name_map.get(area_id, area_id)})"
                        for area_id in areas
                    ]

                    _LOGGER.info("Areas disarmed: %s", ", ".join(area_names))
                    return True
                else:
                    _LOGGER.error("Disarm command failed: HTTP %d, response=%s, payload=%s",
                                response.status, response_text, payload)
                    return False

        except Exception as e:
            _LOGGER.error("Disarm command error: %s", e)
            return False

    async def toggle_zone_inclusion(self, zone_id: int) -> bool:
        """
        Toggle zone inclusion/exclusion (bypass).

        This sends a command to toggle whether a zone is included or excluded from the alarm.
        The command is a toggle - if the zone is included it will be excluded, and vice versa.

        Args:
            zone_id: Zone ID (1-based)

        Returns:
            True if command sent successfully
        """
        try:
            # Reauthenticate if not authenticated
            if not self._auth.is_authenticated():
                _LOGGER.warning("Not authenticated, attempting reauthentication...")
                if not await self._auth.authenticate():
                    _LOGGER.error("Reauthentication failed")
                    return False
                _LOGGER.info("Reauthentication successful")

            session = self._auth.get_session()
            url = f"{self.base_url}/execBypass.xml"

            # nCmd = zone_id, idc = 49 (fixed parameter)
            data = {
                "nCmd": zone_id,
                "idc": 49
            }

            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            _LOGGER.debug("Toggle zone inclusion: zone_id=%d", zone_id)
            _LOGGER.debug("Toggle zone command: URL=%s, cookie=%s, payload=%s",
                         url, cookie, data)

            async with session.post(url, headers=headers, data=data, timeout=self.timeout) as response:
                response_text = await response.text()

                _LOGGER.debug("Toggle zone response: status=%d, body=%s",
                             response.status, response_text[:200] if response_text else "None")

                if response.status == 200:
                    _LOGGER.info("Zone %d inclusion toggled successfully", zone_id)
                    return True
                else:
                    _LOGGER.error("Toggle zone command failed: HTTP %d, response=%s, payload=%s",
                                response.status, response_text[:200] if response_text else "None", data)
                    return False

        except Exception as e:
            _LOGGER.error("Toggle zone command error: %s", e)
            return False

    async def execute_macro(self, macro_id: int, macro_name: str = None) -> bool:
        """
        Execute a macro (scenario).

        Sends a POST command to execChangeImp.xml.
        Payload format: comandi=macro_id;49;master_code;

        Args:
            macro_id: Macro ID
            macro_name: Optional macro name for logging

        Returns:
            True if command executed successfully (<nc>31</nc> in response)
        """
        try:
            # Reauthenticate if not authenticated
            if not self._auth.is_authenticated():
                _LOGGER.warning("Not authenticated, attempting reauthentication...")
                if not await self._auth.authenticate():
                    _LOGGER.error("Reauthentication failed")
                    return False
                _LOGGER.info("Reauthentication successful")

            session = self._auth.get_session()
            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie
            headers["Referer"] = f"{self.base_url}/index.htm?id=2"

            # Execute macro via POST to execChangeImp.xml?id=2
            url = f"{self.base_url}/execChangeImp.xml?id=2"
            payload = f"comandi={macro_id};49;{self.code};"

            macro_desc = f"({macro_name})" if macro_name else f"({macro_id})"
            _LOGGER.debug("Execute macro %d %s: URL=%s, payload=%s",
                         macro_id, macro_desc, url, payload)

            async with session.post(url, headers=headers, data=payload, timeout=self.timeout) as response:
                response_text = await response.text()
                _LOGGER.debug("Response: status=%d, body=%s",
                             response.status, response_text[:200] if response_text else "None")

                if response.status == 200:
                    # Parse XML response: <nc>31</nc> means success
                    if "<nc>" in response_text:
                        try:
                            import re
                            nc_match = re.search(r'<nc>(\d+)</nc>', response_text)
                            if nc_match:
                                nc_value = int(nc_match.group(1))
                                if nc_value == MACRO_SUCCESS_CODE:  # 0x31 = success
                                    _LOGGER.debug("Macro %d %s executed successfully", macro_id, macro_desc)
                                    return True
                                else:
                                    _LOGGER.warning("Macro returned unexpected code: %d (expected %d)", nc_value, MACRO_SUCCESS_CODE)
                                    return False
                        except (ValueError, AttributeError):
                            _LOGGER.warning("Could not parse result code from XML response")
                            return False
                    else:
                        _LOGGER.warning("Macro response does not contain <nc> tag")
                        return False
                else:
                    _LOGGER.error("Macro command failed: HTTP %d, response=%s, payload=%s",
                                response.status, response_text[:200] if response_text else "None", payload)
                    return False

        except Exception as e:
            _LOGGER.error("Execute macro error: %s", e)
            return False

    def get_zones_config(self) -> List[Dict[str, Any]]:
        """Return the zones configuration."""
        return self._zones_config

    def get_areas_config(self) -> List[Dict[str, Any]]:
        """Return the areas configuration."""
        return self._areas_config

    def get_macros_config(self) -> List[Dict[str, Any]]:
        """Return the macros (scenarios) configuration."""
        return self._macros_config

    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """Return the device info."""
        return self._device_info

    def get_device_info_for_ha(self) -> Dict[str, Any]:
        """Return device info formatted for Home Assistant."""
        device_info = self._device_info or {}

        # Extract version information
        firmware_version = device_info.get("firmware_version", "Unknown")
        amicaweb_version = device_info.get("amicaweb_version", "Unknown")
        web_server_version = device_info.get("web_server_version", "Unknown")

        # Format sw_version as: "2.2, AmicaWEB 2.2, Web 2.5"
        if firmware_version != "Unknown" and amicaweb_version != "Unknown" and web_server_version != "Unknown":
            sw_version = f"{firmware_version}, AmicaWEB {amicaweb_version}, Web {web_server_version}"
        else:
            sw_version = "Unknown"

        # Build device info dictionary
        # Use a simple identifier without IP:PORT to avoid name changes
        info = {
            "identifiers": {("combivox_web", f"alarm_{self.ip_address.replace('.', '_')}")},
            "name": "Combivox Alarm",
            "manufacturer": "Combivox",
            "model": device_info.get('model', 'Amica'),
            "sw_version": sw_version,
            "configuration_url": f"{self.base_url}/system"
        }

        # Add serial number if available
        serial_number = device_info.get("serial_number")
        if serial_number and serial_number != "Unknown":
            info["serial_number"] = serial_number

        return info

    async def _fetch_system_info_internal(self) -> Optional[Dict[str, Any]]:
        """
        Fetch system information from /system/index.html using technical code.

        The system requires DUAL authentication:
        1. Login with user/master code → get user cookie
        2. Login with technical code → get technical cookie
        3. Fetch page with BOTH cookies

        Returns:
            Dict with system info or None if error
        """
        import asyncio
        import re
        import base64
        import random

        try:
            _LOGGER.info("Fetching system info from %s/system (dual auth required)", self.base_url)

            # Step 1: Generate password and authenticate with USER CODE to get user cookie
            _LOGGER.info("Step 1: Authenticating with user code")
            if not await self._auth.is_authenticated():
                if not await self._auth.authenticate():
                    _LOGGER.error("User authentication failed")
                    return None

            user_cookie = self._auth.get_cookie()
            _LOGGER.debug("User cookie obtained: %s", user_cookie)

            # Step 2: Generate password and authenticate with TECHNICAL CODE to get technical cookie
            _LOGGER.info("Step 2: Authenticating with technical code")

            # Generate dynamic password using tech_code (same logic as auth.py)
            PERMGEN = random.sample(range(1, 9), 8)
            RAND_LAST = f"{random.randint(0, 99):02d}"
            RAND_BEGIN = f"{random.randint(0, 99):02d}"

            TVALUE1 = self.tech_code + RAND_LAST
            TVALUE2 = "".join(TVALUE1[t - 1] for t in PERMMANUAL)
            TVALUE3 = "".join(TVALUE2[t - 1] for t in PERMGEN)
            TVALUE4PERMGEN = "".join(str(t - 1) for t in PERMGEN)
            password = RAND_BEGIN + TVALUE3 + TVALUE4PERMGEN

            credentials = f"admin:{password}"
            b64_auth = base64.b64encode(credentials.encode()).decode()

            _LOGGER.debug("System login: generated password and B64 auth")

            # Create dedicated session for technical login
            cookie_jar = aiohttp.CookieJar(quote_cookie=False)
            connector = aiohttp.TCPConnector(force_close=False)

            technical_cookie = None
            async with aiohttp.ClientSession(cookie_jar=cookie_jar, connector=connector) as session:
                tech_login_url = f"{self.base_url}/system/login.cgi?Basic%20{b64_auth}"
                tech_login2_url = f"{self.base_url}/system/login2.cgi?Basic%20{b64_auth}"
                data = {"Basic": b64_auth}

                # First technical login call
                _LOGGER.debug("System login: calling %s", tech_login_url)
                async with session.post(tech_login_url, data=data, timeout=self.timeout) as response:
                    if response.status != 200:
                        _LOGGER.error("Technical login error: status %d", response.status)
                        return None
                    _LOGGER.debug("System login: first call OK (status %d)", response.status)

                await asyncio.sleep(1)

                # Second technical login call with timing
                _LOGGER.debug("System login: calling %s with timing", tech_login2_url)

                for delay in [2, 3, 4, 5, 6, 7]:
                    await asyncio.sleep(1)

                    async with session.post(tech_login2_url, data=data, timeout=self.timeout) as response:
                        # Check for session cookie in response
                        if response.cookies:
                            for cookie_name, cookie_value in response.cookies.items():
                                technical_cookie = f"{cookie_name}={cookie_value.value}"
                                _LOGGER.info("Technical cookie obtained: %s", technical_cookie)
                                break

                    if technical_cookie:
                        break

                if not technical_cookie:
                    _LOGGER.warning("Technical cookie not found, trying anyway")

            # Step 3: Fetch system index page with BOTH cookies
            index_url = f"{self.base_url}/system/index.html"

            # Build combined cookie string from session
            if user_cookie and technical_cookie:
                combined_cookie = f"{user_cookie}; {technical_cookie}"
            elif user_cookie:
                combined_cookie = user_cookie
            elif technical_cookie:
                combined_cookie = technical_cookie
            else:
                combined_cookie = None
                _LOGGER.warning("No cookies available")

            headers = {}
            if combined_cookie:
                headers["Cookie"] = combined_cookie

            _LOGGER.debug("Fetching %s with dual cookie", index_url)
            _LOGGER.debug("Cookie header: %s", combined_cookie[:200] if combined_cookie else "None")

            # Use user's authenticated session for fetching
            user_session = self._auth.get_session()
            if not user_session:
                _LOGGER.error("No user session available")
                return None

            async with user_session.get(index_url, headers=headers, timeout=self.timeout,
                                        allow_redirects=True) as response:
                if response.status != 200:
                    _LOGGER.error("Error fetching system page: status %d", response.status)
                    return None

                html = await response.text()
                _LOGGER.debug("System page HTML (first 500 chars): %s", html[:500])

            # Parse HTML for system information
            return self._parse_system_info_html(html)

        except Exception as e:
            _LOGGER.error("Error fetching system info: %s", e)
            return None

    def _parse_system_info_html(self, html: str) -> Optional[Dict[str, Any]]:
        """
        Parse system information from HTML page.

        Expected format variants:
        Variant 1:
        Centrale:         Amica 64
        Ver.:         GSM
        Firmware ver.:         2.2, AmicaWEB
        Build date:         Aug 28 2013 18:28:19
        Firmware ver.:         2.5
        Hardware ver.:         1.0
        Web Server ver.:         2.5 (27/08/2013)

        Variant 2 (with serial):
        Centrale:         Amica 64 (S/N: 12345)
        Ver.:         GSM
        ...

        Variant 3 (Amicaweb PLUS):
        Centrale:         Amica 64
        Ver.:         GSM
        Firmware ver.:         2.2, Amicaweb PLUS
        ...

        Returns:
            Dict with parsed system info
        """
        import re

        try:
            info = {}

            # Extract model name and version (with optional serial number)
            # Pattern: "Centrale:         Amica 64" or "Centrale:         Amica 64 (S/N: 12345)"
            model_match = re.search(MODEL_PATTERN, html)
            ver_match = re.search(VERSION_PATTERN, html)

            if model_match and ver_match:
                model_text = model_match.group(1).strip()
                model_version = ver_match.group(1).strip()

                # Extract serial number if present (format: "Amica 64 (S/N: 12345)")
                serial_match = re.search(SERIAL_NUMBER_PATTERN, model_text)
                if serial_match:
                    model_name = serial_match.group(1).strip()
                    info["serial_number"] = serial_match.group(2).strip()
                else:
                    model_name = model_text

                info["model"] = f"{model_name} - {model_version}"
                info["model_name"] = model_name
                info["model_version"] = model_version
            else:
                _LOGGER.warning("Could not extract model/version from HTML")
                info["model"] = "Amica"
                info["model_name"] = "Amica"
                info["model_version"] = "Unknown"

            # Extract AmicaWEB type and firmware version
            # Pattern: "Firmware ver.:         2.2, AmicaWEB" or "Firmware ver.:         2.2, Amicaweb PLUS"
            fw_full_line = re.search(FIRMWARE_FULL_PATTERN, html, re.IGNORECASE)

            if fw_full_line:
                info["firmware_version"] = fw_full_line.group(1).strip()
                # Normalize AmicaWEB name
                amicaweb_type = fw_full_line.group(2).strip()
                info["amicaweb_type"] = amicaweb_type
                # Extract version number from AmicaWEB name (e.g., "Amicaweb PLUS 2.5" -> "2.5")
                amicaweb_ver_match = re.search(AMICAWEB_VERSION_PATTERN, amicaweb_type)
                info["amicaweb_version"] = amicaweb_ver_match.group(1) if amicaweb_ver_match else "Unknown"
            else:
                # Fallback: just extract first firmware version
                fw_match = re.search(FIRMWARE_FALLBACK_PATTERN, html)
                if fw_match:
                    info["firmware_version"] = fw_match.group(1).strip()
                else:
                    info["firmware_version"] = "Unknown"
                info["amicaweb_type"] = "Unknown"
                info["amicaweb_version"] = "Unknown"

            # Extract build date
            # Pattern: "Build date:         Aug 28 2013 18:28:19"
            build_match = re.search(r'Build date:\s+(.+?)(?:\n|$)', html)
            if build_match:
                info["build_date"] = build_match.group(1).strip()
            else:
                info["build_date"] = "Unknown"

            # Extract web server version
            # Pattern: "Web Server ver.:         2.5 (27/08/2013)"
            web_match = re.search(r'Web Server ver\.:\s+(\S+(?:\s+\S+)*)', html)
            if web_match:
                info["web_server_version"] = web_match.group(1).strip()
            else:
                info["web_server_version"] = "Unknown"

            _LOGGER.info("Parsed system info: model=%s, fw=%s, amicaweb=%s, web=%s, serial=%s",
                        info.get("model"), info.get("firmware_version"),
                        info.get("amicaweb_type"), info.get("web_server_version"),
                        info.get("serial_number", "N/A"))

            return info

        except Exception as e:
            _LOGGER.error("Error parsing system info HTML: %s", e)
            return None

    async def close(self):
        """Close the connection."""
        await self._auth.close()
