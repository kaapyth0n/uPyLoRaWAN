import time
import gc
from constants import BoilerDefaults

def celsius_to_resistance(temp):
    """Convert temperature to NTC 10K resistance value
    
    Args:
        temp (float): Temperature in Celsius
        
    Returns:
        float: Resistance in ohms
        
    Note: This is a simplified conversion for NTC 10K thermistor
    Beta value of 3950K is assumed
    """
    try:
        R25 = 10000.0  # Resistance at 25°C
        B = 3950.0     # Beta value
        T0 = 298.15    # 25°C in Kelvin
        
        # Convert to Kelvin
        temp_k = temp + 273.15
        
        # Calculate resistance
        resistance = R25 * pow(2.718281828, B * (1/temp_k - 1/T0))
        
        return max(100, min(100000, resistance))  # Limit to reasonable range
        
    except:
        return 10000  # Return room temperature resistance on error

def validate_temperature(temp):
    """Validate temperature value
    
    Args:
        temp (float): Temperature to validate
        
    Returns:
        tuple: (is_valid (bool), message (str))
    """
    if temp is None:
        return False, "Temperature is None"
        
    try:
        temp = float(temp)
    except:
        return False, "Invalid temperature format"
        
    if temp < BoilerDefaults.MIN_TEMP:
        return False, f"Temperature too low: {temp}"
    if temp > BoilerDefaults.MAX_TEMP:
        return False, f"Temperature too high: {temp}"
        
    return True, "Temperature valid"

def memory_stats():
    """Get memory statistics
    
    Returns:
        dict: Memory statistics
    """
    gc.collect()
    free = gc.mem_free()
    alloc = gc.mem_alloc()
    total = free + alloc
    
    return {
        'free': free,
        'allocated': alloc,
        'total': total,
        'percent_used': (alloc * 100) / total
    }

def format_time(timestamp=None):
    """Format timestamp for display
    
    Args:
        timestamp (int, optional): Unix timestamp. Uses current time if None
        
    Returns:
        str: Formatted time string
    """
    if timestamp is None:
        timestamp = time.time()
        
    try:
        time_tuple = time.localtime(timestamp)
        return "{:02d}:{:02d}:{:02d}".format(
            time_tuple[3],  # hours
            time_tuple[4],  # minutes
            time_tuple[5]   # seconds
        )
    except:
        return "??:??:??"

def format_uptime(seconds):
    """Format uptime duration
    
    Args:
        seconds (int): Duration in seconds
        
    Returns:
        str: Formatted uptime string
    """
    try:
        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24
        
        if days > 0:
            return f"{days}d {hours%24}h"
        elif hours > 0:
            return f"{hours}h {minutes%60}m"
        else:
            return f"{minutes}m {seconds%60}s"
    except:
        return "??"

def calc_temperature_stats(temp_history):
    """Calculate temperature statistics
    
    Args:
        temp_history (list): List of (timestamp, temperature) tuples
        
    Returns:
        dict: Temperature statistics
    """
    if not temp_history:
        return {
            'min': None,
            'max': None,
            'avg': None,
            'trend': 0
        }
        
    try:
        temps = [t[1] for t in temp_history]
        return {
            'min': min(temps),
            'max': max(temps),
            'avg': sum(temps) / len(temps),
            'trend': calc_trend(temp_history)
        }
    except:
        return {
            'min': None,
            'max': None,
            'avg': None,
            'trend': 0
        }

def calc_trend(history, window=300):
    """Calculate trend from history
    
    Args:
        history (list): List of (timestamp, value) tuples
        window (int): Time window in seconds
        
    Returns:
        float: Trend value (change per minute)
    """
    try:
        # Filter to window
        current_time = time.time()
        filtered = [(t, v) for t, v in history 
                   if current_time - t <= window]
        
        if len(filtered) < 2:
            return 0
            
        # Calculate linear regression slope
        times = [(t - filtered[0][0])/60.0 for t, _ in filtered]
        values = [v for _, v in filtered]
        
        n = len(times)
        sum_x = sum(times)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(times, values))
        sum_xx = sum(x * x for x in times)
        
        try:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
            return slope
        except:
            return 0
            
    except:
        return 0

def clamp(value, min_value, max_value):
    """Clamp value to range
    
    Args:
        value: Value to clamp
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Value clamped to range
    """
    return max(min_value, min(max_value, value))