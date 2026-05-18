"""
Django management command to run the Knowkey MCP Server.

Usage:
    python manage.py run_mcp_server

This starts the Model Context Protocol server that allows AI agents
(Grok, Claude, etc.) to explore and feed the Knowkey knowledge graph.
"""

from django.core.management.base import BaseCommand
from knowkey.mcp.server import mcp


class Command(BaseCommand):
    help = "Run the Knowkey Model Context Protocol (MCP) Server"

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            type=str,
            default="127.0.0.1",
            help="Host to bind the server to (for HTTP transport)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8001,
            help="Port to run the server on (for HTTP transport)",
        )
        parser.add_argument(
            "--transport",
            type=str,
            choices=["stdio", "streamable-http"],
            default="streamable-http",
            help="Transport to use (stdio recommended for most MCP clients)",
        )

    def handle(self, *args, **options):
        transport = options["transport"]

        self.stdout.write(self.style.SUCCESS("Starting Knowkey MCP Server..."))
        self.stdout.write(f"Transport: {transport}")

        if transport == "streamable-http":
            self.stdout.write(
                f"Server will be available at http://{options['host']}:{options['port']}"
            )
            mcp.settings.host = options["host"]
            mcp.settings.port = options["port"]
            mcp.run(transport="streamable-http")
        else:
            # stdio transport (default for most clients like Cursor, Claude Desktop, etc.)
            mcp.run()
