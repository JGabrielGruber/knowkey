"""
Django management command to run the Knowkey MCP Server with the official MCP Inspector.

This is the recommended way to develop and debug the MCP server.

It launches:
- Your Knowkey MCP server
- The MCP Inspector UI (web interface for testing tools, resources & prompts)

Usage:
    python manage.py run_mcp_inspector
"""

import os
import subprocess
import sys

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the Knowkey MCP Server with the MCP Inspector (development mode)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--server",
            type=str,
            default="mcp/server.py",
            help="Path to the MCP server file (relative to project root)",
        )
        parser.add_argument(
            "--no-inspector",
            action="store_true",
            help="Run only the server without launching the inspector UI",
        )

    def handle(self, *args, **options):
        server_path = options["server"]
        use_inspector = not options["no_inspector"]

        # Get absolute path from Django project root
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        full_server_path = os.path.join(project_root, server_path)

        if not os.path.exists(full_server_path):
            raise CommandError(f"MCP server file not found: {full_server_path}")

        self.stdout.write(
            self.style.SUCCESS("Starting Knowkey MCP Server with Inspector...")
        )
        self.stdout.write(f"Server file: {full_server_path}")

        if use_inspector:
            self.stdout.write(
                self.style.WARNING(
                    "Launching MCP Inspector. Use Ctrl+C to stop both server and inspector."
                )
            )
            cmd = ["mcp", "dev", full_server_path]
        else:
            self.stdout.write("Running server in stdio mode (no inspector).")
            cmd = [sys.executable, full_server_path]

        try:
            # Run the mcp dev command (this starts both server + inspector)
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            raise CommandError(
                "The 'mcp' command was not found.\n"
                "Please install it with: pip install 'mcp[cli]'"
            )
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("\nMCP Inspector stopped."))
        except subprocess.CalledProcessError as e:
            raise CommandError(f"MCP Inspector exited with error: {e}")
