"""
Management command to run the Knowkey MCP server with the official MCP Inspector.

This is the recommended way to develop and debug the MCP server.

Usage:
    python manage.py mcp_dev

It will start the MCP Inspector (web UI) connected to your Knowkey MCP server.
"""

import os
import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run Knowkey MCP Server with the official MCP Inspector (dev mode)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-reload",
            action="store_true",
            help="Disable auto-reload (useful for debugging)",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Starting Knowkey MCP Server with Inspector...")
        )
        self.stdout.write("The inspector will open in your browser shortly.\n")

        # Build the command to run `mcp dev` on our server
        cmd = [
            sys.executable,
            "-m",
            "mcp",
            "dev",
            "knowkey/mcp/server.py",
        ]

        if options.get("no_reload"):
            cmd.append("--no-reload")

        # Ensure Django settings are available to the child process
        env = os.environ.copy()
        if not env.get("DJANGO_SETTINGS_MODULE"):
            env["DJANGO_SETTINGS_MODULE"] = "knowkey.settings"

        try:
            subprocess.run(cmd, env=env, check=True)
        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.ERROR(f"MCP dev exited with code {e.returncode}")
            )
        except KeyboardInterrupt:
            self.stdout.write("\nMCP Inspector stopped.")
