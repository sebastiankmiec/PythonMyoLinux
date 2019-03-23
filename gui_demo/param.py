########################################################################################################################
##### CONFIGURABLE PARAMETERS
########################################################################################################################

SINGLE_MYO_FILENAME = "myodata.csv"

#
# Multiple Myo devices
#
FILENAME_1      = "myo_1_data.csv"
FILENAME_2      = "myo_2_data.csv"
FILENAME_all    = "myo_all_data.csv"
BUFFER_PERIOD   = 2                         # How many of the first few seconds of Myo data is ignored when saving
COPY_THRESHOLD  = 30/1000                   # How much can timestamps of readings from both devices differ

#
# (Myo data enforced) Rescaling parameters
#
# Accelerometer values are multipled by the following constant (and are in units of g)
MYOHW_ACCELEROMETER_SCALE = 2048.0

# Gyroscope values are multipled by the following constant (and are in units of deg/s)
MYOHW_GYROSCOPE_SCALE = 16.0

# Orientation values are multipled by the following constant (units of a unit quaternion)
MYOHW_ORIENTATION_SCALE = 16384.0

#
# EMG Plotting parameters
#
NUM_GUI_SAMPLES = 400                       # Number of EMG samples displayed at a given time
SYMBOL_SIZE     = 5                         # Size of circle symbols in pixels
Y_TICK_SPACING  = 40

########################################################################################################################
########################################################################################################################
########################################################################################################################