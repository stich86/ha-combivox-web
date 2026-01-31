"""Constants for Combivox Amica Web integration."""

DOMAIN = "combivox_web"

# Configuration keys
CONF_IP_ADDRESS = "ip_address"
CONF_PORT = "port"
CONF_CODE = "code"
CONF_TECH_CODE = "tech_code"
CONF_AREAS_AWAY = "areas_away"
CONF_AREAS_HOME = "areas_home"
CONF_AREAS_NIGHT = "areas_night"
CONF_AREAS_DISARM = "areas_disarm"
CONF_ARM_MODE_AWAY = "arm_mode_away"
CONF_ARM_MODE_HOME = "arm_mode_home"
CONF_ARM_MODE_NIGHT = "arm_mode_night"
CONF_SCAN_INTERVAL = "scan_interval"

# Macro mapping configuration
CONF_MACRO_AWAY = "macro_away"
CONF_MACRO_HOME = "macro_home"
CONF_MACRO_NIGHT = "macro_night"
CONF_MACRO_DISARM = "macro_disarm"

# Defaults
DEFAULT_SCAN_INTERVAL = 5

# Authentication permutations
PERMMANUAL = [2, 7, 6, 1, 4, 5, 8, 3]

# Regex patterns for system info parsing
MODEL_PATTERN = r'Centrale:\s+(\S+(?:\s+\S+)*)'
VERSION_PATTERN = r'Ver\.:\s+(\S+(?:\s+\S+)*)'
SERIAL_NUMBER_PATTERN = r'(.*?)\s*\(\s*S/N:\s*(.+?)\s*\)'
FIRMWARE_FULL_PATTERN = r'Firmware ver\.:\s+([^,\n]+),\s*(Amicaweb\s*(?:PLUS)?(?:\s*\([^)]+\))?)'
FIRMWARE_FALLBACK_PATTERN = r'Firmware ver\.:\s+(\S+)'
AMICAWEB_VERSION_PATTERN = r'(\d+(?:\.\d+)?)'

# Macro execution response code
MACRO_SUCCESS_CODE = 31  # 0x31 = success

# Arm modes
ARM_MODE_NORMAL = "normal"
ARM_MODE_IMMEDIATE = "immediate"
ARM_MODE_FORCED = "forced"

# GSM Operator hex to name mapping (translatable)
GSM_OPERATOR_HEX_TO_NAME = {
    "00": "other",
    "01": "vodafone",
    "02": "tim",
    "03": "wind",
    "04": "combivox",
    "FF": "unknown"
}

# GSM Status hex to HA state mapping (translatable)
GSM_STATUS_HEX_TO_HA_STATE = {
    "05": "no_sim",
    "04": "searching",
    "18": "ok",
    "08": "ok",
    "00": "ok"
}

# Anomalies hex to HA state mapping (translatable) - 171st byte from <si> start (after FFFFFF marker)
ANOMALIES_HEX_TO_HA_STATE = {
    "00": "ok",
    "40": "gsm_trouble"
}

# XML endpoints
STATUS_URL = "/status9.xml"
LABELZONE_URL = "/labelZone16.xml"
LABELAREA_URL = "/labelAree.xml"
LOGIN_URL = "/login.cgi"
LOGIN2_URL = "/login2.cgi"
INSAREA_URL = "/insAree.xml"
NUMMACRO_URL = "/numMacro.xml"
EXECCHANGEIMP_URL = "/execChangeImp.xml"
EXECDELMEM_URL = "/execDelMem.xml"

# Alarm hex to HA state mapping (priority states checked first)
ALARM_HEX_TO_HA_STATE = {
    "8C": "triggered",           # in_allarme
    "8D": "pending",             # pre_allarme
    "0E": "arming",              # inserimento_ritardato
    "0D": "arming",              # non_in_allarme_con_ritardo
    "88": "triggered",           # in_allarme_gsm_escluso
}

# Data keys
DATA_COORDINATOR = "coordinator"
DATA_UPDATE_LISTENER = "update_listener"
DATA_CONFIG = "config"
