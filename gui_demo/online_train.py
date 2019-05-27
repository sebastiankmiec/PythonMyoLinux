#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QFileDialog, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
                                QFrame, QMainWindow, QPushButton, QGridLayout, QSizePolicy, QGroupBox, QTextEdit,
                                QLineEdit, QErrorMessage, QProgressBar, QStackedWidget, QTableWidget, QHeaderView,
                                QTableWidgetItem, QCheckBox, QProgressDialog, QMessageBox)

from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtCore import (QSize, QThreadPool, Qt, QRunnable, QMetaObject, Q_ARG, QObject, pyqtSignal, QTimer, QUrl,
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
from ninaeval.utils.gt_tools import refine_start_end

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
from functools import partial

#
# Submodules in this repository
#
from movements import *
from param import *
from shared_workers import *


class OnlineTraining(QWidget):
    """
        A GUI tab that allows for online training (update a model based on incoming data)
    """

    class MovementsSelection(QMainWindow):
        """
            A window that allows a user to select movements desired for online training
        """

        def __init__(self, movements_selected, check_ready_to_start):
            super().__init__()

            self.movements_selected     = movements_selected
            self.check_ready_to_start   = check_ready_to_start

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
            self.num_classes    = 53 # 52 + rest
            self.default_reps   = 6

            self.init_ui()

        def init_ui(self):
            self.setGeometry(0, 0, 1024, 768)
            top_level_widget = QWidget(self)
            self.setCentralWidget(top_level_widget)
            self.setWindowTitle("Select Desired Movements")
            top_layout = QGridLayout()

            #
            # Prediction visualization (list)
            #
            self.movements_list = QTableWidget(0, 4)
            self.movements_list.horizontalHeader().setStretchLastSection(True)
            self.movements_list.horizontalHeader().setFont(QFont("Arial", 16, QFont.Bold))
            self.movements_list.verticalHeader().setFont(QFont("Arial", 16, QFont.Bold))
            self.movements_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.movements_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self.movements_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self.movements_list.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            self.movements_list.setHorizontalHeaderLabels(["Screenshot", "Title", "# Reps", "Selected"])
            self.movements_list.setIconSize(QSize(250, 200))

            self.movements_list.clearContents()
            self.movements_list.setRowCount(self.num_classes)
            self.is_movement_selected   = [False for x in range(self.num_classes)]
            self.num_reps               = [QTableWidgetItem(str(self.default_reps)) for x in range(self.num_classes)]

            for idx in range(self.num_classes):

                #
                # Create widget containing relevant movement information
                #
                if idx == 0:
                    cur_title           = "Rest"
                    cur_screenshot_path = None
                else:
                    ex, movement_num    = self.get_ex_movement(idx)
                    cur_screenshot_path = self.all_screenshot_paths[ord(ex) - ord("A")][1][movement_num - 1]
                    cur_title           = MOVEMENT_DESC[ex][movement_num][0]

                # Create new table entry
                screenshot_widget = QTableWidgetItem()
                screenshot_widget.setTextAlignment(Qt.AlignCenter)
                if cur_screenshot_path is not None:
                    screenshot = QIcon(QPixmap(cur_screenshot_path))
                    screenshot_widget.setIcon(screenshot)
                else:
                    screenshot_widget.setText("N / A")

                # Set table entry parameters
                title_widget = QTableWidgetItem(cur_title)
                title_widget.setTextAlignment(Qt.AlignCenter)
                title_widget.setFont(QFont("Helvetica", 14, QFont.Bold))

                self.num_reps[idx] = QTableWidgetItem(str(self.default_reps))
                self.num_reps[idx].setFont(QFont("Helvetica", 14))
                self.num_reps[idx].setTextAlignment(Qt.AlignCenter)
                self.num_reps[idx].setFlags(self.num_reps[idx].flags() | Qt.ItemIsEditable)

                select_box      = QCheckBox()
                selec_layout    = QHBoxLayout()
                selec_layout.addWidget(select_box)
                select_box.clicked.connect(partial(self.on_select_movement, mov_idx=idx))
                selec_layout.setAlignment(Qt.AlignCenter)

                self.movements_list.setItem(idx, 0, screenshot_widget)
                self.movements_list.setItem(idx, 1, title_widget)
                self.movements_list.setItem(idx, 2, self.num_reps[idx])
                self.movements_list.setCellWidget(idx, 3, QWidget())
                self.movements_list.cellWidget(idx, 3).setLayout(selec_layout)
                #self.movements_list.verticalHeader().setSectionResizeMode(idx, QHeaderView.Stretch)

            self.movements_list.resizeColumnsToContents()
            self.movements_list.resizeRowsToContents()

            top_layout.addWidget(self.movements_list, 0, 0)
            top_level_widget.setLayout(top_layout)

        def on_select_movement(self, mov_idx):
            '''
                After a QCheckBox in the MovementsSelection window is toggled, the 'QListWidget' self.movements_selected
                    is updated.

            :param mov_idx: Index of QCheckBox pressed
            '''

            #
            # If the box was originally ticked
            #
            if self.is_movement_selected[mov_idx]:
                self.is_movement_selected[mov_idx] = False

                num_widgets = self.movements_selected.count()
                idx_found   = None

                # Remove previously selected item from QListWidget
                for wid_idx in range(num_widgets):
                    myo_widget = self.movements_selected.item(wid_idx)
                    if myo_widget.label == mov_idx:
                        idx_found = wid_idx

                if idx_found is not None:
                    self.movements_selected.takeItem(idx_found)

            else:
                if mov_idx == 0:
                    cur_title = "Rest"
                else:
                    ex, movement_num    = self.get_ex_movement(mov_idx)
                    cur_title           = MOVEMENT_DESC[ex][movement_num][0]

                try:
                    cur_reps = int(self.num_reps[mov_idx].text())

                    # Add new item to list of selected widgets
                    new_movement = QListWidgetItem()
                    new_movement.setText(cur_title + " ({})".format(cur_reps))
                    new_movement.ex         = ex
                    new_movement.move_num   = movement_num
                    new_movement.reps       = cur_reps
                    new_movement.label      = mov_idx
                    self.movements_selected.addItem(new_movement)

                except ValueError:
                    self.throw_error_message("Invalid number of repetitions entered.")

                self.is_movement_selected[mov_idx] = True

            self.check_ready_to_start()

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

            # Obtain movement number & exercise
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
            lbl  = QLabel(self)
            orig = QPixmap(join(abspath(__file__).replace("online_train.py", ""), "icons/myo.png"))
            new  = orig.scaled(QSize(30, 30), Qt.KeepAspectRatio)
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
        self.controls_stop  = QPushButton("Stop")
        self.controls_stop.setStyleSheet("font-weight: bold")
        controls_layout.addWidget(self.controls_stop, 0, 1)
        controls_layout.setColumnStretch(0, 2)
        controls_layout.setColumnStretch(1, 1)
        controls_layout.setColumnStretch(2, 2)
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
        # Preparation Box: Movements Selected
        #
        self.movements_button = QPushButton("Select Movements")
        self.movements_button.clicked.connect(self.on_movements_selected)
        self.movements_button.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(self.movements_button, 0, 7)
        self.movements_selected = QListWidget()

        hline3 = QFrame()
        hline3.setFrameShape(QFrame.HLine)
        hline3.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline3, 1, 7)

        prep_layout.addWidget(self.movements_selected, 2, 7, 2, 1)

        # To select movements (in a separate window)
        self.move_select = self.MovementsSelection(self.movements_selected, self.check_ready_to_start)

        #
        # Preparation Phase formatting
        #
        prep_layout.setRowStretch(0, 3)
        prep_layout.setRowStretch(1, 1)
        prep_layout.setRowStretch(2, 4)
        prep_layout.setRowStretch(3, 4)

        prep_layout.setColumnStretch(0, 1)
        prep_layout.setColumnStretch(1, 4)
        prep_layout.setColumnStretch(2, 1)
        prep_layout.setColumnStretch(3, 2)
        prep_layout.setColumnStretch(4, 1)
        prep_layout.setColumnStretch(5, 6)
        prep_layout.setColumnStretch(6, 1)
        prep_layout.setColumnStretch(7, 5)

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
        '''
            Displays the MovementsSelection window
        '''
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
        """
            Called on a user initiated connection

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

        # Check if ready to start online training
        self.check_ready_to_start()

    def device_disconnected(self, address):
        """
            Called on an unexpected or user initiated connection

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

        # Check if ready to start online training
        self.check_ready_to_start()

    def enable_train_buttons(self, select_model, movements_button):
        """
            Enables/disables online training buttons

        :param select_model: Enable online training start button
        :param movements_button: Enable online training pause button
        """
        self.model_button.setEnabled(select_model)
        self.movements_button.setEnabled(movements_button)

    def on_noise_collect(self):
        """
            On press of "Noise Collect" button, begin collecting noise via a background worker
        """

        if self.collecting_noise:
            return self.warn_user("Currently collecting noise data and\or creating a noise model.")

        self.enable_train_buttons(False, False)
        self.noise_model_ready  = False

        def acquire_var(self, text, widget_name, func):
            try:
                temp = func(text)
            except:
                self.enable_train_buttons(True, True)

                # Display warning
                if func == float:
                    return self.warn_user("Please set a valid float for \"{}\".".format(widget_name))
                else:
                    return self.warn_user("Please set a valid integer for \"{}\".".format(widget_name))
            return temp

        noise_duration = acquire_var(self, self.noise_duration.text(), "Noise Duration", float)
        if noise_duration is None:
            self.enable_train_buttons(True, True)
            return

        if self.devices_connected.count() < 2:
            self.enable_train_buttons(True, True)
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
        self.enable_train_buttons(True, True)
        self.collecting_noise = False
        self.noise_model_ready = True

        # Check if ready to start online training
        self.check_ready_to_start()

    def on_model_select(self):
        """
            On press of the model select button, allow the user to select a model, and check for validity
        """
        self.enable_train_buttons(False, False)
        dialog              = QFileDialog()
        self.model_file     = dialog.getOpenFileName(self, 'Choose Model')[0]

        if len(self.model_file) == 0:
            self.enable_train_buttons(True, True)
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
            self.enable_train_buttons(True, True)
            return

        valid_model = hasattr(self.classifier_model, "update_training")
        if not valid_model:
            self.warn_user("Invalid model selected, no \"update_training\" member available.")
            self.enable_train_buttons(True, True)
            return

        self.valid_model    = True
        model_name          = self.classifier_model.__class__.__name__
        feat_name           = self.classifier_model.feat_extractor.__class__.__name__
        self.model_name.setText(model_name + " - " + feat_name)

        if self.classifier_model.num_samples is None:
            self.samples_field.setText("N/A")
        else:
            self.samples_field.setText(str(self.classifier_model.num_samples))
        self.enable_train_buttons(True, True)

        # Check if ready to start online training
        self.check_ready_to_start()

    def check_ready_to_start(self):
        """
            Check if we are ready to start online training, if so, enable the start button for online training
        """
        self.status_label.setText("Waiting for Preparation...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 16pt; color: red;")

        # Need two (connected) devices
        if self.devices_connected.count() < 2:
            self.start_button.setEnabled(False)
            return

        # Need prediction model
        if not self.valid_model:
            self.start_button.setEnabled(False)
            return

        # Need noise model
        if not self.noise_model_ready:
            self.start_button.setEnabled(False)
            return

        # Check if at least one movement is selected
        if self.movements_selected.count() == 0:
            self.start_button.setEnabled(False)
            return

        self.start_button.setEnabled(True)
        self.status_label.setText("Waiting to Start...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 16pt; color: green;")

    def on_start_button(self):
        '''
            Switches the initial view, to the online training view, in order to collect data.
                > Starts a GestureTrainingWorker QRunnable as a result
        '''

        control_box_idx = 1
        self.bottom_panel.setCurrentIndex(control_box_idx)

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

        # Start background worker, responsible for training data collection
        self.pred_worker = GestureTrainingWorker(self.myo_data, self.noise_worker.smooth_avg,
                                                    self.noise_worker.smooth_std, self.classifier_model,
                                                    self.status_label, self.progress_label, self.desc_title,
                                                    self.desc_explain, self.video_player, self.controls_stop, self.timer,
                                                    self.close_training_worker, self.movements_selected
                                                   )
        QThreadPool.globalInstance().start(self.pred_worker)

    def close_training_worker(self):
        '''
            Returns the online training view to the initial view. This function is called after GestureTrainingWorker
                finishes execution of "run()".
        '''
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

        # If we updated a model succesfully
        if self.pred_worker.complete:
            response = QMessageBox.question(self, "Training Complete", "Would you like to save the updated model?",
                                                QMessageBox.Yes | QMessageBox.No)

            if response == QMessageBox.Yes:
                dialog = QFileDialog()
                dialog.setFileMode(QFileDialog.Directory)
                dialog.setOption(QFileDialog.ShowDirsOnly)
                self.data_directory = dialog.getExistingDirectory(self, 'Choose Directory', curdir)

                if exists(self.data_directory):
                    self.classifier_model.save_model(self.data_directory)

        elif (not self.pred_worker.stopped):
            self.warn_user("Unable to train on collected samples.")

    def warn_user(self, message):
        """
            Generates a pop-up warning message

        :param message: The text to display
        """
        self.warning = QErrorMessage()
        self.warning.showMessage(message)
        self.warning.show()


class GestureTrainingWorker(QRunnable):
    """
        Collects incoming data, refines signal start/end of a movement performed, and updates a previously trained model.
    """

    #
    # Qt5, QMediaPlayer enum
    # > "Defines the status of a media player's current media."
    #
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
        onShutdown = pyqtSignal()

    def __init__(self, myo_data, smooth_avg, smooth_std, pred_model, status_label, progress_label, desc_title,
                    desc_explain, video_player, controls_stop, timer, close_prediction, movements_selected):
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
        :param controls_stop: The online training stop button
        :param timer: A QTimer object, used to time state updates
        :param close_prediction: On close of this worker thread, this function is called
        :param movements_selected: A list containing all movements selected from MovementsSelection.
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
        self.movements_selected     = movements_selected

        self.controls_stop          = controls_stop
        self.controls_stop.clicked.connect(self.stop_online_train)
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

        #
        # Video playing specific
        #
        ############################################################################################################
        ############################################################################################################
        self.num_exercise_A = 12
        self.num_exercise_B = 17

        # Configurable parameters
        self.timer_interval     = 100   # units of ms
        self.post_display_exit  = 100/1000 # units of secods
        self.preparation_period = 10.0
        self.collect_duration   = 5.0
        self.rest_duration      = 3.0
        self.update_epochs      = 50
        self.use_imu            = False

        # State variables
        self.state_time_remain  = 0  # seconds
        self.video_playing      = False
        self.stopped            = False
        self.current_label      = None
        self.complete           = False
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

    def run(self):

        #
        # Check if all videos exist
        #
        exercises_found = self.check_video_paths()

        def missing_exer(self, ex_found, ex_label):
            if not ex_found:
                # Display warning
                self.warning = QErrorMessage()
                self.warning.showMessage("Unable to find videos for Exercise {}.".format(ex_label))
                self.warning.show()
            return ex_found

        if ((not missing_exer(self, exercises_found[0], "A")) or (not missing_exer(self, exercises_found[1], "B"))
                or (not missing_exer(self, exercises_found[2], "C"))):
            return self.stop_online_train()


        # The start\end index in passed myo data, for the given movement and repetition
        num_selected        = self.movements_selected.count()
        start_end_indices   = []

        first_myo_data  = self.myo_data.band_1
        second_myo_data = self.myo_data.band_2
        data_mapping    = self.myo_data.data_mapping


        for i in range(num_selected):

            if self.stopped:
                break

            movement        = self.movements_selected.item(i)
            movement_num    = movement.move_num
            num_reps        = movement.reps
            exercise        = movement.ex
            label           = movement.label
            video_path      = None

            # Find video path
            for ex_vids in self.all_video_paths:
                if ex_vids[0] == exercise:
                    video_path = ex_vids[1][movement_num - 1]
                    break


            #
            # Setup for current movement
            #
            current_rep = 0
            QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, "{} s ({}/{})".format(self.preparation_period, current_rep,
                                                                        num_reps)))
            current_description = MOVEMENT_DESC[exercise][movement_num]
            QMetaObject.invokeMethod(self.desc_title, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, current_description[0]))
            QMetaObject.invokeMethod(self.desc_explain, "setText",
                                     Qt.QueuedConnection, Q_ARG(str, current_description[1]))

            #
            # Preparation period
            #
            QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, "Preparing for repetition 1..."))
            QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                     Q_ARG(str, "font-weight: bold; font-size: 18pt; color: blue;"))
            self.play_video(video_path, self.preparation_period)
            self.current_label = None

            while self.video_playing and (not self.stopped):
                time.sleep(self.timer_interval / 1000)

            if self.stopped:
                break

            #
            # Collecting\resting periods
            #
            start_end_idx   = [label, None, None]

            for i in range(num_reps):

                start_end_idx[1] = len(first_myo_data.timestamps) - 1

                #
                # Collect
                #
                current_rep = i + 1
                QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                         Q_ARG(str, "Collecting for repetition {}...".format(current_rep)))
                QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                         Q_ARG(str, "font-weight: bold; font-size: 18pt; color: green;"))
                self.play_video(video_path, self.collect_duration)
                self.current_label = label

                while self.video_playing and (not self.stopped):
                    time.sleep(self.timer_interval / 1000)

                if self.stopped:
                    break

                start_end_idx[2] = len(first_myo_data.timestamps) - 1
                start_end_indices.append(start_end_idx)

                #
                # Rest
                #
                if current_rep != num_reps:
                    QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                             Q_ARG(str,
                                                   "Resting before repetition {}...".format(
                                                       current_rep + 1)))
                    QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                             Q_ARG(str, "font-weight: bold; font-size: 18pt; color: orange;"))
                    self.play_video(video_path, self.rest_duration)
                    self.current_label = 0

                    while self.video_playing and (not self.stopped):
                        time.sleep(self.timer_interval / 1000)
                else:
                    self.current_label = None

                if self.stopped:
                    break

        #
        # Process all collected data to update the prediction model
        #
        if not self.stopped:
            train_feat    = []
            train_labels  = []

            #
            # Reformat the raw data
            #
            all_emg_list = []
            all_acc_list = []
            all_gyro_list = []
            for first_idx in range(len(first_myo_data.timestamps)):

                if self.stopped:
                    break

                sec_idx = data_mapping[first_idx]
                if (sec_idx != self.myo_data.invalid_map) and (sec_idx < len(second_myo_data.timestamps)):
                    # EMG
                    first_emg   = [x[first_idx] for x in first_myo_data.emg]
                    second_emg  = [x[sec_idx] for x in second_myo_data.emg]
                    all_emg_list.append(first_emg + second_emg)

                    if self.use_imu:
                        # ACC
                        first_acc   = [x[first_idx] for x in first_myo_data.accel]
                        second_acc  = [x[sec_idx] for x in second_myo_data.accel]
                        all_acc_list.append(first_acc + second_acc)

                        # GYRO
                        first_gyro  = [x[first_idx] for x in first_myo_data.gyro]
                        second_gyro = [x[sec_idx] for x in second_myo_data.gyro]
                        all_gyro_list.append(first_gyro + second_gyro)

            #
            # Process (each repetition) of each selected movement
            #
            for i, start_end_idx in enumerate(start_end_indices):

                if self.stopped:
                    break

                label       = start_end_idx[0]
                start_idx   = start_end_idx[1]
                end_idx     = start_end_idx[2]

                #
                # Attempt to refine the start/end of a movement performed
                #
                best_start, best_end = refine_start_end(all_emg_list, start_idx, end_idx)

                if (best_start is not None) and (best_end is not None):
                    emg_window = np.array(all_emg_list[best_start: best_end])

                    if self.use_imu:
                        acc_window  = np.array(self.acc_list[best_start: best_end])
                        gyro_window = np.array(self.gyro_list[best_start: best_end])

                        # Avoid using magnetometer (overfitting issue)
                        # mag_samp   = np.array(self.mag_list[best_start: best_end])
                        # combined_samples = [emg_samp, acc_samp, gyro_samp, mag_samp]
                        combined_window = [emg_window, acc_window, gyro_window]

                        cur_feat = self.pred_model.feat_extractor.extract_feature_point(combined_window).reshape(-1)
                    else:
                        cur_feat = self.pred_model.feat_extractor.extract_feature_point(emg_window).reshape(-1)

                    train_labels.append(label)
                    train_feat.append(cur_feat)
                else:
                    continue

                QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                         Q_ARG(str,
                                               "Processing seleceted movement {} of {}...".format(i + 1,
                                                                                                  len(start_end_indices))
                                               )
                                         )
                QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                         Q_ARG(str, "font-weight: bold; font-size: 18pt; color: orange;"))

            #
            # Perform the actual training, save the updated model
            #
            if (not self.stopped) and (len(train_feat) != 0):
                train_feat      = np.array(train_feat)
                train_labels    = np.array(train_labels)
                self.pred_model.update_training(train_feat, train_labels, self.update_epochs)
                self.complete = True

        self.on_worker_stopped()

    ################################################################################################################
    ################################################################################################################
    ################################################################################################################
    #
    # Video playing functions
    #
    ################################################################################################################
    ################################################################################################################
    ################################################################################################################

    def stop_online_train(self):
        """
            This function is called when the user presses "Stop".
                > The background worker finishes executing the run() function as a result of being "stopped".
        """
        if self.shutdown:
            return
        self.shutdown = True

        # Force the background worker to leave run()
        self.force_stop()

    def on_worker_stopped(self):
        """
            This function is called when the background worker has finished execution of run().
        """

        # Stop video player
        QMetaObject.invokeMethod(self.video_player, "stop", Qt.QueuedConnection)

        # Update GUI appearance
        QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                 Q_ARG(str, "0.0s"))
        QMetaObject.invokeMethod(self.desc_title, "setText", Qt.QueuedConnection,
                                 Q_ARG(str, "No Movement"))
        QMetaObject.invokeMethod(self.desc_explain, "setText", Qt.QueuedConnection,
                                 Q_ARG(str, "No description available."))

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
        self.stopped = True
    ################################################################################################################
    ################################################################################################################
    ################################################################################################################