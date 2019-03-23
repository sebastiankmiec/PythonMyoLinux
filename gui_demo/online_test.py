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

class OnlineTesting(QWidget):

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
        self.status_label.setStyleSheet(" font-weight: bold; font-size: 16pt; "
                                        "   color: red;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.progress_label = QLabel("N/A")
        self.progress_label.setStyleSheet(" font-size: 14pt; color: black;")
        self.progress_label.setAlignment(Qt.AlignCenter)
        message_layout.addWidget(self.status_label)
        message_layout.addWidget(self.progress_label)
        message_layout.setStretch(0, 66)
        message_layout.setStretch(1, 33)
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
        # Preparation Box: Generate Noise Model
        #
        self.noise_button = QPushButton("Collect Noise")
        self.noise_button.setStyleSheet("font-weight: bold")
        self.noise_button.clicked.connect(self.on_noise_collect)
        prep_layout.addWidget(self.noise_button, 0, 3)
        collect_title = QLabel("Duration")
        collect_title.setAlignment(Qt.AlignCenter | Qt.AlignBottom)

        hline2 = QFrame()
        hline2.setFrameShape(QFrame.HLine)
        hline2.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline2, 1, 3)
        prep_layout.addWidget(collect_title, 2, 3)

        self.noise_duration = QLineEdit("3.0")
        self.noise_duration.setAlignment(Qt.AlignCenter)
        prep_layout.addWidget(self.noise_duration, 3, 3)
        prep_layout.addWidget(vline2, 0, 4, 4, 1)

        #
        # Preparation Box: Devices Connected
        #
        connected_title  = QLabel("Devices Connected")
        connected_title.setAlignment(Qt.AlignCenter)
        connected_title.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(connected_title, 0, 5)
        self.devices_connected = QListWidget()
        self.devices_connected.verticalScrollBar().setDisabled(True)

        hline3 = QFrame()
        hline3.setFrameShape(QFrame.HLine)
        hline3.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline3, 1, 5)

        prep_layout.addWidget(self.devices_connected, 2, 5, 2, 1)
        prep_layout.addWidget(vline3, 0, 6, 4, 1)

        #
        # Online Testing Parameters
        #
        test_title      = QLabel("Test Parameters")
        test_title.setAlignment(Qt.AlignCenter)
        test_title.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(test_title, 0, 7, 1, 2)

        hline4 = QFrame()
        hline4.setFrameShape(QFrame.HLine)
        hline4.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline4, 1, 7, 1, 2)

        self.pred_min_duration  = QLineEdit("2.0")
        self.pred_max_duration  = QLineEdit("4.0")
        self.min_title          = QLabel("<b>(Min)</b> Duration")
        self.max_title          = QLabel("<b>(Max)</b> Duration")

        prep_layout.addWidget(self.min_title, 2, 7)
        prep_layout.addWidget(self.max_title, 3, 7)
        prep_layout.addWidget(self.pred_min_duration, 2, 8)
        prep_layout.addWidget(self.pred_max_duration, 3, 8)

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
        prep_layout.setColumnStretch(3, 2)
        prep_layout.setColumnStretch(4, 1)
        prep_layout.setColumnStretch(5, 6)
        prep_layout.setColumnStretch(6, 1)
        prep_layout.setColumnStretch(7, 1)
        prep_layout.setColumnStretch(8, 3)

        #
        # Start button
        #
        self.start_button = QPushButton("Start Online Testing")
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

    def enable_pred_buttons(self, select_model, noise_button):
        self.model_button.setEnabled(select_model)
        self.noise_button.setEnabled(noise_button)

    def on_noise_collect(self):

        if self.collecting_noise:
            return self.warn_user("Currently collecting noise data and\or creating a noise model.")

        self.enable_pred_buttons(False, False)
        self.noise_model_ready  = False

        def acquire_var(self, text, widget_name, func):
            try:
                temp = func(text)
            except:
                self.enable_pred_buttons(True, True)

                # Display warning
                if func == float:
                    return self.warn_user("Please set a valid float for \"{}\".".format(widget_name))
                else:
                    return self.warn_user("Please set a valid integer for \"{}\".".format(widget_name))
            return temp

        noise_duration = acquire_var(self, self.noise_duration.text(), "Noise Duration", float)
        if noise_duration is None:
            self.enable_pred_buttons(True, True)
            return

        if self.devices_connected.count() < 2:
            self.enable_pred_buttons(True, True)
            return self.warn_user("Please connect two Myo armband devices.")

        if noise_duration < self.min_noise_duration:
            return self.warn_user("Please select a noise duration of at least \"{}\" seconds.".format(
                                    self.min_noise_duration))
        else:
            self.collecting_noise   = True

            self.status_label.setText("Collecting Noise Data...")
            self.status_label.setStyleSheet("font-weight: bold; font-size: 16pt; color: orange;")

            self.progress_bar = QProgressDialog("Collecting Noise Data...", "Cancel", 0, self.noise_increments)
            self.progress_bar.setWindowTitle("In Progress")
            self.progress_bar.show()
            self.progress_bar.setValue(0)
            self.progress_bar.setCancelButton(None)

            self.noise_worker = NoiseCollectionWorker(self.myo_data, noise_duration, self.noise_increments,
                                                            self.progress_bar, self.progress_label,
                                                            self.on_worker_started, self.on_collect_complete,
                                                            self.on_model_ready)
            QThreadPool.globalInstance().start(self.noise_worker)

    def on_worker_started(self):
        pass

    def on_collect_complete(self):
        self.status_label.setText("Processing Noise Data...")
        self.progress_label.setText("N/A")
        self.progress_bar.close()

    def on_model_ready(self):
        self.status_label.setText("Waiting for Preparation...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 16pt; color: red;")
        self.enable_pred_buttons(True, True)
        self.collecting_noise = False
        self.noise_model_ready = True

        # Check if ready to start online testing
        self.check_ready_to_start()

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
                                                    self.noise_worker.smooth_std, self.classifier_model)
        QThreadPool.globalInstance().start(self.pred_worker)

    def warn_user(self, message):
        """
            Generates a pop-up warning message

        :param message: The text to display
        """
        self.warning = QErrorMessage()
        self.warning.showMessage(message)
        self.warning.show()


########################################################################################################################
########################################################################################################################
########################################################################################################################
#
# Custom PyQt5 events (used by QRunnables)
#
########################################################################################################################
########################################################################################################################
########################################################################################################################

# Used by NoiseCollectionWorker
class NoiseUpdates(QObject):
    workerStarted   = pyqtSignal()
    collectComplete = pyqtSignal()
    modelReady      = pyqtSignal()

########################################################################################################################
########################################################################################################################
########################################################################################################################

class NoiseCollectionWorker(QRunnable):

    def __init__(self, myo_data, noise_duration, noise_increments, progress_bar, progress_label, on_worker_started,
                        on_collect_complete, on_model_ready):
        super().__init__()

        self.myo_data           = myo_data
        self.noise_duration     = noise_duration
        self.noise_increments   = noise_increments
        self.progress_bar       = progress_bar
        self.progress_label     = progress_label

        # Configurable
        self.buffer_time    = 1     # Add a buffer to account for startup of this background thread

        # States
        self.start_time         = time.time() + self.buffer_time
        self.currrent_increment = 0

        self.worker_updates = NoiseUpdates()
        self.worker_updates.workerStarted.connect(on_worker_started)
        self.worker_updates.collectComplete.connect(on_collect_complete)
        self.worker_updates.modelReady.connect(on_model_ready)

        # To be filled via run()
        self.smooth_avg = None
        self.smooth_std = None
        self.noise_mean = None
        self.noise_cov  = None

    def run(self):

        time.sleep(self.buffer_time)
        while (time.time() - self.start_time) < self.noise_duration:
            QMetaObject.invokeMethod(self.progress_bar, "setValue", Qt.QueuedConnection,
                                     Q_ARG(int, self.currrent_increment))


            time_remaining = "{0:.1f}".format(self.noise_duration - (time.time() - self.start_time)) + " s"
            QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, time_remaining))

            time.sleep(self.noise_duration / self.noise_increments)
            self.currrent_increment += 1

        end_time = time.time()
        self.worker_updates.collectComplete.emit()

        #
        # Extract data in time window
        #
        first_myo_data  = copy.deepcopy(self.myo_data.band_1)
        second_myo_data = copy.deepcopy(self.myo_data.band_2)
        data_mapping    = copy.deepcopy(self.myo_data.data_mapping)

        # Find start/end indices of first dataset
        first_data_indices  = [None, None]
        default_final       = len(first_myo_data.timestamps)

        for i, data_time in enumerate(first_myo_data.timestamps):
            if first_data_indices[0] is None:
                if data_time > self.start_time:
                    first_data_indices[0] = i
            if first_data_indices[1] is None:
                if data_time > end_time:
                    first_data_indices[1] = i
                    break

        if first_data_indices[1] is None:
            first_data_indices[1] = default_final

        noise_samples = []
        for first_idx in range(first_data_indices[0], first_data_indices[1]):
            if data_mapping[first_idx] != self.myo_data.invalid_map:
                first_emg   = [x[first_idx] for x in first_myo_data.emg]
                sec_idx     = data_mapping[first_idx]
                second_emg  = [x[sec_idx] for x in second_myo_data.emg]
                noise_samples.append(first_emg + second_emg)

        #
        # Fit a noise model
        #
        noise_samples       = np.array(noise_samples)
        self.noise_mean     = np.mean(noise_samples, axis=0)
        self.noise_cov      = np.cov(noise_samples, rowvar=False)
        print(noise_samples.shape)

        # Apply sixth-order digital butterworth lowpass filter with 50 Hz cutoff frequency to rectified signal (first)
        fs              = 200
        nyquist         = 0.5 * fs
        cutoff          = 50
        order           = 6
        b, a            = butter(order, cutoff / nyquist, btype='lowpass')
        noise_samples   = np.abs(noise_samples)
        filt_data       = lfilter(b, a, noise_samples, axis=0)

        self.smooth_avg  = np.mean(filt_data, axis=0)
        self.smooth_std  = np.std(filt_data, axis=0)

        self.worker_updates.modelReady.emit()


class GesturePredictionWorker(QRunnable):

        def __init__(self, myo_data, smooth_avg, smooth_std, pred_model):
            super().__init__()

            self.myo_data       = myo_data
            self.smooth_avg     = smooth_avg
            self.smooth_std     = smooth_std
            self.pred_model     = pred_model

            # Configurable
            self.detect_window  = 700/1000
            self.check_period   = 1000/1000
            self.setup_time     = 2000/1000

            # States
            self.running = False

        def run(self):

            self.running = True
            time.sleep(self.setup_time)

            while self.running:

                movement_detected = False
                while (not movement_detected):

                    #
                    # Extract data in time window
                    #
                    start_time      = time.time()
                    first_myo_data  = self.myo_data.band_1
                    second_myo_data = self.myo_data.band_2
                    data_mapping    = self.myo_data.data_mapping

                    # Find start/end indices of first dataset
                    first_start_idx     = None
                    first_end_idx       = len(first_myo_data.timestamps)

                    idx = first_end_idx - 1
                    while first_start_idx is None:
                        data_time = first_myo_data.timestamps[idx]
                        if start_time - data_time > self.detect_window + 2 * COPY_THRESHOLD:
                            first_start_idx = idx
                        else:
                            idx -= 1

                    emg_samples = []
                    for first_idx in range(first_start_idx, len(first_myo_data.timestamps)-1):
                        if data_mapping[first_idx] != self.myo_data.invalid_map:
                            first_emg   = [x[first_idx] for x in first_myo_data.emg]
                            sec_idx     = data_mapping[first_idx]
                            second_emg  = [x[sec_idx] for x in second_myo_data.emg]
                            emg_samples.append(first_emg + second_emg)
                    emg_samples = np.array(emg_samples)

                    # Apply sixth-order digital butterworth lowpass filter with 50 Hz cutoff frequency to rectified signal (first)
                    fs              = 200
                    nyquist         = 0.5 * fs
                    cutoff          = 50
                    order           = 6
                    b, a            = butter(order, cutoff / nyquist, btype='lowpass')
                    emg_samples     = np.abs(emg_samples)
                    filt_data       = lfilter(b, a, emg_samples, axis=0)

                    # Configurable parameters
                    window_size     = 50
                    baseline_samp   = 200
                    h               = 3  # Number of standard deviations to threshold with
                    min_samples     = 90  # Must meet threshold this many times
                    max_err         = 15  # Up to this many samples can fail to meet this threshold

                    # States
                    emg_start_idx   = None
                    cur_idx         = window_size
                    max_idx         = emg_samples.shape[0]
                    cur_count       = 0
                    err_count       = 0

                    #
                    # Use test function to determine onset of signal (for current channel)
                    #
                    max = 0

                    while (emg_start_idx is None) and (cur_idx <= max_idx):

                        # Test for non-noise data
                        cur_test_func = (np.mean(filt_data[cur_idx - window_size:cur_idx], axis=0) - self.smooth_avg) / self.smooth_std
                        success = np.any(np.greater(cur_test_func, h))

                        # Keeps track of number of successes and failures
                        if success:
                            cur_count += 1
                        else:
                            err_count += 1

                        if err_count >= max_err:
                            err_count = 0
                            cur_count = 0

                        # Found an onset
                        if (cur_count + err_count) > max:
                            max = (cur_count + err_count)

                        if (cur_count + err_count) >= min_samples:
                            emg_start_idx = cur_idx - min_samples + 1
                        else:
                            cur_idx += 1

                    if emg_start_idx is not None:
                        emg_start_idx += first_start_idx

                        time.sleep(0.6)

                        #
                        # Refine signal onset (using likelihood test)
                        #

                        #
                        # Make a prediction
                        #
                        pred_begin      = time.time()
                        first_end_idx   = len(first_myo_data.timestamps)
                        print(first_end_idx - emg_start_idx)

                        if first_end_idx - emg_start_idx > 200:

                            emg_samples = []
                            for first_idx in range(emg_start_idx, len(first_myo_data.timestamps) - 1):
                                if data_mapping[first_idx] != self.myo_data.invalid_map:
                                    first_emg = [x[first_idx] for x in first_myo_data.emg]
                                    sec_idx = data_mapping[first_idx]
                                    second_emg = [x[sec_idx] for x in second_myo_data.emg]

                                    if len(emg_samples) < 200:
                                        emg_samples.append(first_emg + second_emg)
                            emg_samples = np.array(emg_samples)

                            test_feat   = self.pred_model.feat_extractor.extract_feature_point(emg_samples).reshape(1, 16)
                            pred        = self.pred_model.perform_inference(test_feat, None)
                            print("The pred:")
                            print(pred)

                        print(time.time() - pred_begin)

                    time.sleep(self.check_period)