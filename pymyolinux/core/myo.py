from pymyolinux.util.event import Event
from pymyolinux.core.bluegiga import BlueGigaProtocol
from pymyolinux.core.packet_def import *

class MyoDongle():

    # Connection parameters
    default_latency = 0
    default_timeout = 64
    default_conn_interval_min   = 6     # Time between consecutive connection events
                                        # (E.g. a data exchange before going back to an idle state to save power)
    default_conn_interval_max   = 6

    def __init__(self, com_port):
        """
            DESC

        :param com_port: Refers to a path to a character device file, for a usb to BLE controller serial interface.
                            e.g. /dev/ttyACM0
        """
        self.ble        = BlueGigaProtocol(com_port)
        self.emg_event  = Event("On receiving an EMG data packet from the Myo device.")
        self.imu_event  = Event("On receiving an IMU data packet from the Myo device.")

    def clear_state(self):
        # Disable dongle advertisement
        self.transmit(self.ble.ble_cmd_gap_set_mode(GAP_Discoverable_Modes.gap_non_discoverable.value,
                                        GAP_Connectable_Modes.gap_non_connectable.value))

        # Disconnect any connected devices
        max_num_connections = 8
        for i in range(max_num_connections):
            self.transmit(self.ble.ble_cmd_connection_disconnect(i))

        # Stop scanning
        self.transmit(self.ble.ble_cmd_gap_end_procedure())
        self.ble.connection = None

    def discover_device_addresses(self, timeout=2):
        # Scan for advertising packets
        self.transmit(self.ble.ble_cmd_gap_discover(GAP_Discover_Mode.gap_discover_observation.value))
        self.ble.read_incoming(timeout)

        # Stop scanning
        self.transmit(self.ble.ble_cmd_gap_end_procedure())
        return self.ble.myo_addresses

    def connect(self, myo_device_found, timeout=2):
        if self.ble.connection is not None:
            raise RuntimeError("BLE connection is not None.")

        # Attempt to connect, and wait for connection response
        self.transmit(self.ble.ble_cmd_gap_connect_direct(myo_device_found["sender_address"],
                                                myo_device_found["address_type"],
                                                self.default_conn_interval_min, self.default_conn_interval_max,
                                                self.default_timeout, self.default_latency))
        self.ble.read_incoming_conditional(BlueGigaProtocol.ble_rsp_gap_connect_direct, timeout)

        if self.ble.connection is None:
            raise RuntimeError("Unable to receive connection response from Myo device.")

        if self.ble.connection["result"] != 0:
            raise RuntimeError("Incorrect result received in connection response from Myo device.")

    def transmit(self, packet_contents):
        self.ble.send_command(packet_contents)
