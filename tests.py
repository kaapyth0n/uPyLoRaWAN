import time
import gc
import network

class TestResult:
    """Test result container"""
    def __init__(self, name, passed, message=""):
        self.name = name
        self.passed = passed
        self.message = message
        self.timestamp = time.time()

class TestRunner:
    """System test framework"""
    
    def __init__(self, controller):
        """Initialize test runner
        
        Args:
            controller: Reference to main controller
        """
        self.controller = controller
        self.results = []
        
    def run_all_tests(self):
        """Run all system tests
        
        Returns:
            list: Test results
        """
        self.results = []
        
        # Run tests
        self.test_temperature_sensor()
        self.test_display()
        self.test_lora()
        self.test_control()
        self.test_config()
        self.test_updates()
        
        return self.results
    
    def test_updates(self):
        """Test update status"""
        try:
            if not network.WLAN(network.STA_IF).isconnected():
                self.results.append(TestResult(
                    "Updates",
                    True,
                    "No WiFi connection"
                ))
                return

            from update_checker import get_current_versions, is_update_available
            versions = get_current_versions()
            update_available = is_update_available()
            
            self.results.append(TestResult(
                "Updates",
                True,
                f"{'Update available' if update_available else 'System up to date'}"
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                "Updates",
                False,
                f"Update check failed: {str(e)}"
            ))
        
    def test_temperature_sensor(self):
        """Test temperature sensor functionality"""
        try:
            # Test temperature reading
            temp = self.controller.read_temperature()
            if temp is None:
                self.results.append(TestResult(
                    "Temperature Sensor",
                    False,
                    "Failed to read temperature"
                ))
                return
                
            # Validate reading
            if temp < -50 or temp > 150:
                self.results.append(TestResult(
                    "Temperature Sensor",
                    False,
                    f"Invalid temperature: {temp}"
                ))
                return
                
            self.results.append(TestResult(
                "Temperature Sensor",
                True,
                f"Temperature: {temp}°C"
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                "Temperature Sensor",
                False,
                f"Test error: {str(e)}"
            ))
            
    def test_display(self):
        """Test display functionality"""
        try:
            # Try to show test message
            self.controller.display_manager.show_status(
                "Test Message",
                "Display Test",
                "Running..."
            )
            
            self.results.append(TestResult(
                "Display",
                True,
                "Display test message shown"
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                "Display",
                False,
                f"Display test failed: {str(e)}"
            ))
            
    def test_lora(self):
        """Test LoRa communication"""
        try:
            if not self.controller.lora_handler.initialized:
                self.results.append(TestResult(
                    "LoRa",
                    False,
                    "LoRa not initialized"
                ))
                return
                
            # Try to send test status
            if self.controller.lora_handler.send_status():
                self.results.append(TestResult(
                    "LoRa",
                    True,
                    "Status message sent"
                ))
            else:
                self.results.append(TestResult(
                    "LoRa",
                    False,
                    "Failed to send status"
                ))
                
        except Exception as e:
            self.results.append(TestResult(
                "LoRa",
                False,
                f"LoRa test failed: {str(e)}"
            ))
            
    def test_control(self):
        """Test control functionality"""
        try:
            # Test relay control
            self.controller._deactivate_heating()
            time.sleep(1)
            
            if time.time() - self.controller.last_on_time > 2:
                self.results.append(TestResult(
                    "Control",
                    True,
                    "Relay control working"
                ))
            else:
                self.results.append(TestResult(
                    "Control",
                    False,
                    "Relay control failed"
                ))
                
        except Exception as e:
            self.results.append(TestResult(
                "Control",
                False,
                f"Control test failed: {str(e)}"
            ))
            
    def test_config(self):
        """Test configuration functionality"""
        try:
            # Save test config
            test_value = 50.0
            success, message = self.controller.config_manager.set_param(
                'test_param',
                test_value
            )
            
            if not success:
                self.results.append(TestResult(
                    "Configuration",
                    False,
                    f"Failed to save config: {message}"
                ))
                return
                
            # Read back value
            value = self.controller.config_manager.get_param('test_param')
            
            if value == test_value:
                self.results.append(TestResult(
                    "Configuration",
                    True,
                    "Configuration read/write working"
                ))
            else:
                self.results.append(TestResult(
                    "Configuration", 
                    False,
                    f"Config value mismatch: {value} != {test_value}"
                ))
                
        except Exception as e:
            self.results.append(TestResult(
                "Configuration",
                False,
                f"Config test failed: {str(e)}"
            ))
            
    def print_results(self):
        """Print test results"""
        print("\nTest Results:")
        print("-" * 40)
        
        passed = 0
        total = len(self.results)
        
        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            print(f"{result.name}: {status}")
            if result.message:
                print(f"  {result.message}")
            if result.passed:
                passed += 1
                
        print("-" * 40)
        print(f"Passed {passed} of {total} tests")
        
    def show_results_on_display(self):
        """Show test results on display"""
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        self.controller.display_manager.show_status(
            "Test Results",
            f"Passed: {passed}/{total}",
            "Tests complete"
        )

def run_tests(controller):
    """Run system tests
    
    Args:
        controller: System controller
        
    Returns:
        bool: True if all tests passed
    """
    # Free memory before tests
    gc.collect()
    
    # Create and run tests
    runner = TestRunner(controller)
    runner.run_all_tests()
    
    # Show results
    runner.print_results()
    runner.show_results_on_display()
    
    # Return overall status
    return all(r.passed for r in runner.results)