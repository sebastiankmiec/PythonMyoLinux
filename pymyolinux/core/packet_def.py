from enum import Enum

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