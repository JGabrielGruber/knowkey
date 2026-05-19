"""
Django management command to run the Knowkey MCP Server.

Usage (recommended):
    python manage.py run_mcp_server --transport stdio

Other options:
    python manage.py run_mcp_server --transport streamable-http --host 0.0.0.0 --port 8001
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
            help="Host to bind (HTTP transports only)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8001,
            help="Port to run on (HTTP transports only)",
        )
        parser.add_argument(
            "--transport",
            type=str,
            choices=["stdio", "streamable-http", "sse"],
            default="stdio",
            help="Transport protocol. 'stdio' is strongly recommended for most clients (Cursor, Claude, Grok).",
        )

    def handle(self, *args, **options):
        transport = options["transport"]
        host = options["host"]
        port = options["port"]

        self.stdout.write(self.style.SUCCESS("🚀 Starting Knowkey MCP Server..."))
        self.stdout.write(f"   Transport : {transport}")
        self.stdout.write(f"   Version   : 0.2.0 (refactored)")

        if transport in ["streamable-http", "sse"]:
            self.stdout.write(f"   Listening : http://{host}:{port}")
            mcp.run(transport=transport, host=host, port=port)
        else:
            self.stdout.write("   Mode      : stdio (ready for local MCP clients)")
            mcp.run(transport="stdio")
