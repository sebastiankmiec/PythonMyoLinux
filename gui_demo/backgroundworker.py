#
# PyQt5 imports
#
from PyQt5.QtCore import Qt, QRunnable, QMetaObject, Q_ARG, QObject, pyqtSignal, QTimer, QUrl, QFileInfo
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
#
# Miscellaneous imports
#
import sys
import threading
import time
from enum import Enum

#
# Submodules in this repository
#
from pymyolinux import MyoDongle
from param import *
from movements import MOVEMENT_DESC

#
# Custom PyQt5 events
#
class MyoSearch(QObject):
    searchComplete = pyqtSignal()
class ChartUpdate(QObject):
    axesUpdate = pyqtSignal()
    dataUpdate = pyqtSignal()

class MyoDataWorker(QRunnable):
    """
        A background Qt thread that:
            1) Connects to a device (if possible)
            2) Establishes data to be received
            3) Collects data from a Myo armband device
            4) Optionally, disconnects on a second press, halting the receipt of data
    """
    def __init__(self, port, myo_device, series_list, indices_list, axes_callback, data_call_back, data_list):
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
        self.indices_list   = indices_list
        self.data_list      = data_list
        self.update         = ChartUpdate()
        self.update.axesUpdate.connect(axes_callback)
        self.update.dataUpdate.connect(data_call_back)
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

            # Request an axes update for the charts
            if (self.samples_count != 0) and (self.samples_count % NUM_GUI_SAMPLES == 0):
                self.start_range = self.samples_count
                for i in range(len(self.series_list)):
                    self.series_list[i].clear()
                    # self.series_list[i].removePoints(0, NUM_GUI_SAMPLES-1)
                self.indices_list.clear()
                self.update.axesUpdate.emit()

            # Update chart data
            for i in range(len(self.series_list)):
                #self.series_list[i].append(self.samples_count, emg_list[i])
                self.series_list[i].append(emg_list[i])
            self.indices_list.append(self.samples_count)
            self.update.dataUpdate.emit()

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

            # Update list of all data collected (without scaling)
            #
            # self.data_list.append((time.time(), self.samples_count, emg_list, [orient_w, orient_x, orient_y, orient_z],
            #                       [accel_1, accel_2, accel_3],
            #                       [gyro_1, gyro_2, gyro_3]))
            self.samples_count += 1




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


class GroundTruthWorker(QRunnable):

    def __init__(self, status_label, progress_label, desc_title, desc_explain, cur_movement, video_player,
                    all_video_paths, collect_duration, rest_duration, num_reps):
        super().__init__()

        self.status_label       = status_label
        self.progress_label     = progress_label
        self.desc_title         = desc_title
        self.desc_explain       = desc_explain
        self.cur_movement       = cur_movement
        self.video_player       = video_player
        self.all_video_paths    = all_video_paths
        self.collect_duration   = collect_duration
        self.rest_duration      = rest_duration
        self.num_reps           = num_reps

        self.num_class_A        = 12
        self.num_class_B        = 17

        # Used to update time remaining
        self.timer              = QTimer()
        self.timer.timeout.connect(self.timer_update)
        self.timer_interval     = 100 # 100ms
        self.state_end_event    = self.StateComplete()
        self.state_end_event.stateEnded.connect(self.stop_state)

        # On video load or video completion, this is triggered
        self.video_player.mediaStatusChanged.connect(self.media_status_changed)

        # Configurable parameters
        self.preparation_period = 3.0

        # State variables
        self.current_rep        = 0
        self.state_time_remain  = 0     # seconds
        self.video_playing      = False
        self.stopped            = False
        self.paused             = False
        self.current_label      = None

    class StateComplete(QObject):
        stateEnded = pyqtSignal()

    class MediaStatus(Enum):
        UnknownMediaStatus  = 0
        NoMedia             = 1
        LoadingMedia        = 2
        LoadedMedia         = 3
        StalledMedia        = 4
        BufferingMedia      = 5
        BufferedMedia       = 6
        EndOfMedia          = 7
        InvalidMedia        = 8

    def run(self):

        for exercise in self.all_video_paths:
            ex_label    = exercise[0]
            video_paths = exercise[1]

            for movement_num, video_path in enumerate(video_paths):

                #
                # Setup for current movement
                #
                self.current_rep = 0
                self.progress_label.setText("{} s ({}/{})".format(self.preparation_period, self.current_rep,
                                                                    self.num_reps))
                self.cur_movement.setText("Exercise {} - Movement {} of {}".format(ex_label, movement_num + 1,
                                                                                        len(video_paths)
                                                                                   ))
                current_description = MOVEMENT_DESC[ex_label][movement_num + 1]
                self.desc_title.setText(current_description[0])
                QMetaObject.invokeMethod(self.desc_explain, "setText",
                                         Qt.QueuedConnection, Q_ARG(str, current_description[1]))

                #
                # Preparation period
                #
                self.status_label.setText("Preparing for repetition 1...")
                self.status_label.setStyleSheet("font-weight: bold; font-size: 18pt; color: blue;")
                self.play_video(video_path, self.preparation_period)
                self.set_current_label(ex_label, movement_num + 1)

                while self.video_playing or self.paused:
                    time.sleep(self.timer_interval/1000)

                if self.stopped:
                    return

                #
                # Collecting\resting periods
                #
                for i in range(self.num_reps):

                    # Collect
                    self.current_rep = i + 1
                    self.status_label.setText("Collecting for repetition {}...".format(self.current_rep))
                    self.status_label.setStyleSheet("font-weight: bold; font-size: 18pt; color: green;")
                    self.play_video(video_path, self.collect_duration)
                    self.set_current_label(ex_label, movement_num + 1)

                    while self.video_playing or self.paused:
                        time.sleep(self.timer_interval / 1000)

                    if self.stopped:
                        return

                    # Rest
                    if self.current_rep != self.num_reps:
                        self.status_label.setText("Resting before repetition {}...".format(self.current_rep + 1))
                        self.status_label.setStyleSheet("font-weight: bold; font-size: 18pt; color: orange;")
                        self.play_video(video_path, self.collect_duration)
                        self.set_current_label(ex_label, 0)

                        while self.video_playing or self.paused:
                            time.sleep(self.timer_interval / 1000)


                    if self.stopped:
                        return

    def play_video(self, video_path, period):
        self.video_playing      = True
        self.state_time_remain  = period
        abs_path                = QFileInfo(video_path).absoluteFilePath()
        self.video_player.setMedia(QMediaContent(QUrl.fromLocalFile(abs_path)))

    def media_status_changed(self, state):
        if state == self.MediaStatus.LoadedMedia.value:
            self.video_player.play()
            self.timer.start(self.timer_interval)
        elif state == self.MediaStatus.EndOfMedia.value:
            if self.state_time_remain > self.timer_interval/1000:
                self.video_player.play()

    def timer_update(self):
        self.state_time_remain = max(0, self.state_time_remain - self.timer_interval/1000)
        self.progress_label.setText("{}s ({} / {})".format("{0:.1f}".format(self.state_time_remain),
                                                                self.current_rep, self.num_reps))
        if self.state_time_remain == 0:
            self.timer.stop()
            self.state_end_event.stateEnded.emit()

    def set_current_label(self, ex_label, movement_num):
        if movement_num == 0:
            self.current_label = 0
        elif ex_label == "A":
            self.current_label = movement_num
        elif ex_label == "B":
            self.current_label = movement_num + self.num_class_A
        else:
            self.current_label = movement_num + self.num_class_A + self.num_class_B

    def stop_state(self):
        self.video_player.stop()
        self.video_playing = False

    def force_stop(self):
        self.timer.stop()
        self.video_player.stop()
        self.video_playing  = False
        self.stopped        = True

    def force_pause(self):
        self.timer.stop()
        self.video_player.pause()
        self.paused = True

    def force_unpause(self):
        self.timer.start(self.timer_interval)
        self.video_player.play()
        self.paused = False