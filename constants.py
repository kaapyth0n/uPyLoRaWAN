class BoilerDefaults:
    """Default values for boiler operation"""
    
    # Temperature limits
    MIN_TEMP = 20.0        # Minimum allowed temperature (°C)
    MAX_TEMP = 85.0        # Maximum allowed temperature (°C)
    DEFAULT_TEMP = 40.0    # Default target temperature (°C)
    
    # Control parameters
    HYSTERESIS = 5.0       # Temperature hysteresis (°C)
    MIN_ON_TIME = 60       # Minimum burner on time (seconds)
    MIN_OFF_TIME = 60      # Minimum burner off time (seconds)
    
    # Operation modes
    MODE_RELAY = 'relay'   # Direct relay control mode
    MODE_SENSOR = 'sensor' # Temperature sensor simulation mode
    DEFAULT_MODE = MODE_RELAY
    
    # Safety parameters
    WATCHDOG_TIMEOUT = 3600    # Communication timeout (seconds)
    MAX_TEMP_AGE = 300         # Maximum temperature reading age (seconds)
    SAFETY_MARGIN = 2.0        # Safety margin below max temp (°C)
    
    # Communication parameters
    STATUS_INTERVAL = 300      # Status update interval (seconds)
    MAX_RETRIES = 3           # Maximum command retry attempts

class ErrorCodes:
    """Error codes for system events"""
    
    # Temperature errors
    TEMP_READ_FAIL = 'E001'
    TEMP_TOO_HIGH = 'E002'
    TEMP_TOO_LOW = 'E003'
    TEMP_SENSOR_TIMEOUT = 'E004'
    
    # Communication errors
    COMM_TIMEOUT = 'E101'
    LORA_INIT_FAIL = 'E102'
    LORA_SEND_FAIL = 'E103'
    
    # Control errors
    CONTROL_TIMEOUT = 'E201'
    RELAY_FAIL = 'E202'
    SENSOR_FAIL = 'E203'
    
    # Hardware errors
    DISPLAY_FAIL = 'E301'
    MODULE_MISSING = 'E302'
    CONFIG_ERROR = 'E303'

class SystemParameters:
    """System-wide parameters"""
    
    # Module slots
    DISPLAY_SLOT = 2       # IND1-1.1 module slot
    IO_MODULE_SLOT = 6     # IO1-2.2 module slot
    SSR_MODULE_SLOT = 5    # SSR2-2.10 module slot
    
    # Memory limits
    MAX_ERROR_LOG = 50     # Maximum stored error entries
    MAX_TEMP_HISTORY = 60  # Maximum temperature history entries
    
    # Display update
    DISPLAY_UPDATE_INTERVAL = 1.0  # Display update interval (seconds)
    MAX_MESSAGE_LENGTH = 21        # Maximum message length
    
    # Control parameters
    CONTROL_INTERVAL = 1.0     # Control loop interval (seconds)
    TREND_WINDOW = 300         # Temperature trend window (seconds)
    
    # File names
    CONFIG_FILE = 'boiler_config.json'
    ERROR_LOG_FILE = 'error_log.json'
    BACKUP_CONFIG = 'boiler_config.backup.json'

class MessageTypes:
    """LoRaWAN message type definitions"""
    
    # Message types
    STATUS = 0
    CONFIG = 1
    COMMAND = 2
    QUERY = 3
    DIAGNOSTIC = 4
    ERROR = 5
    
    # Command subtypes
    CMD_RESET = 0
    CMD_DIAGNOSTIC = 1
    CMD_CLEAR_ERRORS = 2
    
    # Query subtypes
    QUERY_STATUS = 0
    QUERY_DIAGNOSTIC = 1
    QUERY_ERRORS = 2
    
    # Status fields
    STATUS_MODE = 0
    STATUS_TEMP = 1
    STATUS_SETPOINT = 2
    STATUS_HEATING = 3