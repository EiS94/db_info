"""Constants for the db_info integration."""

DOMAIN = "db_info"

# Configuration keys
CONF_START = "Startpunkt"
CONF_DESTINATION = "Ziel"
CONF_UPDATE_INTERVAL = "Update Intervall"
CONF_CONNECTION_TYPE = "Verkehrsmittel"
CONF_MAX_TRANSFERS = "Max_Umstiege"

# Default values
DEFAULT_UPDATE_INTERVAL = 10
DEFAULT_MAX_CONNECTIONS = 5
# None = unbegrenzt (aktuelles/bisheriges Verhalten)
DEFAULT_MAX_TRANSFERS = None

# Connection types
CONNECTION_ALL = "all"
CONNECTION_REGIONAL = "regional"
CONNECTION_LONG_DISTANCE = "long_distance"
CONNECTION_CUSTOM = "custom"

# Config key for custom transport types
CONF_TRANSPORT_TYPES = "Verkehrsmittel_Custom"

# All available transport types (DB API values)
ALL_TRANSPORT_TYPES = [
    "SBAHN", "UBAHN", "TRAM", "BUS", "SCHIFF", "AST/RUFBUS", "ICE", "IC/EC", "NAHVERKEHR", "SONSTIGE"
]

# Default selections per preset
TRANSPORT_TYPES_ALL = ALL_TRANSPORT_TYPES
TRANSPORT_TYPES_REGIONAL = ["SBAHN", "UBAHN", "TRAM", "BUS", "SCHIFF", "AST/RUFBUS", "NAHVERKEHR", "SONSTIGE"]
TRANSPORT_TYPES_LONG_DISTANCE = ["ICE", "IC/EC"]

# Entity suffixes
DATETIME_ENTITY_SUFFIX = "_departure_time"
USE_CUSTOM_TIME_SUFFIX = "_custom_time"
