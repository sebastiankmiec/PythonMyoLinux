import serial
import struct
import time
from pymyolinux.util.event import Event
from pymyolinux.core.handlers import *

class BlueGigaProtocol():

    # on_busy = BGAPIEvent()
    # on_idle = BGAPIEvent()
    # on_timeout = BGAPIEvent()
    # on_before_tx_command = BGAPIEvent()
    # on_tx_command_complete = BGAPIEvent()

    # Configurable
    debug = False

    # By default the BGAPI protocol assumes that UART flow control (RTS/CTS) is used to ensure reliable data
    # transmission and to prevent lost data because of buffer overflows.
    use_rts_cts         = True
    BLED112_BAUD_RATE   = 115200

    #
    # Myo device specific events
    #
    emg_event           = Event("On receiving an EMG data packet from the Myo device.", fire_type=0)
    imu_event           = Event("On receiving an IMU data packet from the Myo device.", fire_type=0)
    joint_emg_imu_event = Event("On receiving an IMU data packet from the Myo device. Use latest IMU event.",
                                    fire_type=0)

    # Non-empty events
    ble_evt_gap_scan_response                   = Event()
    ble_evt_connection_disconnected             = Event()
    ble_evt_connection_status                   = Event()
    ble_evt_attclient_group_found               = Event()
    ble_evt_attclient_procedure_completed       = Event()
    ble_evt_attclient_find_information_found    = Event()

    # Non-empty (response) events

    # Empty events
    ble_rsp_gap_set_mode                    = Event()
    ble_rsp_connection_disconnect           = Event()
    ble_rsp_gap_end_procedure               = Event()
    ble_rsp_gap_discover                    = Event()
    ble_rsp_attclient_read_by_group_type    = Event()
    ble_rsp_gap_connect_direct              = Event()
    ble_rsp_attclient_find_information      = Event()
    ble_rsp_attclient_attribute_write       = Event()
    ble_evt_attclient_attribute_value       = Event()

    # Non-configurable:
    bgapi_rx_buffer = b""
    bgapi_rx_expected_length = 0
    busy = False
    disconnecting = False

    def __init__(self, com_port):

        self.ser            = serial.Serial(port=com_port, baudrate=self.BLED112_BAUD_RATE, rtscts=self.use_rts_cts)
        self.packet_mode    = not self.use_rts_cts

        # Filled by user of this object
        self.imu_handle         = None
        self.emg_handle_0       = None
        self.emg_handle_1       = None
        self.emg_handle_2       = None
        self.emg_handle_3       = None

        # Filled by event handlers
        self.myo_devices        = []
        self.services_found     = []
        self.attributes_found   = []
        self.connection         = None
        self.current_imu_read   = None

        # Event handlers
        self.ble_evt_gap_scan_response                  += add_myo_device
        self.ble_evt_connection_status                  += add_connection
        self.ble_evt_connection_disconnected            += device_disconnected
        self.ble_evt_attclient_group_found              += add_service_found
        self.ble_evt_attclient_procedure_completed      += service_finding_complete
        self.ble_evt_attclient_find_information_found   += add_attribute_found
        self.ble_evt_attclient_attribute_value          += on_receive_attribute_value

        # Empty handlers (solely to increment event fire count)
        empty_handler_events = [self.ble_rsp_gap_set_mode, self.ble_rsp_connection_disconnect,
                                    self.ble_rsp_gap_end_procedure, self.ble_rsp_gap_discover,
                                    self.ble_rsp_gap_connect_direct, self.ble_rsp_attclient_read_by_group_type,
                                    self.ble_rsp_attclient_find_information, self.ble_rsp_attclient_attribute_write]

        for empty_event in empty_handler_events:
            empty_event += empty_handler

    def send_command(self, packet):
        if self.packet_mode: packet = chr(len(packet) & 0xFF) + packet
        if self.debug: print('=>[ ' + ' '.join(['%02X' % b for b in packet]) + ' ]')
        #self.on_before_tx_command()
        self.busy = True
        #self.on_busy()
        self.ser.write(packet)
        #self.on_tx_command_complete()

    def read_incoming(self, timeout=2):
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            self.busy   = True
            time_left   = timeout - (time.time() - start_time)
            self.check_activity(time_left)

    def read_incoming_conditional(self, event, timeout=2):
        if self.get_event_count(event) > 0:
            self.__eventcounter__[event] = 0
            return True

        start_time = time.time()
        while (time.time() - start_time) < timeout:
            self.busy   = True
            time_left       = timeout - (time.time() - start_time)
            self.check_activity(time_left)

            if self.get_event_count(event) > 0:
                self.__eventcounter__[event] = 0
                return True
        return False

    def get_event_count(self, event):
        if hasattr(self, "__eventcounter__"):
            if event in self.__eventcounter__:
                return self.__eventcounter__[event]
        return 0


    def check_activity(self, timeout=0):
        if timeout > 0:
            self.ser.timeout = timeout
            while 1:
                x = self.ser.read()

                if len(x) > 0:
                    self.parse(x)
                else: # timeout
                    self.busy = False
                    #self.on_idle()
                    #self.on_timeout()
                if not self.busy: # finished
                    break
        else:
            while self.ser.inWaiting(): self.parse(self.ser.read())
        return self.busy

    def parse(self, barray):
        b=barray[0]
        if len(self.bgapi_rx_buffer) == 0 and (b == 0x00 or b == 0x80 or b == 0x08 or b == 0x88):
            self.bgapi_rx_buffer+=bytes([b])
        elif len(self.bgapi_rx_buffer) == 1:
            self.bgapi_rx_buffer+=bytes([b])
            self.bgapi_rx_expected_length = 4 + (self.bgapi_rx_buffer[0] & 0x07) + self.bgapi_rx_buffer[1]
        elif len(self.bgapi_rx_buffer) > 1:
            self.bgapi_rx_buffer+=bytes([b])

        """
        BGAPI packet structure (as of 2012-11-07):
            Byte 0:
                  [7] - 1 bit, Message Type (MT)         0 = Command/Response, 1 = Event
                [6:3] - 4 bits, Technology Type (TT)     0000 = Bluetooth 4.0 single mode, 0001 = Wi-Fi
                [2:0] - 3 bits, Length High (LH)         Payload length (high bits)
            Byte 1:     8 bits, Length Low (LL)          Payload length (low bits)
            Byte 2:     8 bits, Class ID (CID)           Command class ID
            Byte 3:     8 bits, Command ID (CMD)         Command ID
            Bytes 4-n:  0 - 2048 Bytes, Payload (PL)     Up to 2048 bytes of payload
        """

        #print'%02X: %d, %d' % (b, len(self.bgapi_rx_buffer), self.bgapi_rx_expected_length)
        if self.bgapi_rx_expected_length > 0 and len(self.bgapi_rx_buffer) == self.bgapi_rx_expected_length:
            if self.debug: print('<=[ ' + ' '.join(['%02X' % b for b in self.bgapi_rx_buffer ]) + ' ]')
            packet_type, payload_length, packet_class, packet_command = self.bgapi_rx_buffer[:4]
            self.bgapi_rx_payload = self.bgapi_rx_buffer[4:]
            self.bgapi_rx_buffer = b""
            if packet_type & 0x88 == 0x00:
                # 0x00 = BLE response packet
                # if packet_class == 0:
                #     if packet_command == 0: # ble_rsp_system_reset
                #         self.ble_rsp_system_reset({  })
                #         self.busy = False
                #         self.on_idle()
                #     elif packet_command == 1: # ble_rsp_system_hello
                #         self.ble_rsp_system_hello({  })
                #     elif packet_command == 2: # ble_rsp_system_address_get
                #         address = struct.unpack('<6s', self.bgapi_rx_payload[:6])[0]
                #         address = address
                #         self.ble_rsp_system_address_get({ 'address': address })
                #     elif packet_command == 3: # ble_rsp_system_reg_write
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_system_reg_write({ 'result': result })
                #     elif packet_command == 4: # ble_rsp_system_reg_read
                #         address, value = struct.unpack('<HB', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_system_reg_read({ 'address': address, 'value': value })
                #     elif packet_command == 5: # ble_rsp_system_get_counters
                #         txok, txretry, rxok, rxfail, mbuf = struct.unpack('<BBBBB', self.bgapi_rx_payload[:5])
                #         self.ble_rsp_system_get_counters({ 'txok': txok, 'txretry': txretry, 'rxok': rxok, 'rxfail': rxfail, 'mbuf': mbuf })
                #     elif packet_command == 6: # ble_rsp_system_get_connections
                #         maxconn = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         self.ble_rsp_system_get_connections({ 'maxconn': maxconn })
                #     elif packet_command == 7: # ble_rsp_system_read_memory
                #         address, data_len = struct.unpack('<IB', self.bgapi_rx_payload[:5])
                #         data_data = self.bgapi_rx_payload[5:]
                #         self.ble_rsp_system_read_memory({ 'address': address, 'data': data_data })
                #     elif packet_command == 8: # ble_rsp_system_get_info
                #         major, minor, patch, build, ll_version, protocol_version, hw = struct.unpack('<HHHHHBB', self.bgapi_rx_payload[:12])
                #         self.ble_rsp_system_get_info({ 'major': major, 'minor': minor, 'patch': patch, 'build': build, 'll_version': ll_version, 'protocol_version': protocol_version, 'hw': hw })
                #     elif packet_command == 9: # ble_rsp_system_endpoint_tx
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_system_endpoint_tx({ 'result': result })
                #     elif packet_command == 10: # ble_rsp_system_whitelist_append
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_system_whitelist_append({ 'result': result })
                #     elif packet_command == 11: # ble_rsp_system_whitelist_remove
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_system_whitelist_remove({ 'result': result })
                #     elif packet_command == 12: # ble_rsp_system_whitelist_clear
                #         self.ble_rsp_system_whitelist_clear({  })
                #     elif packet_command == 13: # ble_rsp_system_endpoint_rx
                #         result, data_len = struct.unpack('<HB', self.bgapi_rx_payload[:3])
                #         data_data = self.bgapi_rx_payload[3:]
                #         self.ble_rsp_system_endpoint_rx({ 'result': result, 'data': data_data })
                #     elif packet_command == 14: # ble_rsp_system_endpoint_set_watermarks
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_system_endpoint_set_watermarks({ 'result': result })
                # elif packet_class == 1:
                #     if packet_command == 0: # ble_rsp_flash_ps_defrag
                #         self.ble_rsp_flash_ps_defrag({  })
                #     elif packet_command == 1: # ble_rsp_flash_ps_dump
                #         self.ble_rsp_flash_ps_dump({  })
                #     elif packet_command == 2: # ble_rsp_flash_ps_erase_all
                #         self.ble_rsp_flash_ps_erase_all({  })
                #     elif packet_command == 3: # ble_rsp_flash_ps_save
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_flash_ps_save({ 'result': result })
                #     elif packet_command == 4: # ble_rsp_flash_ps_load
                #         result, value_len = struct.unpack('<HB', self.bgapi_rx_payload[:3])
                #         value_data = self.bgapi_rx_payload[3:]
                #         self.ble_rsp_flash_ps_load({ 'result': result, 'value': value_data })
                #     elif packet_command == 5: # ble_rsp_flash_ps_erase
                #         self.ble_rsp_flash_ps_erase({  })
                #     elif packet_command == 6: # ble_rsp_flash_erase_page
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_flash_erase_page({ 'result': result })
                #     elif packet_command == 7: # ble_rsp_flash_write_words
                #         self.ble_rsp_flash_write_words({  })
                # elif packet_class == 2:
                #     if packet_command == 0: # ble_rsp_attributes_write
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_attributes_write({ 'result': result })
                #     elif packet_command == 1: # ble_rsp_attributes_read
                #         handle, offset, result, value_len = struct.unpack('<HHHB', self.bgapi_rx_payload[:7])
                #         value_data = self.bgapi_rx_payload[7:]
                #         self.ble_rsp_attributes_read({ 'handle': handle, 'offset': offset, 'result': result, 'value': value_data })
                #     elif packet_command == 2: # ble_rsp_attributes_read_type
                #         handle, result, value_len = struct.unpack('<HHB', self.bgapi_rx_payload[:5])
                #         value_data = self.bgapi_rx_payload[5:]
                #         self.ble_rsp_attributes_read_type({ 'handle': handle, 'result': result, 'value': value_data })
                #     elif packet_command == 3: # ble_rsp_attributes_user_read_response
                #         self.ble_rsp_attributes_user_read_response({  })
                #     elif packet_command == 4: # ble_rsp_attributes_user_write_response
                #         self.ble_rsp_attributes_user_write_response({  })
                if packet_class == 3:
                    if packet_command == 0: # ble_rsp_connection_disconnect
                        connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                        if result != disconnect_procedure_started:
                            if self.debug:
                                print("Failed to start disconnect procedure for connection {}.".format(connection))
                        else:
                            self.disconnecting = True
                            if self.debug:
                                print("Started disconnect procedure for connection {}.".format(connection))
                        self.ble_rsp_connection_disconnect(**{ 'connection': connection, 'result': result })
                #     elif packet_command == 1: # ble_rsp_connection_get_rssi
                #         connection, rssi = struct.unpack('<Bb', self.bgapi_rx_payload[:2])
                #         self.ble_rsp_connection_get_rssi({ 'connection': connection, 'rssi': rssi })
                #     elif packet_command == 2: # ble_rsp_connection_update
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_connection_update({ 'connection': connection, 'result': result })
                #     elif packet_command == 3: # ble_rsp_connection_version_update
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_connection_version_update({ 'connection': connection, 'result': result })
                #     elif packet_command == 4: # ble_rsp_connection_channel_map_get
                #         connection, map_len = struct.unpack('<BB', self.bgapi_rx_payload[:2])
                #         map_data = self.bgapi_rx_payload[2:]
                #         self.ble_rsp_connection_channel_map_get({ 'connection': connection, 'map': map_data })
                #     elif packet_command == 5: # ble_rsp_connection_channel_map_set
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_connection_channel_map_set({ 'connection': connection, 'result': result })
                #     elif packet_command == 6: # ble_rsp_connection_features_get
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_connection_features_get({ 'connection': connection, 'result': result })
                #     elif packet_command == 7: # ble_rsp_connection_get_status
                #         connection = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         self.ble_rsp_connection_get_status({ 'connection': connection })
                #     elif packet_command == 8: # ble_rsp_connection_raw_tx
                #         connection = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         self.ble_rsp_connection_raw_tx({ 'connection': connection })
                elif packet_class == 4:
                #     if packet_command == 0: # ble_rsp_attclient_find_by_type_value
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_attclient_find_by_type_value({ 'connection': connection, 'result': result })
                    if packet_command == 1: # ble_rsp_attclient_read_by_group_type
                        connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                        self.ble_rsp_attclient_read_by_group_type(**{ 'connection': connection, 'result': result })
                #     elif packet_command == 2: # ble_rsp_attclient_read_by_type
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_attclient_read_by_type({ 'connection': connection, 'result': result })
                    elif packet_command == 3: # ble_rsp_attclient_find_information
                        connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                        if result != find_info_success:
                            if self.debug:
                                print("Error using find information command.")
                        self.ble_rsp_attclient_find_information(**{ 'connection': connection, 'result': result })
                #     elif packet_command == 4: # ble_rsp_attclient_read_by_handle
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_attclient_read_by_handle({ 'connection': connection, 'result': result })
                    elif packet_command == 5: # ble_rsp_attclient_attribute_write
                        connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                        if result != write_success:
                            raise("Write attempt was unsuccessful.")
                        self.ble_rsp_attclient_attribute_write(**{ 'connection': connection, 'result': result })
                #     elif packet_command == 6: # ble_rsp_attclient_write_command
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_attclient_write_command({ 'connection': connection, 'result': result })
                #     elif packet_command == 7: # ble_rsp_attclient_indicate_confirm
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_attclient_indicate_confirm({ 'result': result })
                #     elif packet_command == 8: # ble_rsp_attclient_read_long
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_attclient_read_long({ 'connection': connection, 'result': result })
                #     elif packet_command == 9: # ble_rsp_attclient_prepare_write
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_attclient_prepare_write({ 'connection': connection, 'result': result })
                #     elif packet_command == 10: # ble_rsp_attclient_execute_write
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_attclient_execute_write({ 'connection': connection, 'result': result })
                #     elif packet_command == 11: # ble_rsp_attclient_read_multiple
                #         connection, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_attclient_read_multiple({ 'connection': connection, 'result': result })
                # elif packet_class == 5:
                #     if packet_command == 0: # ble_rsp_sm_encrypt_start
                #         handle, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_sm_encrypt_start({ 'handle': handle, 'result': result })
                #     elif packet_command == 1: # ble_rsp_sm_set_bondable_mode
                #         self.ble_rsp_sm_set_bondable_mode({  })
                #     elif packet_command == 2: # ble_rsp_sm_delete_bonding
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_sm_delete_bonding({ 'result': result })
                #     elif packet_command == 3: # ble_rsp_sm_set_parameters
                #         self.ble_rsp_sm_set_parameters({  })
                #     elif packet_command == 4: # ble_rsp_sm_passkey_entry
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_sm_passkey_entry({ 'result': result })
                #     elif packet_command == 5: # ble_rsp_sm_get_bonds
                #         bonds = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         self.ble_rsp_sm_get_bonds({ 'bonds': bonds })
                #     elif packet_command == 6: # ble_rsp_sm_set_oob_data
                #         self.ble_rsp_sm_set_oob_data({  })
                elif packet_class == 6:
                #     if packet_command == 0: # ble_rsp_gap_set_privacy_flags
                #         self.ble_rsp_gap_set_privacy_flags({  })
                    if packet_command == 1: # ble_rsp_gap_set_mode
                        result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                        if result != GAP_set_mode_success:
                            raise RuntimeError("Failed to set GAP mode.")
                        else:
                            if self.debug:
                                print("Successfully set GAP mode.")
                        self.ble_rsp_gap_set_mode(**{ 'result': result })
                    elif packet_command == 2: # ble_rsp_gap_discover
                        result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                        if result != GAP_start_procedure_success:
                            raise RuntimeError("Failed to start GAP discover procedure.")
                        self.ble_rsp_gap_discover(**{ 'result': result })
                    elif packet_command == 3: # ble_rsp_gap_connect_direct
                        result, connection_handle = struct.unpack('<HB', self.bgapi_rx_payload[:3])
                        if result != GAP_start_procedure_success:
                            raise RuntimeError("Failed to start GAP connection procedure.")
                        self.ble_rsp_gap_connect_direct(**{ 'result': result, 'connection_handle': connection_handle })
                    elif packet_command == 4: # ble_rsp_gap_end_procedure
                        result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                        if result != GAP_end_procedure_success:
                            if self.debug:
                                print("Failed to end GAP procedure.")
                        self.ble_rsp_gap_end_procedure(**{ 'result': result })
                #     elif packet_command == 5: # ble_rsp_gap_connect_selective
                #         result, connection_handle = struct.unpack('<HB', self.bgapi_rx_payload[:3])
                #         self.ble_rsp_gap_connect_selective({ 'result': result, 'connection_handle': connection_handle })
                #     elif packet_command == 6: # ble_rsp_gap_set_filtering
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_gap_set_filtering({ 'result': result })
                #     elif packet_command == 7: # ble_rsp_gap_set_scan_parameters
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_gap_set_scan_parameters({ 'result': result })
                #     elif packet_command == 8: # ble_rsp_gap_set_adv_parameters
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_gap_set_adv_parameters({ 'result': result })
                #     elif packet_command == 9: # ble_rsp_gap_set_adv_data
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_gap_set_adv_data({ 'result': result })
                #     elif packet_command == 10: # ble_rsp_gap_set_directed_connectable_mode
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_gap_set_directed_connectable_mode({ 'result': result })
                # elif packet_class == 7:
                #     if packet_command == 0: # ble_rsp_hardware_io_port_config_irq
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_io_port_config_irq({ 'result': result })
                #     elif packet_command == 1: # ble_rsp_hardware_set_soft_timer
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_set_soft_timer({ 'result': result })
                #     elif packet_command == 2: # ble_rsp_hardware_adc_read
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_adc_read({ 'result': result })
                #     elif packet_command == 3: # ble_rsp_hardware_io_port_config_direction
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_io_port_config_direction({ 'result': result })
                #     elif packet_command == 4: # ble_rsp_hardware_io_port_config_function
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_io_port_config_function({ 'result': result })
                #     elif packet_command == 5: # ble_rsp_hardware_io_port_config_pull
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_io_port_config_pull({ 'result': result })
                #     elif packet_command == 6: # ble_rsp_hardware_io_port_write
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_io_port_write({ 'result': result })
                #     elif packet_command == 7: # ble_rsp_hardware_io_port_read
                #         result, port, data = struct.unpack('<HBB', self.bgapi_rx_payload[:4])
                #         self.ble_rsp_hardware_io_port_read({ 'result': result, 'port': port, 'data': data })
                #     elif packet_command == 8: # ble_rsp_hardware_spi_config
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_spi_config({ 'result': result })
                #     elif packet_command == 9: # ble_rsp_hardware_spi_transfer
                #         result, channel, data_len = struct.unpack('<HBB', self.bgapi_rx_payload[:4])
                #         data_data = self.bgapi_rx_payload[4:]
                #         self.ble_rsp_hardware_spi_transfer({ 'result': result, 'channel': channel, 'data': data_data })
                #     elif packet_command == 10: # ble_rsp_hardware_i2c_read
                #         result, data_len = struct.unpack('<HB', self.bgapi_rx_payload[:3])
                #         data_data = self.bgapi_rx_payload[3:]
                #         self.ble_rsp_hardware_i2c_read({ 'result': result, 'data': data_data })
                #     elif packet_command == 11: # ble_rsp_hardware_i2c_write
                #         written = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         self.ble_rsp_hardware_i2c_write({ 'written': written })
                #     elif packet_command == 12: # ble_rsp_hardware_set_txpower
                #         self.ble_rsp_hardware_set_txpower({  })
                #     elif packet_command == 13: # ble_rsp_hardware_timer_comparator
                #         result = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_hardware_timer_comparator({ 'result': result })
                # elif packet_class == 8:
                #     if packet_command == 0: # ble_rsp_test_phy_tx
                #         self.ble_rsp_test_phy_tx({  })
                #     elif packet_command == 1: # ble_rsp_test_phy_rx
                #         self.ble_rsp_test_phy_rx({  })
                #     elif packet_command == 2: # ble_rsp_test_phy_end
                #         counter = struct.unpack('<H', self.bgapi_rx_payload[:2])[0]
                #         self.ble_rsp_test_phy_end({ 'counter': counter })
                #     elif packet_command == 3: # ble_rsp_test_phy_reset
                #         self.ble_rsp_test_phy_reset({  })
                #     elif packet_command == 4: # ble_rsp_test_get_channel_map
                #         channel_map_len = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         channel_map_data = self.bgapi_rx_payload[1:]
                #         self.ble_rsp_test_get_channel_map({ 'channel_map': channel_map_data })
                #     elif packet_command == 5: # ble_rsp_test_debug
                #         output_len = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         output_data = self.bgapi_rx_payload[1:]
                #         self.ble_rsp_test_debug({ 'output': output_data })
                self.busy = False
                #self.on_idle()

            elif packet_type & 0x88 == 0x80:
                # 0x80 = BLE event packet
                # if packet_class == 0:
                #     if packet_command == 0: # ble_evt_system_boot
                #         major, minor, patch, build, ll_version, protocol_version, hw = struct.unpack('<HHHHHBB', self.bgapi_rx_payload[:12])
                #         self.ble_evt_system_boot({ 'major': major, 'minor': minor, 'patch': patch, 'build': build, 'll_version': ll_version, 'protocol_version': protocol_version, 'hw': hw })
                #         self.busy = False
                #         self.on_idle()
                #     elif packet_command == 1: # ble_evt_system_debug
                #         data_len = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         data_data = self.bgapi_rx_payload[1:]
                #         self.ble_evt_system_debug({ 'data': data_data })
                #     elif packet_command == 2: # ble_evt_system_endpoint_watermark_rx
                #         endpoint, data = struct.unpack('<BB', self.bgapi_rx_payload[:2])
                #         self.ble_evt_system_endpoint_watermark_rx({ 'endpoint': endpoint, 'data': data })
                #     elif packet_command == 3: # ble_evt_system_endpoint_watermark_tx
                #         endpoint, data = struct.unpack('<BB', self.bgapi_rx_payload[:2])
                #         self.ble_evt_system_endpoint_watermark_tx({ 'endpoint': endpoint, 'data': data })
                #     elif packet_command == 4: # ble_evt_system_script_failure
                #         address, reason = struct.unpack('<HH', self.bgapi_rx_payload[:4])
                #         self.ble_evt_system_script_failure({ 'address': address, 'reason': reason })
                #     elif packet_command == 5: # ble_evt_system_no_license_key
                #         self.ble_evt_system_no_license_key({  })
                # elif packet_class == 1:
                #     if packet_command == 0: # ble_evt_flash_ps_key
                #         key, value_len = struct.unpack('<HB', self.bgapi_rx_payload[:3])
                #         value_data = self.bgapi_rx_payload[3:]
                #         self.ble_evt_flash_ps_key({ 'key': key, 'value': value_data })
                # elif packet_class == 2:
                #     if packet_command == 0: # ble_evt_attributes_value
                #         connection, reason, handle, offset, value_len = struct.unpack('<BBHHB', self.bgapi_rx_payload[:7])
                #         value_data = self.bgapi_rx_payload[7:]
                #         self.ble_evt_attributes_value({ 'connection': connection, 'reason': reason, 'handle': handle, 'offset': offset, 'value': value_data })
                #     elif packet_command == 1: # ble_evt_attributes_user_read_request
                #         connection, handle, offset, maxsize = struct.unpack('<BHHB', self.bgapi_rx_payload[:6])
                #         self.ble_evt_attributes_user_read_request({ 'connection': connection, 'handle': handle, 'offset': offset, 'maxsize': maxsize })
                #     elif packet_command == 2: # ble_evt_attributes_status
                #         handle, flags = struct.unpack('<HB', self.bgapi_rx_payload[:3])
                #         self.ble_evt_attributes_status({ 'handle': handle, 'flags': flags })
                if packet_class == 3:
                    if packet_command == 0: # ble_evt_connection_status
                        connection, flags, address, address_type, conn_interval, timeout, latency, bonding = struct.unpack('<BB6sBHHHB', self.bgapi_rx_payload[:16])
                        args = { 'connection': connection, 'flags': flags, 'address': address, 'address_type': address_type, 'conn_interval': conn_interval, 'timeout': timeout, 'latency': latency, 'bonding': bonding }
                        print("Connected to a device with the following parameters:\n{}".format(args))
                        self.ble_evt_connection_status(**args)
                #     elif packet_command == 1: # ble_evt_connection_version_ind
                #         connection, vers_nr, comp_id, sub_vers_nr = struct.unpack('<BBHH', self.bgapi_rx_payload[:6])
                #         self.ble_evt_connection_version_ind({ 'connection': connection, 'vers_nr': vers_nr, 'comp_id': comp_id, 'sub_vers_nr': sub_vers_nr })
                #     elif packet_command == 2: # ble_evt_connection_feature_ind
                #         connection, features_len = struct.unpack('<BB', self.bgapi_rx_payload[:2])
                #         features_data = self.bgapi_rx_payload[2:]
                #         self.ble_evt_connection_feature_ind({ 'connection': connection, 'features': features_data })
                #     elif packet_command == 3: # ble_evt_connection_raw_rx
                #         connection, data_len = struct.unpack('<BB', self.bgapi_rx_payload[:2])
                #         data_data = self.bgapi_rx_payload[2:]
                #         self.ble_evt_connection_raw_rx({ 'connection': connection, 'data': data_data })
                    elif packet_command == 4: # ble_evt_connection_disconnected
                        connection, reason = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                        if (self.connection is None) or (connection == self.connection["connection"]):
                            self.ble_evt_connection_disconnected(**{ 'connection': connection, 'reason': reason })
                elif packet_class == 4:
                #     if packet_command == 0: # ble_evt_attclient_indicated
                #         connection, attrhandle = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_evt_attclient_indicated({ 'connection': connection, 'attrhandle': attrhandle })
                    if packet_command == 1: # ble_evt_attclient_procedure_completed
                        connection, result, chrhandle = struct.unpack('<BHH', self.bgapi_rx_payload[:5])
                        if (self.connection is not None) and (connection == self.connection["connection"]):
                            self.ble_evt_attclient_procedure_completed(**{ 'connection': connection, 'result': result, 'chrhandle': chrhandle })
                    elif packet_command == 2: # ble_evt_attclient_group_found
                        connection, start, end, uuid_len = struct.unpack('<BHHB', self.bgapi_rx_payload[:6])
                        if (self.connection is not None) and (connection == self.connection["connection"]):
                            uuid_data = self.bgapi_rx_payload[6:]
                            self.ble_evt_attclient_group_found(**{ 'connection': connection, 'start': start, 'end': end, 'uuid': uuid_data })
                #     elif packet_command == 3: # ble_evt_attclient_attribute_found
                #         connection, chrdecl, value, properties, uuid_len = struct.unpack('<BHHBB', self.bgapi_rx_payload[:7])
                #         uuid_data = self.bgapi_rx_payload[7:]
                #         self.ble_evt_attclient_attribute_found({ 'connection': connection, 'chrdecl': chrdecl, 'value': value, 'properties': properties, 'uuid': uuid_data })
                    elif packet_command == 4: # ble_evt_attclient_find_information_found
                        connection, chrhandle, uuid_len = struct.unpack('<BHB', self.bgapi_rx_payload[:4])
                        uuid_data = self.bgapi_rx_payload[4:]
                        if (self.connection is not None) and (connection == self.connection["connection"]):
                            self.ble_evt_attclient_find_information_found(**{ 'connection': connection, 'chrhandle': chrhandle, 'uuid': uuid_data })
                    elif packet_command == 5: # ble_evt_attclient_attribute_value
                        connection, atthandle, type, value_len = struct.unpack('<BHBB', self.bgapi_rx_payload[:5])
                        if (self.connection is not None) and (connection == self.connection["connection"]):
                            value_data = self.bgapi_rx_payload[5:]
                            self.ble_evt_attclient_attribute_value(**{ 'connection': connection, 'atthandle': atthandle, 'type': type, 'value': value_data })
                #     elif packet_command == 6: # ble_evt_attclient_read_multiple_response
                #         connection, handles_len = struct.unpack('<BB', self.bgapi_rx_payload[:2])
                #         handles_data = self.bgapi_rx_payload[2:]
                #         self.ble_evt_attclient_read_multiple_response({ 'connection': connection, 'handles': handles_data })
                # elif packet_class == 5:
                #     if packet_command == 0: # ble_evt_sm_smp_data
                #         handle, packet, data_len = struct.unpack('<BBB', self.bgapi_rx_payload[:3])
                #         data_data = self.bgapi_rx_payload[3:]
                #         self.ble_evt_sm_smp_data({ 'handle': handle, 'packet': packet, 'data': data_data })
                #     elif packet_command == 1: # ble_evt_sm_bonding_fail
                #         handle, result = struct.unpack('<BH', self.bgapi_rx_payload[:3])
                #         self.ble_evt_sm_bonding_fail({ 'handle': handle, 'result': result })
                #     elif packet_command == 2: # ble_evt_sm_passkey_display
                #         handle, passkey = struct.unpack('<BI', self.bgapi_rx_payload[:5])
                #         self.ble_evt_sm_passkey_display({ 'handle': handle, 'passkey': passkey })
                #     elif packet_command == 3: # ble_evt_sm_passkey_request
                #         handle = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         self.ble_evt_sm_passkey_request({ 'handle': handle })
                #     elif packet_command == 4: # ble_evt_sm_bond_status
                #         bond, keysize, mitm, keys = struct.unpack('<BBBB', self.bgapi_rx_payload[:4])
                #         self.ble_evt_sm_bond_status({ 'bond': bond, 'keysize': keysize, 'mitm': mitm, 'keys': keys })

                elif packet_class == 6:
                    if packet_command == 0: # ble_evt_gap_scan_response
                        rssi, packet_type, sender, address_type, bond, data_len = struct.unpack('<bB6sBBB', self.bgapi_rx_payload[:11])
                        data_data = self.bgapi_rx_payload[11:]
                        self.ble_evt_gap_scan_response(**{ 'rssi': rssi, 'packet_type': packet_type, 'sender': sender, 'address_type': address_type, 'bond': bond, 'data': data_data })

                    elif packet_command == 1: # ble_evt_gap_mode_changed
                        pass
                        #discover, connect = struct.unpack('<BB', self.bgapi_rx_payload[:2])
                        #self.ble_evt_gap_mode_changed({ 'discover': discover, 'connect': connect })

                # elif packet_class == 7:
                #     if packet_command == 0: # ble_evt_hardware_io_port_status
                #         timestamp, port, irq, state = struct.unpack('<IBBB', self.bgapi_rx_payload[:7])
                #         self.ble_evt_hardware_io_port_status({ 'timestamp': timestamp, 'port': port, 'irq': irq, 'state': state })
                #     elif packet_command == 1: # ble_evt_hardware_soft_timer
                #         handle = struct.unpack('<B', self.bgapi_rx_payload[:1])[0]
                #         self.ble_evt_hardware_soft_timer({ 'handle': handle })
                #     elif packet_command == 2: # ble_evt_hardware_adc_result
                #         input, value = struct.unpack('<Bh', self.bgapi_rx_payload[:3])
                #         self.ble_evt_hardware_adc_result({ 'input': input, 'value': value })
                self.busy = False

            elif packet_type & 0x88 == 0x08:
                pass
                # 0x08 = wifi response packet
            else:
                pass
                # 0x88 = wifi event packet

    def ble_cmd_system_reset(self, boot_in_dfu):
        return struct.pack('<4BB', 0, 1, 0, 0, boot_in_dfu)
    def ble_cmd_system_hello(self):
        return struct.pack('<4B', 0, 0, 0, 1)
    def ble_cmd_system_address_get(self):
        return struct.pack('<4B', 0, 0, 0, 2)
    def ble_cmd_system_reg_write(self, address, value):
        return struct.pack('<4BHB', 0, 3, 0, 3, address, value)
    def ble_cmd_system_reg_read(self, address):
        return struct.pack('<4BH', 0, 2, 0, 4, address)
    def ble_cmd_system_get_counters(self):
        return struct.pack('<4B', 0, 0, 0, 5)
    def ble_cmd_system_get_connections(self):
        return struct.pack('<4B', 0, 0, 0, 6)
    def ble_cmd_system_read_memory(self, address, length):
        return struct.pack('<4BIB', 0, 5, 0, 7, address, length)
    def ble_cmd_system_get_info(self):
        return struct.pack('<4B', 0, 0, 0, 8)
    def ble_cmd_system_endpoint_tx(self, endpoint, data):
        return struct.pack('<4BBB' + str(len(data)) + 's', 0, 2 + len(data), 0, 9, endpoint, len(data), bytes(i for i in data))
    def ble_cmd_system_whitelist_append(self, address, address_type):
        return struct.pack('<4B6sB', 0, 7, 0, 10, bytes(i for i in address), address_type)
    def ble_cmd_system_whitelist_remove(self, address, address_type):
        return struct.pack('<4B6sB', 0, 7, 0, 11, bytes(i for i in address), address_type)
    def ble_cmd_system_whitelist_clear(self):
        return struct.pack('<4B', 0, 0, 0, 12)
    def ble_cmd_system_endpoint_rx(self, endpoint, size):
        return struct.pack('<4BBB', 0, 2, 0, 13, endpoint, size)
    def ble_cmd_system_endpoint_set_watermarks(self, endpoint, rx, tx):
        return struct.pack('<4BBBB', 0, 3, 0, 14, endpoint, rx, tx)
    def ble_cmd_flash_ps_defrag(self):
        return struct.pack('<4B', 0, 0, 1, 0)
    def ble_cmd_flash_ps_dump(self):
        return struct.pack('<4B', 0, 0, 1, 1)
    def ble_cmd_flash_ps_erase_all(self):
        return struct.pack('<4B', 0, 0, 1, 2)
    def ble_cmd_flash_ps_save(self, key, value):
        return struct.pack('<4BHB' + str(len(value)) + 's', 0, 3 + len(value), 1, 3, key, len(value), bytes(i for i in value))
    def ble_cmd_flash_ps_load(self, key):
        return struct.pack('<4BH', 0, 2, 1, 4, key)
    def ble_cmd_flash_ps_erase(self, key):
        return struct.pack('<4BH', 0, 2, 1, 5, key)
    def ble_cmd_flash_erase_page(self, page):
        return struct.pack('<4BB', 0, 1, 1, 6, page)
    def ble_cmd_flash_write_words(self, address, words):
        return struct.pack('<4BHB' + str(len(words)) + 's', 0, 3 + len(words), 1, 7, address, len(words), bytes(i for i in words))
    def ble_cmd_attributes_write(self, handle, offset, value):
        return struct.pack('<4BHBB' + str(len(value)) + 's', 0, 4 + len(value), 2, 0, handle, offset, len(value), bytes(i for i in value))
    def ble_cmd_attributes_read(self, handle, offset):
        return struct.pack('<4BHH', 0, 4, 2, 1, handle, offset)
    def ble_cmd_attributes_read_type(self, handle):
        return struct.pack('<4BH', 0, 2, 2, 2, handle)
    def ble_cmd_attributes_user_read_response(self, connection, att_error, value):
        return struct.pack('<4BBBB' + str(len(value)) + 's', 0, 3 + len(value), 2, 3, connection, att_error, len(value), bytes(i for i in value))
    def ble_cmd_attributes_user_write_response(self, connection, att_error):
        return struct.pack('<4BBB', 0, 2, 2, 4, connection, att_error)
    def ble_cmd_connection_disconnect(self, connection):
        return struct.pack('<4BB', 0, 1, 3, 0, connection)
    def ble_cmd_connection_get_rssi(self, connection):
        return struct.pack('<4BB', 0, 1, 3, 1, connection)
    def ble_cmd_connection_update(self, connection, interval_min, interval_max, latency, timeout):
        return struct.pack('<4BBHHHH', 0, 9, 3, 2, connection, interval_min, interval_max, latency, timeout)
    def ble_cmd_connection_version_update(self, connection):
        return struct.pack('<4BB', 0, 1, 3, 3, connection)
    def ble_cmd_connection_channel_map_get(self, connection):
        return struct.pack('<4BB', 0, 1, 3, 4, connection)
    def ble_cmd_connection_channel_map_set(self, connection, map):
        return struct.pack('<4BBB' + str(len(map)) + 's', 0, 2 + len(map), 3, 5, connection, len(map), bytes(i for i in map))
    def ble_cmd_connection_features_get(self, connection):
        return struct.pack('<4BB', 0, 1, 3, 6, connection)
    def ble_cmd_connection_get_status(self, connection):
        return struct.pack('<4BB', 0, 1, 3, 7, connection)
    def ble_cmd_connection_raw_tx(self, connection, data):
        return struct.pack('<4BBB' + str(len(data)) + 's', 0, 2 + len(data), 3, 8, connection, len(data), bytes(i for i in data))
    def ble_cmd_attclient_find_by_type_value(self, connection, start, end, uuid, value):
        return struct.pack('<4BBHHHB' + str(len(value)) + 's', 0, 8 + len(value), 4, 0, connection, start, end, uuid, len(value), bytes(i for i in value))
    def ble_cmd_attclient_read_by_group_type(self, connection, start, end, uuid):
        return struct.pack('<4BBHHB' + str(len(uuid)) + 's', 0, 6 + len(uuid), 4, 1, connection, start, end, len(uuid), bytes(i for i in uuid))
    def ble_cmd_attclient_read_by_type(self, connection, start, end, uuid):
        return struct.pack('<4BBHHB' + str(len(uuid)) + 's', 0, 6 + len(uuid), 4, 2, connection, start, end, len(uuid), bytes(i for i in uuid))
    def ble_cmd_attclient_find_information(self, connection, start, end):
        return struct.pack('<4BBHH', 0, 5, 4, 3, connection, start, end)
    def ble_cmd_attclient_read_by_handle(self, connection, chrhandle):
        return struct.pack('<4BBH', 0, 3, 4, 4, connection, chrhandle)
    def ble_cmd_attclient_attribute_write(self, connection, atthandle, data):
        return struct.pack('<4BBHB' + str(len(data)) + 's', 0, 4 + len(data), 4, 5, connection, atthandle, len(data), bytes(i for i in data))
    def ble_cmd_attclient_write_command(self, connection, atthandle, data):
        return struct.pack('<4BBHB' + str(len(data)) + 's', 0, 4 + len(data), 4, 6, connection, atthandle, len(data), bytes(i for i in data))
    def ble_cmd_attclient_indicate_confirm(self, connection):
        return struct.pack('<4BB', 0, 1, 4, 7, connection)
    def ble_cmd_attclient_read_long(self, connection, chrhandle):
        return struct.pack('<4BBH', 0, 3, 4, 8, connection, chrhandle)
    def ble_cmd_attclient_prepare_write(self, connection, atthandle, offset, data):
        return struct.pack('<4BBHHB' + str(len(data)) + 's', 0, 6 + len(data), 4, 9, connection, atthandle, offset, len(data), bytes(i for i in data))
    def ble_cmd_attclient_execute_write(self, connection, commit):
        return struct.pack('<4BBB', 0, 2, 4, 10, connection, commit)
    def ble_cmd_attclient_read_multiple(self, connection, handles):
        return struct.pack('<4BBB' + str(len(handles)) + 's', 0, 2 + len(handles), 4, 11, connection, len(handles), bytes(i for i in handles))
    def ble_cmd_sm_encrypt_start(self, handle, bonding):
        return struct.pack('<4BBB', 0, 2, 5, 0, handle, bonding)
    def ble_cmd_sm_set_bondable_mode(self, bondable):
        return struct.pack('<4BB', 0, 1, 5, 1, bondable)
    def ble_cmd_sm_delete_bonding(self, handle):
        return struct.pack('<4BB', 0, 1, 5, 2, handle)
    def ble_cmd_sm_set_parameters(self, mitm, min_key_size, io_capabilities):
        return struct.pack('<4BBBB', 0, 3, 5, 3, mitm, min_key_size, io_capabilities)
    def ble_cmd_sm_passkey_entry(self, handle, passkey):
        return struct.pack('<4BBI', 0, 5, 5, 4, handle, passkey)
    def ble_cmd_sm_get_bonds(self):
        return struct.pack('<4B', 0, 0, 5, 5)
    def ble_cmd_sm_set_oob_data(self, oob):
        return struct.pack('<4BB' + str(len(oob)) + 's', 0, 1 + len(oob), 5, 6, len(oob), bytes(i for i in oob))
    def ble_cmd_gap_set_privacy_flags(self, peripheral_privacy, central_privacy):
        return struct.pack('<4BBB', 0, 2, 6, 0, peripheral_privacy, central_privacy)
    def ble_cmd_gap_set_mode(self, discover, connect):
        return struct.pack('<4BBB', 0, 2, 6, 1, discover, connect)
    def ble_cmd_gap_discover(self, mode):
        return struct.pack('<4BB', 0, 1, 6, 2, mode)
    def ble_cmd_gap_connect_direct(self, address, addr_type, conn_interval_min, conn_interval_max, timeout, latency):
        return struct.pack('<4B6sBHHHH', 0, 15, 6, 3, bytes(i for i in address), addr_type, conn_interval_min, conn_interval_max, timeout, latency)
    def ble_cmd_gap_end_procedure(self):
        return struct.pack('<4B', 0, 0, 6, 4)
    def ble_cmd_gap_connect_selective(self, conn_interval_min, conn_interval_max, timeout, latency):
        return struct.pack('<4BHHHH', 0, 8, 6, 5, conn_interval_min, conn_interval_max, timeout, latency)
    def ble_cmd_gap_set_filtering(self, scan_policy, adv_policy, scan_duplicate_filtering):
        return struct.pack('<4BBBB', 0, 3, 6, 6, scan_policy, adv_policy, scan_duplicate_filtering)
    def ble_cmd_gap_set_scan_parameters(self, scan_interval, scan_window, active):
        return struct.pack('<4BHHB', 0, 5, 6, 7, scan_interval, scan_window, active)
    def ble_cmd_gap_set_adv_parameters(self, adv_interval_min, adv_interval_max, adv_channels):
        return struct.pack('<4BHHB', 0, 5, 6, 8, adv_interval_min, adv_interval_max, adv_channels)
    def ble_cmd_gap_set_adv_data(self, set_scanrsp, adv_data):
        return struct.pack('<4BBB' + str(len(adv_data)) + 's', 0, 2 + len(adv_data), 6, 9, set_scanrsp, len(adv_data), bytes(i for i in adv_data))
    def ble_cmd_gap_set_directed_connectable_mode(self, address, addr_type):
        return struct.pack('<4B6sB', 0, 7, 6, 10, bytes(i for i in address), addr_type)
    def ble_cmd_hardware_io_port_config_irq(self, port, enable_bits, falling_edge):
        return struct.pack('<4BBBB', 0, 3, 7, 0, port, enable_bits, falling_edge)
    def ble_cmd_hardware_set_soft_timer(self, time, handle, single_shot):
        return struct.pack('<4BIBB', 0, 6, 7, 1, time, handle, single_shot)
    def ble_cmd_hardware_adc_read(self, input, decimation, reference_selection):
        return struct.pack('<4BBBB', 0, 3, 7, 2, input, decimation, reference_selection)
    def ble_cmd_hardware_io_port_config_direction(self, port, direction):
        return struct.pack('<4BBB', 0, 2, 7, 3, port, direction)
    def ble_cmd_hardware_io_port_config_function(self, port, function):
        return struct.pack('<4BBB', 0, 2, 7, 4, port, function)
    def ble_cmd_hardware_io_port_config_pull(self, port, tristate_mask, pull_up):
        return struct.pack('<4BBBB', 0, 3, 7, 5, port, tristate_mask, pull_up)
    def ble_cmd_hardware_io_port_write(self, port, mask, data):
        return struct.pack('<4BBBB', 0, 3, 7, 6, port, mask, data)
    def ble_cmd_hardware_io_port_read(self, port, mask):
        return struct.pack('<4BBB', 0, 2, 7, 7, port, mask)
    def ble_cmd_hardware_spi_config(self, channel, polarity, phase, bit_order, baud_e, baud_m):
        return struct.pack('<4BBBBBBB', 0, 6, 7, 8, channel, polarity, phase, bit_order, baud_e, baud_m)
    def ble_cmd_hardware_spi_transfer(self, channel, data):
        return struct.pack('<4BBB' + str(len(data)) + 's', 0, 2 + len(data), 7, 9, channel, len(data), bytes(i for i in data))
    def ble_cmd_hardware_i2c_read(self, address, stop, length):
        return struct.pack('<4BBBB', 0, 3, 7, 10, address, stop, length)
    def ble_cmd_hardware_i2c_write(self, address, stop, data):
        return struct.pack('<4BBBB' + str(len(data)) + 's', 0, 3 + len(data), 7, 11, address, stop, len(data), bytes(i for i in data))
    def ble_cmd_hardware_set_txpower(self, power):
        return struct.pack('<4BB', 0, 1, 7, 12, power)
    def ble_cmd_hardware_timer_comparator(self, timer, channel, mode, comparator_value):
        return struct.pack('<4BBBBH', 0, 5, 7, 13, timer, channel, mode, comparator_value)
    def ble_cmd_test_phy_tx(self, channel, length, type):
        return struct.pack('<4BBBB', 0, 3, 8, 0, channel, length, type)
    def ble_cmd_test_phy_rx(self, channel):
        return struct.pack('<4BB', 0, 1, 8, 1, channel)
    def ble_cmd_test_phy_end(self):
        return struct.pack('<4B', 0, 0, 8, 2)
    def ble_cmd_test_phy_reset(self):
        return struct.pack('<4B', 0, 0, 8, 3)
    def ble_cmd_test_get_channel_map(self):
        return struct.pack('<4B', 0, 0, 8, 4)
    def ble_cmd_test_debug(self, input):
        return struct.pack('<4BB' + str(len(input)) + 's', 0, 1 + len(input), 8, 5, len(input), bytes(i for i in input))