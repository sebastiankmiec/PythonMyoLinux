#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QProgressDialog, QTabWidget, QFileDialog, QMessageBox,
                             QWidget, QLabel, QHBoxLayout, QVBoxLayout, QCheckBox, QFrame, QMainWindow, QPushButton,
                             QGridLayout, QSizePolicy, QGroupBox, QTextEdit, QLineEdit, QErrorMessage, QProgressBar)

from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import (QSize, QThreadPool, Qt, QRunnable, QMetaObject, Q_ARG, QObject, pyqtSignal, QTimer, QUrl,\
                            QFileInfo)
from PyQt5.QtMultimediaWidgets import QVideoWidget
import pyqtgraph as pg
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

#
# Miscellaneous imports
#
import threading
from enum import Enum
import time
from functools import partial
from os.path import curdir, exists, join, abspath
import copy
from serial.tools.list_ports import comports

#
# Submodules in this repository
#
from pymyolinux import MyoDongle
from movements import *
from param import *



########################################################################################################################
########################################################################################################################
########################################################################################################################
#
# Custom PyQt5 events (used by QRunnables)
#
########################################################################################################################
########################################################################################################################
########################################################################################################################

# Used by GroundTruthWorker
class GTWorkerUpdate(QObject):
    workerStarted = pyqtSignal()
    workerUnpaused = pyqtSignal()
    workerPaused = pyqtSignal()
    workerStopped = pyqtSignal()

########################################################################################################################
########################################################################################################################
########################################################################################################################


class OnlineTraining(QWidget):

    def __init__(self):
        super().__init__()

        # Each video path has the following format:
        #   -> (1, 2, 3):
        #       1: Path relative to video_dir
        #       2: Minimum video number in specified path
        #       3. Maximum video number in specified path
        #
        self.video_dir = "../gesture_videos"
        self.video_path_template = [
            ("arrows/exercise_a/a{}.mp4", 12),
            ("arrows/exercise_b/b{}.mp4", 17),
            ("arrows/exercise_c/c{}.mp4", 23)
        ]

        # States
        self.playing = False
        self.all_video_paths = None
        self.worker = None
        self.unpausing = False
        self.pausing = False
        self.shutdown = False

        self.init_ui()

    def init_ui(self):

        # DataTools top layout
        self.setContentsMargins(5, 15, 5, 5)

        #
        # Contains all widgets within this main window
        #
        #top_level_widget = QWidget(self)
        #self.setCentralWidget(top_level_widget)
        top_layout = QGridLayout()
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(12)

        #
        # Top Text
        #
        self.status_label = QLabel("Waiting to Start...")
        self.status_label.setStyleSheet(" font-weight: bold; font-size: 18pt; "
                                        "   color: red;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.progress_label = QLabel("0.0s (1 / 1)")
        self.progress_label.setStyleSheet(" font-size: 16pt; color: black;")
        self.progress_label.setAlignment(Qt.AlignCenter)

        #
        # Video box
        #
        self.setWindowTitle("Ground Truth Helper")
        self.video_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        videoWidget = QVideoWidget()

        #
        # Description Box
        #
        description_box = QGroupBox()
        description_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        description_box.setContentsMargins(0, 0, 0, 0)
        desc_layout = QVBoxLayout()
        desc_layout.setContentsMargins(0, 0, 0, 0)
        desc_layout.setSpacing(0)

        self.desc_title = QLabel("No Movement")
        self.desc_title.setStyleSheet("border: 4px solid gray; font-weight: bold; font-size: 14pt;")
        self.desc_title.setAlignment(Qt.AlignCenter)
        self.desc_explain = QTextEdit("No description available.")
        self.desc_explain.setStyleSheet("border: 4px solid gray; font-size: 12pt; border-color: black;")
        self.desc_explain.setReadOnly(True)

        desc_layout.addWidget(self.desc_title)
        desc_layout.addWidget(self.desc_explain)
        desc_layout.setStretchFactor(self.desc_title, 1)
        desc_layout.setStretchFactor(self.desc_explain, 9)
        description_box.setLayout(desc_layout)

        #
        # Start, Pause, Stop Buttons
        #
        start_stop_box = QGroupBox()
        start_stop_box.setContentsMargins(0, 0, 0, 0)
        start_stop_box.setObjectName("StartBox")
        start_box_layout = QGridLayout()

        self.current_movement = QLabel("")
        self.current_movement.setAlignment(Qt.AlignCenter)
        self.current_movement.setStyleSheet("background-color: #cccccc; border: 1px solid gray; font-size: 14pt;"
                                            "   font-weight: bold;")
        start_box_layout.addWidget(self.current_movement, 0, 1, 1, 3)

        self.play_button = QPushButton()
        self.play_button.setText("Start")
        self.play_button.setStyleSheet("font-weight: bold;")
        self.play_button.clicked.connect(self.start_videos)
        self.pause_button = QPushButton()
        self.pause_button.setText("Pause")
        self.pause_button.setStyleSheet("font-weight: bold;")
        self.pause_button.clicked.connect(self.pause_videos)
        self.stop_button = QPushButton()
        self.stop_button.setText("Stop")
        self.stop_button.setStyleSheet("font-weight: bold;")
        self.stop_button.clicked.connect(self.stop_videos)
        start_box_layout.addWidget(self.play_button, 2, 1)
        start_box_layout.addWidget(self.pause_button, 2, 2)
        start_box_layout.addWidget(self.stop_button, 2, 3)

        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setLineWidth(2)
        start_box_layout.addWidget(separator, 1, 1, 1, 3)

        start_stop_box.setLayout(start_box_layout)
        start_box_layout.setColumnStretch(0, 10)
        start_box_layout.setColumnStretch(1, 10)
        start_box_layout.setColumnStretch(2, 10)
        start_box_layout.setColumnStretch(3, 10)
        start_box_layout.setColumnStretch(4, 10)
        start_box_layout.setRowStretch(0, 1)
        start_box_layout.setRowStretch(1, 1)
        start_box_layout.setRowStretch(2, 1)

        #
        # Training Session Parameters
        #
        parameters_box = QGroupBox()
        parameters_box.setTitle("Collection Parameters")
        parameters_box.setObjectName("CollecParamBox")
        parameters_box.setStyleSheet(
            "QGroupBox#CollecParamBox { border: 1px solid gray; border-radius: 7px; margin-top: 0.5em;"
            "                              font-weight: bold; }"
            "QGroupBox#CollecParamBox::title { subcontrol-origin: margin; left: 9px; }")
        parameters_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        top_param_layout = QGridLayout()

        rep_title = QLabel("Number of Repetitions")
        self.num_reps = QLineEdit("6")
        top_param_layout.addWidget(rep_title, 0, 0)
        top_param_layout.addWidget(self.num_reps, 0, 2, 1, 2)
        top_param_layout.setSpacing(0)

        collect_title = QLabel("(<b>Collect</b>\\<b>Rest</b>) Duration")
        self.collect_entry = QLineEdit("5.0")
        self.rest_entry = QLineEdit("3.0")
        top_param_layout.addWidget(collect_title, 1, 0)
        top_param_layout.addWidget(self.collect_entry, 1, 2)
        top_param_layout.addWidget(self.rest_entry, 1, 3)

        ex_label = QLabel("Exercise (<b>A</b>\\<b>B</b>\\<b>C</b>)")
        check_layout = QHBoxLayout()
        check_layout.setSpacing(0)
        check_layout.setContentsMargins(0, 0, 0, 0)

        self.ex_a_check = QCheckBox()
        self.ex_a_check.setChecked(True)
        self.ex_b_check = QCheckBox()
        self.ex_b_check.setChecked(True)
        self.ex_c_check = QCheckBox()
        self.ex_c_check.setChecked(True)
        check_layout.addWidget(self.ex_a_check)
        check_layout.addWidget(self.ex_b_check)
        check_layout.addWidget(self.ex_c_check)
        top_param_layout.addWidget(ex_label, 2, 0)
        top_param_layout.addLayout(check_layout, 2, 2, 1, 2)
        top_param_layout.setColumnStretch(0, 5)
        top_param_layout.setColumnStretch(1, 1)
        top_param_layout.setColumnStretch(2, 3)
        top_param_layout.setColumnStretch(3, 3)
        parameters_box.setLayout(top_param_layout)

        #
        # Positions and sizes of all widgets in grid layout
        #
        top_layout.addWidget(self.status_label, 0, 0)
        top_layout.addWidget(self.progress_label, 0, 1)
        top_layout.addWidget(videoWidget, 1, 0)
        top_layout.addWidget(description_box, 1, 1)
        top_layout.addWidget(start_stop_box, 2, 0)
        top_layout.addWidget(parameters_box, 2, 1)
        top_layout.setRowStretch(0, 7)
        top_layout.setRowStretch(1, 100)
        top_layout.setRowStretch(2, 10)
        top_layout.setColumnStretch(0, 66)
        top_layout.setColumnStretch(1, 33)

        #
        # Set widget to contain window contents
        #
        #top_level_widget.setLayout(top_layout)
        self.setLayout(top_layout)
        self.video_player.setVideoOutput(videoWidget)
        self.video_player.setMuted(True)

    def enable_video_buttons(self, state_play, state_pause, state_stop):
        """
            A helper function to set the current states of the play/pause/stop buttons.

        :param state_play: [bool] Enable/disable play button.
        :param state_pause: [bool] Enable/disable pause button.
        :param state_stop: [bool] Enable/disable stop button.
        :return:
        """
        self.play_button.setEnabled(state_play)
        self.pause_button.setEnabled(state_pause)
        self.stop_button.setEnabled(state_stop)

    def start_videos(self):
        """
            A function called when the "Start" button is pressed.
                > Either
                    i. Starts the background worker thread to play video, update text fields and more
                    ii. Unpauses the background worker, in order to continue doing the aforesaid.
        """

        # Disable play/pause/stop buttons until it is safe
        self.enable_video_buttons(False, False, False)

        # If any button click is still being processed
        if (self.unpausing) or (self.pausing) or (self.shutdown):
            return

        if self.playing:
            self.enable_video_buttons(False, True, True)
            return

        if self.worker is not None:
            self.worker.force_unpause()
            return

        #
        # Check for valid inputs
        #
        def throw_error_message(self, message):
            # Re-enable video buttons
            self.enable_video_buttons(True, False, False)

            # Display warning
            self.warning = QErrorMessage()
            self.warning.showMessage(message)
            self.warning.show()
            return None

        def acquire_var(self, text, widget_name, func):
            try:
                temp = func(text)
            except:
                # Re-enable video buttons
                self.enable_video_buttons(True, False, False)

                # Display warning
                if func == float:
                    return throw_error_message(self, "Please set a valid float for \"{}\".".format(widget_name))
                else:
                    return throw_error_message(self, "Please set a valid integer for \"{}\".".format(widget_name))
            return temp

        if ((acquire_var(self, self.collect_entry.text(), "Collect Duration", float) is None) or
                (acquire_var(self, self.collect_entry.text(), "Rest Duration", float) is None) or
                (acquire_var(self, self.num_reps.text(), "Number of Repetitions", int) is None)):
            return

        self.collect_duration = acquire_var(self, self.collect_entry.text(), "Collect Duration", float)
        self.rest_duration = acquire_var(self, self.rest_entry.text(), "Rest Duration", float)
        self.repetitions = acquire_var(self, self.num_reps.text(), "Rest Duration", int)

        if (not self.ex_a_check.isChecked()) and (not self.ex_b_check.isChecked()) and (
                not self.ex_c_check.isChecked()):
            return throw_error_message(self, "Please select at least one exercise.")

        if self.collect_duration < 1.0:
            return throw_error_message(self, "Please select a collect duration >= 1.0s.")
        if self.rest_duration < 1.0:
            return throw_error_message(self, "Please select a rest duration >= 1.0s.")
        if self.repetitions < 1:
            return throw_error_message(self, "Please select a number of repetitions >= 1.")

        #
        # Attempt to find all videos
        #
        exercises_found = self.check_video_paths()

        def missing_exer(self, ex_found, ex_label):
            if not ex_found:
                # Re-enable video buttons
                self.enable_video_buttons(True, False, False)

                # Display warning
                self.warning = QErrorMessage()
                self.warning.showMessage("Unable to find videos for Exercise {}.".format(ex_label))
                self.warning.show()
            return ex_found

        if ((not missing_exer(self, exercises_found[0], "A")) or (not missing_exer(self, exercises_found[1], "B")) or
                (not missing_exer(self, exercises_found[2], "C"))):
            return

        #
        # Start playing videos, and updating text fields, via background thread
        #
        self.worker = GroundTruthWorker(self.status_label, self.progress_label, self.desc_title, self.desc_explain,
                                        self.current_movement, self.video_player, self.all_video_paths,
                                        self.collect_duration, self.rest_duration, self.repetitions,
                                        self.on_worker_started, self.on_worker_unpaused, self.on_worker_paused,
                                        self.on_worker_stopped)
        QThreadPool.globalInstance().start(self.worker)


    def enable_video_buttons(self, state_play, state_pause, state_stop):
        """
            A helper function to set the current states of the play/pause/stop buttons.

        :param state_play: [bool] Enable/disable play button.
        :param state_pause: [bool] Enable/disable pause button.
        :param state_stop: [bool] Enable/disable stop button.
        :return:
        """
        self.play_button.setEnabled(state_play)
        self.pause_button.setEnabled(state_pause)
        self.stop_button.setEnabled(state_stop)

    def on_worker_started(self):
        """
            This function is called when the background worker has started.
        """
        self.playing = True
        self.enable_video_buttons(False, True, True)

    def on_worker_unpaused(self):
        """
             This function is called when the background worker has unpaused.
         """
        self.playing = True
        self.enable_video_buttons(False, True, True)
        self.unpausing = False

    def on_worker_paused(self):
        """
            This function is called when the background worker has paused.
        """
        self.playing = False
        self.pausing = False
        self.enable_video_buttons(True, False, True)

    def on_worker_stopped(self):
        """
            This function is called when the background worker has finished execution of run().
        """
        self.playing = False
        self.shutdown = False
        self.worker = None

        # Update GUI appearance
        self.status_label.setText("Waiting to Start...")
        self.status_label.setStyleSheet(" font-weight: bold; font-size: 18pt; "
                                        "   color: red;")
        self.progress_label.setText("0.0s (1 / 1)")
        self.desc_title.setText("No Movement")
        self.desc_explain.setText("No description available.")
        self.current_movement.setText("")

        self.enable_video_buttons(True, False, False)

    def pause_videos(self):
        """
            This function is called when the user presses "Pause".
                > The background worker pauses the playback of video, and updating of text fields.
                > The ground truth labels also become invalid.
        """
        if (not self.playing) or (self.pausing) or (self.shutdown):
            return
        self.enable_video_buttons(False, False, False)
        self.pausing = True

        # Pause the background worker
        self.worker.force_pause()

    def stop_videos(self):
        """
            This function is called when the user presses "Stop".
                > The background worker finishes executing the run() function as a result of being "stopped".
        """
        if ((not self.playing) and (self.worker is None)) or (self.shutdown):
            return
        self.enable_video_buttons(False, False, False)
        self.shutdown = True

        # Force the background worker to leave run()
        self.worker.force_stop()

    def check_video_paths(self):
        """
            Determines if an exercise has all videos necessary for playback, upon pressing "Start".

        :return: [bool, bool, bool]

                > Where each bool determines if exercise A/B/C has all videos available.
        """

        exercises_found = [True, True, True]
        self.all_video_paths = [("A", []), ("B", []), ("C", [])]

        def create_exercise_paths(self, ex_label):
            ex_index = ord(ex_label) - ord('A')
            found_videos = True
            path_template = join(self.video_dir, self.video_path_template[ex_index][0])
            max_idx = self.video_path_template[ex_index][1]
            ex_path_created = []

            for i in range(1, max_idx + 1):
                full_path = path_template.format(i)
                ex_path_created.append(full_path)

                if not exists(full_path):
                    found_videos = False
                    break

            self.all_video_paths[ex_index][1].extend(ex_path_created)
            return found_videos

        if self.ex_a_check.isChecked():
            exercises_found[0] = create_exercise_paths(self, "A")
        if self.ex_b_check.isChecked():
            exercises_found[1] = create_exercise_paths(self, "B")
        if self.ex_c_check.isChecked():
            exercises_found[2] = create_exercise_paths(self, "C")

        return exercises_found

    #
    # Used for data logging, by TopLevel
    #
    def get_current_label(self):
        """
        :return: [int] Ground truth label for current movement
        """
        if (self.worker is None) or (not self.playing):
            return -1
        else:
            if self.worker.current_label is None:
                return -1
            else:
                return self.worker.current_label

class GroundTruthWorker(QRunnable):
    """
        A background worker that controls playback of videos and text field updates, for the GT Helper.
    """

    def __init__(self, status_label, progress_label, desc_title, desc_explain, cur_movement, video_player,
                 all_video_paths, collect_duration, rest_duration, num_reps, on_worker_started, on_worker_unpaused,
                 on_worker_paused, on_worker_stopped):
        """
        :param status_label: A QLabel displaying a message of what the GT Helper is currently performing.
        :param progress_label:  A QLabel displaying the current progress of data collection.
        :param desc_title: A QLabel displaying the name of current movement.
        :param desc_explain: A QLabel describing how to perform the current movement.
        :param cur_movement: A QLabel displaying the current exercise and movement number.
        :param video_player: A QMediaPlayer, to show videos of gestures performed.
        :param all_video_paths: An object containing paths to all selected videos (based on exercises checked off).
        :param collect_duration: Duration of gesture data collection.
        :param rest_duration: Duration of rest data collection.
        :param num_reps: Number of repetitions to be performed per movement.
        :param on_worker_started: A callback function used once this background worker has started.
        :param on_worker_unpaused: A callback function used once this background worker has unpaused.
        :param on_worker_paused: A callback function used once this background worker has paused.
        :param on_worker_stopped: A callback function used once this background worker has stopped.
        """
        super().__init__()

        self.status_label = status_label
        self.progress_label = progress_label
        self.desc_title = desc_title
        self.desc_explain = desc_explain
        self.cur_movement = cur_movement
        self.video_player = video_player
        self.all_video_paths = all_video_paths
        self.collect_duration = collect_duration
        self.rest_duration = rest_duration
        self.num_reps = num_reps

        self.num_class_A = 12
        self.num_class_B = 17

        # Signals
        self.update = GTWorkerUpdate()
        self.update.workerStarted.connect(on_worker_started)
        self.update.workerUnpaused.connect(on_worker_unpaused)
        self.update.workerPaused.connect(on_worker_paused)
        self.update.workerStopped.connect(on_worker_stopped)

        # Used to update time remaining
        self.timer = QTimer()
        self.timer.timeout.connect(self.timer_update)
        self.timer_interval = 100  # units of ms
        self.state_end_event = self.StateComplete()
        self.state_end_event.stateEnded.connect(self.stop_state)

        # On video load or video completion, this is triggered
        self.video_player.mediaStatusChanged.connect(self.media_status_changed)

        # Configurable parameters
        self.preparation_period = 20.0

        # State variables
        self.current_rep = 0
        self.state_time_remain = 0  # seconds
        self.video_playing = False
        self.stopped = False
        self.paused = False
        self.current_label = None
        self.complete = False

    # On finish of repetition/rest/prepation
    class StateComplete(QObject):
        stateEnded = pyqtSignal()

    # Qt5, QMediaPlayer enum
    # > "Defines the status of a media player's current media."
    class MediaStatus(Enum):
        UnknownMediaStatus = 0
        NoMedia = 1
        LoadingMedia = 2
        LoadedMedia = 3
        StalledMedia = 4
        BufferingMedia = 5
        BufferedMedia = 6
        EndOfMedia = 7
        InvalidMedia = 8

    def run(self):

        # Re-enable video buttons
        self.complete = False
        self.update.workerStarted.emit()

        for exercise in self.all_video_paths:

            if self.stopped:
                break

            ex_label = exercise[0]
            video_paths = exercise[1]

            for movement_num, video_path in enumerate(video_paths):

                if self.stopped:
                    break
                #
                # Setup for current movement
                #
                self.current_rep = 0
                QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                            Q_ARG(str, "{} s ({}/{})".format(self.preparation_period, self.current_rep,
                                                                                self.num_reps)))
                QMetaObject.invokeMethod(self.cur_movement, "setText", Qt.QueuedConnection,
                                            Q_ARG(str, "Exercise {} - Movement {} of {}".format(ex_label, movement_num + 1,
                                                                                   len(video_paths))
                                                )
                                         )

                current_description = MOVEMENT_DESC[ex_label][movement_num + 1]
                QMetaObject.invokeMethod(self.desc_title, "setText", Qt.QueuedConnection,
                                            Q_ARG(str, current_description[0]))
                QMetaObject.invokeMethod(self.desc_explain, "setText",
                                         Qt.QueuedConnection, Q_ARG(str, current_description[1]))

                #
                # Preparation period
                #
                QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                         Q_ARG(str, "Preparing for repetition 1..." ))
                QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                         Q_ARG(str, "font-weight: bold; font-size: 18pt; color: blue;"))
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
                    QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                             Q_ARG(str, "Collecting for repetition {}...".format(self.current_rep)))
                    QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                             Q_ARG(str, "font-weight: bold; font-size: 18pt; color: green;"))
                    self.play_video(video_path, self.collect_duration)
                    self.set_current_label(ex_label, movement_num + 1)

                    while self.video_playing or (self.paused and not self.stopped):
                        time.sleep(self.timer_interval / 1000)

                    if self.stopped:
                        break

                    # Rest
                    if self.current_rep != self.num_reps:
                        QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                                    Q_ARG(str, "Resting before repetition {}...".format(self.current_rep + 1)))
                        QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                                 Q_ARG(str, "font-weight: bold; font-size: 18pt; color: orange;"))
                        self.play_video(video_path, self.rest_duration)
                        self.current_label = 0

                        while self.video_playing or (self.paused and not self.stopped):
                            time.sleep(self.timer_interval / 1000)
                    else:
                        self.current_label = None

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
        self.video_playing = True
        self.state_time_remain = period
        abs_path = QFileInfo(video_path).absoluteFilePath()
        QMetaObject.invokeMethod(self.video_player, "setMedia", Qt.QueuedConnection,
                                 Q_ARG(QMediaContent, QMediaContent(QUrl.fromLocalFile(abs_path))))

    def media_status_changed(self, state):
        """
            This function is called when the media player's media finishes loading/playing/etc.
        :param state: State corresponding to media player update
        """
        if state == self.MediaStatus.LoadedMedia.value:
            QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)
            self.timer.start(self.timer_interval)
        elif state == self.MediaStatus.EndOfMedia.value:
            if self.state_time_remain > self.timer_interval / 1000:
                QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)

    def timer_update(self):
        """
            This function is called every "self.timer_interval" seconds, upon timer completion.
        """
        self.state_time_remain = max(0, self.state_time_remain - self.timer_interval / 1000)

        QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                 Q_ARG(str, "{}s ({} / {})".format("{0:.1f}".format(self.state_time_remain),
                                                           self.current_rep, self.num_reps)))

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

        QMetaObject.invokeMethod(self.video_player, "stop", Qt.QueuedConnection)
        self.video_playing = False

    def force_stop(self):
        """
            GroundTruthHelper calls this function to stop this background worker thread.
        """
        self.timer.stop()
        QMetaObject.invokeMethod(self.video_player, "stop", Qt.QueuedConnection)
        self.video_playing = False
        self.stopped = True

    def force_pause(self):
        """
            GroundTruthHelper calls this function to pause this background worker thread.
        """
        self.timer.stop()
        QMetaObject.invokeMethod(self.video_player, "pause", Qt.QueuedConnection)
        self.paused = True

        # Re-enable video buttons
        self.update.workerPaused.emit()

    def force_unpause(self):
        """
            GroundTruthHelper calls this function to unpause this background worker thread.
        """
        self.timer.start(self.timer_interval)
        QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)
        self.paused = False

        # Re-enable video buttons
        self.update.workerUnpaused.emit()