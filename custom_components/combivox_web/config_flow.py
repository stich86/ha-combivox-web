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

from . import CONF_AREAS_CUSTOM_BYPASS, CONF_ARM_MODE_CUSTOM_BYPASS, CONF_MACRO_CUSTOM_BYPASS, CannotConnect, InvalidAuth
from .base import CombivoxWebClient
from .const import (
    DOMAIN,
    CONF_IP_ADDRESS,
    CONF_CODE,
    CONF_PORT,
    CONF_AREAS_AWAY,
    CONF_AREAS_HOME,
    CONF_AREAS_NIGHT,
    CONF_AREAS_CUSTOM_BYPASS,
    CONF_AREAS_DISARM,
    CONF_ARM_MODE_AWAY,
    CONF_ARM_MODE_HOME,
    CONF_ARM_MODE_NIGHT,
    CONF_ENABLE_CUSTOM_BYPASS,
    CONF_ARM_MODE_CUSTOM_BYPASS,
    CONF_SCAN_INTERVAL,
    CONF_MACRO_AWAY,
    CONF_MACRO_HOME,
    CONF_MACRO_NIGHT,
    CONF_MACRO_CUSTOM_BYPASS,
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
        self._general_data: Dict[str, Any] = {}

    async def async_step_init(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """First step: General settings and exclusions."""
        if user_input is not None:
            # Salviamo temporaneamente la scelta nel contesto dell'istanza
            self._general_data = user_input
            # Passiamo al prossimo step per configurare i singoli modi
            return await self.async_step_modes()

        options = self._entry.options
        data = self._entry.data

        schema = vol.Schema({
            vol.Optional(CONF_CODE, default=data.get(CONF_CODE, "")): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
            vol.Optional(CONF_ENABLE_CUSTOM_BYPASS, default=options.get(CONF_ENABLE_CUSTOM_BYPASS, False)): bool,
        })

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_modes(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Second step: Configure arming modes based on first step selection."""
        if not self._areas_config:
            await self._load_areas_config()
        if not self._macros_config:
            await self._load_macros_config()

        options = self._entry.options
        enable_bypass = self._general_data.get(CONF_ENABLE_CUSTOM_BYPASS, False)

        if user_input is not None:
            # Uniamo i dati del primo step con quelli del secondo
            user_code = self._general_data.get(CONF_CODE, "")
            if user_code and len(user_code) < 6:
                user_code = user_code.ljust(6, '0')

            def to_int_list(lst):
                return [int(x) for x in lst] if lst else []

            def macro_name_to_id(macro_name):
                if not macro_name or macro_name in ("", "No") or macro_name is None:
                    return ""
                for macro in self._macros_config:
                    if macro.get("macro_name") == macro_name:
                        return str(macro["macro_id"])
                return ""

            areas_custom_bypass = to_int_list(user_input.get(CONF_AREAS_CUSTOM_BYPASS, [])) if enable_bypass else [] 
            macro_custom_bypass = macro_name_to_id(user_input.get(CONF_MACRO_CUSTOM_BYPASS, "")) if enable_bypass else ""
            arm_mode_custom_bypass = user_input.get(CONF_ARM_MODE_CUSTOM_BYPASS, ARM_MODE_NORMAL) if enable_bypass else ARM_MODE_NORMAL 

            result = {
                CONF_CODE: user_code,
                CONF_SCAN_INTERVAL: self._general_data.get(CONF_SCAN_INTERVAL),
                CONF_ENABLE_CUSTOM_BYPASS: enable_bypass,
                CONF_AREAS_AWAY: to_int_list(user_input.get(CONF_AREAS_AWAY, [])),
                CONF_AREAS_HOME: to_int_list(user_input.get(CONF_AREAS_HOME, [])),
                CONF_AREAS_NIGHT: to_int_list(user_input.get(CONF_AREAS_NIGHT, [])),
                CONF_AREAS_CUSTOM_BYPASS: areas_custom_bypass,
                CONF_AREAS_DISARM: to_int_list(user_input.get(CONF_AREAS_DISARM, [])),
                CONF_ARM_MODE_AWAY: user_input.get(CONF_ARM_MODE_AWAY, ARM_MODE_NORMAL),
                CONF_ARM_MODE_HOME: user_input.get(CONF_ARM_MODE_HOME, ARM_MODE_NORMAL),
                CONF_ARM_MODE_NIGHT: user_input.get(CONF_ARM_MODE_NIGHT, ARM_MODE_NORMAL),
                CONF_ARM_MODE_CUSTOM_BYPASS: arm_mode_custom_bypass,
                CONF_MACRO_AWAY: macro_name_to_id(user_input.get(CONF_MACRO_AWAY, "")),
                CONF_MACRO_HOME: macro_name_to_id(user_input.get(CONF_MACRO_HOME, "")),
                CONF_MACRO_NIGHT: macro_name_to_id(user_input.get(CONF_MACRO_NIGHT, "")),
                CONF_MACRO_CUSTOM_BYPASS: macro_custom_bypass,
                CONF_MACRO_DISARM: macro_name_to_id(user_input.get(CONF_MACRO_DISARM, "")),
            }
            return self.async_create_entry(title="", data=result)

        # Generazione liste aree e macro (identica a prima)
        select_areas = {str(area["area_id"]): area["area_name"] for area in self._areas_config if area.get("area_name", "").strip()}
        if not select_areas:
            select_areas = {str(i): f"Area {i}" for i in range(1, 9)}

        macro_names = [macro["macro_name"] for macro in self._macros_config if macro.get("macro_name", "").strip()]

        def to_str_list(lst):
            return [str(x) for x in lst] if lst else []

        def filter_valid_areas(lst, available_areas):
            return [x for x in lst if x in available_areas]

        def macro_id_to_name(macro_id):
            if not macro_id: return "No"
            for macro in self._macros_config:
                if str(macro["macro_id"]) == str(macro_id): return macro.get("macro_name", "")
            return "No"

        # Costruiamo lo schema del secondo step
        schema_dict = {
            # AWAY MODE
            vol.Optional(CONF_MACRO_AWAY, default=macro_id_to_name(options.get(CONF_MACRO_AWAY, ""))): vol.In(["No"] + macro_names),
            vol.Optional(CONF_AREAS_AWAY, default=filter_valid_areas(to_str_list(options.get(CONF_AREAS_AWAY, [])), select_areas.keys())): cv.multi_select(select_areas),
            vol.Optional(CONF_ARM_MODE_AWAY, default=options.get(CONF_ARM_MODE_AWAY, ARM_MODE_NORMAL)): SelectSelector(SelectSelectorConfig(options=[ARM_MODE_NORMAL, ARM_MODE_IMMEDIATE, ARM_MODE_FORCED], translation_key="arm_mode")),
            
            # HOME MODE
            vol.Optional(CONF_MACRO_HOME, default=macro_id_to_name(options.get(CONF_MACRO_HOME, ""))): vol.In(["No"] + macro_names),
            vol.Optional(CONF_AREAS_HOME, default=filter_valid_areas(to_str_list(options.get(CONF_AREAS_HOME, [])), select_areas.keys())): cv.multi_select(select_areas),
            vol.Optional(CONF_ARM_MODE_HOME, default=options.get(CONF_ARM_MODE_HOME, ARM_MODE_NORMAL)): SelectSelector(SelectSelectorConfig(options=[ARM_MODE_NORMAL, ARM_MODE_IMMEDIATE, ARM_MODE_FORCED], translation_key="arm_mode")),
            
            # NIGHT MODE
            vol.Optional(CONF_MACRO_NIGHT, default=macro_id_to_name(options.get(CONF_MACRO_NIGHT, ""))): vol.In(["No"] + macro_names),
            vol.Optional(CONF_AREAS_NIGHT, default=filter_valid_areas(to_str_list(options.get(CONF_AREAS_NIGHT, [])), select_areas.keys())): cv.multi_select(select_areas),
            vol.Optional(CONF_ARM_MODE_NIGHT, default=options.get(CONF_ARM_MODE_NIGHT, ARM_MODE_NORMAL)): SelectSelector(SelectSelectorConfig(options=[ARM_MODE_NORMAL, ARM_MODE_IMMEDIATE, ARM_MODE_FORCED], translation_key="arm_mode")),
        }

        # Mostra CUSTOM_BYPASS solo se NON è stato escluso nel primo step
        if enable_bypass:
            schema_dict.update({
                vol.Optional(CONF_MACRO_CUSTOM_BYPASS, default=macro_id_to_name(options.get(CONF_MACRO_CUSTOM_BYPASS, ""))): vol.In(["No"] + macro_names),
                vol.Optional(CONF_AREAS_CUSTOM_BYPASS, default=filter_valid_areas(to_str_list(options.get(CONF_AREAS_CUSTOM_BYPASS, [])), select_areas.keys())): cv.multi_select(select_areas),
                vol.Optional(CONF_ARM_MODE_CUSTOM_BYPASS, default=options.get(CONF_ARM_MODE_CUSTOM_BYPASS, ARM_MODE_NORMAL)): SelectSelector(SelectSelectorConfig(options=[ARM_MODE_NORMAL, ARM_MODE_IMMEDIATE, ARM_MODE_FORCED], translation_key="arm_mode")),
            })

        # DISARM
        schema_dict.update({
            vol.Optional(CONF_MACRO_DISARM, default=macro_id_to_name(options.get(CONF_MACRO_DISARM, ""))): vol.In(["No"] + macro_names),
            vol.Optional(CONF_AREAS_DISARM, default=filter_valid_areas(to_str_list(options.get(CONF_AREAS_DISARM, [])), select_areas.keys())): cv.multi_select(select_areas),
        })

        return self.async_show_form(step_id="modes", data_schema=vol.Schema(schema_dict))

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
