from __future__ import annotations

import tkinter as tk
from pathlib import Path


class ForgeControlApp:
    def __init__(self, root: Path, bootstrap_report: dict[str, object]) -> None:
        self.project_root = root
        self.bootstrap_report = bootstrap_report
        self.window = tk.Tk()
        self.window.title("ForgeOS Device Agent")
        self.window.geometry("920x560")

        header = tk.Label(
            self.window,
            text="ForgeOS Device Agent",
            font=("DejaVu Sans", 20, "bold"),
            anchor="w",
        )
        header.pack(fill="x", padx=20, pady=(20, 8))

        summary = tk.Label(
            self.window,
            text="Master-first Android assessment and build control environment",
            font=("DejaVu Sans", 11),
            anchor="w",
        )
        summary.pack(fill="x", padx=20)

        self.status_box = tk.Text(self.window, wrap="word", font=("DejaVu Sans Mono", 10))
        self.status_box.pack(fill="both", expand=True, padx=20, pady=20)
        self.status_box.insert("end", self._compose_status())
        self.status_box.configure(state="disabled")

    def _compose_status(self) -> str:
        details = self.bootstrap_report
        lines = [
            "Status: bootstrap complete",
            f"Project root: {self.project_root}",
            f"Workspace file: {details.get('workspace_file')}",
            f"Bootstrap report: {details.get('bootstrap_report')}",
            f"VS Code CLI available: {details.get('code_available')}",
            f"ADB available: {details.get('adb_available')}",
            f"Fastboot available: {details.get('fastboot_available')}",
            f"udev support present: {details.get('udev_present')}",
            "",
            "Watchers now monitor adb and fastboot visibility in the background.",
            "New device sessions are created under devices/ and start in ASSESS state.",
            "Destructive actions remain dry-run or blocked until policy and restore feasibility allow them.",
        ]
        return "\n".join(lines)

    def run(self) -> None:
        self.window.mainloop()
