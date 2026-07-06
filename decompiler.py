import os
import sys
import time

from PyQt5 import QtCore, QtWidgets

import decompile_all_multi
import settings


class DecompileWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(str)

    def __init__(self, decompiler, game_folder):
        super().__init__()
        self.decompiler = decompiler
        self.game_folder = game_folder

    @QtCore.pyqtSlot()
    def run(self):
        try:
            self.progress.emit("Preparing extracted script folders...")
            if getattr(sys, "frozen", False):
                base_dir = os.path.dirname(os.path.abspath(sys.executable))
            else:
                base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            self.decompiler.ea_folder = os.path.join(base_dir, "EA")
            self.progress.emit(f"Output folder: {self.decompiler.ea_folder}")
            start_time = time.time()
            self.decompiler.run_decompile_all(self.game_folder)
            elapsed = time.time() - start_time
            self.finished.emit({
                "elapsed": elapsed,
                "output_folder": self.decompiler.ea_folder,
            })
        except Exception as exc:
            self.error.emit(str(exc))


class App(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.title = "Sims 4 Decompiler"
        self.left = 200
        self.top = 200
        self.width = 640
        self.height = 480

        self.curr_settings = settings.Settings()
        self.curr_decompiler = decompile_all_multi.SimsDecompiler()
        self.curr_decompiler.progress.callback = self.handle_progress
        self.worker_thread = None
        self.worker = None

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.game_folder_input = QtWidgets.QLineEdit(self.curr_settings.get_game_folder())
        self.game_folder_input.setReadOnly(True)

        form.addRow("Game folder", self.game_folder_input)
        layout.addLayout(form)

        button_row = QtWidgets.QHBoxLayout()
        self.browse_button = QtWidgets.QPushButton("Browse")
        self.browse_button.clicked.connect(self.choose_game_folder)
        button_row.addWidget(self.browse_button)

        self.run_button = QtWidgets.QPushButton("Run decompiler")
        self.run_button.clicked.connect(self.start_decompile)
        button_row.addWidget(self.run_button)
        layout.addLayout(button_row)

        self.status_label = QtWidgets.QLabel("Choose the game folder containing the Sims 4 install and click Run decompiler.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.current_file_label = QtWidgets.QLabel("Waiting to start")
        layout.addWidget(self.current_file_label)

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Decompile progress will appear here")
        layout.addWidget(self.log_box)

        self.setLayout(layout)
        self.show()

    def handle_progress(self, message):
        if self.thread() is not None and self.thread() is not QtCore.QThread.currentThread():
            QtCore.QMetaObject.invokeMethod(
                self,
                "_apply_progress",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(object, message),
            )
            return
        self._apply_progress(message)

    @QtCore.pyqtSlot(object)
    def _apply_progress(self, message):
        if isinstance(message, dict):
            total = message.get("total", 0)
            completed = message.get("completed", 0)
            self.progress_bar.setMaximum(max(1, total))
            self.progress_bar.setValue(completed)
            self.current_file_label.setText(
                f"{completed}/{total} files processed"
                if total else f"{completed} files processed"
            )
            return
        self.log_box.appendPlainText(str(message))
        self.current_file_label.setText(str(message))

    def log(self, message):
        self._apply_progress(message)

    def choose_game_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select the Sims 4 install folder")
        if not folder:
            return

        self.curr_settings.set_game_folder(folder)
        self.game_folder_input.setText(folder)
        self.log(f"Selected game folder: {folder}")

    def start_decompile(self):
        if not self.curr_settings.get_game_folder():
            QtWidgets.QMessageBox.warning(self, "Missing folder", "Please choose the Sims 4 install folder first.")
            return

        self.run_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Decompiling Sims 4 scripts. This can take a while...")
        self.log_box.clear()
        self.curr_decompiler.progress.callback = self.handle_progress
        self.log(f"Using game folder: {self.curr_settings.get_game_folder()}")
        self.log("Starting decompiler...")

        self.worker_thread = QtCore.QThread(self)
        self.worker = DecompileWorker(self.curr_decompiler, self.curr_settings.get_game_folder())
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_decompile_finished)
        self.worker.error.connect(self.on_decompile_error)
        self.worker.progress.connect(self.log)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def on_decompile_finished(self, result):
        self.progress_bar.setMaximum(max(1, 100))
        self.progress_bar.setValue(100)
        self.status_label.setText(
            f"Finished in {result['elapsed']:.1f}s. Output folder: {result['output_folder']}"
        )
        self.log(f"Finished in {result['elapsed']:.1f}s")
        self.log(f"Output written to {result['output_folder']}")
        self.run_button.setEnabled(True)
        self.browse_button.setEnabled(True)

    def on_decompile_error(self, message):
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Decompilation failed")
        self.log(f"Error: {message}")
        QtWidgets.QMessageBox.critical(self, "Decompilation failed", message)
        self.run_button.setEnabled(True)
        self.browse_button.setEnabled(True)


def main():
    if os.environ.get("SIMS_DECOMPILER_CHILD") == "1":
        return 0

    if len(sys.argv) > 1 and sys.argv[1].endswith(".pyc"):
        decompiler = decompile_all_multi.SimsDecompiler()
        decompiler.progress.callback = print
        decompiler.decompile_dir(sys.argv[1])
        return 0

    app = QtWidgets.QApplication(sys.argv)
    ex = App()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())