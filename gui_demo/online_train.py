#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QProgressDialog, QTabWidget, QFileDialog, QMessageBox,
                             QWidget, QLabel, QHBoxLayout, QVBoxLayout, QCheckBox, QFrame, QMainWindow, QPushButton,
                             QGridLayout, QSizePolicy, QGroupBox, QTextEdit, QLineEdit, QErrorMessage, QProgressBar,
                             QSpacerItem, QStackedWidget)

from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import (QSize, QThreadPool, Qt, QRunnable, QMetaObject, Q_ARG, QObject, pyqtSignal, QTimer, QUrl,\
                            QFileInfo)
from PyQt5.QtMultimediaWidgets import QVideoWidget
import pyqtgraph as pg
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent


#
# Imports for online prediction tasks
#
from scipy.signal import butter, lfilter
from scipy.stats import multivariate_normal
import numpy as np
import ninaeval
from ninaeval.utils.gt_tools_v3 import optimize_start_end

try:
    import cPickle as pickle
except:
    import pickle

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
import copy

#
# Submodules in this repository
#
from pymyolinux import MyoDongle
from movements import *
from param import *

class OnlineTraining(QWidget):

    class MovementsSelection(QMainWindow):

        def __init__(self):
            super().__init__()
            self.init_ui()

        def init_ui(self):
            self.setGeometry(0, 0, 1024/2, 768/2)
            top_level_widget = QWidget(self)
            self.setCentralWidget(top_level_widget)

            self.setWindowTitle("Select Desired Movements")

    class MyoConnectedWidget(QWidget):

        def __init__(self, address, rssi, battery):
            super().__init__()
            self.address = address
            self.init_ui(address, rssi, battery)

        def init_ui(self, address, rssi, battery):

            infoLayout = QHBoxLayout()
            infoLayout.setSpacing(5)

            # Myo armband icon
            lbl = QLabel(self)
            orig = QPixmap(join(abspath(__file__).replace("online_test.py", ""), "icons/myo.png"))
            new = orig.scaled(QSize(30, 30), Qt.KeepAspectRatio)
            lbl.setPixmap(new)

            #
            # Format the Myo hardware (MAC) into a readable form
            #
            infoLayout.addWidget(lbl)
            formatted_address = ""
            length = len(address.hex())

            for i, ch in enumerate(address.hex()):
                formatted_address += ch
                if ((i - 1) % 2 == 0) and (i != length - 1):
                    formatted_address += "-"

            vline = QFrame()
            vline.setFrameShape(QFrame.VLine)
            vline.setFrameShadow(QFrame.Sunken)
            # vline2 = QFrame()
            # vline2.setFrameShape(QFrame.VLine)
            # vline2.setFrameShadow(QFrame.Sunken)

            #
            # Myo armband address, signal strength
            #
            addr_label = QLabel(formatted_address)
            addr_label.setContentsMargins(5, 0, 0, 0)
            cur_font = addr_label.font()
            cur_font.setPointSize(10)
            addr_label.setFont(cur_font)
            infoLayout.addWidget(addr_label)
            infoLayout.addWidget(vline)
            # rssi_label = QLabel(str(rssi) + " dBm")
            # infoLayout.addWidget(rssi_label)
            # infoLayout.addWidget(vline2)
            # infoLayout.setStretchFactor(rssi_label, 3)
            infoLayout.setStretchFactor(addr_label, 4)

            #
            # Battery Level
            #
            self.battery_level = QProgressBar()
            self.battery_level.setMinimum(0)
            self.battery_level.setMaximum(100)
            self.battery_level.setValue(battery)
            infoLayout.addWidget(self.battery_level)
            infoLayout.setStretchFactor(self.battery_level, 2)



            self.setLayout(infoLayout)

    def __init__(self, myo_data):
        super().__init__()
        self.myo_data = myo_data

        # Configurable
        self.min_noise_duration = 2 # seconds
        self.noise_increments   = 100

        # States
        self.collecting_noise   = False
        self.valid_model        = False
        self.noise_model_ready  = False
        self.classifier_model   = None
        self.noise_worker       = None
        self.pred_worker        = None

        #
        # To select movements
        #
        self.move_select = self.MovementsSelection()

        #
        # For video playing
        #
        self.timer = QTimer()
        self.timer.timeout.connect(self.timer_update)

        self.init_ui()


    def init_ui(self):

        self.top_layout = QVBoxLayout()
        self.top_layout.setContentsMargins(10, 10, 10, 10)
        self.top_layout.setSpacing(15)

        #
        # Top "message box" / time remaining
        #
        message_layout  = QHBoxLayout()
        self.status_label = QLabel("Waiting for Preparation...")
        self.status_label.setStyleSheet(" font-weight: bold; font-size: 16pt; color: red;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.progress_label = QLineEdit("N/A")
        self.progress_label.setReadOnly(True)
        self.progress_label.setStyleSheet("font-size: 14pt; color: black; background: #eeeeee; border: none;")
        self.progress_label.setAlignment(Qt.AlignCenter)

        message_layout.addWidget(self.status_label)
        message_layout.addWidget(QWidget())
        message_layout.addWidget(self.progress_label)
        message_layout.addWidget(QWidget())
        message_layout.setStretch(0, 66)
        message_layout.setStretch(1, 11)
        message_layout.setStretch(2, 11)
        message_layout.setStretch(3, 11)
        self.top_layout.addLayout(message_layout)

        #
        # Video player
        #
        video_layout        = QHBoxLayout()
        self.video_player   = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        video_widget        = QVideoWidget()
        video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_player.setVideoOutput(video_widget)

        video_layout.addWidget(video_widget)

        #
        # Description & Play Buttons
        #
        descrip_layout  = QVBoxLayout()
        self.desc_title = QLabel("No Movement")
        self.desc_title.setStyleSheet("border: 4px solid gray; font-weight: bold; font-size: 14pt;")
        self.desc_title.setAlignment(Qt.AlignCenter)
        self.desc_explain = QTextEdit("No description available.")
        self.desc_explain.setStyleSheet("border: 4px solid gray; font-size: 12pt; border-color: black;")
        self.desc_explain.setReadOnly(True)
        self.desc_explain.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        descrip_layout.addWidget(self.desc_title)
        descrip_layout.addWidget(self.desc_explain)

        video_layout.addLayout(descrip_layout)
        video_layout.setStretch(0, 66)
        video_layout.setStretch(1, 33)
        self.top_layout.addLayout(video_layout)

        #
        # Preparation Box
        #
        self.parameters_box = QGroupBox()
        self.parameters_box.setTitle("Preparation Phase")
        self.parameters_box.setObjectName("CollecParamBox")
        self.parameters_box.setStyleSheet(
            "QGroupBox#CollecParamBox { border: 1px solid gray; border-radius: 7px; margin-top: 1.6em;"
            "                              font-weight: bold; background-color: #dddddd;}"
            "QGroupBox#CollecParamBox::title { subcontrol-origin: margin; subcontrol-position: top center; "
            " border: 1px solid gray; border-radius: 7px;}")
        self.parameters_box.title()
        font = self.parameters_box.font()
        font.setPointSize(14)
        self.parameters_box.setFont(font)
        self.parameters_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.bottom_panel = QStackedWidget()
        self.bottom_panel.addWidget(self.parameters_box)

        prep_layout = QGridLayout()
        prep_layout.setHorizontalSpacing(15)
        self.parameters_box.setLayout(prep_layout)

        #
        # Controls Box (initially hidden)
        #
        self.controls_box = QGroupBox()
        self.controls_box.setObjectName("ControlBox")
        self.controls_box.setStyleSheet(
            "QGroupBox#ControlBox { border: 1px solid gray; border-radius: 7px; font-weight: bold;"
            "                            background-color: #dddddd; height: 60px;}")
        self.controls_box.setFixedHeight(60)
        self.controls_box.setAlignment(Qt.AlignBottom)
        self.controls_box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.bottom_panel.addWidget(self.controls_box)


        self.top_layout.addWidget(self.bottom_panel)
        self.bottom_panel.setCurrentIndex(0)
        self.bottom_panel.adjustSize()

        controls_layout = QGridLayout()
        self.controls_start = QPushButton("Start")
        self.controls_start.setStyleSheet("font-weight: bold")
        self.controls_pause = QPushButton("Pause")
        self.controls_pause.setStyleSheet("font-weight: bold")
        self.controls_stop  = QPushButton("Stop")
        self.controls_stop.setStyleSheet("font-weight: bold")
        controls_layout.addWidget(self.controls_start, 0, 1)
        controls_layout.addWidget(self.controls_pause, 0, 2)
        controls_layout.addWidget(self.controls_stop, 0, 3)
        controls_layout.setColumnStretch(0, 1)
        controls_layout.setColumnStretch(1, 1)
        controls_layout.setColumnStretch(2, 1)
        controls_layout.setColumnStretch(3, 1)
        controls_layout.setColumnStretch(4, 1)
        self.controls_box.setLayout(controls_layout)

        #
        # Preparation Box: Model Selection
        #
        self.model_button = QPushButton("Select Model")
        self.model_button.clicked.connect(self.on_model_select)
        self.model_button.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(self.model_button, 0, 0, 1, 2)

        hline = QFrame()
        hline.setFrameShape(QFrame.HLine)
        hline.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline, 1, 0, 1, 2)

        name_title = QLabel("Name")
        prep_layout.addWidget(name_title, 2, 0)
        samples_title = QLabel("Samples")
        prep_layout.addWidget(samples_title, 3, 0)

        self.model_name = QLineEdit()
        self.model_name.setReadOnly(True)
        prep_layout.addWidget(self.model_name, 2, 1)
        self.samples_field = QLineEdit()
        self.samples_field.setReadOnly(True)
        prep_layout.addWidget(self.samples_field, 3, 1)

        # Note: No copy constructors for Qt5 objects...
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)
        vline2 = QFrame()
        vline2.setFrameShape(QFrame.VLine)
        vline2.setFrameShadow(QFrame.Sunken)
        vline3 = QFrame()
        vline3.setFrameShape(QFrame.VLine)
        vline3.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(vline, 0, 2, 4, 1)


        #
        # Preparation Box: Devices Connected
        #
        connected_title  = QLabel("Devices Connected")
        connected_title.setAlignment(Qt.AlignCenter)
        connected_title.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(connected_title, 0, 3)
        self.devices_connected = QListWidget()
        self.devices_connected.verticalScrollBar().setDisabled(True)

        hline3 = QFrame()
        hline3.setFrameShape(QFrame.HLine)
        hline3.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline3, 1, 3)

        prep_layout.addWidget(self.devices_connected, 2, 3, 2, 1)
        prep_layout.addWidget(vline3, 0, 4, 4, 1)

        #
        # Preparation Box: Movements Selected
        #
        self.movements_button = QPushButton("Select Movements")
        self.movements_button.clicked.connect(self.on_movements_selected)
        self.movements_button.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(self.movements_button, 0, 5)
        self.movements_selected = QListWidget()

        hline3 = QFrame()
        hline3.setFrameShape(QFrame.HLine)
        hline3.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline3, 1, 5)

        prep_layout.addWidget(self.movements_selected, 2, 5, 2, 1)

        #
        # Preparation Phase formatting
        #
        prep_layout.setRowStretch(0, 3)
        prep_layout.setRowStretch(1, 1)
        prep_layout.setRowStretch(2, 4)
        prep_layout.setRowStretch(3, 4)

        prep_layout.setColumnStretch(0, 1)
        prep_layout.setColumnStretch(1, 3)
        prep_layout.setColumnStretch(2, 1)
        prep_layout.setColumnStretch(3, 6)
        prep_layout.setColumnStretch(4, 1)
        prep_layout.setColumnStretch(5, 6)

        #
        # Start button
        #
        self.start_button = QPushButton("Start Online Training")
        self.start_button.setStyleSheet("font-weight: bold;")
        self.start_button.clicked.connect(self.on_start_button)
        self.start_button.setEnabled(False)
        button_layout = QHBoxLayout()
        button_layout.addWidget(QWidget())
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(QWidget())
        button_layout.setStretch(0, 20)
        button_layout.setStretch(1, 45)
        button_layout.setStretch(2, 20)
        self.top_layout.addLayout(button_layout)

        #
        # Overall formatting
        #
        self.top_layout.setStretch(0, 1)
        self.top_layout.setStretch(1, 15)
        self.top_layout.setStretch(2, 1)
        self.top_layout.setStretch(3, 1)

        self.setLayout(self.top_layout)

    def on_movements_selected(self):
        self.move_select.show()

    def timer_update(self):
        """
            This function is called every "self.timer_interval" seconds, upon timer completion.
        """
        time_remaining                      =  max(0, self.pred_worker.state_time_remain  -
                                                        self.pred_worker.timer_interval / 1000)
        self.pred_worker.state_time_remain  = time_remaining

        self.progress_label.setText("{}s".format("{0:.1f}".format(time_remaining)))
        self.progress_label.setAlignment(Qt.AlignCenter)

        if self.pred_worker.state_time_remain == 0:
            self.timer.stop()
            self.pred_worker.stop_state()


    def device_connected(self, address, rssi, battery):

        new_device = self.MyoConnectedWidget(address, rssi, battery)
        temp_widget = QListWidgetItem()
        temp_widget.setBackground(Qt.gray)
        size_hint = new_device.sizeHint()
        size_hint.setHeight(36)
        temp_widget.setSizeHint(size_hint)
        self.devices_connected.addItem(temp_widget)
        self.devices_connected.setItemWidget(temp_widget, new_device)

        # Check if ready to start online testing
        self.check_ready_to_start()

    def device_disconnected(self, address):

        num_widgets = self.devices_connected.count()

        for idx in range(num_widgets):
            # Ignore port widgets (only interested in Myo device rows)
            list_widget = self.devices_connected.item(idx)
            myo_widget  = self.devices_connected.itemWidget(list_widget)

            if myo_widget.address.endswith(address):
                self.devices_connected.takeItem(idx)
                break

        # Check if ready to start online testing
        self.check_ready_to_start()

    def enable_train_buttons(self, select_model, movements_button):
        self.model_button.setEnabled(select_model)
        self.movements_button.setEnabled(movements_button)

    def on_model_select(self):

        self.enable_pred_buttons(False, False)
        dialog              = QFileDialog()
        self.model_file     = dialog.getOpenFileName(self, 'Choose Model')[0]

        if len(self.model_file) == 0:
            self.enable_pred_buttons(True, True)
            return

        # Clear states
        self.valid_model    = False
        self.samples_field.setText("")
        self.model_name.setText("")
        self.classifier_model = None

        try:
            with open(self.model_file, 'rb') as f:
                self.classifier_model = pickle.load(f)
        except:
            self.warn_user("Pickle was unable to decode the selected file.")
            self.enable_pred_buttons(True, True)
            return

        valid_model = hasattr(self.classifier_model, "perform_inference")
        if not valid_model:
            self.warn_user("Invalid model selected, no \"perform_inferfence\" member available.")
            self.enable_pred_buttons(True, True)
            return

        self.valid_model    = True
        model_name          = self.classifier_model.__class__.__name__
        feat_name           = self.classifier_model.feat_extractor.__class__.__name__
        self.model_name.setText(model_name + " - " + feat_name)

        if self.classifier_model.num_samples is None:
            self.samples_field.setText("N/A")
        else:
            self.samples_field.setText(str(self.classifier_model.num_samples))
        self.enable_pred_buttons(True, True)

        # Check if ready to start online testing
        self.check_ready_to_start()

    def check_ready_to_start(self):

        self.status_label.setText("Waiting for Preparation...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 16pt; color: red;")

        # Need two (connected) devices
        if self.devices_connected.count() < 2:
            self.start_button.setEnabled(False)
            return

        # Need noise model
        if not self.noise_model_ready:
            self.start_button.setEnabled(False)
            return

        # Need prediction model
        if not self.valid_model:
            self.start_button.setEnabled(False)
            return

        self.start_button.setEnabled(True)
        self.status_label.setText("Waiting to Start...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 16pt; color: green;")

    def enable_control_buttons(self, enable_start, enable_pause, enable_stop):
        self.controls_start.setEnabled(enable_start)
        self.controls_pause.setEnabled(enable_pause)
        self.controls_stop.setEnabled(enable_stop)

    def on_start_button(self):

        control_box_idx = 1
        self.bottom_panel.setCurrentIndex(control_box_idx)
        self.enable_control_buttons(False, False, False)

        # Hide start button
        self.start_button.hide()
        self.top_layout.setStretch(3, 0)

        self.status_label.setText("Waiting for Movement...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 16pt; color: orange;")

        # Adjust size of bottom panel
        self.parameters_box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.controls_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.controls_box.adjustSize()
        self.parameters_box.adjustSize()
        self.bottom_panel.adjustSize()

        # Start background worker, reponsible for gesture detection
        self.pred_worker = GesturePredictionWorker(self.myo_data, self.noise_worker.smooth_avg,
                                                    self.noise_worker.smooth_std, self.classifier_model,
                                                    self.status_label, self.progress_label, self.desc_title,
                                                    self.desc_explain, self.video_player, self.enable_control_buttons,
                                                    self.controls_start, self.controls_pause, self.controls_stop,
                                                    self.timer, self.close_prediction_worker
                                                   )
        QThreadPool.globalInstance().start(self.pred_worker)

    def close_prediction_worker(self):
        control_box_idx = 0
        self.bottom_panel.setCurrentIndex(control_box_idx)

        # Hide start button
        self.start_button.show()
        self.top_layout.setStretch(3, 1)

        # Adjust size of bottom panel
        self.parameters_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.controls_box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.controls_box.adjustSize()
        self.parameters_box.adjustSize()
        self.bottom_panel.adjustSize()

    def warn_user(self, message):
        """
            Generates a pop-up warning message

        :param message: The text to display
        """
        self.warning = QErrorMessage()
        self.warning.showMessage(message)
        self.warning.show()


class GesturePredictionWorker(QRunnable):

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

        class GPWSignal(QObject):
            onShutdown = pyqtSignal()

        def __init__(self, myo_data, smooth_avg, smooth_std, pred_model, status_label, progress_label, desc_title,
                        desc_explain, video_player, enable_control_buttons, controls_start, controls_pause,
                        controls_stop, timer, close_prediction):
            super().__init__()

            self.myo_data               = myo_data
            self.smooth_avg             = smooth_avg
            self.smooth_std             = smooth_std
            self.pred_model             = pred_model
            self.status_label           = status_label
            self.progress_label         = progress_label
            self.desc_title             = desc_title
            self.desc_explain           = desc_explain
            self.video_player           = video_player

            self.enable_control_buttons = enable_control_buttons
            self.controls_start         = controls_start
            self.controls_start.clicked.connect(self.start_online_pred)
            self.controls_pause         = controls_pause
            self.controls_pause.clicked.connect(self.pause_online_pred)
            self.controls_stop          = controls_stop
            self.controls_stop.clicked.connect(self.stop_online_pred)
            self.timer                  = timer

            self.close_event            = self.GPWSignal()
            self.close_event.onShutdown.connect(close_prediction)

            # Each video path has the following format:
            #   -> (1, 2, 3):
            #       1: Path relative to video_dir
            #       2: Minimum video number in specified path
            #       3. Maximum video number in specified path
            #
            self.video_dir              = "gesture_videos"
            self.video_path_template    = [
                                            ("arrows/exercise_a/a{}.mp4", 12),
                                            ("arrows/exercise_b/b{}.mp4", 17),
                                            ("arrows/exercise_c/c{}.mp4", 23)
                                        ]

            # Configurable parameters (threshold algorithm)
            self.window_size        = 50
            self.h                  = 3     # Number of standard deviations to threshold with
            self.min_rest_samples   = 80   # Must meet threshold this many times
            self.min_sig_samples    = 200   # Must meet threshold this many times
            self.max_err            = 15    # Up to this many samples can fail to meet this threshold

            # Other configurable parameters
            self.max_samples    = 600   # 3 seconds
            self.trim_samples   = 200
            self.detect_window  = 400 / 1000
            self.check_period   = 50 / 1000
            self.setup_time     = 2000 / 1000
            self.wait_period    = 1000 / 1000  # Wait for movement signal to die out
            self.min_duration   = 2000 / 1000
            self.max_duration   = 5000 / 1000
            self.emg_rate       = 200
            self.rest_label     = 0
            self.use_imu        = False

            # States
            self.cur_count      = 0
            self.err_count      = 0
            self.running        = False
            self.emg_list       = []
            self.acc_list       = []
            self.gyro_list      = []
            self.mag_list       = []
            self.last_end_idx   = None
            self.playing        = False
            self.started        = False


            #
            # Video playing specific
            #
            ############################################################################################################
            ############################################################################################################
            self.num_exercise_A = 12
            self.num_exercise_B = 17

            # Configurable parameters
            self.display_period = 10.0  # Used to update time remaining
            self.timer_interval = 100   # units of ms
            self.post_display_exit = 100/1000 # units of secods

            # State variables
            self.state_time_remain  = 0  # seconds
            self.video_playing      = False
            self.stopped            = False
            self.current_label      = None
            self.complete           = False
            self.paused             = False
            self.pausing            = False
            self.unpausing          = False
            self.shutdown           = False

            self.video_player.mediaStatusChanged.connect(self.media_status_changed)
            ############################################################################################################
            ############################################################################################################

        def check_video_paths(self):
            """
                Determines if an exercise has all videos necessary for playback, upon pressing "Start".

            :return: [bool, bool, bool]

                    > Where each bool determines if exercise A/B/C has all videos available.
            """

            exercises_found         = [True, True, True]
            self.all_video_paths    = [("A", []), ("B", []), ("C", [])]

            def create_exercise_paths(self, ex_label):
                ex_index = ord(ex_label) - ord('A')
                found_videos = True
                path_template   = join(self.video_dir, self.video_path_template[ex_index][0])
                max_idx         = self.video_path_template[ex_index][1]
                ex_path_created = []

                for i in range(1, max_idx + 1):
                    full_path = path_template.format(i)
                    ex_path_created.append(full_path)

                    if not exists(full_path):
                        found_videos = False
                        break

                self.all_video_paths[ex_index][1].extend(ex_path_created)
                return found_videos

            exercises_found[0] = create_exercise_paths(self, "A")
            exercises_found[1] = create_exercise_paths(self, "B")
            exercises_found[2] = create_exercise_paths(self, "C")

            return exercises_found

        def detect_movement(self, detect_start):

            #
            # Extract data in time window
            #
            first_myo_data  = self.myo_data.band_1
            second_myo_data = self.myo_data.band_2
            data_mapping    = self.myo_data.data_mapping

            # Find start/end indices of first dataset
            first_end_idx   = len(first_myo_data.timestamps) - 1

            # Skip seen samples
            if self.last_end_idx is not None:
                new_emg_count   = first_end_idx - self.last_end_idx
                first_start_idx = self.last_end_idx + 1

            # Get all samples within "detection window"
            else:
                start_time      = time.time()
                idx             = first_end_idx
                first_start_idx = None

                while first_start_idx is None:
                    data_time = first_myo_data.timestamps[idx]

                    if (start_time - data_time > self.detect_window + 2 * COPY_THRESHOLD):
                        first_start_idx = idx
                    else:
                        idx -= 1

                #self.very_first = first_start_idx
                new_emg_count   = first_end_idx - first_start_idx + 1

            # Add new emg\imu samples:
            for first_idx in range(first_start_idx, first_end_idx + 1):
                sec_idx = data_mapping[first_idx]

                if (sec_idx != self.myo_data.invalid_map) and (sec_idx < len(second_myo_data.timestamps)):
                    # EMG
                    first_emg   = [x[first_idx] for x in first_myo_data.emg]
                    second_emg  = [x[sec_idx] for x in second_myo_data.emg]
                    self.emg_list.append(first_emg + second_emg)

                    if self.use_imu:
                        # ACC
                        first_acc   = [x[first_idx] for x in first_myo_data.accel]
                        second_acc  = [x[sec_idx] for x in second_myo_data.accel]
                        self.acc_list.append(first_acc + second_acc)

                        # GYRO
                        first_gyro   = [x[first_idx] for x in first_myo_data.gyro]
                        second_gyro  = [x[sec_idx] for x in second_myo_data.gyro]
                        self.gyro_list.append(first_gyro + second_gyro)

                        # MAG
                        first_mag   = [x[first_idx] for x in first_myo_data.orient]
                        second_mag  = [x[sec_idx] for x in second_myo_data.orient]
                        self.mag_list.append(first_mag + second_mag)

            emg_samples = np.array(self.emg_list)

            # Apply sixth-order digital butterworth lowpass filter with 50 Hz cutoff frequency to rectified signal (first)
            fs          = 200
            nyquist     = 0.5 * fs
            cutoff      = 50
            order       = 6
            b, a        = butter(order, cutoff / nyquist, btype='lowpass')
            emg_samples = np.abs(emg_samples)
            filt_data   = lfilter(b, a, emg_samples, axis=0)

            ##########################################################################################################################################################################
            ##########################################################################################################################################################################
            ##########################################################################################################################################################################
            ##########################################################################################################################################################################

            #
            # Use test function to determine onset of signal (for current channel)
            #
            max_idx         = emg_samples.shape[0] - 1
            emg_start_idx   = None
            max_count       = 0

            if self.last_end_idx is None:
                cur_idx = self.window_size
            else:
                cur_idx = max_idx - new_emg_count + 1

            if detect_start:
                min_samples = self.min_sig_samples
            else:
                min_samples = self.min_rest_samples

            while (emg_start_idx is None) and (cur_idx <= max_idx):

                # Test for non-noise data
                cur_test_func = (np.mean(filt_data[cur_idx - self.window_size: cur_idx],
                                         axis=0) - self.smooth_avg) / self.smooth_std

                success = np.any(np.greater(cur_test_func, self.h))
                if not detect_start:
                    success = not success

                # Keeps track of number of successes and failures
                if success:
                    self.cur_count += 1
                else:
                    self.err_count += 1

                if self.err_count >= self.max_err:
                    self.err_count = 0
                    self.cur_count = 0

                if (self.cur_count + self.err_count) > max_count:
                    max_count = (self.cur_count + self.err_count)

                if max_count >= min_samples:
                    emg_start_idx = cur_idx - min_samples + 1
                else:
                    cur_idx += 1

            #print((self.cur_count, new_emg_count))
            self.last_end_idx = first_end_idx

            if emg_start_idx is not None:
                self.cur_count = 0
                self.err_count = 0
                return emg_start_idx

            return None

        def run(self):

            #
            # Check if all videos exist
            #
            exercises_found = self.check_video_paths()

            def missing_exer(self, ex_found, ex_label):
                if not ex_found:
                    # Re-enable video buttons
                    self.enable_control_buttons(True, False, True)

                    # Display warning
                    self.warning = QErrorMessage()
                    self.warning.showMessage("Unable to find videos for Exercise {}.".format(ex_label))
                    self.warning.show()
                return ex_found

            if ((not missing_exer(self, exercises_found[0], "A")) or (not missing_exer(self, exercises_found[1], "B"))
                    or (not missing_exer(self, exercises_found[2], "C"))):
                return

            self.running = True
            time.sleep(self.setup_time)
            self.enable_control_buttons(False, False, False)

            while self.running:

                start_idx = self.detect_movement(True)
                if start_idx is None:
                    #
                    # Trim EMG data
                    #
                    # if len(self.emg_list) > self.max_samples:
                    #    self.emg_list = self.emg_list[self.trim_samples:]

                    time.sleep(self.check_period)
                else:
                    print("START")
                    #time.sleep(self.wait_period)

                    end_idx = None
                    while (end_idx is None) and (self.running):

                        end_idx = self.detect_movement(False)
                        if end_idx is None:
                            time.sleep(self.check_period)
                        else:
                            print("END")

                    if not self.running:
                        break

                    #
                    # Refine signal onset (using likelihood test)
                    #

                    emg_samples = np.array(self.emg_list)
                    with open("temparray2", "wb") as f:
                        np.save(f, emg_samples)

                    #
                    # Trim excess data on the end
                    #
                    num_samples = end_idx - start_idx

                    if num_samples > 550:
                        print("Num samples:")
                        print((num_samples, len(self.emg_list)))

                        #
                        # Refine start/end
                        #
                        best_start, best_end = optimize_start_end(self.emg_list, start_idx, end_idx)

                        if ((best_start is not None) and (best_end is not None)) and (best_end - best_start > 400):
                            with open("temparray", "wb") as f:
                                np.save(f, np.array(self.emg_list[best_start: best_end]))

                            print("BEST")
                            print(best_start, best_end)

                            if (best_start is not None) and (best_end is not None):
                                emg_samp   = np.array(self.emg_list[best_start: best_end])

                                if self.use_imu:
                                    acc_samp   = np.array(self.acc_list[best_start: best_end])
                                    gyro_samp  = np.array(self.gyro_list[best_start: best_end])
                                    mag_samp   = np.array(self.mag_list[best_start: best_end])
                                    combined_samples = [emg_samp, acc_samp, gyro_samp, mag_samp]

                                if not self.running:
                                    break

                                #
                                # Make a prediction
                                #
                                if self.use_imu:
                                    test_feat   = self.pred_model.feat_extractor.extract_feature_point(combined_samples).reshape(1, -1)
                                else:
                                    test_feat   = self.pred_model.feat_extractor.extract_feature_point(emg_samp).reshape(1, -1)
                                pred        = self.pred_model.perform_inference(test_feat, None)[0]
                                print("The pred:")
                                print(pred)
                                prob = self.pred_model.get_class_probabilities(test_feat)
                                print(prob[0][np.argmax(prob)])
                                print(np.sort(prob[0])[48:])

                                if pred != self.rest_label:

                                    if not self.running:
                                        break

                                    #
                                    # Start playing videos, and updating text fields, via background thread
                                    #
                                    self.set_label(pred)
                                    self.display_prediction()
                                    time.sleep(self.post_display_exit)
                                    print("Done")
                                #with open("temparray", "wb") as f:
                                #    np.save(f, emg_samples)
                                #return

                    #
                    #
                    # #
                    # # Clear states
                    # #
                    self.emg_list.clear()
                    self.acc_list.clear()
                    self.gyro_list.clear()
                    self.mag_list.clear()
                    self.last_end_idx = None



        ################################################################################################################
        ################################################################################################################
        ################################################################################################################
        #
        # Video playing functions
        #
        ################################################################################################################
        ################################################################################################################
        ################################################################################################################


        def start_online_pred(self):
            # Disable play/pause/stop buttons until it is safe
            self.enable_control_buttons(False, False, False)

            # If any button click is still being processed
            if (self.unpausing) or (self.pausing) or (self.shutdown):
                return

            if self.playing:
                self.enable_control_buttons(False, True, True)
                return

            if self.paused:
                self.force_unpause()
                return

            self.run()

        def pause_online_pred(self):
            """
                This function is called when the user presses "Pause".
                    > The background worker pauses the playback of video, and updating of text fields.
                    > The ground truth labels also become invalid.
            """
            if (not self.playing) or (self.pausing) or (self.shutdown):
                return
            self.enable_control_buttons(False, False, False)
            self.pausing = True

            # Pause the background worker
            self.force_pause()

        def stop_online_pred(self):
            """
                This function is called when the user presses "Stop".
                    > The background worker finishes executing the run() function as a result of being "stopped".
            """
            if (not self.playing) or (self.shutdown):
                return
            self.enable_control_buttons(False, False, False)
            self.shutdown = True

            # Force the background worker to leave run()
            self.force_stop()

        def on_worker_started(self):
            """
                This function is called when the background worker has started.
            """
            self.started = True
            self.playing = True
            self.enable_control_buttons(False, True, True)

        def on_worker_unpaused(self):
            """
                 This function is called when the background worker has unpaused.
             """
            self.playing = True
            self.enable_control_buttons(False, True, True)
            self.unpausing = False

        def on_worker_paused(self):
            """
                This function is called when the background worker has paused.
            """
            self.playing = False
            self.pausing = False
            self.enable_control_buttons(True, False, True)

        def on_worker_stopped(self):
            """
                This function is called when the background worker has finished execution of run().
            """
            self.playing    = False

            # Stop video player
            QMetaObject.invokeMethod(self.video_player, "stop", Qt.QueuedConnection)

            # Update GUI appearance
            QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, "0.0s"))
            QMetaObject.invokeMethod(self.desc_title, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, "No Movement"))
            QMetaObject.invokeMethod(self.desc_explain, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, "No description available."))


            if not self.shutdown:
                QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                         Q_ARG(str, "Waiting for Movement..."))
                QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                         Q_ARG(str, "font-weight: bold; font-size: 16pt; color: orange;"))

                self.enable_control_buttons(False, True, True)
            else:
                self.running = False
                self.enable_control_buttons(False, False, False)

                QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                         Q_ARG(str, "Waiting to Start..."))
                QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                         Q_ARG(str, " font-weight: bold; font-size: 18pt; "
                                                    "   color: green;"))

                self.close_event.onShutdown.emit()

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
            if self.video_playing:
                if state == self.MediaStatus.LoadedMedia.value:
                    QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)
                    QMetaObject.invokeMethod(self.timer, "start", Qt.QueuedConnection, Q_ARG(int, self.timer_interval))
                elif state == self.MediaStatus.EndOfMedia.value:
                    if self.state_time_remain > self.timer_interval / 1000:
                        QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)

        def stop_state(self):
            """
                Upon completion of a repetition/rest/prepation state, this function is called.
            """
            self.video_playing = False
            QMetaObject.invokeMethod(self.video_player, "stop", Qt.QueuedConnection)


        def force_stop(self):
            """
                GroundTruthHelper calls this function to stop this background worker thread.
            """
            QMetaObject.invokeMethod(self.timer, "stop", Qt.QueuedConnection)
            QMetaObject.invokeMethod(self.video_player, "stop", Qt.QueuedConnection)
            self.video_playing  = False
            self.stopped        = True


        def force_pause(self):
            """
                GroundTruthHelper calls this function to pause this background worker thread.
            """
            QMetaObject.invokeMethod(self.timer, "stop", Qt.QueuedConnection)
            QMetaObject.invokeMethod(self.video_player, "pause", Qt.QueuedConnection)
            self.paused = True

            # Re-enable video buttons
            self.on_worker_paused()


        def force_unpause(self):
            """
                GroundTruthHelper calls this function to unpause this background worker thread.
            """
            QMetaObject.invokeMethod(self.timer, "start", Qt.QueuedConnection, Q_ARG(int, self.timer_interval))
            QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)
            self.paused = False

            # Re-enable video buttons
            self.on_worker_unpaused()

        def set_label(self, cur_label):
            #
            # Obtain movement number & exercise
            #
            if cur_label > self.num_exercise_A:

                if cur_label > self.num_exercise_A + self.num_exercise_B:
                    self.cur_ex = "C"
                    self.movement_num = cur_label - self.num_exercise_B - self.num_exercise_A

                else:
                    self.cur_ex = "B"
                    self.movement_num = cur_label - self.num_exercise_A
            else:
                self.movement_num = cur_label
                self.cur_ex = "A"


        def display_prediction(self):
            # Re-enable video buttons
            self.complete = False
            self.on_worker_started()

            #
            # Setup for current movement
            #
            QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, "{} s".format(self.display_period)))

            current_description = MOVEMENT_DESC[self.cur_ex][self.movement_num]
            QMetaObject.invokeMethod(self.desc_title, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, current_description[0]))
            QMetaObject.invokeMethod(self.desc_explain, "setText",
                                     Qt.QueuedConnection, Q_ARG(str, current_description[1]))

            #
            # Preparation period
            #
            QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, "Prediction made."))
            QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                     Q_ARG(str, "font-weight: bold; font-size: 18pt; color: blue;"))

            for ex_vids in self.all_video_paths:
                if ex_vids[0] == self.cur_ex:
                    video_path = ex_vids[1][self.movement_num - 1]
                    break

            self.play_video(video_path, self.display_period)

            while self.video_playing or (self.paused and not self.stopped):
                time.sleep(self.timer_interval / 1000)

            #
            # If user pressed stop
            #
            self.complete = True
            self.on_worker_stopped()

        ################################################################################################################
        ################################################################################################################
        ################################################################################################################

