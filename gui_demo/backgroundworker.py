#
# PyQt5 imports
#
from PyQt5.QtCore import Qt, QRunnable, QMetaObject, Q_ARG, QObject, pyqtSignal

#
# Miscellaneous imports
#
import sys
import threading
import time

#
# Submodules in this repository
#
from pymyolinux import MyoDongle
from param import *


#
# Custom PyQt5 events
#
class MyoSearch(QObject):
    searchComplete = pyqtSignal()
class ChartUpdate(QObject):
    axesUpdate = pyqtSignal()


class MyoDataWorker(QRunnable):
    """
        A background Qt thread that:
            1) Connects to a device (if possible)
            2) Establishes data to be received
            3) Collects data from a Myo armband device
            4) Optionally, disconnects on a second press, halting the receipt of data
    """
    def __init__(self, port, myo_device, series_list, axes_callback, data_list):
        """
        :param port: Port used to create MyoFoundWidget widget.
        :param myo_device: Address of Myo device to interact with.
        :param series_list: A list of series that hold data, connected to the charts.
        :param axes_callback: Called when chart axes need an update.
        :param data_list: A list of all data collected from this device.
        """
        super().__init__()
        self.dongle         = MyoDongle(port)
        self.myo_device     = myo_device
        self.series_list    = series_list
        self.data_list      = data_list
        self.update         = ChartUpdate()
        self.update.axesUpdate.connect(axes_callback)
        self.scan_period    = 0.2 # seconds

        # States
        self.exiting        = False
        self.running        = False
        self.samples_count  = 0

    def run(self):

        self.running = True

        # Connect
        self.dongle.clear_state()
        self.dongle.connect(self.myo_device)

        # Enable IMU/EMG readings and callback functions
        self.dongle.set_sleep_mode(False)
        self.dongle.enable_imu_readings()
        self.dongle.enable_emg_readings()

        self.dongle.add_joint_emg_imu_handler(self.create_emg_event)

        while self.running:
            self.dongle.scan_for_data_packets(self.scan_period)
        self.dongle.clear_state()
        self.exiting = True


    def create_emg_event(self, emg_list, orient_w, orient_x, orient_y, orient_z,
                                accel_1, accel_2, accel_3, gyro_1, gyro_2, gyro_3):
        """
            On receipt of a data packet from a Myo device, triggered by "scan_for_data_packets", this function is
            called.
        :param emg_list: A list of 8 EMG readings.
        :param orient_w/x/y/z: Magnetometer readings, corresponding to a unit quaternion.
        :param accel_1/2/3: Accelerometer readings.
        :param gyro_1/2/3: Gyroscope readings.

        :return: None
        """

        if self.running:
            # Update chart data
            for i in range(len(self.series_list)):
                self.series_list[i].append(self.samples_count, emg_list[i])

            # Accelerometer values are multipled by the following constant (and are in units of g)
            MYOHW_ACCELEROMETER_SCALE = 2048.0

            # Gyroscope values are multipled by the following constant (and are in units of deg/s)
            MYOHW_GYROSCOPE_SCALE = 16.0

            # Orientation values are multipled by the following constant (units of a unit quaternion)
            MYOHW_ORIENTATION_SCALE = 16384.0

            # Update list of all data collected (with correct rescaling)
            self.data_list.append((time.time(), self.samples_count, emg_list,
                                        [orient_w / MYOHW_ORIENTATION_SCALE, orient_x / MYOHW_ORIENTATION_SCALE,
                                         orient_y / MYOHW_ORIENTATION_SCALE, orient_z / MYOHW_ORIENTATION_SCALE],
                                        [accel_1 / MYOHW_ACCELEROMETER_SCALE, accel_2 / MYOHW_ACCELEROMETER_SCALE,
                                         accel_3 / MYOHW_ACCELEROMETER_SCALE],
                                        [gyro_1 / MYOHW_GYROSCOPE_SCALE, gyro_2 / MYOHW_GYROSCOPE_SCALE,
                                         gyro_3 / MYOHW_GYROSCOPE_SCALE]))

            # Update list of all data collected
            # self.data_list.append((time.time(), self.samples_count, emg_list, [orient_w, orient_x, orient_y, orient_z],
            #                       [accel_1, accel_2, accel_3],
            #                       [gyro_1, gyro_2, gyro_3]))

            self.samples_count += 1

            # Request an axes update for the charts
            if self.samples_count % NUM_GUI_SAMPLES == 0:
                for i in range(len(self.series_list)):
                    self.series_list[i].removePoints(0, NUM_GUI_SAMPLES-1)
                self.update.axesUpdate.emit()


class MyoSearchWorker(QRunnable):
    """
        A background Qt thread that:
            1) Searches for Myo devices
            2) Updates a progress bar
            3) Emits an event upon completion
    """
    def __init__(self, cur_port, progress_bar, finished_callback, increments):
        """
        :param cur_port: A communication port to search for Myo devices on.
        :param progress_bar: A progress bar to update.
        :param finished_callback: A callback function, called after searching is complete.
        """
        super().__init__()
        self.cur_port       = cur_port
        self.progress_bar   = progress_bar
        self.finish         = MyoSearch()
        self.finish.searchComplete.connect(finished_callback)

        #
        # Configurable
        #
        self.increments         = increments    # Progress bar increments
        self.time_to_search     = 3             # In seconds
        self.currrent_increment = 0

    def run(self):

        while self.currrent_increment <= self.increments:

            if self.currrent_increment == 0:
                self.myo_dongle = MyoDongle(self.cur_port)
                self.myo_dongle.clear_state()
                self.myo_found = []

                # Create a (Python) background thread to perform the scanning of packets
                def helper_func():
                    self.myo_found.extend(self.myo_dongle.discover_myo_devices(self.time_to_search))
                self.background_thread = threading.Thread(target=helper_func)
                self.background_thread.start()

            self.currrent_increment += 1

            # Done searching!
            if self.currrent_increment > self.increments:
                self.background_thread.join()  # Wait for work completion
                if len(self.myo_found) > 0:
                    self.finish.searchComplete.emit()

            else:
                # Inter-thread communication (GUI thread will make the call to update the progress bar):
                QMetaObject.invokeMethod(self.progress_bar, "setValue",
                                            Qt.QueuedConnection, Q_ARG(int, self.currrent_increment))
                time.sleep(self.time_to_search/self.increments)

        # Clear Myo device states and disconnect
        self.myo_dongle.clear_state()