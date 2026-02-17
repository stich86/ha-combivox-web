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
    JSCRIPT9_URL,
    LABELZONE_URL,
    LABELAREA_URL,
    INSAREA_URL,
    NUMMACRO_URL,
    EXECCHANGEIMP_URL,
    EXECCMD_URL,
    EXECDELMEM_URL,
    NUMTROUBLE_URL,
    NUMMEMPROG_URL,
    LABELMEM_URL,
    NUMCOMANDIPROG_URL,
    LABELCOMANDI_URL,
    CONF_IP_ADDRESS,
    CONF_PORT,
    CONF_CODE,
    PERMMANUAL,
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
        timeout: int = 10
    ):
        """
        Initialize the client.

        Args:
            ip_address: Panel IP address
            code: User code
            port: HTTP port
            config_file_path: JSON config file path
            timeout: HTTP request timeout
        """
        self.ip_address = ip_address
        self.code = code
        self.port = port
        self.timeout = timeout
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
        self._commands_config: List[Dict[str, Any]] = []
        self._zone_ids: List[int] = []  # Active zone IDs from numZoneProg.xml
        self._device_info: Optional[Dict[str, Any]] = None

    def is_config_loaded(self) -> bool:
        """
        Check if configuration (zones/areas/macros/commands) has been loaded.

        Returns:
            True if at least one of zones, areas, macros, or commands config is loaded
        """
        return bool(self._zones_config or self._areas_config or self._macros_config or self._commands_config)

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

            # Try to fetch initial status, but don't fail if offline
            # (we might have cached config)
            try:
                await self._fetch_initial_status()
            except Exception as e:
                _LOGGER.warning("Could not fetch initial status (panel may be offline): %s", e)

            # Try to fetch device variant info from jscript9.js
            try:
                await self._fetch_device_info()
            except Exception as e:
                _LOGGER.warning("Could not fetch device variant info: %s", e)

            # If we have config (cached or fresh), connection is successful enough
            return self.is_config_loaded()

        except Exception as e:
            _LOGGER.error("Connection failed: %s", e)
            # Even on exception, check if we have cached config
            return self.is_config_loaded()

    async def reload_configuration(self) -> bool:
        """
        Force reload configuration from panel (zones, areas, macros, commands).

        This method re-downloads the configuration from the panel and compares
        with the previous configuration to detect changes.
        IMPORTANT: Does NOT break existing authentication - reuses the session.

        Returns:
            True if configuration changed (reload needed), False otherwise
        """
        _LOGGER.info("Reloading configuration from panel (reusing existing session)")

        # Store previous config for comparison
        prev_zones_count = len(self._zones_config) if self._zones_config else 0
        prev_macros_count = len(self._macros_config) if self._macros_config else 0
        prev_commands_count = len(self._commands_config) if self._commands_config else 0
        prev_zone_ids = set(self._zone_ids) if self._zone_ids else set()
        prev_macro_ids = set(m.get("id") for m in self._macros_config) if self._macros_config else set()
        prev_command_ids = set(c.get("id") for c in self._commands_config) if self._commands_config else set()

        # Re-download configuration using existing session (don't reauthenticate)
        try:
            # Download zones and areas (uses existing session)
            prog_state = await self._download_prog_state_config()
            if prog_state:
                new_zones = prog_state.get("zones", [])
                new_areas = prog_state.get("areas", [])
                self._zones_config = new_zones
                self._zone_ids = [z["zone_id"] for z in new_zones]
                self._areas_config = new_areas
                self._area_name_map = {area["area_id"]: area["area_name"] for area in new_areas}
            else:
                _LOGGER.warning("Failed to download zones/areas config during reload")
                return False

            # Download macros (uses existing session)
            macros_config = await self._download_macros_config()
            if macros_config:
                self._macros_config = macros_config
            else:
                _LOGGER.warning("Failed to download macros config during reload")

            # Download commands (uses existing session)
            commands_config = await self._download_commands_config()
            if commands_config:
                self._commands_config = commands_config
            else:
                _LOGGER.warning("Failed to download commands config during reload")

            # Save to file
            if self._config_file_path:
                await self._save_config_to_file()

            # Compare configurations
            new_zones_count = len(self._zones_config) if self._zones_config else 0
            new_macros_count = len(self._macros_config) if self._macros_config else 0
            new_commands_count = len(self._commands_config) if self._commands_config else 0
            new_zone_ids = set(self._zone_ids) if self._zone_ids else set()
            new_macro_ids = set(m.get("id") for m in self._macros_config) if self._macros_config else set()
            new_command_ids = set(c.get("id") for c in self._commands_config) if self._commands_config else set()

            # Check for changes
            zones_changed = (prev_zones_count != new_zones_count or
                            prev_zone_ids != new_zone_ids)
            macros_changed = (prev_macros_count != new_macros_count or
                             prev_macro_ids != new_macro_ids)
            commands_changed = (prev_commands_count != new_commands_count or
                               prev_command_ids != new_command_ids)

            if zones_changed or macros_changed or commands_changed:
                _LOGGER.info("Configuration changed - zones: %d→%d, macros: %d→%d, commands: %d→%d",
                           prev_zones_count, new_zones_count,
                           prev_macros_count, new_macros_count,
                           prev_commands_count, new_commands_count)
                return True
            else:
                _LOGGER.info("Configuration unchanged - zones: %d, macros: %d, commands: %d",
                           new_zones_count, new_macros_count, new_commands_count)
                return False

        except Exception as e:
            _LOGGER.error("Error reloading configuration: %s", e)
            return False

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

        # Download commands configuration
        commands_config = await self._download_commands_config()
        if commands_config:
            self._commands_config = commands_config
            _LOGGER.info("Loaded %d commands", len(self._commands_config))

        # Save to file if path provided
        if self._config_file_path and (prog_state or macros_config or commands_config):
            await self._save_config_to_file()

        return True

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

            _LOGGER.debug("Connected: variant=%s, state=%s",
                       self._device_info.get("variant", "Unknown"),
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

    async def _download_commands_config(self) -> Optional[List[Dict[str, Any]]]:
        """
        Download commands configuration.

        Process:
        1. GET reqProg.cgi?id=4&idc=49 to trigger command data population
        2. Wait 2 seconds for data to be populated
        3. GET numComandiProg.xml to get command IDs
        4. POST with payload comandi=id1;id2;etc to get command labels
        5. Parse labels and return list of commands with types

        Returns:
            List of command configs: [{"command_id": 1, "command_name": "Luci Sala", "command_type": "button"}, ...]
        """
        try:
            if not self._auth.is_authenticated():
                _LOGGER.error("Not authenticated, cannot download commands configuration")
                return None

            session = self._auth.get_session()
            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            # Step 1: Trigger command data population (id=4 for commands)
            # This is required to populate the data before downloading
            trigger_url = f"{self.base_url}/reqProg.cgi?id=4&idc=49"

            # Add Referer header as required by the panel
            headers_with_referer = headers.copy()
            headers_with_referer["Referer"] = f"{self.base_url}/index.htm?id=6"

            _LOGGER.debug("Triggering command data population: URL=%s, Referer=%s",
                         trigger_url, headers_with_referer.get("Referer"))

            try:
                async with session.get(trigger_url, headers=headers_with_referer, timeout=self.timeout) as response:
                    if response.status == 200:
                        _LOGGER.debug("Command data population triggered successfully")
                    else:
                        _LOGGER.warning("Trigger request returned status %d (continuing anyway)", response.status)
            except Exception as e:
                _LOGGER.warning("Failed to trigger command data population: %s (continuing anyway)", e)

            # Step 2: Wait 2 seconds for data to be populated
            await asyncio.sleep(2)

            # Step 3: Download numComandiProg.xml to get command IDs
            url = f"{self.base_url}{NUMCOMANDIPROG_URL}"
            _LOGGER.debug("Downloading numComandiProg.xml: URL=%s", url)

            async with session.get(url, headers=headers, timeout=self.timeout) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to download numComandiProg.xml: status %d", response.status)
                    return None

                text = await response.text()
                _LOGGER.debug("Downloaded numComandiProg.xml successfully (%d bytes)", len(text))

            # Parse command IDs
            command_ids = self._parser.parse_command_ids(text)
            if not command_ids:
                _LOGGER.info("No commands found in numComandiProg.xml")
                return []

            _LOGGER.debug("Found %d command IDs: %s", len(command_ids), command_ids)

            # Step 4: Download command labels using the IDs
            # Build comandi parameter with command IDs
            comandi_param = ";".join(str(c_id) for c_id in command_ids) + ";"
            labels_url = f"{self.base_url}{LABELCOMANDI_URL}"

            # Build POST payload
            payload = f"comandi={comandi_param}"

            # Add Referer header as required by the panel
            headers_with_referer = headers.copy()
            headers_with_referer["Referer"] = f"{self.base_url}/index.htm?id=6"

            # Try multiple times to download labels (panel takes time to respond)
            max_retries = 10
            text = None

            for attempt in range(1, max_retries + 1):
                _LOGGER.debug("Downloading command labels (attempt %d/%d): URL=%s, Referer=%s, cookie=%s, payload=%s",
                             attempt, max_retries, labels_url, headers_with_referer.get("Referer"),
                             cookie, payload)

                async with session.post(labels_url, headers=headers_with_referer, data=payload, timeout=self.timeout) as response:
                    if response.status == 200:
                        text = await response.text()
                        _LOGGER.info("Downloaded command labels successfully on attempt %d (%d bytes)", attempt, len(text))
                        break
                    else:
                        _LOGGER.warning("Attempt %d failed: status %d", attempt, response.status)
                        if attempt < max_retries:
                            await asyncio.sleep(1)  # Wait 1 second between retries

            if text is None:
                _LOGGER.warning("Failed to download command labels after %d attempts (using IDs only)", max_retries)
                # Return commands without names
                return [{"command_id": c_id, "command_name": f"Command {c_id}", "command_type": "button"} for c_id in command_ids]

            _LOGGER.debug("Command labels downloaded successfully (%d bytes)", len(text))

            # Step 5: Parse command labels
            commands = self._parser.parse_command_labels(text, command_ids)

            if commands:
                _LOGGER.debug("Parsed %d command labels", len(commands))
                return commands
            else:
                _LOGGER.warning("Failed to parse command labels, using IDs only")
                return [{"command_id": c_id, "command_name": f"Command {c_id}", "command_type": "button"} for c_id in command_ids]

        except Exception as e:
            _LOGGER.error("Error downloading commands configuration: %s", e)
            return None

    async def _load_config_from_file(self) -> bool:
        """Load zones, areas, macros and commands configuration from JSON file."""
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

            if 'commands' in config:
                self._commands_config = config['commands']
                _LOGGER.info("Loaded %d commands from cache file", len(self._commands_config))

            return True

        except Exception as e:
            _LOGGER.warning("Failed to load config from file: %s", e)
            return False

    async def _save_config_to_file(self) -> bool:
        """Save zones, areas, macros and commands configuration to JSON file."""
        try:
            if not self._config_file_path:
                return False

            # Ensure directory exists
            os.makedirs(os.path.dirname(self._config_file_path), exist_ok=True)

            config = {
                "zones": self._zones_config,
                "areas": self._areas_config,
                "macros": self._macros_config,
                "commands": self._commands_config,
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

    async def clear_alarm_memory(self) -> bool:
        """
        Clear alarm memory.

        This sends a command to clear the alarm memory on the panel.

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
            url = f"{self.base_url}{EXECDELMEM_URL}"

            # Payload: comandi=del
            data = {
                "comandi": "del"
            }

            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            _LOGGER.debug("Clear alarm memory command: URL=%s, cookie=%s, payload=%s",
                         url, cookie, data)

            async with session.post(url, headers=headers, data=data, timeout=self.timeout) as response:
                response_text = await response.text()

                _LOGGER.debug("Clear alarm memory response: status=%d, body=%s",
                             response.status, response_text[:200] if response_text else "None")

                if response.status == 200:
                    _LOGGER.info("Alarm memory cleared successfully")
                    return True
                else:
                    _LOGGER.error("Clear alarm memory command failed: HTTP %d, response=%s, payload=%s",
                                response.status, response_text[:200] if response_text else "None", data)
                    return False

        except Exception as e:
            _LOGGER.error("Clear alarm memory command error: %s", e)
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

    async def execute_command(self, command_id: int, activate: bool = True) -> bool:
        """
        Execute a command (button or switch).

        Sends a POST command to execCmd.xml.
        Payload format: nCmd=command_id&idc=49&val=7 (activate) or val=0 (deactivate)

        TODO: Add code parameter in payload like macros (currently no code required)

        Args:
            command_id: Command ID
            activate: True to activate (val=7), False to deactivate (val=0, for switches)

        Returns:
            True if command executed successfully
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
            headers["Referer"] = f"{self.base_url}/index.htm?id=6"

            # val=7 to activate, val=0 to deactivate
            val = 7 if activate else 0
            url = f"{self.base_url}{EXECCMD_URL}"
            payload = f"nCmd={command_id}&idc=49&val={val}"

            action = "activate" if activate else "deactivate"
            _LOGGER.debug("Execute command %d (%s): URL=%s, payload=%s",
                         command_id, action, url, payload)

            async with session.post(url, headers=headers, data=payload, timeout=self.timeout) as response:
                response_text = await response.text()
                _LOGGER.debug("Response: status=%d, body=%s",
                             response.status, response_text[:200] if response_text else "None")

                if response.status == 200:
                    # TODO: Parse response to verify success (currently no response format known)
                    _LOGGER.debug("Command %d (%s) executed successfully", command_id, action)
                    return True
                else:
                    _LOGGER.error("Command failed: HTTP %d, response=%s, payload=%s",
                                response.status, response_text[:200] if response_text else "None", payload)
                    return False

        except Exception as e:
            _LOGGER.error("Execute command error: %s", e)
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

    def get_commands_config(self) -> List[Dict[str, Any]]:
        """Return the commands configuration."""
        return self._commands_config

    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """Return the device info."""
        return self._device_info

    def get_config_file_path(self) -> Optional[str]:
        """Return the cached config file path."""
        return self._config_file_path

    def get_device_info_for_ha(self) -> Dict[str, Any]:
        """Return device info formatted for Home Assistant."""
        # Get variant from device info (fetched from jscript9.js)
        device_info = self._device_info or {}
        variant = device_info.get("variant", "Amica + AmicaWeb")

        # Build device info dictionary with variant as model
        info = {
            "identifiers": {("combivox_web", f"alarm_{self.ip_address.replace('.', '_')}")},
            "name": "Combivox Alarm",
            "manufacturer": "Combivox",
            "model": variant,  # Use variant (e.g., "Amica 64 LTE + AmicaWeb")
            "configuration_url": self.base_url
        }

        return info

    async def _fetch_device_info(self) -> None:
        """
        Fetch device variant information from jscript9.js.

        Parses JavaScript file to extract:
        - vertype: panel type (e.g., "AMICA 64 LTE")
        - typWeb: web interface type (e.g., "Amicaweb", "Smartweb")

        Returns:
            None (updates self._device_info["variant"])
        """
        import re

        try:
            # Get authenticated session
            session = self._auth.get_session()
            if not session:
                _LOGGER.warning("No session available for device info fetch")
                return

            # Build headers with cookie (same as labelProgStato.xml and other requests)
            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            url = f"{self.base_url}{JSCRIPT9_URL}"
            _LOGGER.debug("Fetching device info from %s", url)

            async with session.get(url, headers=headers, timeout=self.timeout) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch jscript9.js: status %d", response.status)
                    return

                js_content = await response.text()

            # Extract vertype - handles both single and double quotes
            vertype_match = re.search(r'var\s+vertype\s*=\s*["\']([^"\']+)["\']', js_content)
            if not vertype_match:
                _LOGGER.warning("Could not find vertype in jscript9.js")
                _LOGGER.debug("Content length: %d bytes, first 200 chars: %s", len(js_content), js_content[:200])
                return

            vertype = vertype_match.group(1).strip()
            _LOGGER.debug("Found vertype: %s", vertype)

            # Extract typWeb - handles both single and double quotes
            typweb_match = re.search(r'var\s+typWeb\s*=\s*["\']([^"\']+)["\']', js_content)
            typweb = typweb_match.group(1).strip() if typweb_match else None
            _LOGGER.debug("Found typWeb: %s", typweb)

            # Apply formatting rules
            # Rule 1: vertype to uppercase, but fix AMICA/ELISA to title case
            vertype_upper = vertype.upper()

            # Fix AMICA → Amica, ELISA → Elisa
            vertype_upper = re.sub(r'\bAMICA\b', 'Amica', vertype_upper)
            vertype_upper = re.sub(r'\bELISA\b', 'Elisa', vertype_upper)

            # Rule 2: If contains both "LTE" and "GSM", remove "GSM"
            if "LTE" in vertype_upper and "GSM" in vertype_upper:
                vertype_upper = vertype_upper.replace("GSM", "").strip()

            # Rule 3: Format typWeb correctly
            if typweb:
                typweb_lower = typweb.lower()

                # Handle special cases
                if "amicaweb" in typweb_lower:
                    # Amicaweb always becomes "AmicaWeb Plus"
                    typweb_formatted = "AmicaWeb Plus"
                elif "smartweb" in typweb_lower:
                    # Smartweb becomes "SmartWeb"
                    typweb_formatted = "SmartWeb"
                else:
                    # Generic title case for unknown values
                    typweb_formatted = typweb.title()
            else:
                # Default to "AmicaWeb" if not present
                typweb_formatted = "AmicaWeb"

            # Combine: "VERTYPE + TypWeb"
            variant = f"{vertype_upper} + {typweb_formatted}"

            # Store in device info
            if not self._device_info:
                self._device_info = {}

            self._device_info["variant"] = variant
            _LOGGER.info("Device variant: %s", variant)

        except Exception as e:
            _LOGGER.warning("Error fetching device info: %s", e)

    async def get_anomalies_info(self) -> Optional[int]:
        """
        Get active anomaly/trouble ID from the panel.

        Returns:
            Active anomaly ID (0-15) from numTrouble.xml c0, or None if no anomaly
        """
        try:
            # Reauthenticate if not authenticated
            if not self._auth.is_authenticated():
                _LOGGER.warning("Not authenticated, attempting reauthentication...")
                if not await self._auth.authenticate():
                    _LOGGER.error("Reauthentication failed")
                    return None
                _LOGGER.info("Reauthentication successful")

            session = self._auth.get_session()
            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            # Get active anomaly ID from numTrouble.xml
            url = f"{self.base_url}{NUMTROUBLE_URL}"
            async with session.get(url, headers=headers, timeout=self.timeout) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to get numTrouble: HTTP %d", response.status)
                    return None

                xml_content = await response.text()
                _LOGGER.debug("numTrouble.xml response: %s", xml_content[:200])

                # Parse active anomaly ID from <c0>id</c0>
                import xml.etree.ElementTree as ET
                root = ET.fromstring(xml_content)
                c0_elem = root.find("c0")
                if c0_elem is None or not c0_elem.text:
                    _LOGGER.warning("No c0 element in numTrouble.xml")
                    return None

                try:
                    anomaly_id = int(c0_elem.text.strip())
                    _LOGGER.info("Retrieved active anomaly ID: %d", anomaly_id)
                    return anomaly_id
                except ValueError:
                    _LOGGER.error("Invalid anomaly ID: %s", c0_elem.text)
                    return None

        except Exception as e:
            _LOGGER.error("Error getting anomalies info: %s", e)
            return None

    async def get_alarm_memory_info(self) -> List[Dict[str, Any]]:
        """
        Get alarm memory information from the panel.

        Returns:
            List of alarm memory entries with id and message
        """
        try:
            # Reauthenticate if not authenticated
            if not self._auth.is_authenticated():
                _LOGGER.warning("Not authenticated, attempting reauthentication...")
                if not await self._auth.authenticate():
                    _LOGGER.error("Reauthentication failed")
                    return []
                _LOGGER.info("Reauthentication successful")

            session = self._auth.get_session()
            headers = {}
            cookie = self._auth.get_cookie()
            if cookie:
                headers["Cookie"] = cookie

            # Step 1: Get number of alarm memories
            url = f"{self.base_url}{NUMMEMPROG_URL}"
            async with session.get(url, headers=headers, timeout=self.timeout) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to get numMemProg: HTTP %d", response.status)
                    return []

                xml_content = await response.text()
                _LOGGER.debug("numMemProg.xml response: %s", xml_content[:200])

                # Parse number of memories from <c0>count</c0>
                import xml.etree.ElementTree as ET
                root = ET.fromstring(xml_content)
                c0_elem = root.find("c0")
                if c0_elem is None or not c0_elem.text:
                    _LOGGER.warning("No c0 element in numMemProg.xml")
                    return []

                memory_count = c0_elem.text.strip()
                _LOGGER.debug("Alarm memory count: %s", memory_count)

                # If memory_count is just the count as integer, we need to get individual IDs
                # For now, assume it's the actual ID (like "1058")
                # If it's a count, we would need to iterate and get each label

            # Step 2: Get alarm memory label
            url = f"{self.base_url}{LABELMEM_URL}"
            payload = f"comandi={memory_count};"

            async with session.post(url, headers=headers, data=payload, timeout=self.timeout) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to get labelMem: HTTP %d", response.status)
                    return []

                xml_content = await response.text()
                _LOGGER.debug("labelMem.xml response: %s", xml_content[:200])

                # Parse alarm memory label
                root = ET.fromstring(xml_content)
                mem_tag = root.find(f"m{memory_count}")
                if mem_tag is None or not mem_tag.text:
                    _LOGGER.warning("No m%s element in labelMem.xml", memory_count)
                    return []

                hex_text = mem_tag.text.strip()

                # Convert hex to ASCII using bytes.fromhex().decode()
                try:
                    message = bytes.fromhex(hex_text).decode('utf-8')
                except Exception as e:
                    _LOGGER.error("Error converting hex to ASCII: %s", e)
                    message = hex_text  # Fallback to raw hex

                alarm_memory = [{
                    "id": memory_count,
                    "message": message
                }]

                _LOGGER.info("Retrieved alarm memory: %s", message)
                return alarm_memory

        except Exception as e:
            _LOGGER.error("Error getting alarm memory info: %s", e)
            return []

    async def close(self):
        """Close the connection."""
        await self._auth.close()
