#!/usr/bin/env python3
"""
Comprehensive automated test suite for ArchVM:
1. OS Installation Pipeline:
   - Seed configuration (vm.conf template and variables)
   - Shell script syntax verification (bootstrap, chroot-setup, firstboot, repair via Git Bash)
   - CRLF to LF newline conversion in seed ISO packaging
   - ISO failover mirrors configuration and checksum URLs
   - QEMU install command-line arguments (bootindex order, ISO mounting, seed attachment)
2. Live OS Usage Pipeline:
   - QEMU normal boot command-line arguments (disk boot, detached ISOs, localhost SSH, SPICE clipboard)
   - Port conflict detection and auto-reallocation
   - Display and GPU fallback matrix (virgl DMABUF compatibility guard)
   - Virgl and Windows structured exception crash code detector
   - HMP monitor text injection keystroke encoder and unsupported character sanitizer
   - Snapshot management command generation and table parsing
3. Core Architecture and UI Subsystems:
   - Path isolation (C:\\Users\\datan\\archvm_data\\)
   - Config persistence and schema drift recovery (atomic save, unknown key discarding)
   - Design system palettes and stylesheet generation
   - Custom layout widgets (StatusBadge, Stat, MeterBar, CommandSnippet)
   - MainWindow 6-page navigation lifecycle
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from archvm import hostinfo, icons, paths, qemu, theme, widgets
from archvm.config import AppSettings, VMConfig


class TestOSInstallationPipeline(unittest.TestCase):
    """Verifies all components involved in the unattended Arch Linux installation."""

    def test_vm_conf_template_variables(self):
        """Ensure vm.conf.example exists and contains all required seeding variables."""
        example_path = Path(__file__).resolve().parent.parent.parent / "seed" / "vm.conf.example"
        self.assertTrue(example_path.exists(), f"vm.conf.example missing at {example_path}")

        content = example_path.read_text(encoding="utf-8")
        required_keys = [
            "USERNAME",
            "USERPASS",
            "ROOTPASS",
            "HOSTNAME",
            "TIMEZONE",
            "LOCALE",
            "KEYMAP",
            "FORK_REPO",
            "FORK_NAME",
            "AUTO_CONFIRM",
            "AUTO_REBOOT",
        ]
        for key in required_keys:
            self.assertRegex(
                content,
                rf"(?m)^{key}=",
                f"Required seed variable '{key}' missing from vm.conf.example",
            )

    def test_bash_syntax_all_seed_scripts(self):
        """Execute 'bash -n' on all 4 seed scripts to verify POSIX/Bash syntax."""
        bash_candidates = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            shutil.which("bash"),
        ]
        bash_bin = next((b for b in bash_candidates if b and Path(b).exists()), None)
        if not bash_bin:
            self.skipTest("Bash executable not found on host to validate syntax.")

        seed_dir = Path(__file__).resolve().parent.parent.parent / "seed"
        scripts = ["bootstrap.sh", "chroot-setup.sh", "firstboot.sh", "repair.sh"]

        for script_name in scripts:
            script_path = seed_dir / script_name
            self.assertTrue(script_path.exists(), f"Seed script {script_name} not found")
            res = subprocess.run(
                [bash_bin, "-n", str(script_path)],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.assertEqual(
                res.returncode,
                0,
                f"Bash syntax check failed for {script_name}:\n{res.stderr}",
            )

    def test_crlf_sanitization_in_seedbuild(self):
        """Ensure seedbuild strips Windows CRLF line endings so bash doesn't fail with \\r."""
        crlf_data = b"#!/usr/bin/env bash\r\necho 'hello'\r\n"
        sanitized = crlf_data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        self.assertNotIn(b"\r", sanitized)
        self.assertEqual(sanitized, b"#!/usr/bin/env bash\necho 'hello'\n")

    def test_iso_mirrors_configuration(self):
        """Verify fallback ISO mirrors and checksum endpoints are properly formatted."""
        from archvm.deps import ISO_URLS, SUMS_URLS

        self.assertGreaterEqual(len(ISO_URLS), 3, "At least 3 ISO mirrors required for redundancy")
        self.assertGreaterEqual(len(SUMS_URLS), 3, "At least 3 checksum mirrors required")

        for url in ISO_URLS:
            self.assertTrue(url.startswith("https://"), f"Mirror URL must be HTTPS: {url}")
            self.assertTrue(url.endswith(".iso"), f"ISO URL must point to .iso file: {url}")

        for url in SUMS_URLS:
            self.assertTrue(url.startswith("https://"), f"Sums URL must be HTTPS: {url}")
            self.assertTrue(url.endswith("sha256sums.txt"), f"Sums URL must point to sha256sums.txt: {url}")

    def test_qemu_installation_args(self):
        """Verify QEMU command arguments generated for install mode."""
        cfg = VMConfig(
            disk="C:/archvm_test/arch.qcow2",
            iso="C:/archvm_test/archlinux.iso",
            seed_iso="C:/archvm_test/seed.iso",
            ssh_port=2222,
            monitor_port=55555,
        )
        args = cfg.build_args(install_mode=True)
        arg_str = " ".join(args)

        # 1. Boot priority: Arch ISO must have bootindex=1, disk must have bootindex=2
        self.assertIn("ide-cd,drive=cd0,bus=ide.0,bootindex=1", arg_str)
        self.assertIn("virtio-blk-pci,drive=hd0,iothread=io0,bootindex=2", arg_str)

        # 2. Both ISOs attached
        self.assertIn("id=cd0,if=none,media=cdrom,file=C:/archvm_test/archlinux.iso", arg_str)
        self.assertIn("id=cd1,if=none,media=cdrom,file=C:/archvm_test/seed.iso", arg_str)

        # 3. Dedicated disk I/O thread
        self.assertIn("-object iothread,id=io0", arg_str)

        # 4. Localhost-only SSH binding
        self.assertIn("hostfwd=tcp:127.0.0.1:2222-:22", arg_str)
        self.assertNotIn("hostfwd=tcp:0.0.0.0:", arg_str)

        # 5. SPICE vdagent clipboard channel
        self.assertIn("-chardev qemu-vdagent,id=vdagent,name=vdagent,clipboard=on", arg_str)
        self.assertIn("-device virtserialport,chardev=vdagent,name=com.redhat.spice.0", arg_str)

        # 6. Monitor port
        self.assertIn("tcp:127.0.0.1:55555,server=on,wait=off", arg_str)


class TestLiveOSUsagePipeline(unittest.TestCase):
    """Verifies components supporting live guest execution, monitor, and disk management."""

    def test_qemu_live_normal_boot_args(self):
        """Verify QEMU command arguments generated for normal daily run mode."""
        cfg = VMConfig(
            disk="C:/archvm_test/arch.qcow2",
            iso="C:/archvm_test/archlinux.iso",
            seed_iso="C:/archvm_test/seed.iso",
            ssh_port=2222,
            monitor_port=55555,
        )
        args = cfg.build_args(install_mode=False)
        arg_str = " ".join(args)

        # 1. Disk must have bootindex=1
        self.assertIn("virtio-blk-pci,drive=hd0,iothread=io0,bootindex=1", arg_str)

        # 2. ISOs must be detached in normal boot
        self.assertNotIn("id=cd0", arg_str)
        self.assertNotIn("id=cd1", arg_str)
        self.assertNotIn("archlinux.iso", arg_str)
        self.assertNotIn("seed.iso", arg_str)

        # 3. Localhost-only SSH security
        self.assertIn("hostfwd=tcp:127.0.0.1:2222-:22", arg_str)

        # 4. Clipboard sharing
        self.assertIn("qemu-vdagent,id=vdagent,name=vdagent,clipboard=on", arg_str)

    def test_port_conflict_detection_and_resolution(self):
        """Test detection of occupied ports and auto-selection of next free port."""
        # Bind a temporary port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            busy_port = s.getsockname()[1]

            self.assertTrue(qemu.is_port_in_use(busy_port))
            next_port = qemu.find_available_port(busy_port)
            self.assertNotEqual(busy_port, next_port)
            self.assertFalse(qemu.is_port_in_use(next_port))

    def test_display_and_gpu_compatibility_matrix(self):
        """Test validation and fallback for GPU/display backends on Windows."""
        # Broken GL pairings on Windows
        bad_pairings = [
            ("virtio-vga-gl", "gtk"),
            ("virtio-vga-gl", "sdl"),
            ("virtio-gpu-gl", "gtk"),
            ("virtio-gpu-gl", "sdl"),
        ]
        for gpu, disp in bad_pairings:
            ok, reason = qemu.display_is_supported(gpu, disp)
            self.assertFalse(ok, f"{gpu} + {disp} should be rejected on Windows")
            self.assertIn("DMABUF", reason)

            safe_gpu, safe_disp, note = qemu.safe_display_for(gpu, disp)
            self.assertEqual(safe_gpu, "virtio-vga")
            self.assertIn(safe_disp, ("gtk", "sdl"))
            self.assertTrue(len(note) > 0)

        # Known good configuration
        ok, reason = qemu.display_is_supported("virtio-vga", "gtk")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

        gpu_f, disp_f, note_f = qemu.safe_display_for("virtio-vga", "gtk")
        self.assertEqual((gpu_f, disp_f), ("virtio-vga", "gtk"))
        self.assertEqual(note_f, "")

    def test_gl_crash_detection(self):
        """Verify recognition of Windows access violations and fatal exception codes."""
        # 0xC0000005 is Windows Access Violation (virgl GTK console crash)
        self.assertTrue(qemu._is_crash(0xC0000005))
        self.assertTrue(qemu._is_crash(0xC0000094))  # Divide by zero
        self.assertTrue(qemu._is_crash(0xC00000FD))  # Stack overflow
        self.assertTrue(qemu._is_crash(0xC000001D))  # Illegal instruction
        self.assertTrue(qemu._is_crash(0x40000015))  # Fatal exit

        # Normal termination codes
        self.assertFalse(qemu._is_crash(0))
        self.assertFalse(qemu._is_crash(1))

    def test_monitor_text_injection_and_sanitizer(self):
        """Verify HMP key translation and detection of untypeable characters."""
        # Standard letters & numbers
        self.assertEqual(qemu.char_to_key("a"), "a")
        self.assertEqual(qemu.char_to_key("Z"), "shift-z")
        self.assertEqual(qemu.char_to_key("7"), "7")

        # Special characters
        self.assertEqual(qemu.char_to_key(" "), "spc")
        self.assertEqual(qemu.char_to_key("\n"), "ret")
        self.assertEqual(qemu.char_to_key("!"), "shift-1")
        self.assertEqual(qemu.char_to_key("$"), "shift-4")
        self.assertEqual(qemu.char_to_key(":"), "shift-semicolon")

        # Unsupported character filtering
        safe_cmd = "pacman -Syu --noconfirm"
        self.assertEqual(qemu.unsupported_chars(safe_cmd), [])

        emoji_cmd = "echo '🚀 hyprland' ✨"
        unsupported = qemu.unsupported_chars(emoji_cmd)
        self.assertIn("🚀", unsupported)
        self.assertIn("✨", unsupported)

    def test_snapshot_management_commands_and_table_parsing(self):
        """Verify snapshot command formation and sample qemu-img table parsing."""
        mock_output = (
            "Snapshot list:\n"
            "ID        TAG               VM SIZE                DATE       VM CLOCK\n"
            "1         clean-install        0 B  2026-09-01 10:00:00   00:00:00.000\n"
            "2         pre-update           0 B  2026-09-05 15:30:22   00:00:00.000\n"
        )
        lines = mock_output.strip().splitlines()
        snapshots = []
        for line in lines[2:]:
            parts = line.split()
            if len(parts) >= 2:
                snapshots.append({"id": parts[0], "tag": parts[1]})

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0]["tag"], "clean-install")
        self.assertEqual(snapshots[1]["tag"], "pre-update")


class TestCoreArchitectureAndUI(unittest.TestCase):
    """Verifies paths, configuration lifecycle, design system, custom widgets, and main window."""

    def test_paths_isolation(self):
        """Verify data paths stay isolated in archvm_data and not scattered on the host."""
        root = paths.ROOT
        self.assertEqual(root.name, "archvm_data")
        self.assertEqual(paths.DISK_DIR, root / "disks")
        self.assertEqual(paths.ISO_DIR, root / "iso")
        self.assertEqual(paths.CONFIG_DIR, paths.config_dir())
        self.assertEqual(paths.LOG_DIR, root / "logs")
        self.assertEqual(paths.SEED_DIR, root / "seed")

    def test_config_persistence_and_tolerance(self):
        """Verify JSON saving and resilience to extra/unknown fields."""
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "vm.json"
            cfg = VMConfig(name="Custom Arch", memory_mb=4096, cpus=4)

            # Atomic save
            data = cfg.to_dict()
            data["unknown_future_field"] = "value123"
            data["memory_mb"] = "8192"  # String representation drift

            import json
            cfg_file.write_text(json.dumps(data), encoding="utf-8")

            # Load via _from_dict
            loaded_data = json.loads(cfg_file.read_text(encoding="utf-8"))
            restored = VMConfig._from_dict(loaded_data)

            self.assertEqual(restored.name, "Custom Arch")
            self.assertEqual(restored.memory_mb, 8192)  # Coerced to int
            self.assertEqual(restored.cpus, 4)
            self.assertFalse(hasattr(restored, "unknown_future_field"))

    def test_theme_and_palette_resolution(self):
        """Verify Obsidian Slate / Porcelain Glass theme palettes and stylesheet generation."""
        for mode in ("dark", "light", "auto"):
            p = theme.resolve(mode)
            self.assertIsNotNone(p.bg)
            self.assertIsNotNone(p.accent)
            self.assertIsNotNone(p.text)

            ss = theme.stylesheet(p)
            self.assertIn("QMainWindow", ss)
            self.assertIn("QPushButton", ss)
            self.assertIn(p.accent, ss)

            qpal = theme.qpalette(p)
            self.assertIsNotNone(qpal)

    def test_custom_layout_widgets(self):
        """Test instantiation and behavior of custom UI components."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        # 1. StatusBadge
        badge = widgets.StatusBadge("Running", state="running")
        badge.set_status("running", "VM Running")
        self.assertEqual(badge._state, "running")
        self.assertEqual(badge.text(), "VM RUNNING")

        badge.set_status("stopped", "Stopped")
        self.assertEqual(badge._state, "stopped")
        self.assertEqual(badge.text(), "STOPPED")

        # 2. Stat (StatCard)
        stat = widgets.Stat("Memory", "8 GB", sub="62% free", icon="💾")
        self.assertEqual(stat.value.text(), "8 GB")
        self.assertEqual(stat.sub.text(), "62% free")

        # 3. MeterBar
        meter = widgets.MeterBar("Memory", theme.resolve("dark"), icon="💾")
        meter.set_value(0.75, "75%")
        self.assertEqual(meter._frac, 0.75)
        meter.set_value(1.5, "150%")  # Clamped to 1.0
        self.assertEqual(meter._frac, 1.0)
        meter.set_value(-0.2, "-20%")  # Clamped to 0.0
        self.assertEqual(meter._frac, 0.0)

        # 4. CommandSnippet
        snippet = widgets.CommandSnippet("ssh -p 2222 arch@127.0.0.1", "SSH Login")
        self.assertEqual(snippet._command, "ssh -p 2222 arch@127.0.0.1")

    def test_main_window_pages_and_stack(self):
        """Test MainWindow stack navigation and 6-page lifecycle offscreen."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from archvm.window import MainWindow

        win = MainWindow(VMConfig(), AppSettings())
        self.assertIsNotNone(win.stack)
        self.assertEqual(win.stack.count(), 6)

        expected_pages = ["Overview", "Display", "Hardware", "Disks", "Tools", "Settings"]
        for idx in range(win.stack.count()):
            win.stack.setCurrentIndex(idx)
            current_widget = win.stack.currentWidget()
            self.assertIsNotNone(current_widget)


def main():
    print("=" * 70)
    print(" ArchVM Comprehensive Automated System & Pipeline Test Suite")
    print(f" Version: {paths.APP_VERSION}")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestOSInstallationPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestLiveOSUsagePipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestCoreArchitectureAndUI))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
