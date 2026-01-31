"""Diagnostics support for Combivox Amica Web."""
from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, TROUBLE_ID_TO_DESCRIPTION
from .base import CombivoxWebClient

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    _LOGGER.info("Generating diagnostic data for config entry %s", config_entry.entry_id)

    try:
        # Get client and coordinator
        client: CombivoxWebClient = hass.data[DOMAIN][config_entry.entry_id]["config"]
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

        # Filter sensitive data from config_entry_data (remove code, tech_code)
        filtered_data = dict(config_entry.data)
        filtered_data.pop("code", None)
        filtered_data.pop("tech_code", None)

        diagnostic_data = {
            "config_entry_data": filtered_data,
            "config_entry_options": dict(config_entry.options),
            "connection": {
                "ip_address": client.ip_address,
                "port": client.port,
                "base_url": client.base_url,
                "timeout": client.timeout,
            },
            "coordinator": {
                "update_interval": str(coordinator.update_interval),
                "last_update_success": coordinator.last_update_success,
                "last_update_time": coordinator.data.get("datetime") if coordinator.data else None,
            },
        }

        # Add zones config for name lookup
        zones_config = client.get_zones_config()

        # Add current state data
        if coordinator.data:
            diagnostic_data["current_state"] = {
                "alarm_state": coordinator.data.get("alarm_state"),
                "alarm_hex": coordinator.data.get("alarm_hex"),
                "status_hex": coordinator.data.get("status_hex"),
                "state": coordinator.data.get("state"),
                "armed_areas": coordinator.data.get("armed_areas", []),
            }

            # Add zones info (summary only)
            zones = coordinator.data.get("zones", {})
            if zones:
                # Get zone names from config (zones_config is a list of dicts with "id" and "name")
                zones_with_alarm = []
                for zid, zdata in zones.items():
                    if zdata.get("alarm_memory"):
                        # Find zone config by matching id
                        zone_config = None
                        for zc in zones_config:
                            if zc.get("id") == zid:
                                zone_config = zc
                                break
                        zone_name = zone_config.get("name") if zone_config else None
                        zones_with_alarm.append({
                            "zone_id": zid,
                            "zone_name": zone_name
                        })

                diagnostic_data["zones"] = {
                    "total_zones": len(zones),
                    "zones_with_alarm": zones_with_alarm,
                }

            # Add areas info
            areas = coordinator.data.get("areas", {})
            if areas:
                diagnostic_data["areas"] = {
                    "total_areas": len(areas),
                    "armed_areas": [
                        {"area_id": aid, "area_name": adata.get("name"), "state": "armed"}
                        for aid, adata in areas.items()
                        if adata.get("armed")
                    ],
                }

            # Add GSM info
            gsm = coordinator.data.get("gsm", {})
            if gsm:
                diagnostic_data["gsm"] = {
                    "status": gsm.get("status_hex"),
                    "operator": gsm.get("operator_hex"),
                    "signal_bars": gsm.get("signal_bars"),
                    "signal_percent": gsm.get("signal_percent"),
                }

            # Add anomalies info (from coordinator data + live panel query)
            anomalies = coordinator.data.get("anomalies", {})
            if anomalies:
                diagnostic_data["anomalies"] = {
                    "hex": anomalies.get("anomalies_hex"),
                }

        # Add configuration info
        areas_config = client.get_areas_config()
        macros_config = client.get_macros_config()

        diagnostic_data["configuration"] = {
            "zones_count": len(client.get_zones_config()),
            "areas_count": len(areas_config),
            "macros_count": len(macros_config),
            "areas": areas_config,
            "macros": macros_config,
            "alarm_control_panel_config": {
                "away_uses_macro": bool(config_entry.options.get("conf_macro_away")),
                "home_uses_macro": bool(config_entry.options.get("conf_macro_home")),
                "night_uses_macro": bool(config_entry.options.get("conf_macro_night")),
                "disarm_uses_macro": bool(config_entry.options.get("conf_macro_disarm")),
            },
        }

        # Add device info
        device_info = client.get_device_info()
        if device_info:
            diagnostic_data["device"] = {
                "variant": device_info.get("variant"),
            }

        # Fetch active anomaly and add to anomalies section
        try:
            anomaly_id = await client.get_anomalies_info()
            # Ensure anomalies section exists
            if "anomalies" not in diagnostic_data:
                diagnostic_data["anomalies"] = {}

            if anomaly_id is not None:
                anomaly_descriptions = TROUBLE_ID_TO_DESCRIPTION.get(anomaly_id, {"en": f"Anomaly {anomaly_id}", "it": f"Anomalia {anomaly_id}"})
                diagnostic_data["anomalies"]["active_anomaly"] = {
                    "id": anomaly_id,
                    "description_en": anomaly_descriptions.get("en"),
                    "description_it": anomaly_descriptions.get("it")
                }
            else:
                diagnostic_data["anomalies"]["active_anomaly"] = None
        except Exception as e:
            _LOGGER.warning("Failed to get anomalies info for diagnostics: %s", e)
            if "anomalies" not in diagnostic_data:
                diagnostic_data["anomalies"] = {}
            diagnostic_data["anomalies"]["error"] = str(e)

        # Fetch and add alarm memory info
        try:
            alarm_memory = await client.get_alarm_memory_info()
            diagnostic_data["alarm_memory"] = {
                "count": len(alarm_memory),
                "entries": alarm_memory,
            }
        except Exception as e:
            _LOGGER.warning("Failed to get alarm memory info for diagnostics: %s", e)
            diagnostic_data["alarm_memory"] = {"error": str(e)}

        _LOGGER.info("Diagnostic data generated successfully")
        return diagnostic_data

    except Exception as e:
        _LOGGER.error("Error generating diagnostic data: %s", e)
        return {"error": str(e)}
