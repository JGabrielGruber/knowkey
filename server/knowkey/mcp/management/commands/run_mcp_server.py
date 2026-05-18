"""
Django management command to run the Knowkey MCP Server.

Usage examples:

    # Recommended for most local development (Cursor, Claude, etc.)
    python manage.py run_mcp_server --transport stdio

    # Run as HTTP server (useful for remote access or testing)
    python manage.py run_mcp_server --transport streamable-http --host 0.0.0.0 --port 8001

    # With allowed hosts for security
    python manage.py run_mcp_server --transport streamable-http \
        --allowed-hosts 127.0.0.1 --allowed-hosts localhost --allowed-hosts yourdomain.com
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
            help="Host to bind the server to (HTTP transports only)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8001,
            help="Port to run the server on (HTTP transports only)",
        )
        parser.add_argument(
            "--transport",
            type=str,
            choices=["stdio", "streamable-http", "sse"],
            default="streamable-http",
            help="Transport protocol to use. 'stdio' is recommended for most MCP clients.",
        )
        parser.add_argument(
            "--allowed-hosts",
            action="append",
            default=[],
            help="Allowed hosts for HTTP transports (can be specified multiple times). "
            "Example: --allowed-hosts 127.0.0.1 --allowed-hosts localhost",
        )

    def handle(self, *args, **options):
        transport = options["transport"]
        host = options["host"]
        port = options["port"]
        allowed_hosts = options["allowed_hosts"]

        self.stdout.write(self.style.SUCCESS("Starting Knowkey MCP Server..."))
        self.stdout.write(f"Transport : {transport}")

        # Security: allowed_hosts is important for HTTP-based transports
        if transport in ["streamable-http", "sse"]:
            self.stdout.write(f"Server listening on http://{host}:{port}")
            mcp.run(transport=transport, host=host, port=port)

        elif transport == "stdio":
            mcp.run()
