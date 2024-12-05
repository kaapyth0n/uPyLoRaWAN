import time
from collections import deque

class TemperatureController:
    """Advanced temperature controller with trend analysis"""
    
    def __init__(self, config_manager):
        """Initialize temperature controller
        
        Args:
            config_manager: Reference to configuration manager
        """
        self.config = config_manager
        self.temp_history = deque(maxlen=60)  # Store last 60 readings
        self.error_history = deque(maxlen=10)  # Store last 10 error values
        self.last_control_time = 0
        self.integral_error = 0
        self.last_error = 0
        self.min_control_interval = 1.0  # Minimum time between control decisions
        
    def calculate_control_action(self, current_temp, setpoint, dt):
        """Calculate control action using advanced algorithm
        
        Args:
            current_temp (float): Current temperature reading
            setpoint (float): Target temperature
            dt (float): Time since last control action
            
        Returns:
            tuple: (should_heat (bool), error_magnitude (float))
        """
        if current_temp is None or setpoint is None:
            return False, 0
            
        # Basic safety checks
        if current_temp > self.config.get_param('max_temp'):
            return False, 0
            
        # Calculate basic error
        error = setpoint - current_temp
        
        # Store history
        self.temp_history.append((time.time(), current_temp))
        self.error_history.append(error)
        
        # Calculate integral error with anti-windup
        self.integral_error += error * dt
        max_integral = 20.0  # Prevent excessive integral term
        self.integral_error = max(-max_integral, min(max_integral, self.integral_error))
        
        # Calculate derivative term
        derivative = (error - self.last_error) / dt if dt > 0 else 0
        
        # Get control parameters
        hysteresis = self.config.get_param('hysteresis')
        
        # Calculate temperature trend
        trend = self.calculate_trend()
        
        # Decision logic
        should_heat = False
        
        # Simple hysteresis control
        if abs(error) > hysteresis:
            should_heat = error > 0
        else:
            # Use trend information for fine control
            if trend < -0.1:  # Temperature falling
                should_heat = error >= -hysteresis/2
            elif trend > 0.1:  # Temperature rising
                should_heat = error > hysteresis/2
            else:  # Stable temperature
                should_heat = error > 0
                
        # Additional checks based on trend and history
        if should_heat:
            # Check if heating too aggressive
            if trend > 0.5:  # Temperature rising too fast
                should_heat = False
        else:
            # Check if cooling too aggressive
            if trend < -0.5:  # Temperature falling too fast
                should_heat = True
                
        self.last_error = error
        return should_heat, abs(error)
        
    def calculate_trend(self):
        """Calculate temperature trend from history
        
        Returns:
            float: Temperature change rate (°C/minute)
        """
        if len(self.temp_history) < 2:
            return 0
            
        # Calculate linear regression slope
        times = [(t - self.temp_history[0][0])/60.0 for t, _ in self.temp_history]
        temps = [t for _, t in self.temp_history]
        
        n = len(times)
        sum_x = sum(times)
        sum_y = sum(temps)
        sum_xy = sum(x * y for x, y in zip(times, temps))
        sum_xx = sum(x * x for x in times)
        
        try:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
            return slope
        except:
            return 0
            
    def get_control_stats(self):
        """Get control statistics
        
        Returns:
            dict: Control statistics
        """
        return {
            'trend': self.calculate_trend(),
            'integral_error': self.integral_error,
            'last_error': self.last_error,
            'error_history': list(self.error_history),
            'temp_history': list(self.temp_history)
        }
        
    def reset(self):
        """Reset controller state"""
        self.temp_history.clear()
        self.error_history.clear()
        self.integral_error = 0
        self.last_error = 0
        self.last_control_time = 0