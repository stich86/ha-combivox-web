"""Config flow for Combivox Amica Web integration."""

import logging
import os
from typing import Any, Dict

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
)

from . import CannotConnect, InvalidAuth
from .base import CombivoxWebClient
from .const import (
    DOMAIN,
    CONF_IP_ADDRESS,
    CONF_CODE,
    CONF_PORT,
    CONF_TECH_CODE,
    CONF_AREAS_AWAY,
    CONF_AREAS_HOME,
    CONF_AREAS_NIGHT,
    CONF_AREAS_DISARM,
    CONF_ARM_MODE_AWAY,
    CONF_ARM_MODE_HOME,
    CONF_ARM_MODE_NIGHT,
    CONF_SCAN_INTERVAL,
    CONF_MACRO_AWAY,
    CONF_MACRO_HOME,
    CONF_MACRO_NIGHT,
    CONF_MACRO_DISARM,
    DEFAULT_SCAN_INTERVAL,
    ARM_MODE_NORMAL,
    ARM_MODE_IMMEDIATE,
    ARM_MODE_FORCED,
)

_LOGGER = logging.getLogger(__name__)


def parse_areas_string(areas_str: str) -> list[int]:
    """Parse area list from string."""
    if not areas_str:
        return []
    # Supports formats: "1,2,3" or "[1,2,3]" or "1 2 3"
    areas_str = areas_str.strip().strip("[]")
    areas = []
    for part in areas_str.replace(",", " ").split():
        try:
            areas.append(int(part))
        except ValueError:
            pass
    return areas


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS, default="192.168.1.25"): str,
        vol.Required(CONF_PORT, default=80): int,
        vol.Required(CONF_CODE, default="123456"): str,
        vol.Required(CONF_TECH_CODE, default="111111"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # TODO: Add actual validation logic here
    # For now, just check if IP and code are provided
    if not data.get(CONF_IP_ADDRESS) or not data.get(CONF_CODE):
        raise InvalidAuth

    # Return info to store in config entry
    return {
        "title": f"Combivox ({data[CONF_IP_ADDRESS]})",
    }


class CombivoxOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Combivox."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self._entry = config_entry
        self._areas_config: list[Dict] = []
        self._macros_config: list[Dict] = []

    async def async_step_init(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        # Load areas and macros from JSON the first time
        if not self._areas_config:
            await self._load_areas_config()
        if not self._macros_config:
            await self._load_macros_config()

        if user_input is not None:
            # Debug: log what we received
            _LOGGER.debug("user_input received: %s", user_input)

            # Multi-select returns list of strings, convert to integers
            def to_int_list(lst):
                return [int(x) for x in lst] if lst else []

            areas_away = to_int_list(user_input.get(CONF_AREAS_AWAY, []))
            areas_home = to_int_list(user_input.get(CONF_AREAS_HOME, []))
            areas_night = to_int_list(user_input.get(CONF_AREAS_NIGHT, []))
            areas_disarm = to_int_list(user_input.get(CONF_AREAS_DISARM, []))

            # Convert macro names back to IDs for saving
            def macro_name_to_id(macro_name):
                """Convert macro name from dropdown back to ID for storage."""
                if not macro_name or macro_name == "" or macro_name is None:
                    return ""
                # Check for the special "no scenario" option
                if macro_name == "No":
                    return ""
                # Find macro ID by name
                for macro in self._macros_config:
                    if macro.get("macro_name") == macro_name:
                        return str(macro["macro_id"])
                return ""

            # Get macro values from user_input
            # vol.Optional() with defaults ensures values are always present
            macro_away_raw = user_input.get(CONF_MACRO_AWAY, "")
            macro_home_raw = user_input.get(CONF_MACRO_HOME, "")
            macro_night_raw = user_input.get(CONF_MACRO_NIGHT, "")
            macro_disarm_raw = user_input.get(CONF_MACRO_DISARM, "")

            _LOGGER.debug("Macro raw values from UI - away=%s, home=%s, night=%s, disarm=%s",
                        macro_away_raw, macro_home_raw, macro_night_raw, macro_disarm_raw)

            # Convert macro names to IDs
            macro_away = macro_name_to_id(macro_away_raw)
            macro_home = macro_name_to_id(macro_home_raw)
            macro_night = macro_name_to_id(macro_night_raw)
            macro_disarm = macro_name_to_id(macro_disarm_raw)

            _LOGGER.debug("Saving options - macros: away=%s, home=%s, night=%s, disarm=%s",
                        macro_away or "(none)", macro_home or "(none)",
                        macro_night or "(none)", macro_disarm or "(none)")
            _LOGGER.debug("Saving options - areas: away=%s, home=%s, night=%s, disarm=%s",
                        areas_away, areas_home, areas_night, areas_disarm)

            # Pad codes to 6 digits if less than 6 characters (panel expects 6 digits)
            user_code = user_input.get(CONF_CODE, "")
            tech_code = user_input.get(CONF_TECH_CODE, "")

            if user_code and len(user_code) < 6:
                user_code = user_code.ljust(6, '0')
                _LOGGER.debug("User code padded to 6 digits: %s", user_code)

            if tech_code and len(tech_code) < 6:
                tech_code = tech_code.ljust(6, '0')
                _LOGGER.debug("Technical code padded to 6 digits: %s", tech_code)

            # Get arm_mode values - always present since we use vol.Required() with defaults
            arm_mode_away = user_input.get(CONF_ARM_MODE_AWAY, ARM_MODE_NORMAL)
            arm_mode_home = user_input.get(CONF_ARM_MODE_HOME, ARM_MODE_NORMAL)
            arm_mode_night = user_input.get(CONF_ARM_MODE_NIGHT, ARM_MODE_NORMAL)

            _LOGGER.debug("Arm mode values from UI - away=%s, home=%s, night=%s",
                        arm_mode_away, arm_mode_home, arm_mode_night)

            result = {
                CONF_CODE: user_code,
                CONF_TECH_CODE: tech_code,
                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL),
                CONF_AREAS_AWAY: areas_away,
                CONF_AREAS_HOME: areas_home,
                CONF_AREAS_NIGHT: areas_night,
                CONF_AREAS_DISARM: areas_disarm,
                CONF_ARM_MODE_AWAY: arm_mode_away,
                CONF_ARM_MODE_HOME: arm_mode_home,
                CONF_ARM_MODE_NIGHT: arm_mode_night,
                CONF_MACRO_AWAY: macro_away,
                CONF_MACRO_HOME: macro_home,
                CONF_MACRO_NIGHT: macro_night,
                CONF_MACRO_DISARM: macro_disarm,
            }

            _LOGGER.debug("Options SAVED to config entry - scan_interval: %s",
                        result.get(CONF_SCAN_INTERVAL))

            return self.async_create_entry(title="", data=result)

        # Build select_areas dictionary -> map ID to name
        select_areas = {}
        for area in self._areas_config:
            area_id = str(area["area_id"])
            area_name = area["area_name"]
            if area_name and area_name.strip():
                select_areas[area_id] = area_name

        _LOGGER.debug("Loaded %d areas with names from config: %s", len(select_areas), select_areas)

        # If there are no areas with names, use fallback
        if not select_areas:
            _LOGGER.warning("No areas with names found, using numbered areas")
            select_areas = {str(i): f"Area {i}" for i in range(1, 9)}

        # Build macro lists with names for dropdown
        # Create list of macro names for dropdown options
        macro_names = []
        macro_name_to_id = {}  # Map name back to ID for saving
        for macro in self._macros_config:
            macro_id = str(macro["macro_id"])
            macro_name = macro.get("macro_name", "")
            if macro_name and macro_name.strip():
                macro_names.append(macro_name)
                macro_name_to_id[macro_name] = macro_id

        _LOGGER.debug("Loaded %d macros with names for dropdown", len(macro_names))

        # Build current options
        options = self._entry.options
        data = self._entry.data

        # Convert saved areas (integers) to strings for multi-select
        def to_str_list(lst):
            return [str(x) for x in lst] if lst else []

        # Filter defaults to remove areas that no longer exist in select_areas
        def filter_valid_areas(lst, available_areas):
            """Remove from lists areas that don't exist in available_areas."""
            return [x for x in lst if x in available_areas]

        # Log defaults BEFORE filter
        default_away_raw = to_str_list(options.get(CONF_AREAS_AWAY, []))
        default_home_raw = to_str_list(options.get(CONF_AREAS_HOME, []))
        default_night_raw = to_str_list(options.get(CONF_AREAS_NIGHT, []))
        default_disarm_raw = to_str_list(options.get(CONF_AREAS_DISARM, []))

        _LOGGER.debug("Raw defaults from options - away: %s, home: %s, night: %s, disarm: %s",
                    default_away_raw, default_home_raw, default_night_raw, default_disarm_raw)

        # Filter to keep only areas that exist in select_areas
        default_away = filter_valid_areas(default_away_raw, select_areas.keys())
        default_home = filter_valid_areas(default_home_raw, select_areas.keys())
        default_night = filter_valid_areas(default_night_raw, select_areas.keys())
        default_disarm = filter_valid_areas(default_disarm_raw, select_areas.keys())

        if (default_away != default_away_raw or default_home != default_home_raw or
            default_night != default_night_raw or default_disarm != default_disarm_raw):
            _LOGGER.warning("Filtered invalid areas - away: %s→%s, home: %s→%s, night: %s→%s, disarm: %s→%s",
                          default_away_raw, default_away,
                          default_home_raw, default_home,
                          default_night_raw, default_night,
                          default_disarm_raw, default_disarm)

        _LOGGER.debug("Building schema with filtered defaults - away: %s, home: %s, night: %s, disarm: %s",
                    default_away, default_home, default_night, default_disarm)

        # Build helper to convert macro ID to name for defaults
        def macro_id_to_name(macro_id):
            """Convert saved macro ID to macro name for dropdown default."""
            if not macro_id:
                return "No"
            # Find macro name by ID
            for macro in self._macros_config:
                if str(macro["macro_id"]) == str(macro_id):
                    return macro.get("macro_name", "")
            return "No"

        # Build schema - Order: Scenario → Areas → Arm Mode
        schema = vol.Schema({
            vol.Optional(
                CONF_CODE,
                default=data.get(CONF_CODE, ""),
            ): str,
            vol.Optional(
                CONF_TECH_CODE,
                default=data.get(CONF_TECH_CODE, ""),
            ): str,
            # Scan interval
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),            
            # AWAY MODE: Scenario → Areas → Arm Mode
            vol.Optional(
                CONF_MACRO_AWAY,
                default=macro_id_to_name(options.get(CONF_MACRO_AWAY, "")),
            ): vol.In(["No"] + macro_names),
            vol.Optional(
                CONF_AREAS_AWAY,
                default=default_away,
            ): cv.multi_select(select_areas),
            vol.Optional(
                CONF_ARM_MODE_AWAY,
                default=options.get(CONF_ARM_MODE_AWAY, ARM_MODE_NORMAL),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[ARM_MODE_NORMAL, ARM_MODE_IMMEDIATE, ARM_MODE_FORCED],
                    translation_key="arm_mode",
                )
            ),
            # HOME MODE: Scenario → Areas → Arm Mode
            vol.Optional(
                CONF_MACRO_HOME,
                default=macro_id_to_name(options.get(CONF_MACRO_HOME, "")),
            ): vol.In(["No"] + macro_names),
            vol.Optional(
                CONF_AREAS_HOME,
                default=default_home,
            ): cv.multi_select(select_areas),
            vol.Optional(
                CONF_ARM_MODE_HOME,
                default=options.get(CONF_ARM_MODE_HOME, ARM_MODE_NORMAL),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[ARM_MODE_NORMAL, ARM_MODE_IMMEDIATE, ARM_MODE_FORCED],
                    translation_key="arm_mode",
                )
            ),
            # NIGHT MODE: Scenario → Areas → Arm Mode
            vol.Optional(
                CONF_MACRO_NIGHT,
                default=macro_id_to_name(options.get(CONF_MACRO_NIGHT, "")),
            ): vol.In(["No"] + macro_names),
            vol.Optional(
                CONF_AREAS_NIGHT,
                default=default_night,
            ): cv.multi_select(select_areas),
            vol.Optional(
                CONF_ARM_MODE_NIGHT,
                default=options.get(CONF_ARM_MODE_NIGHT, ARM_MODE_NORMAL),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[ARM_MODE_NORMAL, ARM_MODE_IMMEDIATE, ARM_MODE_FORCED],
                    translation_key="arm_mode",
                )
            ),
            # Disarm scenario
            vol.Optional(
                CONF_MACRO_DISARM,
                default=macro_id_to_name(options.get(CONF_MACRO_DISARM, "")),
            ): vol.In(["No"] + macro_names),
            vol.Optional(
                CONF_AREAS_DISARM,
                default=default_disarm,
            ): cv.multi_select(select_areas),
        })

        return self.async_show_form(step_id="init", data_schema=schema)

    async def _load_areas_config(self):
        """Load areas configuration from JSON file."""
        try:
            data = self._entry.data
            ip_address = data.get(CONF_IP_ADDRESS)
            port = data.get(CONF_PORT, 80)

            # Build config file path
            config_file_path = f"/config/combivox_web/config_{ip_address}_{port}.json"

            if not os.path.exists(config_file_path):
                _LOGGER.warning("Config file not found: %s", config_file_path)
                return

            import json

            # Use async_executor to avoid blocking the event loop
            def _read_json():
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)

            config = await self.hass.async_add_executor_job(_read_json)

            if 'areas' in config:
                self._areas_config = config['areas']
                _LOGGER.info("Loaded %d areas for options flow", len(self._areas_config))

        except Exception as e:
            _LOGGER.error("Error loading areas config: %s", e)

    async def _load_macros_config(self):
        """Load macros configuration from JSON file."""
        try:
            data = self._entry.data
            ip_address = data.get(CONF_IP_ADDRESS)
            port = data.get(CONF_PORT, 80)

            # Build config file path
            config_file_path = f"/config/combivox_web/config_{ip_address}_{port}.json"

            if not os.path.exists(config_file_path):
                _LOGGER.debug("Config file not found: %s", config_file_path)
                return

            import json

            # Use async_executor to avoid blocking the event loop
            def _read_json():
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)

            config = await self.hass.async_add_executor_job(_read_json)

            if 'macros' in config:
                self._macros_config = config['macros']
                _LOGGER.info("Loaded %d macros for options flow", len(self._macros_config))

        except Exception as e:
            _LOGGER.error("Error loading macros config: %s", e)


@config_entries.HANDLERS.register(DOMAIN)
class CombivoxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Combivox Amica Web."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return CombivoxOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                # Create entry immediately without showing options
                return self.async_create_entry(title=info["title"], data=user_input)

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
