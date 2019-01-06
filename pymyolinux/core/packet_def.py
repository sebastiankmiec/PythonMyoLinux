from enum import Enum

# See "https://github.com/thalmiclabs/myo-bluetooth/blob/master/myohw.h" as a reference
MYO_SERVICE_BASE_UUID = bytearray(b"\x42\x48\x12\x4a\x7f\x2c\x48\x47\xb9\xde\x04\xa9\x00\x00\x06\xd5")

#
# Command definitions
#
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
# Response Conditions
#
GAP_set_mode_success            = 0
disconnect_procedure_started    = 0
disconnect_due_local_user       = 0
GAP_start_procedure_success     = 0
GAP_end_procedure_success       = 0