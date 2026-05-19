import asyncio

from fastmcp import Client

# HTTP server
client = Client("https://mcp.dotproj.com/mcp")


async def main():
    async with client:
        # Basic server interaction
        await client.ping()

        # List available operations
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        print(tools)
        print(resources)
        print(prompts)


asyncio.run(main())
