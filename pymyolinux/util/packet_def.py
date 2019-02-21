from enum import Enum
import copy

#
# See "https://github.com/thalmiclabs/myo-bluetooth/blob/master/myohw.h" as a reference
#
MYO_SERVICE_BASE_UUID = bytearray(b"\x42\x48\x12\x4a\x7f\x2c\x48\x47\xb9\xde\x04\xa9\x00\x00\x06\xd5")

def get_full_uuid(short_uuid):
    new_uuid = copy.deepcopy(MYO_SERVICE_BASE_UUID)
    new_uuid[12] = short_uuid[1]
    new_uuid[13] = short_uuid[0]
    return new_uuid

class HW_Services(Enum):
    ControlService              = b"\x00\x01" # Myo info service (advertising packets)

    IMUDataCharacteristic       = b"\x04\x02"   # Notify only characteristic for IMU data

    CommandCharacteristic       = b"\x04\x01"   # A write only attribute to issue commands (such as setting Myo mode).

    EmgData0Characteristic      = b"\x01\x05"   # Raw EMG data. Notify-only characteristic.
    EmgData1Characteristic      = b"\x02\x05"   # Raw EMG data. Notify-only characteristic.
    EmgData2Characteristic      = b"\x03\x05"   # Raw EMG data. Notify-only characteristic.
    EmgData3Characteristic      = b"\x04\x05"   # Raw EMG data. Notify-only characteristic.

    BatteryLevelCharacteristic  = b"\x19\x2a"   # Current battery level information. Read/notify characteristic
                                                # Note: The order of bytes

########################################################################################################################
########################################################################################################################

#
# Bluegiga packet defintions
#

# Message / technology types
bluetooth_resp      = 0x00
bluetooth_event     = 0x80
wifi_resp           = 0x08
wifi_event          = 0x88
packet_type_bits    = 0x88
command_message     = 0x00

packet_header_legnth    = 4
packet_length_high_bits = 0x07

class BGAPI_Classes(Enum):
    Connection  = 0x03 # Provides access to connection management functions
    GATT        = 0x04 # Functions to access remote devices GATT database
    GAP         = 0x06 # GAP (Generic Access Profile) functions

class GATT_Response_Commands(Enum):
    ble_rsp_attclient_read_by_group_type = 0x01
    ble_rsp_attclient_find_information   = 0x03
    ble_rsp_attclient_attribute_write    = 0x05

class GATT_Event_Commands(Enum):
    ble_evt_attclient_procedure_completed       = 0x01
    ble_evt_attclient_group_found               = 0x02
    ble_evt_attclient_find_information_found    = 0x04
    ble_evt_attclient_attribute_value           = 0x05

class GAP_Event_Commands(Enum):
    ble_evt_gap_scan_response = 0x00
    ble_evt_gap_mode_changed  = 0x01

class GAP_Response_Commands(Enum):
    ble_rsp_gap_set_mode        = 0x01
    ble_rsp_gap_discover        = 0x02
    ble_rsp_gap_connect_direct  = 0x03
    ble_rsp_gap_end_procedure   = 0x04

# Connection (response/event) commands
ble_rsp_connection_disconnect   = 0x00 # Response
ble_evt_connection_status       = 0x00 # Event
ble_evt_connection_disconnected = 0x04 # Event

########################################################################################################################
########################################################################################################################
#
# Bluegiga packet definitions (for transmission)
#

# GATT
ble_cmd_connection_disconnect           = 0x00
ble_cmd_attclient_read_by_group_type    = 0x01
ble_cmd_attclient_find_information      = 0x03
ble_cmd_attclient_read_by_handle        = 0x04
ble_cmd_attclient_attribute_write       = 0x05

# GAP
ble_cmd_gap_set_mode        = 0x01
ble_cmd_gap_discover        = 0x02
ble_cmd_gap_connect_direct  = 0x03
ble_cmd_gap_end_procedure   = 0x04

########################################################################################################################
########################################################################################################################

#
# BLE Command definitions
#
disable_notifications   = b"\x00\x00"
enable_notifications    = b"\x01\x00"

class GAP_Discoverable_Modes(Enum):
    gap_non_discoverable        = 0
    gap_limited_discoverable    = 1
    gap_general_discoverable    = 2
    gap_broadcast               = 3
    gap_user_data               = 4
    gap_discoverable_mode_max   = 5

class GAP_Connectable_Modes(Enum):
    gap_non_connectable         = 0
    gap_directed_connectable    = 1
    gap_undirected_connectable  = 2
    gap_scannable_connectable   = 3
    gap_connectable_mode_max    = 4

class GAP_Discover_Mode(Enum):
    gap_discover_limited        = 0
    gap_discover_generic        = 1
    gap_discover_observation    = 2
    gap_discover_mode_max       = 3

class Connection_Status(Enum):
    connection_connected         = 1
    connection_encrypted         = 2
    connection_completed         = 4
    connection_parameters_change = 8
    connection_connstatus_max    = 9

#
# BLE Response Conditions
#
GAP_set_mode_success            = 0
disconnect_procedure_started    = 0
disconnect_due_local_user       = 0
GAP_start_procedure_success     = 0
GAP_end_procedure_success       = 0
GATT_end_procedure_success      = 0
find_info_success               = 0
write_success                   = 0


#
# Bluetooth Error Codes
#
connection_timeout              = 0x0208
connection_term_by_local_host   = 0x0216

########################################################################################################################
########################################################################################################################

#
# Myo Command Definitions
#   > Reference: https://github.com/thalmiclabs/myo-bluetooth/blob/master/myohw.h
#
class Myo_Commands(Enum):
    myohw_command_set_mode          = 0x01  # Set EMG and IMU modes.
    myohw_command_vibrate           = 0x03  # Vibrate.
    myohw_command_deep_sleep        = 0x04  # Put Myo into deep sleep.
    myohw_command_vibrate2          = 0x07  # Extended vibrate.
    myohw_command_set_sleep_mode    = 0x09  # Set sleep mode.
    myohw_command_unlock            = 0x0a  # Unlock Myo.
    myohw_command_user_action       = 0x0b  # Notify user that an action has been recognized / confirmed.

class EMG_Modes(Enum):
    myohw_emg_mode_none         = 0x00  # Do not send EMG data.
    myohw_emg_mode_send_emg     = 0x02  # Send filtered EMG data.
    myohw_emg_mode_send_emg_raw = 0x03  # Send raw(unfiltered) EMG data.

class IMU_Modes(Enum):
    myohw_imu_mode_none         = 0x00  # Do not send IMU data or events.
    myohw_imu_mode_send_data    = 0x01  # Send IMU data streams (accelerometer, gyroscope, and orientation).
    myohw_imu_mode_send_events  = 0x02  # Send motion events detected by the IMU (e.g. taps).
    myohw_imu_mode_send_all     = 0x03  # Send both IMU data streams and motion events.
    myohw_imu_mode_send_raw     = 0x04  # Send raw IMU data streams.

class Classifier_Modes(Enum):
    myohw_classifier_mode_disabled  = 0x00   # Disable and reset the internal state of the onboard classifier.
    myohw_classifier_mode_enabled   = 0x01   # Send classifier events (poses and arm events).

class Sleep_Modes(Enum):
    myohw_sleep_mode_normal      = 0 # Normal sleep mode; Myo will sleep after a period of inactivity.
    myohw_sleep_mode_never_sleep = 1 # Never go to sleep.