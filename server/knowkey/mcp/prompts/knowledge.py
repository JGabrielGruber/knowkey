"""
Prompts: Knowledge Extraction & Curation
========================================
High-quality prompts that guide the LLM in building excellent knowledge.
"""

from fastmcp.prompts import base

from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


@mcp.prompt
@sync_to_async()
def extract_and_persist_knowledge(
    conversation_transcript: str,
    focus_area: str = "",
    max_new_nodes: int = 4,
) -> list[base.Message]:
    """
    Main prompt for extracting high-quality knowledge from a conversation
    and persisting it into Knowkey.

    Use this when you have a rich conversation that contains insights worth keeping.
    """
    system_instructions = f"""
You are Knowkey's expert Knowledge Curator.

## Mandatory Workflow
1. First, read these resources:
   - knowkey://ontology/node_types
   - knowkey://ontology/relationship_types
   - knowkey://ontology/tags (if relevant)

2. Use `search_nodes` extensively to understand what already exists.

3. Create **at most {max_new_nodes}** high-quality nodes using `create_node`.
   - Prioritize quality and connection over quantity.
   - Write excellent summaries.

4. Link new nodes to existing relevant knowledge using `create_relationship`.
   - Only link live nodes.
   - Choose precise relationship types.

5. If you improve existing knowledge, use `update_node`.

## Quality Standards
- Summaries should be self-contained and useful even without reading full content.
- Prefer specific NodeTypes.
- Be conservative with new NodeTypes — reuse existing ones when reasonable.
- Document provenance in metadata when helpful.

Focus area: {focus_area or "General knowledge from conversation"}

Now process the following conversation.
"""

    return [
        base.Message(role="system", content=system_instructions),
        base.Message(
            role="user",
            content=f"Conversation transcript:\n\n{conversation_transcript}",
        ),
    ]
