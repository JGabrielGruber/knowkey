import os
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Builds Tailwind CSS using the binary in web/bin/ and outputs to static/web/css/output.css"

    def handle(self, *args, **options):
        app_dir = settings.BASE_DIR / "knowkey" / "web"
        tailwind_bin = app_dir / "bin" / "tailwindcss"
        input_css = app_dir / "src" / "css" / "input.css"
        output_css = app_dir / "static" / "web" / "css" / "output.css"
        config_file = app_dir / "src" / "tailwind.config.js"

        # Ensure output directory exists
        os.makedirs(output_css.parent, exist_ok=True)

        # Ensure the Tailwind binary is executable
        if tailwind_bin.exists():
            os.chmod(tailwind_bin, 0o755)
        else:
            self.stdout.write(
                self.style.ERROR(f"Tailwind CSS binary not found at {tailwind_bin}.")
            )
            return

        # Run Tailwind CLI
        try:
            cmd = [
                str(tailwind_bin),
                "-i",
                str(input_css),
                "-o",
                str(output_css),
                "-c",
                str(config_file),
                "--minify",  # Optional: Minify output for production
            ]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.stdout.write(
                self.style.SUCCESS(f"Successfully built Tailwind CSS: {result.stdout}")
            )
        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.ERROR(f"Error building Tailwind CSS: {e.stderr}")
            )
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(
                    f"Tailwind CSS binary not found at {tailwind_bin}. Ensure it is placed in web/bin/."
                )
            )
