import os
import sys
import time
import qdarkstyle
import subprocess
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QSpacerItem, QWidget, QComboBox, QMenu, QLabel, QLineEdit, QProgressBar, QHBoxLayout, QTableWidget, QTableWidgetItem, QSizePolicy, QGroupBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings

class DenoiseThread(QThread):
    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal()

    def __init__(self, input_file, output_file, denoise_strength):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.denoise_strength = denoise_strength

    def run(self):
        ffmpeg_cmd = "ffmpeg"
        ffprobe_cmd = "ffprobe"

        cmd = [
            ffprobe_cmd,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            self.input_file
        ]

        total_duration = float(subprocess.check_output(cmd, universal_newlines=True))

        cmd = [
            ffmpeg_cmd,
            "-hwaccel", "cuda",
            "-i", self.input_file,
            "-c:v", "h264_nvenc",
            "-b:v", "3M",
            "-vf", f"hqdn3d={self.denoise_strength}:1:2:3",
            "-c:a", "aac",
            "-y",
            self.output_file
        ]

        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, creationflags=subprocess.CREATE_NO_WINDOW)

        while True:
            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                time_info = output.strip().split("time=")
                if len(time_info) > 1:
                    time_str = time_info[1].split()[0]
                    current_time = sum(float(x) * 60 ** i for i, x in enumerate(reversed(time_str.split(":"))))
                    progress = int((current_time / total_duration) * 100)
                    self.progress_signal.emit(progress)

        self.completed_signal.emit()

    def closeEvent(self, event):
        # Check if the thread is running
        if hasattr(self, 'denoise_thread') and self.denoise_thread.isRunning():
            # Option 1: Wait for the thread to finish
            self.denoise_thread.wait()
            
            # Option 2: Terminate the thread (less recommended as it's forceful)
            # self.denoise_thread.terminate()
            # self.denoise_thread.wait()
            
        event.accept()




class CustomTitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)  # Set the height of the custom title bar

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a label for the custom title text
        self.title_label = QLabel('Video Denoiser')
        layout.addWidget(self.title_label)

        # Add a horizontal spacer to push buttons to the right
        horizontal_spacer = QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addItem(horizontal_spacer)

        # Create buttons for the custom minimize, maximize, and close buttons
        self.minimize_button = QPushButton('—')  # Minimize button
        self.minimize_button.setFixedWidth(40)  # Set the width of the minimize button
        self.minimize_button.clicked.connect(self.on_minimize_clicked)
        layout.addWidget(self.minimize_button)

        self.maximize_button = QPushButton('▢')  # Maximize button
        self.maximize_button.setFixedWidth(40)  # Set the width of the maximize button
        self.maximize_button.clicked.connect(self.on_maximize_clicked)
        layout.addWidget(self.maximize_button)

        self.close_button = QPushButton('✕')  # Close button
        self.close_button.setFixedWidth(40)  # Set the width of the close button
        self.close_button.clicked.connect(self.on_close_clicked)
        layout.addWidget(self.close_button)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Set the custom title bar stylesheet
        self.setStyleSheet("""
            QWidget {
                background-color: #44444;
                color: white;
                font-size: 14px;
                padding-left: 10px;
            }
          
            QPushButton {
                border: none;
                min-width: 40px; /* Set the minimum width for the buttons */
            }
        """)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def mousePressEvent(self, event):
        # Allow the user to drag the window when clicking on the custom title bar
        if event.buttons() == Qt.LeftButton:
            self.parent().drag_position = event.globalPos() - self.parent().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        # Allow the user to drag the window
        if event.buttons() == Qt.LeftButton:
            if hasattr(self.parent(), 'drag_position'):
                self.parent().move(event.globalPos() - self.parent().drag_position)
                event.accept()

    def on_minimize_clicked(self):
        self.parent().showMinimized()

    def on_maximize_clicked(self):
        if self.parent().isMaximized():
            self.parent().showNormal()
        else:
            self.parent().showMaximized()

    def on_close_clicked(self):
        self.parent().close()


class CustomTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super(CustomTableWidget, self).__init__(parent)

    def contextMenuEvent(self, event):
        context_menu = QMenu(self)
        
        # Option to clear the selected rows
        clear_selected_action = context_menu.addAction("Clear Selected Row")
        clear_selected_action.triggered.connect(self.clear_selected_rows)
        
        # Option to clear all rows
        clear_all_action = context_menu.addAction("Clear All Rows")
        clear_all_action.triggered.connect(self.clear_all_rows)
        
        context_menu.exec_(event.globalPos())

    def clear_selected_rows(self):
        selected_rows = set([index.row() for index in self.selectedIndexes()])
        for row in sorted(selected_rows, reverse=True):
            self.removeRow(row)

    def clear_all_rows(self):
        self.setRowCount(0)


class DenoiseApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.start_time = None
        self.video_selected = False  # Initialize the video_selected variable
        self.num_videos_to_denoise = 1  # Initialize the number of videos to denoise
        self.video_start_times = {}  # Add this line to initialize the dictionary

        # Load settings to remember the last input folder
        self.settings = QSettings("MyCompany", "DenoiseApp")
        self.input_folder = self.settings.value("input_folder", os.path.expanduser("~"))

    def initUI(self):
        self.setWindowTitle('Video Denoiser')
        self.setGeometry(100, 100, 1000, 500)
        # Hide the default title bar
        self.setWindowFlag(Qt.FramelessWindowHint)
      
        # Apply the dark style using qdarkstyle
        self.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

        # Create a custom title bar
        self.custom_title_bar = CustomTitleBar(self)
        self.setMenuWidget(self.custom_title_bar)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Group for Input and Denoise Controls
        input_denoise_group = QGroupBox("Input and Denoise Controls")
        input_denoise_layout = QVBoxLayout()

        file_layout = QHBoxLayout()
        self.input_label = QLabel('No video selected')
        self.select_button = QPushButton('Select Video')
        self.select_button.clicked.connect(self.select_video)
        file_layout.addWidget(self.input_label)
        file_layout.addWidget(self.select_button)
        input_denoise_layout.addLayout(file_layout)

        strength_layout = QHBoxLayout()
        self.strength_label = QLabel('Denoise Strength:')
        self.strength_input = QLineEdit()
        self.strength_input.setPlaceholderText('e.g., 3')
        strength_layout.addWidget(self.strength_label)
        strength_layout.addWidget(self.strength_input)
        input_denoise_layout.addLayout(strength_layout)

        # Add a QComboBox to select the number of videos to denoise
        self.num_videos_combo = QComboBox()
        self.num_videos_combo.addItems(['1', '2', '3', '4', '5'])
        self.num_videos_combo.setCurrentIndex(0)  # Set the default value to 1
        self.num_videos_combo.currentIndexChanged.connect(self.on_num_videos_changed)

        # Create a horizontal layout for the simultaneous denoise label and combo box
        simultaneous_denoise_layout = QHBoxLayout()
        self.simultaneous_label = QLabel("Simultaneous Denoise:")
        simultaneous_denoise_layout.addWidget(self.simultaneous_label)
        simultaneous_denoise_layout.addWidget(self.num_videos_combo)

        # Add the simultaneous denoise layout to the main layout
        input_denoise_layout.addLayout(simultaneous_denoise_layout)

        self.denoise_button = QPushButton('Start Denoising')
        self.denoise_button.clicked.connect(self.denoise_video)
        # self.denoise_button.setStyleSheet('background-color: #4CAF50; color: white;')
        input_denoise_layout.addWidget(self.denoise_button)

        input_denoise_group.setLayout(input_denoise_layout)
        main_layout.addWidget(input_denoise_group)

        # Group for Video Status Table
        table_group = QGroupBox("Video Status")
        table_layout = QVBoxLayout()

        self.table_widget = CustomTableWidget()
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(["Video File", "Elapsed Time", "Remaining Time", "Status"])
        table_layout.addWidget(self.table_widget)

        table_group.setLayout(table_layout)
        main_layout.addWidget(table_group)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        # central_widget.setStyleSheet('background-color: #F5F5F5;')
        self.setCentralWidget(central_widget)

        self.show()

    def on_num_videos_changed(self):
        # Update the number of videos to denoise based on the selected value in the QComboBox
        self.num_videos_to_denoise = int(self.num_videos_combo.currentText())

    def select_video(self):
        options = QFileDialog.Options()
        file_names, _ = QFileDialog.getOpenFileNames(
            self, "Select Files", self.input_folder,
            "Video Files (*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.flv;*.webm;*.mpeg;*.mpg;*.m4v;*.ts)", options=options
        )

        if file_names:
            self.input_folder = os.path.dirname(file_names[0])
            self.settings.setValue("input_folder", self.input_folder)
            self.video_files = file_names
            self.video_selected = True  # Add this line to indicate videos are selected

            self.table_widget.setRowCount(len(file_names))
            for i, file_name in enumerate(file_names):
                item = QTableWidgetItem(file_name)
                self.table_widget.setItem(i, 0, item)

                elapsed_time_item = QTableWidgetItem("--:--:--")
                self.table_widget.setItem(i, 1, elapsed_time_item)

                fps_item = QTableWidgetItem("--")
                self.table_widget.setItem(i, 2, fps_item)

    def add_video_to_table(self, file):
        row_count = self.table.rowCount()
        self.table.setRowCount(row_count + 1)

        filename_item = QTableWidgetItem(file)
        filename_item.setFlags(Qt.ItemIsEnabled)
        status_item = QTableWidgetItem("Pending")
        status_item.setFlags(Qt.ItemIsEnabled)

        self.table.setItem(row_count, 0, filename_item)
        self.table.setItem(row_count, 1, status_item)

    def denoise_video(self):
        if not self.video_selected:
            return            # Disable denoise button to prevent starting multiple denoise threads simultaneously
        
        self.denoise_button.setEnabled(False)
        self.active_threads = []  # List to keep track of active threads
        self.current_video_index = 0
        self.denoise_next_video()

    def denoise_next_video(self):
        if self.current_video_index >= len(self.video_files):
            # All videos have been denoised
            self.denoising_completed()
            return
            
        # Start threads based on the num_videos_to_denoise value
        for i in range(self.num_videos_to_denoise):
            if self.current_video_index >= len(self.video_files):
                return  # No more videos to process, return

            video_file = self.video_files[self.current_video_index]
            denoise_strength = self.strength_input.text() or "3"
            output_file = f"output_{os.path.splitext(os.path.basename(video_file))[0]}_denoised.mp4"
            self.video_start_times[self.current_video_index] = time.time()
            
            # Pass the current video index to the lambda functions to ensure they use the correct value
            current_index = self.current_video_index
            denoise_thread = DenoiseThread(video_file, output_file, denoise_strength)
            denoise_thread.progress_signal.connect(lambda progress, i=current_index: self.update_progress(i, progress))
            denoise_thread.completed_signal.connect(lambda i=current_index: self.denoising_completed(i))
            self.active_threads.append(denoise_thread)
            denoise_thread.start()
            self.current_video_index += 1  # Move to the next video in the list

    def update_progress(self, index, progress):
        self.table_widget.setItem(index, 3, QTableWidgetItem(f"Processing {progress}%"))
        
        # Calculate elapsed time
        elapsed_seconds = time.time() - self.video_start_times[index]
        elapsed_time = time.strftime('%H:%M:%S', time.gmtime(elapsed_seconds))

        if progress > 0:  # Add this check
            # Estimate total duration of the video using the progress and elapsed time
            total_duration = elapsed_seconds / (progress / 100)
            # Estimate remaining time
            remaining_seconds = total_duration - elapsed_seconds
            remaining_time = time.strftime('%H:%M:%S', time.gmtime(remaining_seconds))
            # Update the elapsed and remaining time in the table
            self.table_widget.setItem(index, 1, QTableWidgetItem(elapsed_time))
            self.table_widget.setItem(index, 2, QTableWidgetItem(remaining_time))
        else:
            # If progress is 0, simply set the elapsed time and indicate remaining time is unknown
            self.table_widget.setItem(index, 1, QTableWidgetItem(elapsed_time))
            self.table_widget.setItem(index, 2, QTableWidgetItem("--:--:--"))

    def denoising_completed(self, index):
        self.table_widget.setItem(index, 3, QTableWidgetItem("Completed"))

        # Remove the completed thread from the active_threads list
        self.active_threads = [thread for thread in self.active_threads if thread.isRunning()]

        # If more videos are left to process, start denoising them
        if self.current_video_index < len(self.video_files):
            self.denoise_next_video()

        # If all videos are processed, re-enable the denoise button
        if not self.active_threads and self.current_video_index >= len(self.video_files):
            self.denoise_button.setEnabled(True)
            self.video_selected = False

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = DenoiseApp()
    sys.exit(app.exec_())