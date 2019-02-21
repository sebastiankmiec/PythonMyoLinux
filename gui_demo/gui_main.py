#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QPushButton, QGridLayout, QApplication, QSizePolicy,
                                QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QProgressDialog, QErrorMessage,
                                QTabWidget, QGroupBox, QFileDialog, QMessageBox, QFrame)

from PyQt5.QtGui import QFontMetrics, QIcon
from PyQt5.QtCore import Qt, QThreadPool, QObject, pyqtSignal
import pyqtgraph as pg
from pyqtgraph import GraphicsLayout
# from PyQt5.QtChart import QChartView

#
# Miscellaneous imports
#
import sys
import time
from functools import partial
from os.path import curdir, exists, join, abspath
import copy
from serial.tools.list_ports import comports

#
# Submodules in this repository
#
from backgroundworker import MyoSearchWorker
from widgets import MyoFoundWidget, GroundTruthHelper
from param import *

########################################################################################################################
########################################################################################################################
##### CONFIGURABLE PARAMETERS ---> See util.py.
########################################################################################################################
########################################################################################################################

class TopLevel(QWidget):
    """
        Main window containing all GUI components.
    """

    #
    # Used to cleanup background worker thread(s) (on exit)
    #
    class Exit(QObject):
        exitClicked = pyqtSignal()
    def closeEvent(self, event):
        self.close_event.exitClicked.emit()

    def __init__(self):
        super().__init__()

        self.myo_devices    = []
        self.first_myo      = None          # Currently connected myo devices, and associated ports
        self.first_port     = None
        self.second_myo     = None
        self.second_port    = None

        self.first_myo_data     = []        # Data collected by event handlers
        self.second_myo_data    = []


        self.progress_bars  = []            # Progress bars, used when searching for Myo armband devies
        self.search_threads = []            # Background threads that scan for advertising packets from advertising
                                            # Myo armband devices.

        self.myo_counts = []                # The number of Myo devices found, via a given communication port


        self.start_time     = time.time()
        self.data_directory = None
        self.increments     = 100           # Number of progress bar increments (when searching for Myo devices)

        self.gt_helper_open = False         # Ground truth helper

        self.close_event = self.Exit()
        self.close_event.exitClicked.connect(self.stop_background_workers)
        self.worker_check_period = 1        # seconds

        self.initUI()

    def initUI(self):

        #
        # Top-level layout
        #
        grid = QGridLayout()
        grid.setSpacing(15)
        self.setGeometry(0, 0, 1024, 768)
        self.setWindowTitle('Myo Data Collection Tool')

        #
        # Myo dongle and device discovery
        #
        com_port_button = QPushButton("Find COM Ports")
        com_port_button.clicked.connect(self.find_ports)
        grid.addWidget(com_port_button, 0, 0, Qt.AlignBottom)
        self.ports_found = QListWidget()                                    # Populated with found dongles and devices
        self.ports_found.itemPressed.connect(self.serial_port_clicked)
        grid.addWidget(self.ports_found, 1, 0, 1, 1)

        #
        # EMG Data Visualization
        #

        # EMG data plots
        self.myo_1_layouts  = [pg.GraphicsLayoutWidget() for x in range(8)]
        self.myo_2_layouts  = [pg.GraphicsLayoutWidget() for x in range(8)]
        self.myo_1_charts   = [None for x in range(8)]
        self.myo_2_charts   = [None for x in range(8)]
        self.top_tab        = QTabWidget()                                  # Top-level tab container

        # Old backend
        #self.myo_1_charts = [QChartView() for x in range(8)]               # EMG data plots
        #self.myo_2_charts = [QChartView() for x in range(8)]

        # Custom y-axis for EMG plots
        def custom_y_ticks(*args):
            return [(200.0, [-128, 0, 127]), (100.0, [-80, -40, 40, 80])]

        def initialize_plots(charts_list, layouts_list, top_tab, device_num):
            """
                A helper function that initializes all plots (for both devices, and all channels)

            :param charts_list: A list of None -> becomes a list of PlotItem
            :param layouts_list: A list of GraphicsLayoutWidget
            :param top_tab: A top level tab per device
            :param device_num: The device number (1/2)
            :return:
            """

            for i, chart in enumerate(charts_list):                       # Channels 1-8 subtabs

                brush = pg.functions.mkBrush(255, 255, 255)
                layouts_list[i].setBackgroundBrush(brush)

                # Add widget to tab
                top_tab.addTab(layouts_list[i], "Ch. " + str(i+1))

                # Add plot to new widget
                temp_plot = pg.PlotItem()
                layouts_list[i].addItem(row=0, col=0, rowspan=1, colspan=1, item = temp_plot)
                charts_list[i] = temp_plot
                temp_plot.setMenuEnabled(False)

                # Customize plot
                charts_list[i].setXRange(0, NUM_GUI_SAMPLES, padding=0.075)
                charts_list[i].setYRange(-150, 150, padding=0)  # EMG values are signed 8-bit
                charts_list[i].showGrid(True, True, 0.6)
                layouts_list[i].ci.setContentsMargins(10, 10, 40, 20)

                left_axis               = charts_list[i].getAxis("left")
                left_axis.tickValues    = custom_y_ticks
                left_axis.setPen(color="333")

                bottom_axis             = charts_list[i].getAxis("bottom")
                labelStyle = {'color': '#000', 'font-size': '12pt', "font-style": "italic", "font-weight": "bold"}
                bottom_axis.setLabel(text="Sample Number", **labelStyle)
                bottom_axis.setPen(color="333")

                charts_list[i].setTitle(title="Device {} - Channel {} - EMG Amplitude".format(device_num, i + 1),
                                            size="15pt", bold=True, color="000088")

        # Plot formatting (device one)
        self.myo_1_tab = QTabWidget()  # Myo device 1 tab
        self.myo_1_tab.setStyleSheet("font-weight: normal;")
        initialize_plots(self.myo_1_charts, self.myo_1_layouts, self.myo_1_tab, 1)

        # Plot formatting (device two)
        self.myo_2_tab    = QTabWidget()
        self.myo_2_tab.setStyleSheet("font-weight: normal;")
        initialize_plots(self.myo_2_charts, self.myo_2_layouts, self.myo_2_tab, 2)

        self.top_tab.setStyleSheet("font-weight: bold;")

        # Plot layout
        grid.addWidget(self.top_tab, 0, 1, 4, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 20)
        grid.setRowStretch(2, 5)
        grid.setRowStretch(3, 1)
        grid.setColumnStretch(0, 4)
        grid.setColumnStretch(1, 6)

        #
        # Data Saving Options
        #
        self.data_gen_box = QGroupBox()                                     # Data Saving Options layout
        #self.data_gen_box.setObjectName("DataGroupBox")
        #self.data_gen_box.setStyleSheet("QGroupBox#DataGroupBox { border: 2px solid black;}")
        self.data_gen_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        top_layout          = QVBoxLayout()
        top_layout.setSpacing(12)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Data Generation Box
        inner_box = QGroupBox()
        inner_box.setObjectName("DataInnerBox")
        inner_box.setStyleSheet("QGroupBox#DataInnerBox { border: 1px solid gray; background-color: #cccccc;"
                                "                             border-radius: 7px;}")
        box_title = QLabel("Data Generation")
        box_title.setStyleSheet("font-weight: bold; font-size: 14pt")
        top_layout.addWidget(box_title)
        top_layout.addWidget(inner_box)
        top_inner_layout    = QVBoxLayout()
        top_inner_layout.setSpacing(10)
        top_inner_layout.setContentsMargins(10, 10, 10, 10)

        buttons_layout      = QHBoxLayout()                                 # "Save" and "GT Helper" buttons
        path_layout         = QHBoxLayout()                                 # Line to enter path

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setLineWidth(2)

        path_title = QLabel("Output Directory")
        path_title.setStyleSheet("font-weight: bold")
        top_inner_layout.addWidget(path_title)                              # Line to enter path
        self.save_path      = QLineEdit()
        path_layout.addWidget(self.save_path)

        file_browser_button     = QPushButton("...")                        # File explorer button
        file_browser_button.clicked.connect(self.file_browser_clicked)
        path_layout.addWidget(file_browser_button)

        self.save_data_button   = QPushButton("Save")                       # Save button
        self.save_data_button.clicked.connect(self.save_clicked)

        self.gt_helper_button   = QPushButton("GT Helper")                  # Ground truth button
        self.gt_helper_button.clicked.connect(self.gt_helper_clicked)
        self.gt_helper = GroundTruthHelper(close_function=self.gt_helper_closed)

        top_inner_layout.addLayout(path_layout)
        top_inner_layout.addWidget(separator)
        top_inner_layout.addLayout(buttons_layout)
        buttons_layout.addWidget(self.save_data_button)
        buttons_layout.addWidget(self.gt_helper_button)
        inner_box.setLayout(top_inner_layout)
        self.data_gen_box.setLayout(top_layout)
        grid.addWidget(self.data_gen_box, 2, 0, 2, 1)

        self.setLayout(grid)
        self.show()

    def stop_background_workers(self):
        #
        # Wait on Myo search workers to complete
        #
        waiting_on_search = True
        while waiting_on_search:

            waiting_on_search = False
            for worker in self.search_threads:
                if not worker.complete:
                    worker.running      = False
                    waiting_on_search   = True
                    break

            if waiting_on_search:
                time.sleep(self.worker_check_period)

        #
        # Stop data workers
        #
        waiting_on_search = True
        while waiting_on_search:

            waiting_on_search   = False
            num_widgets         = self.ports_found.count()

            for idx in range(num_widgets):

                # Ignore port widgets (only interested in Myo device rows)
                list_widget = self.ports_found.item(idx)
                if hasattr(list_widget, "port_idx"):
                    continue

                myo_widget = self.ports_found.itemWidget(list_widget)

                if not (myo_widget.worker is None):
                    if not myo_widget.worker.complete:
                        myo_widget.worker.running   = False
                        waiting_on_search           = True
                        break

            if waiting_on_search:
                time.sleep(self.worker_check_period)


    def gt_helper_closed(self):
        self.gt_helper_open = False

    def file_browser_clicked(self):
        """
            File explorer button clicked.
        :return: None
        """
        dialog = QFileDialog()
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly)
        self.data_directory = dialog.getExistingDirectory(self, 'Choose Directory', curdir)

        if exists(curdir):
            self.save_path.setText(self.data_directory)

    def save_clicked(self):
        """
            Save button clicked.
        :return: None
        """

        if ( ((self.data_directory is None) or (not exists(self.data_directory))) and
            (not exists(self.save_path.text())) ):
            self.warning = QErrorMessage()
            self.warning.showMessage("Invalid path selected.")
            self.warning.show()
            return
        else:
            self.data_directory = self.save_path.text()

        if (self.first_myo != None) or (self.second_myo != None):
            self.warning = QErrorMessage()
            self.warning.showMessage("Please disconnect Myo devices first.")
            self.warning.show()
            return

        #
        # Helper function that saves one data point to a file descriptor (for a file containing a single device)
        #
        def write_single(data, fd):

            # See "create_emg_event" for details:
            base_time   = self.start_time
            cur_time    = data[0]
            index       = data[1]
            emg_list    = data[2]
            orient_list = data[3]
            accel_list  = data[4]
            gyro_list   = data[5]

            # Write to file descriptor
            fd.write("{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
                cur_time - base_time, index,
                emg_list[0], emg_list[1], emg_list[2], emg_list[3], emg_list[4],
                emg_list[5], emg_list[6], emg_list[7],
                orient_list[0], orient_list[1], orient_list[2], orient_list[3],
                accel_list[0], accel_list[1], accel_list[2],
                gyro_list[0], gyro_list[1], gyro_list[2]
            ))

        if (len(self.first_myo_data) == 0) and (len(self.second_myo_data) == 0):
            self.warning = QErrorMessage()
            self.warning.showMessage("No data available to save.")
            self.warning.show()

        # Multiple myo devices to save data from
        elif (len(self.first_myo_data) != 0) and (len(self.second_myo_data) != 0):

            full_path_1     = join(self.data_directory, FILENAME_1)
            full_path_2     = join(self.data_directory, FILENAME_2)
            full_path_all   = join(self.data_directory, FILENAME_all)
            first_myo_data  = copy.deepcopy(self.first_myo_data)
            sec_myo_data    = copy.deepcopy(self.second_myo_data)

            # File descriptors for 3 created files
            fd_1    = open(full_path_1, "w")
            fd_2    = open(full_path_2, "w")
            fd_all  = open(full_path_all, "w")

            # Headers
            fd_1.write("Time, Index, EMG_1, EMG_2, EMG_3, EMG_4, EMG_5, EMG_6, EMG_7, EMG_8, OR_W, OR_X, OR_Y, OR_Z,"
                     "ACC_1, ACC_2, ACC_3, GYRO_1, GYRO_2, GYRO_3\n")
            fd_2.write("Time, Index, EMG_1, EMG_2, EMG_3, EMG_4, EMG_5, EMG_6, EMG_7, EMG_8, OR_W, OR_X, OR_Y, OR_Z,"
                     "ACC_1, ACC_2, ACC_3, GYRO_1, GYRO_2, GYRO_3\n")
            fd_all.write("Time_1, Time_2, D1_EMG_1, D1_EMG_2, D1_EMG_3, D1_EMG_4, D1_EMG_5, D1_EMG_6, D1_EMG_7,"
                         " D1_EMG_8, D1_OR_W, D1_OR_X, D1_OR_Y, D1_OR_Z, D1_ACC_1, D1_ACC_2, D1_ACC_3, D1_GYRO_1,"
                         " D1_GYRO_2, D1_GYRO_3,"
                         " D2_EMG_1, D2_EMG_2, D2_EMG_3, D2_EMG_4, D2_EMG_5, D2_EMG_6, D2_EMG_7, D2_EMG_8, D2_OR_W,"
                         " D2_OR_X, D2_OR_Y, D2_OR_Z, D2_ACC_1, D2_ACC_2, D2_ACC_3, D2_GYRO_1, D2_GYRO_2, D2_GYRO_3\n")

            # Find
            #   1) Time of which both devices are recording,
            #   2) Time of which the first device stops recording
            max_first   = float("-inf")
            min_last    = float("inf")

            if max_first < first_myo_data[0][0]:
                max_first = first_myo_data[0][0]
            if max_first < sec_myo_data[0][0]:
                max_first = sec_myo_data[0][0]
            if min_last > first_myo_data[len(first_myo_data) - 1][0]:
                min_last = first_myo_data[len(first_myo_data) - 1][0]
            if min_last > sec_myo_data[len(sec_myo_data) - 1][0]:
                min_last = sec_myo_data[len(sec_myo_data) - 1][0]

            # Define time of first data point (using a buffer period)
            start_time      = max_first + BUFFER_PERIOD
            if start_time > min_last:
                self.warning = QErrorMessage()
                self.warning.showMessage("Less than {} seconds worth of data collected.".format(BUFFER_PERIOD))
                self.warning.show()
                fd_1.close()
                fd_2.close()
                fd_all.close()
                return

            #
            # Save data to individual files, and find start indices
            #
            min_first_dist  = float("inf")
            min_sec_dist    = float("inf")
            first_idx       = None
            sec_idx         = None

            for i, data in enumerate(first_myo_data):
                time = data[0]
                if abs(start_time - time) < min_first_dist:
                    min_first_dist  = abs(start_time - time)
                    first_idx       = i
                write_single(data, fd_1)
            for i, data in enumerate(sec_myo_data):
                time = data[0]
                if abs(start_time - time) < min_sec_dist:
                    min_sec_dist = abs(start_time - time)
                    sec_idx      = i
                    write_single(data, fd_2)

            #
            # Attempt to create a file with data synchronized file (using timestamps)
            #
            second_offset = sec_idx # Index to data of second device

            for first_offset, data in enumerate(first_myo_data):
                if first_offset < first_idx:
                    continue
                if second_offset >= len(sec_myo_data):
                    break

                #
                # See "create_emg_event" for details:
                #
                base_time   = self.start_time                       # Single data point (device one)
                cur_time    = data[0]
                emg_list    = data[2]
                orient_list = data[3]
                accel_list  = data[4]
                gyro_list   = data[5]

                cur_sec_data    = sec_myo_data[second_offset]       # Single data point (device two)
                cur_time_2      = cur_sec_data[0]

                # Time since opening of GUI program
                first_delta_time    = cur_time - base_time
                sec_delta_time      = cur_time_2 - base_time

                #
                # If the second device is lagging, let the second device catch up
                #       ---> By finding a more recent second device data point
                #
                if first_delta_time - sec_delta_time > COPY_THRESHOLD:
                    while first_delta_time - sec_delta_time > COPY_THRESHOLD:
                        second_offset += 1
                        if second_offset >= len(sec_myo_data):
                            break

                        cur_sec_data    = sec_myo_data[second_offset]
                        cur_time_2      = cur_sec_data[0]
                        sec_delta_time  = cur_time_2 - base_time

                if second_offset >= len(sec_myo_data):
                    break
                else:
                    cur_sec_data    = sec_myo_data[second_offset]   # Update single data point
                    cur_time_2      = cur_sec_data[0]
                    emg_list_2      = cur_sec_data[2]
                    orient_list_2   = cur_sec_data[3]
                    accel_list_2    = cur_sec_data[4]
                    gyro_list_2     = cur_sec_data[5]
                    sec_delta_time  = cur_time_2 - base_time

                #
                # If second data is ahead, let the first device catch up
                #       ---> By finding a more recent first device data point
                #
                if sec_delta_time - first_delta_time > COPY_THRESHOLD:
                    continue

                # Write to file descriptor
                fd_all.write("{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},"
                                "{},{},{},{},{},{},{},{},{}\n".format(
                    first_delta_time, sec_delta_time,
                    emg_list[0], emg_list[1], emg_list[2], emg_list[3], emg_list[4],
                    emg_list[5], emg_list[6], emg_list[7],
                    orient_list[0], orient_list[1], orient_list[2], orient_list[3],
                    accel_list[0], accel_list[1], accel_list[2],
                    gyro_list[0], gyro_list[1], gyro_list[2],

                    emg_list_2[0], emg_list_2[1], emg_list_2[2], emg_list_2[3], emg_list_2[4],
                    emg_list_2[5], emg_list_2[6], emg_list_2[7],
                    orient_list_2[0], orient_list_2[1], orient_list_2[2], orient_list_2[3],
                    accel_list_2[0], accel_list_2[1], accel_list_2[2],
                    gyro_list_2[0], gyro_list_2[1], gyro_list_2[2]
                ))
                second_offset += 1

            fd_1.close()
            fd_2.close()
            fd_all.close()

            self.update = QMessageBox()
            self.update.setText("Saved data from two Myo devices.")
            self.update.show()

        # Only a single Myo device to save data from (simpler)
        else:

            full_path = join(self.data_directory, SINGLE_MYO_FILENAME)

            # Select data from valid device
            data_ref = None
            if len(self.first_myo_data) == 0:
                data_ref = copy.deepcopy(self.second_myo_data)
            else:
                data_ref = copy.deepcopy(self.first_myo_data)

            # Create file, write header
            fd = open(full_path, "w")
            fd.write("Time, Index, EMG_1, EMG_2, EMG_3, EMG_4, EMG_5, EMG_6, EMG_7, EMG_8, OR_W, OR_X, OR_Y, OR_Z,"
                        "ACC_1, ACC_2, ACC_3, GYRO_1, GYRO_2, GYRO_3\n")

            # Save data points
            for data in data_ref:
                write_single(data, fd)
            fd.close()

            self.update = QMessageBox()
            self.update.setText("Saved data from one Myo device.")
            self.update.show()

    def gt_helper_clicked(self):
        if not self.gt_helper_open:
            self.gt_helper_open = True
            self.gt_helper.show()


    def find_ports(self):
        """
            Find available serial USB interfaces (character device files, /dev/tty*), corresponding to Myo dongles.
        :return: None
        """

        self.myo_counts.clear()
        self.ports_found.clear()
        self.progress_bars.clear()

        expec_manufac = "Bluegiga"
        expec_name    = "Low Energy Dongle"

        ports_found = 0
        for port in comports():

            #
            # If this is a Bluegiga - Low Energy Dongle
            #
            port_attr = port.__dict__
            if not (
                        ("manufacturer" in port_attr.keys()) and
                        (("product" in port_attr.keys()) or ("description" in port_attr.keys())) and
                        ("device" in port_attr.keys())
                ):
                continue

            if not (
                    (expec_manufac in port_attr["manufacturer"]) or
                    ((expec_name in port_attr["product"]) and (expec_name in port_attr["description"]))
            ):
                continue

            port_list_entry = QListWidgetItem(port_attr["device"])
            port_list_entry.setIcon(QIcon(join(abspath(__file__).replace("gui_main.py", ""), "icons/sp.png")))
            port_list_entry.port_idx    = ports_found
            port_list_entry.port        = port_attr["device"]
            self.ports_found.insertItem(ports_found, port_list_entry);
            ports_found += 1
            self.myo_counts.append(0) # No Myo devices found for this newly found port yet

    def serial_port_clicked(self, e):
        """
            On a click event (may not be a port), search for Myo devices using this port.
        :param e: A click event on a port (ideally).
        :return: None
        """
        try:
            index   = e.port_idx    # Port number
            port    = e.port        # /dev/ttyXYZ
        except:
            return

        #
        # First, clear Myo devices previously found on this port
        #
        list_index = 0
        for i in range(index):
            list_index += 1
            list_index += self.myo_counts[i]

        for j in range(self.myo_counts[index]):
           self.ports_found.takeItem(list_index + 1)

        #
        # Add a progress bar message
        #
        progress = QProgressDialog("Searching for Myo armbands...", "Cancel", 0, self.increments)
        progress.setWindowTitle("In Progress")
        progress.show()
        progress.setValue(0)
        progress.setCancelButton(None)
        self.progress_bars.append(progress)

        #
        # Create background thread to search for Myo devices
        #
        self.myo_counts[index] = 0
        worker = MyoSearchWorker(port, progress, partial(self.devices_found,
                                                                            thread_idx = len(self.search_threads),
                                                                            port = port,
                                                                            myo_count_index = index), self.increments)
        self.search_threads.append(worker)
        QThreadPool.globalInstance().start(worker)

    def devices_found(self, thread_idx = None, port = None, myo_count_index = None):
        """
            After searching for devices (see serial_port_clicked) is complete, an event is emitted and this
                function is called.

        :param thread_idx: Index in list of threads
        :param port: Port used to find devices.
        :param myo_count_index: Index to list storing number of Myo devices found for a given port
        :return:
        """

        # Find index to insert found Myo results
        list_index = 0
        for i in range(myo_count_index):
            list_index += 1
            list_index += self.myo_counts[i]

        # For each myo found
        for i, device in enumerate(self.search_threads[thread_idx].myo_found):

            temp_widget = QListWidgetItem()
            temp_widget.setBackground(Qt.gray)

            #
            # Holds relevant information about Myo found, and reacts to user actions
            #
            widget = MyoFoundWidget(port, device, self.connection_made, self.connection_dropped)

            # Add to list of Myo dongles and devices found
            temp_widget.setSizeHint(widget.sizeHint())
            self.ports_found.insertItem(list_index + i + 1, temp_widget)
            self.ports_found.setItemWidget(temp_widget, widget)
            self.myo_counts[myo_count_index] += 1

    def connection_dropped(self, address):
        """
                Prior to disconnecting from a Myo device, this function is called to ensure a disconnect is valid.
        :param address: Address of Myo device.
        :return: None
        """

        def throw_error_message(self, message):
            self.warning = QErrorMessage()
            self.warning.showMessage(message)
            self.warning.show()
            return None

        if self.first_myo is None:

            if (self.second_myo != None) and (self.second_myo == address):
                self.second_myo = None
                self.second_port = None
                self.top_tab.removeTab(0)

                # Old backend:
                # for i in range(len(self.myo_1_charts)):
                #    self.myo_2_charts[i].chart().removeAllSeries()
            else:
                return throw_error_message(self, "An unexpected error has occured.")

        else:
            if self.first_myo == address:
                self.first_myo = None
                self.first_port = None
                self.top_tab.removeTab(0)

                # Old backend:
                #for i in range(len(self.myo_1_charts)):
                #    self.myo_1_charts[i].chart().removeAllSeries()

            elif self.second_myo != None:
                if (self.second_myo != None) and (self.second_myo == address):
                    self.second_myo = None
                    self.second_port = None
                    self.top_tab.removeTab(1)

                    # Old backend:
                    #for i in range(len(self.myo_1_charts)):
                    #    self.myo_2_charts[i].chart().removeAllSeries()
                else:
                    return throw_error_message(self, "An unexpected error has occured.")

    def connection_made(self, address, port):
        """
            Prior to connecting to a Myo device, this function is called to ensure a connection can be made.
        :param address: Address of Myo device.
        :param port: Communication port to be used for connection.
        :return: (index, charts, myo_data)

            Where:
                index: Refers to index of channel tab open
                charts: Refers to one of two chart objects that should be filled with EMG data visualizations
                myo_data: Refers to a list that should be filled with incoming EMG/IMU data
        """

        def throw_error_message(self, message):
            self.warning = QErrorMessage()
            self.warning.showMessage(message)
            self.warning.show()
            return None

        if self.first_myo is None:

            if self.second_myo != None:

                if self.second_myo == address:
                    return throw_error_message(self, "The device you attempted to connect to is already connected.")
                elif port == self.second_port:
                    return throw_error_message(self, "The device you attempted to connect to, requires a port that"
                                             " is already in use.")

            self.first_myo  = address
            self.first_port = port
            self.top_tab.addTab(self.myo_1_tab, "Myo Device 1")

            return (self.top_tab.currentIndex, None, self.myo_1_tab.currentIndex, self.myo_1_charts, self.first_myo_data)

        else:
            if self.second_myo != None:
                return throw_error_message(self, "This GUI only currently supports up to two Myo devices.")
            elif self.first_myo == address:
                return throw_error_message(self, "The device you attempted to connect to is already connected.")
            elif port == self.first_port:
                return throw_error_message(self, "The device you attempted to connect to, requires a port that"
                                           " is already in use.")
            else:
                self.second_myo     = address
                self.second_port    = port

                self.top_tab.addTab(self.myo_2_tab, "Myo Device 2")

                return (self.top_tab.currentIndex, self.first_myo, self.myo_2_tab.currentIndex, self.myo_2_charts, self.second_myo_data)


if __name__ == '__main__':
    gui         = QApplication(sys.argv)
    top         = TopLevel()

    # Event loop
    sys.exit(gui.exec_())