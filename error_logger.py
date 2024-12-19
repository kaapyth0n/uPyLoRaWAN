import time
import json
import gc

class ErrorLogger:
    """Error logging system with persistence and severity levels"""
    
    # Severity levels
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4
    
    def __init__(self, controller, max_entries=50):
        """Initialize error logger
        
        Args:
            max_entries (int): Maximum number of entries to keep in memory
        """
        self.controller = controller
        self.max_entries = max_entries
        self.errors = []
        self.log_file = 'error_log.json'
        self.needs_saving = False
        self.last_save = 0
        self.save_interval = 300  # 5 minutes
        
        # Load existing errors
        self.load_errors()
        
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
            
        # Mark for saving
        self.needs_saving = True
        
        # Save periodically
        self._check_save()
        
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
        """Check if errors should be saved"""
        if not self.needs_saving:
            return
            
        current_time = time.time()
        if current_time - self.last_save > self.save_interval:
            self.save_errors()
            
    def save_errors(self):
        """Save errors to file"""
        if not self.needs_saving:
            return
            
        try:
            # Keep only essential data
            save_data = []
            for error in self.errors[-20:]:  # Save only last 20 errors
                save_data.append({
                    't': error['timestamp'],
                    'y': error['type'],
                    'm': error['message'],
                    's': error['severity']
                })
                
            with open(self.log_file, 'w') as f:
                json.dump(save_data, f)
                
            self.needs_saving = False
            self.last_save = time.time()
            
            gc.collect()  # Help with memory management
            
        except Exception as e:
            print(f"Error saving log: {e}")
            
    def load_errors(self):
        """Load errors from file"""
        try:
            with open(self.log_file, 'r') as f:
                save_data = json.load(f)
                
            # Convert back to full format
            self.errors = []
            for entry in save_data:
                self.errors.append({
                    'timestamp': entry['t'],
                    'type': entry['y'],
                    'message': entry['m'],
                    'severity': entry['s']
                })
                
        except:
            self.errors = []
            
    def clear_errors(self, min_severity=None):
        """Clear error log
        
        Args:
            min_severity (int, optional): Clear only errors >= this severity
        """
        if min_severity is None:
            self.errors = []
        else:
            self.errors = [e for e in self.errors if e['severity'] < min_severity]
            
        self.needs_saving = True
        self._check_save()
        
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