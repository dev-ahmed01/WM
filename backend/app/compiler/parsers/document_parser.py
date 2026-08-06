"""Document Parser Module.

Parses raw markdown into a generic AST of structural nodes (Blocks, Lists, Headers).
This avoids fragile regex across the entire document in the extractors.
"""

import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class RawASTNode(BaseModel):
    """A generic AST node representing a structural element of the markdown document."""
    node_type: str  # 'HEADER', 'PARAGRAPH', 'LIST_ITEM', 'DIRECTIVE_BLOCK', 'INLINE_DIRECTIVE'
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    children: List['RawASTNode'] = Field(default_factory=list)

class DocumentParser:
    """Parses raw markdown text into a structural AST."""

    @staticmethod
    def parse_to_ast(markdown_text: str) -> List[RawASTNode]:
        """Convert markdown string to a list of RawASTNodes."""
        normalized = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.splitlines()
        
        nodes = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            line_trim = line.strip()
            
            if not line_trim:
                i += 1
                continue
                
            # Headers
            if line_trim.startswith("#"):
                header_match = re.match(r"^(#+)\s*(.*)", line_trim)
                if header_match:
                    level = len(header_match.group(1))
                    text = header_match.group(2)
                    nodes.append(RawASTNode(node_type="HEADER", content=text, metadata={"level": level}))
                i += 1
                continue
                
            # List items
            list_match = re.match(r"^[-*]\s*(\[\s*\])?\s*(.*)", line_trim)
            num_list_match = re.match(r"^\d+\.\s*(.*)", line_trim)
            if list_match or num_list_match:
                has_checkbox = False
                if list_match:
                    has_checkbox = bool(list_match.group(1))
                    content = list_match.group(2)
                else:
                    content = num_list_match.group(1)
                
                directive_match = re.search(r"::step\[(.*?)\]", content)
                step_code = None
                if directive_match:
                    step_code = directive_match.group(1)
                    content = content.replace(directive_match.group(0), "").strip()
                
                meta = {}
                if step_code:
                    meta["step_code"] = step_code
                if has_checkbox:
                    meta["is_checkbox"] = True

                nodes.append(RawASTNode(
                    node_type="LIST_ITEM", 
                    content=content,
                    metadata=meta
                ))
                i += 1
                continue
                
            # Directive block :::type[...]
            directive_block_match = re.match(r"^:::(\w+)(?:\[(.*?)\])?(?:\{(.*?)\})?", line_trim)
            if directive_block_match:
                d_type = directive_block_match.group(1).lower()
                d_code = directive_block_match.group(2)
                d_props_str = directive_block_match.group(3)
                
                d_props = {}
                if d_props_str:
                    for p in re.finditer(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\w+))', d_props_str):
                        d_props[p.group(1).lower()] = p.group(2) or p.group(3) or p.group(4)
                
                block_content = []
                i += 1
                nesting = 1
                while i < len(lines):
                    line_tmp = lines[i].strip()
                    if line_tmp.startswith(":::"):
                        if re.match(r"^:::\w+", line_tmp):
                            nesting += 1
                            block_content.append(lines[i])
                        elif line_tmp == ":::":
                            nesting -= 1
                            if nesting == 0:
                                break
                            else:
                                block_content.append(lines[i])
                        else:
                            block_content.append(lines[i])
                    else:
                        block_content.append(lines[i])
                    i += 1
                
                nodes.append(RawASTNode(
                    node_type="DIRECTIVE_BLOCK",
                    content="\n".join(block_content),
                    metadata={
                        "directive_type": d_type,
                        "directive_code": d_code,
                        "properties": d_props
                    }
                ))
                if i < len(lines):
                    i += 1  # Skip the closing :::
                continue
                
            # Inline directive ::type[...]
            inline_directive_match = re.match(r"^::(\w+)(?:\[(.*?)\])?(?:\{(.*?)\})?", line_trim)
            if inline_directive_match:
                d_type = inline_directive_match.group(1).lower()
                d_code = inline_directive_match.group(2)
                d_props_str = inline_directive_match.group(3)
                
                d_props = {}
                if d_props_str:
                    for p in re.finditer(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\w+))', d_props_str):
                        d_props[p.group(1).lower()] = p.group(2) or p.group(3) or p.group(4)
                        
                nodes.append(RawASTNode(
                    node_type="INLINE_DIRECTIVE",
                    content="",
                    metadata={
                        "directive_type": d_type,
                        "directive_code": d_code,
                        "properties": d_props
                    }
                ))
                i += 1
                continue
                
            # Otherwise it's a paragraph
            nodes.append(RawASTNode(node_type="PARAGRAPH", content=line_trim))
            i += 1
            
        return nodes
