import time

class TemperatureController:
    """Advanced temperature controller with trend analysis"""
    
    def __init__(self, config_manager):
        """Initialize temperature controller
        
        Args:
            config_manager: Reference to configuration manager
        """
        self.config = config_manager
        self.temp_history = []  # Replace deque with a list
        self.max_history_len = 60  # Store up to 60 readings manually
        self.error_history = []  # Same change for error history
        self.max_error_len = 10  # Store up to 10 errors manually
        self.last_control_time = 0
        self.integral_error = 0
        self.last_error = 0
        self.min_control_interval = 1.0  # Minimum time between control decisions
        
        # Add public variables for PID components
        self.p_value = None
        self.i_value = None
        self.d_value = None

    def add_temp_to_history(self, timestamp, temp):
        """Add a temperature reading to the history"""
        if len(self.temp_history) >= self.max_history_len:
            self.temp_history.pop(0)  # Remove the oldest entry
        self.temp_history.append((timestamp, temp))
    
    def add_error_to_history(self, error):
        """Add an error value to the history"""
        if len(self.error_history) >= self.max_error_len:
            self.error_history.pop(0)  # Remove the oldest entry
        self.error_history.append(error)
        
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
        self.add_temp_to_history(time.time(), current_temp)
        self.add_error_to_history(error)
        
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

    def calculate_soft_pid_output(self, current_temp, setpoint, dt):
        """Calculate software PID output using standard form parameters
        
        Args:
            current_temp (float): Current temperature reading
            setpoint (float): Target temperature
            dt (float): Time since last control action
            
        Returns:
            float: Output value (0-max_volts)
        """
        if current_temp is None or setpoint is None:
            return 0.0
            
        # Get PID parameters - standard form
        kp = self.config.get_param('pid_kp_std')
        ti = self.config.get_param('pid_ti_std')
        td = self.config.get_param('pid_td_std')
        
        # Safety checks for parameters
        if kp is None or kp <= 0:
            kp = 1.0  # Default value
        if ti is None or ti <= 0:
            ti = 100.0  # Prevent division by zero
        if td is None:
            td = 0.0  # Default to no derivative action
        
        # Get min/max voltage limits
        pid_min = self.config.get_param('pid_min_volts') or 0.0
        pid_max = self.config.get_param('pid_max_volts') or 10.0
        
        # Calculate error
        error = setpoint - current_temp
        
        # Store history
        self.add_temp_to_history(time.time(), current_temp)
        self.add_error_to_history(error)
        
        # Calculate proportional term
        p_term = kp * error
        
        # Calculate derivative term
        if dt > 0:
            # Use error difference for derivative calculation
            derivative = (error - self.last_error) / dt
        else:
            derivative = 0
        
        d_term = kp * td * derivative
        
        # Calculate integral term with dynamic anti-windup
        # Limit integral based on available control range after P contribution
        
        # Update integral with error contribution
        self.integral_error += error * dt
        
        # Calculate integral term
        i_term = kp * self.integral_error / ti
        
        # Apply dynamic limits to integral term based on P-term
        # This ensures the total output stays within range
        if p_term >= pid_max:
            # P term already at max, integral can only reduce output
            i_max = 0
            i_min = pid_min - pid_max
        elif p_term <= pid_min:
            # P term at or below min, integral can only increase output
            i_max = pid_max - pid_min
            i_min = 0
        else:
            # P term in range, limit integral to keep total output in range
            i_max = pid_max - p_term
            i_min = pid_min - p_term
        
        # Apply limits to integral term
        if i_term > i_max:
            i_term = i_max
            # Recalculate integral_error to match limited i_term
            self.integral_error = i_term * ti / kp
        elif i_term < i_min:
            i_term = i_min
            # Recalculate integral_error to match limited i_term
            self.integral_error = i_term * ti / kp
        
        # Calculate final output
        output = p_term + i_term + d_term
        
        # Store the PID components as public variables for MQTT reporting
        self.p_value = p_term
        self.i_value = i_term
        self.d_value = d_term
        
        # Apply global limits
        output = max(pid_min, min(pid_max, output))
        
        # Store last error for next derivative calculation
        self.last_error = error
        
        return output