from pymyolinux.util.event import Event
from pymyolinux.core.bluegiga import BlueGigaProtocol
from pymyolinux.core.packet_def import *

class MyoDongle():

    # Connection parameters
    default_latency = 0     # This parameter configures the slave latency. Slave latency defines how many connection
                            # intervals a slave device can skip.

    default_timeout = 64    # How long the devices can be out of range before the connection is closed.
                            # Range: 10 - 3200

    # Range: 6 - 3200 (in units of 1.25ms).
    #   Note: Lower implies faster data transfer, but potentially less reliable data exchanges.
    #
    default_conn_interval_min   = 6     # Time between consecutive connection events (a connection interval).
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

    def clear_state(self, timeout=2):
        # Disable dongle advertisement
        self.transmit_wait(self.ble.ble_cmd_gap_set_mode(GAP_Discoverable_Modes.gap_non_discoverable.value,
                                                            GAP_Connectable_Modes.gap_non_connectable.value),
                                BlueGigaProtocol.ble_rsp_gap_set_mode)

        # Disconnect any connected devices
        max_num_connections = 8
        for i in range(max_num_connections):
            self.transmit_wait(self.ble.ble_cmd_connection_disconnect(i),
                                    BlueGigaProtocol.ble_rsp_connection_disconnect)
            if self.ble.disconnecting:
                # Need to wait for disconnect response
                resp_received = self.ble.read_incoming_conditional(BlueGigaProtocol.ble_evt_connection_disconnected,
                                                                        timeout)
                if not resp_received:
                    raise RuntimeError("Disconnect response timed out.")

        # Stop scanning
        self.transmit_wait(self.ble.ble_cmd_gap_end_procedure(), BlueGigaProtocol.ble_rsp_gap_end_procedure)
        self.ble.connection = None

    def discover_myo_devices(self, timeout=2):
        # Scan for advertising packets
        self.transmit_wait(self.ble.ble_cmd_gap_discover(GAP_Discover_Mode.gap_discover_observation.value),
                                BlueGigaProtocol.ble_rsp_gap_discover)
        self.ble.read_incoming(timeout)

        # Stop scanning
        self.transmit_wait(self.ble.ble_cmd_gap_end_procedure(), BlueGigaProtocol.ble_rsp_gap_end_procedure)
        return self.ble.myo_devices

    def connect(self, myo_device_found, timeout=2):
        if self.ble.connection is not None:
            raise RuntimeError("BLE connection is not None.")

        # Attempt to connect
        self.transmit_wait(self.ble.ble_cmd_gap_connect_direct(myo_device_found["sender_address"],
                                                myo_device_found["address_type"],
                                                self.default_conn_interval_min, self.default_conn_interval_max,
                                                self.default_timeout, self.default_latency),
                                BlueGigaProtocol.ble_rsp_gap_connect_direct)

        # Need to wait for conenction response
        resp_received = self.ble.read_incoming_conditional(BlueGigaProtocol.ble_evt_connection_status, timeout)
        if not resp_received:
            raise RuntimeError("Connection response timed out.")

    def transmit(self, packet_contents):
        self.ble.send_command(packet_contents)

    def transmit_wait(self, packet_contents, event, timeout=2):
        self.ble.send_command(packet_contents)
        resp_received = self.ble.read_incoming_conditional(event, timeout)
        if not resp_received:
            raise RuntimeError("Response timed out for the transmitted command.")