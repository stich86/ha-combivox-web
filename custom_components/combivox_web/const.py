"""Constants for Combivox Amica Web integration."""

DOMAIN = "combivox_web"

# Configuration keys
CONF_IP_ADDRESS = "ip_address"
CONF_PORT = "port"
CONF_CODE = "code"
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
JSCRIPT9_URL = "/jscript9.js"
LABELZONE_URL = "/labelZone16.xml"
LABELAREA_URL = "/labelAree.xml"
LOGIN_URL = "/login.cgi"
LOGIN2_URL = "/login2.cgi"
INSAREA_URL = "/insAree.xml"
NUMMACRO_URL = "/numMacro.xml"
EXECCHANGEIMP_URL = "/execChangeImp.xml"
EXECDELMEM_URL = "/execDelMem.xml"
NUMTROUBLE_URL = "/numTrouble.xml"
NUMMEMPROG_URL = "/numMemProg.xml"
LABELMEM_URL = "/labelMem.xml"

# Trouble ID to description mapping (from labelTrouble.xml t0-t15)
TROUBLE_ID_TO_DESCRIPTION = {
    0: {"en": "Panel tamper", "it": "Tamper centrale"},
    1: {"en": "Panel network anomaly", "it": "Anomalia rete centrale"},
    2: {"en": "Panel fuse 1 failure", "it": "Avaria fusib.1 centrale"},
    3: {"en": "Panel fuse 2 failure", "it": "Avaria fusib.2 centrale"},
    4: {"en": "Panel fuse 3 failure", "it": "Avaria fusib.3 centrale"},
    5: {"en": "Phone line absent", "it": "Assenza linea telefonica"},
    6: {"en": "GSM anomaly", "it": "Anomalia GSM"},
    7: {"en": "Panel battery anomaly", "it": "Anomalia batteria centrale"},
    8: {"en": "Video battery anomaly", "it": "Anomalia batteria video"},
    9: {"en": "Panel battery alarm", "it": "Allarme batteria centrale"},
    10: {"en": "Video battery alarm", "it": "Allarme batteria video"},
    11: {"en": "Panel system tamper", "it": "Manomissione sistema centrale"},
    12: {"en": "Video system tamper", "it": "Manomissione sistema video"},
    13: {"en": "SIM RF module anomaly", "it": "Anomalia modulo rf SIM"},
    14: {"en": "SIM card expired", "it": "Scheda SIM scaduta"},
    15: {"en": "Insufficient credit", "it": "Credito residuo insufficiente"}
}

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
