#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QProgressDialog, QFileDialog, QWidget, QLabel, QHBoxLayout,
                                QVBoxLayout, QFrame, QMainWindow, QPushButton, QGridLayout, QSizePolicy, QGroupBox,
                                QTextEdit, QLineEdit, QErrorMessage, QProgressBar, QStackedWidget, QTableWidget,
                                QTableWidgetItem, QHeaderView)

from PyQt5.QtGui import QPixmap, QIcon, QFont
from PyQt5.QtCore import (QSize, QThreadPool, Qt, QRunnable, QMetaObject, Q_ARG, QObject, pyqtSignal, QTimer, QUrl,\
                            QFileInfo)
from PyQt5.QtMultimediaWidgets import QVideoWidget
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
from enum import Enum
import time
from os.path import curdir, exists, join, abspath

#
# Submodules in this repository
#
from movements import *
from param import *

class OnlineTesting(QWidget):
    """
        A GUI tab that allows for real-time predictions to be made on incoming data.
    """

    class PredictionsVisualizer(QMainWindow):
        """
            A window that visualizes the top K predictions, among other stats.
        """

        def __init__(self):
            super().__init__()

            #
            # Find paths to all screenshots
            #
            self.all_screenshot_paths       = [("A", []), ("B", []), ("C", [])]
            self.screenshots_dir            = "gesture_screenshots"
            self.screenshot_path_template   = [
                                                ("exercise_a/a{}.jpg", 12),
                                                ("exercise_b/b{}.jpg", 17),
                                                ("exercise_c/c{}.jpg", 23)
                                            ]

            self.is_ready       = self.generate_screenshot_paths()
            self.num_exercise_A = 12
            self.num_exercise_B = 17

            #
            # Configurable
            #
            self.default_top_k  = 5
            self.init_ui()

        def init_ui(self):
            self.setGeometry(0, 0, 1024/2, 768/2)
            top_level_widget = QWidget(self)
            self.setCentralWidget(top_level_widget)
            self.setWindowTitle("Gesture Predictions")

            #
            # Configurable Parameters
            #
            top_layout          = QGridLayout()
            top_k_title         = QLabel("Top K")
            top_k_title.setStyleSheet("font-weight: bold")
            self.top_k_field    = QLineEdit(str(self.default_top_k))
            top_layout.addWidget(top_k_title, 0, 0)
            top_layout.addWidget(self.top_k_field, 0, 1)

            hline = QFrame()
            hline.setFrameShape(QFrame.HLine)
            hline.setFrameShadow(QFrame.Sunken)
            top_layout.addWidget(hline, 1, 0, 1, 3)

            #
            # Simple stats
            #
            num_samples_title   = QLabel("# of Samples  ")
            num_samples_title.setStyleSheet("font-weight: bold")
            self.num_samples    = QLineEdit()
            self.num_samples.setReadOnly(True)
            top_layout.addWidget(num_samples_title, 2, 0)
            top_layout.addWidget(self.num_samples, 2, 1)

            #
            # Prediction visualization (list)
            #
            self.predictions_list = QTableWidget(0, 3)
            self.predictions_list.horizontalHeader().setStretchLastSection(True)
            self.predictions_list.horizontalHeader().setFont(QFont("Arial", 16, QFont.Bold))
            self.predictions_list.verticalHeader().setFont(QFont("Arial", 16, QFont.Bold))
            self.predictions_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.predictions_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self.predictions_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self.predictions_list.setHorizontalHeaderLabels(["Screenshot", "Title", "Probability"])
            self.predictions_list.setIconSize(QSize(400, 175))
            self.predictions_list.setContentsMargins(10, 30, 10, 10)
            top_layout.addWidget(self.predictions_list, 3, 0, 1, 3)

            top_layout.setColumnStretch(1, 3)
            top_layout.setColumnStretch(2, 5)
            top_level_widget.setLayout(top_layout)

        def display_predictions(self, prediction_probabilities, num_samples):
            """
                Updates the top K prediction visualization window.

            :param prediction_probabilities: Class probabilities associated with a prediction attempt
            :param num_samples: The number of data samples used to make this prediction
            """

            def acquire_var(self, text, widget_name, func):
                try:
                    temp = func(text)
                except:
                    # Display warning
                    if func == float:
                        return self.throw_error_message(self,
                                                        "Please set a valid float for \"{}\".".format(widget_name))
                    else:
                        return self.throw_error_message(self,
                                                        "Please set a valid integer for \"{}\".".format(widget_name))
                return temp

            if acquire_var(self, self.top_k_field.text(), "Top K", int) is None:
                self.cur_top_k = self.default_top_k
            else:
                self.cur_top_k = acquire_var(self, self.top_k_field.text(), "Top K", int)

            # Update "# of samples" field
            self.num_samples.setText(str(num_samples))

            #
            # Update list of predictions
            #
            if self.is_ready:
                indices = np.argsort(prediction_probabilities)
                indices = np.flip(indices[indices.shape[0] - self.cur_top_k:])

                self.predictions_list.clearContents()
                self.predictions_list.setRowCount(self.cur_top_k)
                list_idx = 0

                for idx in indices:

                    temp_widget = QListWidgetItem()
                    temp_widget.setBackground(Qt.gray)

                    #
                    # Create widget containing relevant prediction information
                    #
                    if idx == 0:
                        cur_title           = "Rest"
                        cur_screenshot_path = None
                    else:
                        ex, movement_num    = self.get_ex_movement(idx)
                        cur_screenshot_path = self.all_screenshot_paths[ord(ex) - ord("A")][1][movement_num-1]
                        cur_title           = MOVEMENT_DESC[ex][movement_num][0]

                    cur_probability  = prediction_probabilities[idx]

                    # Create new table entry
                    screenshot_widget   = QTableWidgetItem()
                    screenshot_widget.setTextAlignment(Qt.AlignCenter)
                    if cur_screenshot_path is not None:
                        screenshot = QIcon(QPixmap(cur_screenshot_path))
                        screenshot_widget.setIcon(screenshot)
                    else:
                        screenshot_widget.setText("N / A")

                    # Set table entry parameters
                    title_widget        = QTableWidgetItem(cur_title)
                    title_widget.setTextAlignment(Qt.AlignCenter)
                    title_widget.setFont(QFont("Helvetica", 14, QFont.Bold))
                    prob_widget         = QTableWidgetItem(str(cur_probability))
                    prob_widget.setFont(QFont("Helvetica", 14))
                    prob_widget.setTextAlignment(Qt.AlignCenter)
                    self.predictions_list.setItem(list_idx, 0, screenshot_widget)
                    self.predictions_list.setItem(list_idx, 1, title_widget)
                    self.predictions_list.setItem(list_idx, 2, prob_widget)
                    self.predictions_list.verticalHeader().setSectionResizeMode(list_idx, QHeaderView.Stretch)
                    list_idx += 1

        def generate_screenshot_paths(self):
            """
                Generates all screenshot paths from a template

            :return: [bool, bool, bool] : Do all screenshots exist for the ith exercise?
            """

            def create_exercise_paths(self, ex_label):
                ex_index            = ord(ex_label) - ord('A')
                found_screenshots   = True
                path_template       = join(self.screenshots_dir, self.screenshot_path_template[ex_index][0])
                max_idx             = self.screenshot_path_template[ex_index][1]
                ex_path_created     = []

                for i in range(1, max_idx + 1):
                    full_path = path_template.format(i)
                    ex_path_created.append(full_path)

                    if not exists(full_path):
                        found_screenshots = False
                        break

                self.all_screenshot_paths[ex_index][1].extend(ex_path_created)
                return found_screenshots

            exercises_found     = [True, True, True]
            exercises_found[0]  = create_exercise_paths(self, "A")
            exercises_found[1]  = create_exercise_paths(self, "B")
            exercises_found[2]  = create_exercise_paths(self, "C")

            return exercises_found

        def get_ex_movement(self, current_pred):
            """
            :param current_pred: A prediction label (0-52)
            :return: The exercise label, and movement number
            """

            #
            # Obtain movement number & exercise
            #
            if current_pred > self.num_exercise_A:

                if current_pred > self.num_exercise_A + self.num_exercise_B:
                    cur_ex          = "C"
                    movement_num    = current_pred - self.num_exercise_B - self.num_exercise_A

                else:
                    cur_ex          = "B"
                    movement_num    = current_pred - self.num_exercise_A
            else:
                movement_num   = current_pred
                cur_ex         = "A"

            return cur_ex, movement_num

        def throw_error_message(self, message):
            # Re-enable video buttons
            self.enable_video_buttons(True, False, False)

            # Display warning
            self.warning = QErrorMessage()
            self.warning.showMessage(message)
            self.warning.show()
            return None

    class MyoConnectedWidget(QWidget):
        """
            A widget representing a connected Myo armband device.
        """

        def __init__(self, address, rssi, battery):
            """
            :param address: MAC address of Myo armband device
            :param rssi: Signal strength of connected armband
            :param battery: Battery level (1-100) of connected armband
            """
            super().__init__()
            self.address = address
            self.init_ui(address, rssi, battery)

        def init_ui(self, address, rssi, battery):
            infoLayout = QHBoxLayout()
            infoLayout.setSpacing(5)

            # Myo armband icon
            lbl     = QLabel(self)
            orig    = QPixmap(join(abspath(__file__).replace("online_test.py", ""), "icons/myo.png"))
            new     = orig.scaled(QSize(30, 30), Qt.KeepAspectRatio)
            lbl.setPixmap(new)

            #
            # Format the Myo hardware (MAC) into a readable form
            #
            infoLayout.addWidget(lbl)
            formatted_address   = ""
            length              = len(address.hex())

            for i, ch in enumerate(address.hex()):
                formatted_address += ch
                if ((i - 1) % 2 == 0) and (i != length - 1):
                    formatted_address += "-"

            vline = QFrame()
            vline.setFrameShape(QFrame.VLine)
            vline.setFrameShadow(QFrame.Sunken)

            #
            # Myo armband address, signal strength
            #
            addr_label  = QLabel(formatted_address)
            addr_label.setContentsMargins(5, 0, 0, 0)
            cur_font    = addr_label.font()
            cur_font.setPointSize(10)
            addr_label.setFont(cur_font)
            infoLayout.addWidget(addr_label)
            infoLayout.addWidget(vline)
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
        """
        :param myo_data: All data collected from both Myo armband devices
        """
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
        # For video playing
        #
        self.timer = QTimer()
        self.timer.timeout.connect(self.timer_update)

        #
        # Prediction visualization
        #
        self.prediction_visualization = self.PredictionsVisualizer()
        self.init_ui()


    def init_ui(self):
        self.top_layout = QVBoxLayout()
        self.top_layout.setContentsMargins(10, 10, 10, 10)
        self.top_layout.setSpacing(15)

        #
        # Top "message box" / time remaining
        #
        message_layout      = QHBoxLayout()
        self.status_label   = QLabel("Waiting for Preparation...")
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

        controls_layout     = QGridLayout()
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

        self.noise_duration = QLineEdit("10.0")
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
        test_title = QLabel("Test Parameters")
        test_title.setAlignment(Qt.AlignCenter)
        test_title.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(test_title, 0, 7, 1, 2)

        hline4 = QFrame()
        hline4.setFrameShape(QFrame.HLine)
        hline4.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline4, 1, 7, 1, 2)

        self.pred_min_duration  = QLineEdit("2.5")
        self.pred_max_duration  = QLineEdit("6.0")
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
        """
            Called on user initiated connection

            :param address: MAC address of Myo armband device
            :param rssi: Signal strength of connected armband
            :param battery: Battery level (1-100) of connected armband
        """
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
        """
            Called on unexpected or user initiated connection

            :param address: MAC address of Myo armband device
        """

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
        """
        :param select_model: Enable select model button
        :param noise_button: Enable collect noise button
        :return:
        """
        self.model_button.setEnabled(select_model)
        self.noise_button.setEnabled(noise_button)

    def on_noise_collect(self):
        """
            On press of "Noise Collect" button, begin collecting noise via a background worker
        """

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
        """
            Called on start of noise data collection worker
        """
        pass

    def on_collect_complete(self):
        """
            Called on completion of noise data worker data collection
        """
        self.status_label.setText("Processing Noise Data...")
        self.progress_label.setText("N/A")
        self.progress_bar.close()

    def on_model_ready(self):
        """
            Called on completion of noise data worker data processing (model fitting)
        """
        self.status_label.setText("Waiting for Preparation...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 16pt; color: red;")
        self.enable_pred_buttons(True, True)
        self.collecting_noise = False
        self.noise_model_ready = True

        # Check if ready to start online testing
        self.check_ready_to_start()

    def on_model_select(self):
        """
            On press of the model select button, allow the user to select a model, and check for validity
        """

        self.enable_pred_buttons(False, False)
        dialog          = QFileDialog()
        self.model_file = dialog.getOpenFileName(self, 'Choose Model')[0]

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
        """
            Check if we are ready to start online testing, if so, enable the start button for online testing
        """
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
        """
            Enables/disables online testing buttons

        :param enable_start: Enable online testing start button
        :param enable_pause: Enable online testing pause button
        :param enable_stop: Enable online testing stop button
        :return:
        """
        self.controls_start.setEnabled(enable_start)
        self.controls_pause.setEnabled(enable_pause)
        self.controls_stop.setEnabled(enable_stop)

    def throw_error_message(self, message):
        # Re-enable video buttons
        self.enable_video_buttons(True, False, False)

        # Display warning
        self.warning = QErrorMessage()
        self.warning.showMessage(message)
        self.warning.show()
        return None

    def on_start_button(self):
        """
            On press of online testing start button, start background worker to process incoming data (to make predictions)
        """

        #
        # Check test parameters first!
        #
        def acquire_var(self, text, widget_name, func):
            try:
                temp = func(text)
            except:
                # Display warning
                if func == float:
                    return self.throw_error_message(self, "Please set a valid float for \"{}\".".format(widget_name))
                else:
                    return self.throw_error_message(self, "Please set a valid integer for \"{}\".".format(widget_name))
            return temp

        if ((acquire_var(self, self.pred_min_duration.text(), "Min. Duration", float) is None) or
                (acquire_var(self, self.pred_max_duration.text(), "Max. Duration", float) is None)):
            return

        self.min_pred_duration = acquire_var(self, self.pred_min_duration.text(), "Collect Duration", float)
        self.max_pred_duration = acquire_var(self, self.pred_max_duration.text(), "Rest Duration", float)

        #
        # For two reasons:
        #   1) Need at least 200 samples to have a single window in the features computed later on.
        #   2) Need at least 250 samples for the signal start/end refinement algorithm to work properly.
        #
        if self.min_pred_duration < 250/200:
            return self.throw_error_message("Please pick a minimum duration greater than {}.".format(250/200))

        ################################################################################################################

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
        self.prediction_visualization.show()
        self.pred_worker = GesturePredictionWorker(self.myo_data, self.noise_worker.smooth_avg,
                                                    self.noise_worker.smooth_std, self.classifier_model,
                                                    self.status_label, self.progress_label, self.desc_title,
                                                    self.desc_explain, self.video_player, self.enable_control_buttons,
                                                    self.controls_start, self.controls_pause, self.controls_stop,
                                                    self.timer, self.close_prediction_worker, self.min_pred_duration,
                                                    self.max_pred_duration, self.worker_prediction
                                                   )
        QThreadPool.globalInstance().start(self.pred_worker)

    def close_prediction_worker(self):
        """
            On press of online testing stop button, the background worker stops and this function is called
        """
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

        # Hide gesture prediction visualization
        self.prediction_visualization.hide()

    def worker_prediction(self):
        """
            On a prediction made by a background worker, this function is called
        """

        # Visualize top K predictions
        self.prediction_visualization.display_predictions(self.pred_worker.class_probabilities,
                                                            self.pred_worker.num_samples_used)

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
    """
        Collects noise data, processes it, and creates a noise model, used by signal detection.
    """

    def __init__(self, myo_data, noise_duration, noise_increments, progress_bar, progress_label, on_worker_started,
                        on_collect_complete, on_model_ready):
        """
        :param myo_data: A MyoData object, holding all data collected from both Myo armbands
        :param noise_duration: The duration to collect noise data for
        :param noise_increments: How many increments for the noise collection progress bar
        :param progress_bar: The noise collection progress bar
        :param progress_label: A QLineEdit text field, containing the remaining amount of time
        :param on_worker_started: A function called on the start of noise data collection
        :param on_collect_complete: A function called on completion of noise data collection
        :param on_model_ready: A function called on completion of noise model creation
        """
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
        #
        # Wait for data collection to finish
        #
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
        first_myo_data  = self.myo_data.band_1
        second_myo_data = self.myo_data.band_2
        data_mapping    = self.myo_data.data_mapping

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
            if ((data_mapping[first_idx] != self.myo_data.invalid_map) and
                    (data_mapping[first_idx] < len(second_myo_data.timestamps))):
                first_emg   = [x[first_idx] for x in first_myo_data.emg]
                sec_idx     = data_mapping[first_idx]
                second_emg  = [x[sec_idx] for x in second_myo_data.emg]
                noise_samples.append(first_emg + second_emg)

        #
        # Fit a noise model
        #
        noise_samples   = np.array(noise_samples)
        self.noise_mean = np.mean(noise_samples, axis=0)
        self.noise_cov  = np.cov(noise_samples, rowvar=False)

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
    """
        Collects incoming data, detects signal start/end, creates predictions, and visualizes predictions (video, etc)
    """

    #
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

    class GPWSignal(QObject):
        onShutdown   = pyqtSignal()
        onPrediction = pyqtSignal()

    def __init__(self, myo_data, smooth_avg, smooth_std, pred_model, status_label, progress_label, desc_title,
                    desc_explain, video_player, enable_control_buttons, controls_start, controls_pause,
                    controls_stop, timer, close_prediction, min_duration, max_duration, on_prediction):
        """

        :param myo_data: A MyoData object containing all data collected from both Myo armband devices
        :param smooth_avg: The mean across EMG data channels (smoothed, rectified) for noisy/rest movement
        :param smooth_std: The standard deviation across EMG data channels (smoothed, rectified) for noisy/rest movement
        :param pred_model: The loaded prediction model (of type ClassifierModel), to make predictions
        :param status_label: The top-left text field containing the current status of this module
        :param progress_label: The top-right text field containing the amount of time left
        :param desc_title: A text field containing a name\title of the movement being performed
        :param desc_explain: A text field containing a description of the movement being performed
        :param video_player: A QVideoWidget widget, used to play videos
        :param enable_control_buttons: A function enabling/disabling online testing start/pause/stop buttons
        :param controls_start: The online testing start button
        :param controls_pause: The online testing pause button
        :param controls_stop: The online testing stop button
        :param timer: A QTimer object, used to time state updates
        :param close_prediction: On close of this worker thread, this function is called
        :param min_duration: The minimum duration acceptable for a prediction
        :param max_duration: The maximum duration acceptable for a prediction
        :param on_prediction: A function called on prediction made
        """
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

        self.worker_event           = self.GPWSignal()
        self.worker_event.onShutdown.connect(close_prediction)
        self.worker_event.onPrediction.connect(on_prediction)

        self.min_duration = min_duration
        self.max_duration = max_duration

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
        self.max_samples    = 2000   # 5 seconds
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
        self.display_period     = 10.0  # Used to update time remaining
        self.timer_interval     = 100   # units of ms
        self.post_display_exit  = 100/1000 # units of secods

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
        """
            A helper function used to help find the start/end of a signal

        :param detect_start: True/False: Start/End

        :return: None or (start/end) index
        """

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
                    # first_mag   = [x[first_idx] for x in first_myo_data.orient]
                    # second_mag  = [x[sec_idx] for x in second_myo_data.orient]
                    # self.mag_list.append(first_mag + second_mag)

        emg_samples = np.array(self.emg_list)

        #
        # Apply sixth-order digital butterworth lowpass filter with 50 Hz cutoff frequency to rectified signal
        #
        fs          = 200
        nyquist     = 0.5 * fs
        cutoff      = 50
        order       = 6
        b, a        = butter(order, cutoff / nyquist, btype='lowpass')
        emg_samples = np.abs(emg_samples)
        filt_data   = lfilter(b, a, emg_samples, axis=0)

        #
        # Use test function to determine onset/end of signal
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

        #
        # Until user initiates a "stop", indefinitely make predictions
        #
        while self.running:

            start_idx = self.detect_movement(True)
            if start_idx is None:
                #
                # Trim EMG data
                #
                if len(self.emg_list) > self.max_samples:
                   self.emg_list = self.emg_list[self.trim_samples:]
                time.sleep(self.check_period)

            else:
                QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                         Q_ARG(str, "Collecting Movement Data..."))
                QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                         Q_ARG(str, "font-weight: bold; font-size: 16pt; color: gold;"))

                end_idx = None
                while (end_idx is None) and (self.running):
                    end_idx = self.detect_movement(False)
                    if end_idx is None:
                        time.sleep(self.check_period)

                if not self.running:
                    break

                #
                # Refine signal onset (using likelihood test)
                #

                # For debugging:
                # emg_samples = np.array(self.emg_list)
                # with open("temparray2", "wb") as f:
                #     np.save(f, emg_samples)

                #
                # Trim excess data on the end
                #
                num_samples = end_idx - start_idx

                if ((num_samples > self.min_duration * self.emg_rate) and
                        (num_samples < self.max_duration * self.emg_rate)):

                    #
                    # Refine start/end
                    #
                    best_start, best_end = optimize_start_end(self.emg_list, start_idx, end_idx)

                    if ( ((best_start is not None) and (best_end is not None)) and
                            (best_end - best_start > self.min_duration * self.emg_rate)
                        ):

                        # For debugging:
                        # with open("temparray", "wb") as f:
                        #     np.save(f, np.array(self.emg_list[best_start: best_end]))

                        if (best_start is not None) and (best_end is not None):
                            emg_samp   = np.array(self.emg_list[best_start: best_end])

                            if self.use_imu:
                                acc_samp   = np.array(self.acc_list[best_start: best_end])
                                gyro_samp  = np.array(self.gyro_list[best_start: best_end])

                                # Avoid using magnetometer
                                # mag_samp   = np.array(self.mag_list[best_start: best_end])
                                # combined_samples = [emg_samp, acc_samp, gyro_samp, mag_samp]
                                combined_samples = [emg_samp, acc_samp, gyro_samp]

                            if not self.running:
                                break

                            #
                            # Make a prediction
                            #
                            if self.use_imu:
                                test_feat   = self.pred_model.feat_extractor.extract_feature_point(combined_samples).reshape(1, -1)
                            else:
                                test_feat   = self.pred_model.feat_extractor.extract_feature_point(emg_samp).reshape(1, -1)
                            pred = self.pred_model.perform_inference(test_feat, None)[0]


                            if pred != self.rest_label:
                                prob                        = self.pred_model.get_class_probabilities(test_feat)
                                self.class_probabilities    = prob[0]
                                self.num_samples_used       = num_samples
                                self.worker_event.onPrediction.emit()

                                if not self.running:
                                    break

                                #
                                # Start playing videos, and updating text fields, via background thread
                                #
                                self.set_label(pred)
                                self.display_prediction()
                                time.sleep(self.post_display_exit)

                            else:
                                QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                                         Q_ARG(str, "Predicted rest..."))
                                QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                                         Q_ARG(str,
                                                               "font-weight: bold; font-size: 16pt; color: red;"))

                    else:
                        QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                                 Q_ARG(str, "Unable to refine gesture detection..."))
                        QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                                 Q_ARG(str, "font-weight: bold; font-size: 16pt; color: red;"))

                else:
                    QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                             Q_ARG(str, "Invalid waveform length..."))
                    QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                             Q_ARG(str, "font-weight: bold; font-size: 16pt; color: red;"))

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

            self.worker_event.onShutdown.emit()

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