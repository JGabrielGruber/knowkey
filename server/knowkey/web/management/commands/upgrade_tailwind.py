import platform
import stat
import sys
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Downloads the latest Tailwind CSS standalone CLI + daisyUI plugin files"

    # Mapping: (system, machine) → filename on GitHub
    TAILWIND_PLATFORMS = {
        ("Linux", "x86_64"): "tailwindcss-linux-x64",
        ("Linux", "aarch64"): "tailwindcss-linux-arm64",
        ("Linux", "arm64"): "tailwindcss-linux-arm64",  # some systems report arm64
        ("Darwin", "x86_64"): "tailwindcss-macos-x64",
        ("Darwin", "arm64"): "tailwindcss-macos-arm64",
        ("Windows", "AMD64"): "tailwindcss-windows-x64.exe",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download even if files already exist",
        )

    def handle(self, *args, **options):
        force = options["force"]

        base_dir = settings.BASE_DIR / "knowkey" / "web"
        bin_dir = base_dir / "bin"
        plugins_dir = base_dir / "src" / "plugins"

        bin_dir.mkdir(parents=True, exist_ok=True)
        plugins_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------
        # 1. Download Tailwind CSS standalone CLI
        # ------------------------------------------------------------------
        system = platform.system()
        machine = platform.machine()

        # Normalize some machine names
        if system == "Linux" and machine == "AMD64":
            machine = "x86_64"
        if system == "Darwin" and machine == "arm64":
            machine = "arm64"  # already correct

        key = (system, machine)
        if key not in self.TAILWIND_PLATFORMS:
            self.stdout.write(
                self.style.ERROR(
                    f"Unsupported platform: {system} {machine}\n"
                    "Please download the Tailwind binary manually."
                )
            )
            sys.exit(1)

        filename = self.TAILWIND_PLATFORMS[key]
        is_windows = system == "Windows"
        binary_name = "tailwindcss.exe" if is_windows else "tailwindcss"
        binary_path = bin_dir / binary_name

        tailwind_url = f"https://github.com/tailwindlabs/tailwindcss/releases/latest/download/{filename}"
        if is_windows:
            tailwind_url += ".exe"

        if not force and binary_path.exists():
            self.stdout.write(
                self.style.WARNING(f"Tailwind binary already exists: {binary_path}")
            )
        else:
            self.stdout.write(f"Downloading Tailwind CSS for {system} {machine} ...")
            self._download_file(tailwind_url, binary_path)

            # Make executable on Unix systems
            if not is_windows:
                binary_path.chmod(binary_path.stat().st_mode | stat.S_IEXEC)
            self.stdout.write(
                self.style.SUCCESS("Tailwind CSS binary downloaded and ready")
            )

        # ------------------------------------------------------------------
        # 2. Download daisyUI latest plugin files
        # ------------------------------------------------------------------
        daisy_files = [
            (
                "daisyui.mjs",
                "https://github.com/saadeghi/daisyui/releases/latest/download/daisyui.mjs",
            ),
            (
                "daisyui-theme.mjs",
                "https://github.com/saadeghi/daisyui/releases/latest/download/daisyui-theme.mjs",
            ),
        ]

        for name, url in daisy_files:
            dest = plugins_dir / name
            if not force and dest.exists():
                self.stdout.write(
                    self.style.WARNING(f"daisyUI file already exists: {dest}")
                )
                continue

            self.stdout.write(f"Downloading daisyUI {name} ...")
            self._download_file(url, dest)

        self.stdout.write(self.style.SUCCESS("daisyUI plugin files downloaded"))

        # ------------------------------------------------------------------
        # Final instructions
        # ------------------------------------------------------------------
        self.stdout.write(
            "\nAll set! Remember to reference daisyUI in your tailwind.config.js:"
        )
        self.stdout.write(self.style.SUCCESS("""
# knowkey/web/src/tailwind.config.js
module.exports = {
  content: [ ... ],
  plugins: [
    require("./plugins/daisyui.mjs"),          // <-- add this line
    // or if you prefer ESM: import daisyui from "./plugins/daisyui.mjs"
  ],
}
            """.strip()))

    def _download_file(self, url: str, dest: Path):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Failed to download {url}: {e}"))
            sys.exit(1)
