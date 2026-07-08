import fnmatch
import io
import os
import queue
import shutil
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from zipfile import PyZipFile

try:
    from decompyle3 import decompile_file as decompile3
except Exception as exc:
    decompile3 = None
    decompile3_error = exc
else:
    decompile3_error = None

try:
    from uncompyle6.main import decompile_file as decompile6
except Exception as exc:
    decompile6 = None
    decompile6_error = exc
else:
    decompile6_error = None


def decompile_pyc_file(path):
    os.environ["SIMS_DECOMPILER_CHILD"] = "1"
    source_path = os.path.abspath(path)
    output_path = source_path.replace(".pyc", ".py")

    def write_output(content):
        tmp_path = f"{output_path}.tmp"
        with io.open(tmp_path, "w", encoding="utf-8") as output_file:
            output_file.write(content)
        os.replace(tmp_path, output_path)

    placeholder = (
        f"# Decompilation in progress for {os.path.basename(output_path)}\n"
        "# The decompiler is still working on this file.\n"
    )
    write_output(placeholder)

    failure_reason = "decompilation backend could not recover this bytecode file"

    try:
        from decompyle3 import decompile_file as decompile3
    except Exception as exc:
        decompile3 = None
        failure_reason = f"decompyle3 import failed: {exc}"

    try:
        from uncompyle6.main import decompile_file as decompile6
    except Exception as exc:
        decompile6 = None
        if decompile3 is None:
            failure_reason = f"uncompyle6 import failed: {exc}"

    try:
        if decompile3 is not None:
            temp_path = f"{output_path}.tmp"
            with io.open(temp_path, "w", encoding="utf-8") as out_stream:
                decompile3(source_path, outstream=out_stream)
            with io.open(temp_path, "r", encoding="utf-8") as current_output:
                decompiled = current_output.read().strip()
            if decompiled and "__decompilation_failed__" not in decompiled:
                os.replace(temp_path, output_path)
                return output_path
            if os.path.exists(temp_path):
                os.remove(temp_path)

        if decompile6 is not None and failure_reason != "decompilation backend could not recover this bytecode file":
            temp_path = f"{output_path}.tmp"
            with io.open(temp_path, "w", encoding="utf-8") as out_stream:
                decompile6(source_path, outstream=out_stream)
            with io.open(temp_path, "r", encoding="utf-8") as current_output:
                decompiled = current_output.read().strip()
            if decompiled and "__decompilation_failed__" not in decompiled:
                os.replace(temp_path, output_path)
                return output_path
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except Exception as exc:
        failure_reason = f"decompiler error: {exc}"

    fallback_source = (
        f"# Automatic fallback for {os.path.basename(source_path)}\n"
        f"# Reason: {failure_reason}.\n"
        "\n"
        "def __decompilation_failed__():\n"
        "    raise NotImplementedError('Automatic decompilation was not possible for this bytecode file.')\n"
    )
    write_output(fallback_source)
    return output_path


class DecompileProgress:
    def __init__(self, callback=None):
        self.callback = callback
        self.total_files = 0
        self.completed_files = 0
        self._lock = threading.RLock()

    def emit(self, message):
        if self.callback:
            self.callback(message)

    def update(self, completed=None, total=None):
        with self._lock:
            if completed is not None:
                self.completed_files = completed
            if total is not None:
                self.total_files = total
            completed_files = self.completed_files
            total_files = self.total_files
        if self.callback:
            self.callback({"type": "progress", "completed": completed_files, "total": total_files})


class SimsDecompiler:
    def __init__(self):
        self.delay_time = 2.0
        self.ea_folder = os.path.abspath("EA")
        self.gameplay_folder_data = ""
        self.gameplay_folder_game = ""
        self.script_package_types = ["*.zip", "*.ts4script"]
        self.q = queue.Queue()
        self.progress = DecompileProgress()
        self.progress_lock = threading.Lock()

        os.makedirs(self.ea_folder, exist_ok=True)

    def _mark_completed(self):
        with self.progress_lock:
            self.progress.completed_files += 1
            completed = self.progress.completed_files
            total = self.progress.total_files
        self.progress.update(completed, total)

    def _write_output(self, output_path, content):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        tmp_path = f"{output_path}.tmp"
        with io.open(tmp_path, "w", encoding="utf-8") as output_file:
            output_file.write(content)
        os.replace(tmp_path, output_path)

    def _write_placeholder(self, output_path):
        placeholder = (
            f"# Decompilation in progress for {os.path.basename(output_path)}\n"
            "# The decompiler is still working on this file.\n"
        )
        self._write_output(output_path, placeholder)

    def decompile_dir(self, p):
        self.progress.emit(f"Decompiling {os.path.basename(p)}")
        try:
            relative_path = os.path.relpath(p, self.ea_folder)
        except ValueError:
            relative_path = os.path.basename(p)
        output_path = os.path.join(self.ea_folder, relative_path.replace(".pyc", ".py"))
        self._write_placeholder(output_path)
        failure_reason = "decompilation backend could not recover this bytecode file"
        if decompile3_error is not None:
            failure_reason = f"decompyle3 import failed: {decompile3_error}"
        if decompile6_error is not None and decompile3_error is None:
            failure_reason = f"uncompyle6 import failed: {decompile6_error}"

        try:
            decompiled = None
            if decompile3 is not None:
                try:
                    temp_path = f"{output_path}.tmp"
                    with io.open(temp_path, "w", encoding="utf-8") as out_stream:
                        decompile3(p, outstream=out_stream)
                    with io.open(temp_path, "r", encoding="utf-8") as current_output:
                        decompiled = current_output.read().strip()
                    if decompiled and "__decompilation_failed__" not in decompiled:
                        os.replace(temp_path, output_path)
                        self._mark_completed()
                        return
                    failure_reason = "decompyle3 produced no usable source"
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception as exc:
                    failure_reason = f"decompyle3 failed: {exc}"
                    self.progress.emit(f"decompyle3 failed for {os.path.basename(p)}: {exc}")

            if decompile6 is not None and failure_reason != "decompilation backend could not recover this bytecode file":
                try:
                    temp_path = f"{output_path}.tmp"
                    with io.open(temp_path, "w", encoding="utf-8") as out_stream:
                        decompile6(p, outstream=out_stream)
                    with io.open(temp_path, "r", encoding="utf-8") as current_output:
                        decompiled = current_output.read().strip()
                    if decompiled and "__decompilation_failed__" not in decompiled:
                        os.replace(temp_path, output_path)
                        self._mark_completed()
                        return
                    failure_reason = "uncompyle6 produced no usable source"
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception as exc:
                    failure_reason = f"uncompyle6 failed: {exc}"
                    self.progress.emit(f"uncompyle6 failed for {os.path.basename(p)}: {exc}")
        except Exception as exc:
            failure_reason = f"decompiler error: {exc}"
            self.progress.emit(f"Unexpected decompiler error for {os.path.basename(p)}: {exc}")

        self._mark_completed()

        fallback_source = (
            f"# Automatic fallback for {os.path.basename(p)}\n"
            f"# Reason: {failure_reason}.\n"
            "\n"
            "def __decompilation_failed__():\n"
            "    raise NotImplementedError('Automatic decompilation was not possible for this bytecode file.')\n"
        )
        self._write_output(output_path, fallback_source)

    def fill_queue(self, curr_folder):
        if not curr_folder or not os.path.isdir(curr_folder):
            return

        self.progress.emit(f"Scanning {curr_folder}")
        for root, dirs, files in os.walk(curr_folder):
            for ext_filter in self.script_package_types:
                for filename in fnmatch.filter(files, ext_filter):
                    src = os.path.join(root, filename)
                    dst = os.path.join(self.ea_folder, filename)
                    os.makedirs(self.ea_folder, exist_ok=True)

                    try:
                        if src != dst:
                            shutil.copyfile(src, dst)

                        if filename.lower().endswith(".zip") or filename.lower().endswith(".ts4script"):
                            with PyZipFile(dst) as zip_file:
                                out_folder = os.path.join(self.ea_folder, os.path.splitext(filename)[0])
                                os.makedirs(out_folder, exist_ok=True)
                                zip_file.extractall(out_folder)
                            self.q.put(out_folder)
                        else:
                            self.q.put(os.path.dirname(src))
                    except Exception as exc:
                        print(f"Failed to unpack {src}: {exc}")

    def worker(self, target_folder):
        pattern = "*.pyc"
        pyc_files = []
        for root, _, files in os.walk(target_folder):
            for pyc_name in fnmatch.filter(files, pattern):
                pyc_files.append(str(os.path.join(root, pyc_name)))

        if not pyc_files:
            return

        cpu_count = max(1, (os.cpu_count() or 4))
        max_workers = 4 if getattr(sys, "frozen", False) else min(6, cpu_count)
        if getattr(sys, "frozen", False):
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self.decompile_dir, f): f for f in pyc_files}
                for future in as_completed(futures):
                    pass  # decompile_dir already calls _mark_completed internally
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(decompile_pyc_file, f): f for f in pyc_files}
                for future in as_completed(futures):
                    self._mark_completed()

    def run_decompile_all(self, game_folder):
        self.ea_folder = os.path.abspath(self.ea_folder)
        os.makedirs(self.ea_folder, exist_ok=True)
        self.q = queue.Queue()

        self.gameplay_folder_data = os.path.join(game_folder, "Data", "Simulation", "Gameplay")
        self.gameplay_folder_game = os.path.join(game_folder, "Game", "Bin", "Python")

        self.progress.completed_files = 0
        self.progress.total_files = 0
        self.progress.emit("Preparing extracted script folders...")
        self.fill_queue(self.gameplay_folder_data)
        self.fill_queue(self.gameplay_folder_game)

        discovered_folders = []
        while not self.q.empty():
            discovered_folders.append(self.q.get())

        self.progress.total_files = sum(
            sum(
                1
                for _, _, files in os.walk(folder)
                for name in files
                if name.lower().endswith(".pyc")
            )
            for folder in discovered_folders
            if os.path.isdir(folder)
        )
        self.progress.update(self.progress.completed_files, self.progress.total_files)

        if not discovered_folders:
            raise FileNotFoundError("No script packages were found in the selected game folder.")

        for folder in discovered_folders:
            self.worker(folder)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: decompile_all_multi.py <pyc-file>")
    decompiler = SimsDecompiler()
    decompiler.progress.callback = print
    decompiler.decompile_dir(sys.argv[1])
    print(f"Wrote {sys.argv[1].replace('.pyc', '.py')}")