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

# MyoSearchWorker
class MyoSearch(QObject):
    searchComplete = pyqtSignal()

# Used by MyoDataWorker
class DataWorkerUpdate(QObject):
    axesUpdate      = pyqtSignal()
    dataUpdate      = pyqtSignal()
    workerStarted   = pyqtSignal()
    workerStopped   = pyqtSignal()
    connectFailed   = pyqtSignal()
    disconOccurred  = pyqtSignal()
    batteryUpdate   = pyqtSignal([int])

# Used by GroundTruthWorker
class GTWorkerUpdate(QObject):
    workerStarted   = pyqtSignal()
    workerUnpaused  = pyqtSignal()
    workerPaused    = pyqtSignal()
    workerStopped   = pyqtSignal()

class MyoDataWorker(QRunnable):
    """
        A background Qt thread that:
            1) Connects to a device (if possible)
            2) Establishes data to be received
            3) Collects data from a Myo armband device
            4) Passes data to MyoFoundWidget for plotting
            5) Optionally, disconnects on a second press, halting the receipt of data
    """
    def __init__(self, port, myo_device, series_list, indices_list, axes_callback, data_call_back, data_list,
                    on_worker_started, on_worker_stopped, on_connect_failed, on_discon_occurred, battery_notify,
                    create_event, get_current_label):
        """
        :param port: Port used to create MyoFoundWidget widget.
        :param myo_device: Address of Myo device to interact with.
        :param series_list: A list of series that hold data, corresponding to the charts.
        :param indices_list: A list of sample indices, corresponding to the charts.
        :param axes_callback: Called when chart axes need an update.
        :param data_call_back: A function called on receipt of EMG data.
        :param data_list: A list of all data collected from this device.
        :param on_worker_started: A function called when this background worker starts.
        :param on_worker_stopped: A function called when this background worker exits run().
        :param on_connect_failed: A function called when this background worker fails to connect to a Myo device.
        :param on_discon_occurred: A function called when the corresponding Myo device disconnects unexpectedly.
        :param battery_notify: A function called on receipt of battery level update.
        :param create_event: A function that determines whether to push data updates, based on open tabs.
        :param get_current_label: A function that returns the current ground truth label being collected.
        """
        super().__init__()
        self.port               = port
        self.myo_device         = myo_device
        self.series_list        = series_list
        self.indices_list       = indices_list
        self.data_list          = data_list
        self.update             = DataWorkerUpdate()
        self.create_event       = create_event
        self.get_current_label  = get_current_label

        # Signals
        self.update.axesUpdate.connect(axes_callback)
        self.update.dataUpdate.connect(data_call_back)
        self.update.workerStarted.connect(on_worker_started)
        self.update.workerStopped.connect(on_worker_stopped)
        self.update.connectFailed.connect(on_connect_failed)
        self.update.disconOccurred.connect(on_discon_occurred)
        self.update.batteryUpdate.connect(battery_notify)

        # Configurable parameters
        self.scan_period        = 0.2 # seconds
        self.update_period      = 4
        self.emg_sample_rate    = 200 # 200 hz

        # States
        self.running        = False
        self.samples_count  = 0
        self.complete       = False

        # Timestamp states
        self.reset_period   = 200
        self.cur_sample     = 0
        self.base_time      = None

    def run(self):
        # State setup
        self.dongle     = MyoDongle(self.port)
        self.running    = True
        self.complete   = False
        self.update.workerStarted.emit()

        # Connect
        self.dongle.clear_state()
        connect_success = self.dongle.connect(self.myo_device)
        if not connect_success:
            self.update.connectFailed.emit()
            return

        # Attempt to update battery level
        level = self.dongle.read_battery_level()
        if not (level is None):
            self.update.batteryUpdate.emit(level)

        # Enable IMU/EMG readings and callback functions
        self.dongle.set_sleep_mode(False)
        self.dongle.enable_imu_readings()
        self.dongle.enable_emg_readings()
        self.dongle.add_joint_emg_imu_handler(self.create_emg_event)

        disconnect_occurred = False
        while self.running and (not disconnect_occurred):
            disconnect_occurred = self.dongle.scan_for_data_packets_conditional(self.scan_period)

        if disconnect_occurred:
            self.dongle.clear_state()
            self.update.disconOccurred.emit()
        else:
            self.dongle.clear_state()
            self.update.workerStopped.emit()

        self.complete = True

    def create_emg_event(self, emg_list, orient_w, orient_x, orient_y, orient_z,
                                accel_1, accel_2, accel_3, gyro_1, gyro_2, gyro_3, sample_num):
        """
            On receipt of a data packet from a Myo device, triggered by "scan_for_data_packets", this function is
            called.
        :param emg_list: A list of 8 EMG readings.
        :param orient_w/x/y/z: Magnetometer readings, corresponding to a unit quaternion.
        :param accel_1/2/3: Accelerometer readings.
        :param gyro_1/2/3: Gyroscope readings.
        :param sample_num: [int] 1/2 : Sample 1 or 2 (data is sent in pairs)
        """

        if self.running:

            if self.cur_sample % self.reset_period == 0:
                self.base_time = time.time()
                self.cur_sample = 0

            time_received    = self.base_time + self.cur_sample * (1/self.emg_sample_rate)
            self.cur_sample += 1

            # Is this tab corresponding to this worker open
            create_events = self.create_event()

            # Request an axes update for the charts
            if (self.samples_count != 0) and (self.samples_count % NUM_GUI_SAMPLES == 0):
                self.start_range = self.samples_count
                for i in range(len(self.series_list)):
                    self.series_list[i].clear()
                    # self.series_list[i].removePoints(0, NUM_GUI_SAMPLES-1)
                self.indices_list.clear()

                if create_events:
                    self.update.axesUpdate.emit()

            # Update chart data
            for i in range(len(self.series_list)):
                #self.series_list[i].append(self.samples_count, emg_list[i])
                self.series_list[i].append(emg_list[i])
            self.indices_list.append(self.samples_count)

            if create_events:
                if self.samples_count % self.update_period == 0:
                    self.update.dataUpdate.emit()

            # Accelerometer values are multipled by the following constant (and are in units of g)
            MYOHW_ACCELEROMETER_SCALE = 2048.0

            # Gyroscope values are multipled by the following constant (and are in units of deg/s)
            MYOHW_GYROSCOPE_SCALE = 16.0

            # Orientation values are multipled by the following constant (units of a unit quaternion)
            MYOHW_ORIENTATION_SCALE = 16384.0

            #
            # Update list of all data collected (with correct rescaling)
            #
            current_label = self.get_current_label()                        # Grabbed from GT Helper

            self.data_list.append((time_received, self.samples_count, emg_list,
                                        [orient_w / MYOHW_ORIENTATION_SCALE, orient_x / MYOHW_ORIENTATION_SCALE,
                                         orient_y / MYOHW_ORIENTATION_SCALE, orient_z / MYOHW_ORIENTATION_SCALE],
                                        [accel_1 / MYOHW_ACCELEROMETER_SCALE, accel_2 / MYOHW_ACCELEROMETER_SCALE,
                                         accel_3 / MYOHW_ACCELEROMETER_SCALE],
                                        [gyro_1 / MYOHW_GYROSCOPE_SCALE, gyro_2 / MYOHW_GYROSCOPE_SCALE,
                                         gyro_3 / MYOHW_GYROSCOPE_SCALE],
                                        current_label))

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
        :param increments: Number of increments to progress bar.
        """
        super().__init__()
        self.cur_port       = cur_port
        self.progress_bar   = progress_bar
        self.finish         = MyoSearch()
        self.finish.searchComplete.connect(finished_callback)

        # States
        self.complete   = False

        #
        # Configurable
        #
        self.increments         = increments    # Progress bar increments
        self.time_to_search     = 3             # In seconds
        self.currrent_increment = 0

    def run(self):
        self.complete   = False

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
                self.background_thread.join()               # Wait for work completion
                self.finish.searchComplete.emit()

            else:
                # Inter-thread communication (GUI thread will make the call to update the progress bar):
                QMetaObject.invokeMethod(self.progress_bar, "setValue",
                                            Qt.QueuedConnection, Q_ARG(int, self.currrent_increment))
                time.sleep(self.time_to_search/self.increments)

        # Clear Myo device states and disconnect
        self.myo_dongle.clear_state()
        self.complete   = True


class GroundTruthWorker(QRunnable):
    """
        A background worker that controls playback of videos and text field updates, for the GT Helper.
    """

    def __init__(self, status_label, progress_label, desc_title, desc_explain, cur_movement, video_player,
                    all_video_paths, collect_duration, rest_duration, num_reps, on_worker_started, on_worker_unpaused,
                    on_worker_paused, on_worker_stopped):
        """
        :param status_label:
        :param progress_label:
        :param desc_title:
        :param desc_explain:
        :param cur_movement:
        :param video_player:
        :param all_video_paths:
        :param collect_duration:
        :param rest_duration:
        :param num_reps:
        :param on_worker_started:
        :param on_worker_unpaused:
        :param on_worker_paused:
        :param on_worker_stopped:
        """
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

        # Signals
        self.update                 = GTWorkerUpdate()
        self.update.workerStarted.connect(on_worker_started)
        self.update.workerUnpaused.connect(on_worker_unpaused)
        self.update.workerPaused.connect(on_worker_paused)
        self.update.workerStopped.connect(on_worker_stopped)

        # Used to update time remaining
        self.timer              = QTimer()
        self.timer.timeout.connect(self.timer_update)
        self.timer_interval     = 100                               # units of ms
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
        self.complete           = False

    # On finish of repetition/rest/prepation
    class StateComplete(QObject):
        stateEnded = pyqtSignal()

    # Qt5, QMediaPlayer enum
    # > "Defines the status of a media player's current media."
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

        # Re-enable video buttons
        self.complete = False
        self.update.workerStarted.emit()

        for exercise in self.all_video_paths:

            if self.stopped:
                break

            ex_label    = exercise[0]
            video_paths = exercise[1]

            for movement_num, video_path in enumerate(video_paths):

                if self.stopped:
                    break
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
                self.current_label = None

                while self.video_playing or (self.paused and not self.stopped):
                    time.sleep(self.timer_interval / 1000)

                if self.stopped:
                    break

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

                    while self.video_playing or (self.paused and not self.stopped):
                        time.sleep(self.timer_interval / 1000)

                    if self.stopped:
                        break

                    # Rest
                    if self.current_rep != self.num_reps:
                        self.status_label.setText("Resting before repetition {}...".format(self.current_rep + 1))
                        self.status_label.setStyleSheet("font-weight: bold; font-size: 18pt; color: orange;")
                        self.play_video(video_path, self.collect_duration)
                        self.current_label = 0

                        while self.video_playing or (self.paused and not self.stopped):
                            time.sleep(self.timer_interval / 1000)

                    if self.stopped:
                        break

        #
        # If user pressed stop
        #
        if self.stopped:
            self.update.workerStopped.emit()
        self.complete = True

    def play_video(self, video_path, period):
        """
            Prepare video for playback, media_status_changed is called when loading finishes.

        :param video_path: Path to video
        :param period: Time to play video
        """
        self.video_playing      = True
        self.state_time_remain  = period
        abs_path                = QFileInfo(video_path).absoluteFilePath()
        self.video_player.setMedia(QMediaContent(QUrl.fromLocalFile(abs_path)))

    def media_status_changed(self, state):
        """
            This function is called when the media player's media finishes loading/playing/etc.
        :param state: State corresponding to media player update
        """
        if state == self.MediaStatus.LoadedMedia.value:
            self.video_player.play()
            self.timer.start(self.timer_interval)
        elif state == self.MediaStatus.EndOfMedia.value:
            if self.state_time_remain > self.timer_interval/1000:
                self.video_player.play()

    def timer_update(self):
        """
            This function is called every "self.timer_interval" seconds, upon timer completion.
        """
        self.state_time_remain = max(0, self.state_time_remain - self.timer_interval/1000)
        self.progress_label.setText("{}s ({} / {})".format("{0:.1f}".format(self.state_time_remain),
                                                                self.current_rep, self.num_reps))
        if self.state_time_remain == 0:
            self.timer.stop()
            self.state_end_event.stateEnded.emit()

    def set_current_label(self, ex_label, movement_num):
        """
            Computes the ground truth label
        :param ex_label: [str] Exercise "A/B/C"
        :param movement_num: [int] Movement number
        """
        if ex_label == "A":
            self.current_label = movement_num
        elif ex_label == "B":
            self.current_label = movement_num + self.num_class_A
        else:
            self.current_label = movement_num + self.num_class_A + self.num_class_B

    def stop_state(self):
        """
            Upon completion of a repetition/rest/prepation state, this function is called.
        """
        self.video_player.stop()
        self.video_playing = False

    def force_stop(self):
        """
            GroundTruthHelper calls this function to stop this background worker thread.
        """
        self.timer.stop()
        self.video_player.stop()
        self.video_playing  = False
        self.stopped        = True

    def force_pause(self):
        """
            GroundTruthHelper calls this function to pause this background worker thread.
        """
        self.timer.stop()
        self.video_player.pause()
        self.paused = True

        # Re-enable video buttons
        self.update.workerPaused.emit()

    def force_unpause(self):
        """
            GroundTruthHelper calls this function to unpause this background worker thread.
        """
        self.timer.start(self.timer_interval)
        self.video_player.play()
        self.paused = False

        # Re-enable video buttons
        self.update.workerUnpaused.emit()