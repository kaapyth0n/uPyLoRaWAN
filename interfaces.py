class ObjectInterface:
    INTERFACE_ID = 0

    def is_id_occupied(self, id):
        raise NotImplementedError

    def is_interface_supported(self, interface):
        raise NotImplementedError

    def get_type(self):
        raise NotImplementedError

    def get_interfaces(self):
        raise NotImplementedError

class BoilerInterface:
    INTERFACE_ID = 1
    PARAM_MODE = 0
    PARAM_SETPOINT = 1
    PARAM_CURRENT_TEMP = 2
    PARAM_MIN_TEMP = 3
    PARAM_MAX_TEMP = 4
    PARAM_HYSTERESIS = 5
    PARAM_MIN_ON_TIME = 6
    PARAM_MIN_OFF_TIME = 7
    PARAM_WATCHDOG = 8
    FUNC_SET_PARAM = 0
    FUNC_GET_PARAM = 1
    FUNC_STATUS = 2
    FUNC_DIAGNOSTIC = 3

    def get_parameter(self, param_id, param_index=None):
        raise NotImplementedError

    def set_parameter(self, param_id, value, param_index=None):
        raise NotImplementedError

    def get_status(self):
        raise NotImplementedError

    def run_diagnostic(self):
        raise NotImplementedError

class RemoteControlInterface:
    INTERFACE_ID = 2

    def connect_input(self, input_id, source_object, output_id):
        raise NotImplementedError

    def get_connection(self, input_id):
        raise NotImplementedError