import time
import gc

class ErrorLogger:
    """Error logging system that keeps logs in memory only
    
    This version eliminates filesystem writes to reduce wear and save space.
    Error logs are kept in memory and transmitted via MQTT when available.
    
    Severity levels:
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4
    """
    
    # Severity levels
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4
    
    def __init__(self, controller, max_entries=50):
        """Initialize error logger
        
        Args:
            controller: Reference to main controller for MQTT access
            max_entries (int): Maximum number of entries to keep in memory
        """
        self.controller = controller
        self.max_entries = max_entries
        self.errors = []
        # These attributes are kept for API compatibility but not used
        self.log_file = 'error_log.json'
        self.needs_saving = False
        self.last_save = 0
        self.save_interval = 300  # 5 minutes
        
        # We no longer load from file, starting with a clean history
        print("Initialized memory-only error logger")
        
    def log_error(self, error_type, message, severity=2):
        """Log an error with timestamp and severity
        
        Args:
            error_type (str): Type of error
            message (str): Error message
            severity (int): Error severity (1=info to 4=critical)
        """
        # Create error entry
        error_entry = {
            'timestamp': time.time(),
            'type': error_type,
            'message': message[:100],  # Limit message length
            'severity': severity
        }
        
        # Add to list
        self.errors.append(error_entry)
        
        # Trim if needed
        while len(self.errors) > self.max_entries:
            self.errors.pop(0)  # Remove oldest entry
        
        # Print critical errors immediately
        if severity >= self.WARNING:
            print(f"ERROR: {error_type} - {message}")
            
        # Publish via MQTT if available
        try:
            if hasattr(self.controller, 'mqtt_handler') and \
            self.controller.mqtt_handler.initialized:
                self.controller.mqtt_handler.publish_error(
                    error_type, message, severity
                )
        except:
            pass # Don't let MQTT issues affect error logging
            
    def get_recent_errors(self, count=10, min_severity=1):
        """Get most recent errors
        
        Args:
            count (int): Number of errors to return
            min_severity (int): Minimum severity level
            
        Returns:
            list: Recent error entries
        """
        filtered = [e for e in self.errors if e['severity'] >= min_severity]
        return filtered[-count:]
        
    def _check_save(self):
        """Stub method for API compatibility
        No longer saves to file
        """
        pass
            
    def save_errors(self):
        """Stub method for API compatibility
        No longer saves to file
        """
        # Force garbage collection to free memory
        gc.collect()
            
    def load_errors(self):
        """Stub method for API compatibility
        No longer loads from file
        """
        # Already initialized with empty list
        pass
            
    def clear_errors(self, min_severity=None):
        """Clear error log
        
        Args:
            min_severity (int, optional): Clear only errors >= this severity
        """
        if min_severity is None:
            self.errors = []
        else:
            self.errors = [e for e in self.errors if e['severity'] < min_severity]
            
        # Force garbage collection after clearing errors
        gc.collect()
        
    def get_error_stats(self):
        """Get error statistics
        
        Returns:
            dict: Error statistics
        """
        stats = {
            'total': len(self.errors),
            'by_severity': {
                self.INFO: 0,
                self.WARNING: 0,
                self.ERROR: 0,
                self.CRITICAL: 0
            },
            'by_type': {}
        }
        
        for error in self.errors:
            stats['by_severity'][error['severity']] += 1
            
            error_type = error['type']
            if error_type not in stats['by_type']:
                stats['by_type'][error_type] = 0
            stats['by_type'][error_type] += 1
            
        return stats