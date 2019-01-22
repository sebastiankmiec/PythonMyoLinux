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
BUFFER_PERIOD   = 1                         # How many of the first few seconds of Myo data is ignored when saving
COPY_THRESHOLD  = 20                        # How much can timestamps of readings from both devices differ

NUM_GUI_SAMPLES = 400                       # Number of EMG samples displayed at a given time

########################################################################################################################
########################################################################################################################
########################################################################################################################