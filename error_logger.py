import time
import gc
class ErrorLogger:
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4
    def __init__(self, controller, max_entries=50):
        self.controller = controller
        self.max_entries = max_entries
        self.errors = []
        self.log_file = 'error_log.json'
        self.needs_saving = False
        self.last_save = 0
        self.save_interval = 300
    def log_error(self, error_type, message, severity=2):
        error_entry = {
            'timestamp': time.time(),
            'type': error_type,
            'message': message[:100],
            'severity': severity
        }
        self.errors.append(error_entry)
        while len(self.errors) > self.max_entries:
            self.errors.pop(0)
        if severity >= self.WARNING:
            pass
        try:
            if hasattr(self.controller, 'mqtt_handler') and \
            self.controller.mqtt_handler.initialized:
                self.controller.mqtt_handler.publish_error(
                    error_type, message, severity
                )
        except:
            pass
    def get_recent_errors(self, count=10, min_severity=1):
        filtered = [e for e in self.errors if e['severity'] >= min_severity]
        return filtered[-count:]
    def _check_save(self):
        pass
    def save_errors(self):
        gc.collect()
    def load_errors(self):
        pass
    def clear_errors(self, min_severity=None):
        if min_severity is None:
            self.errors = []
        else:
            self.errors = [e for e in self.errors if e['severity'] < min_severity]
        gc.collect()
    def get_error_stats(self):
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