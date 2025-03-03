from typing import Optional, Any

from .uim_pb2 import Node, Token, Location, UniHref, IndexItem
from .uim_pb2 import NodeKind, TokenType, IndexItemKind


class UimTokenWriter:
    def __init__(self, node: Node, calculated_line: int):
        self.node = node
        self.calculated_line = calculated_line
        self.text_parts = []
        self.offset = 0

    def append_token(self, token_type: str, text: str, href: Any, real_line: Optional[int] = None) -> None:
        """
        Append a token to the current node.

        Args:
            token_type: The type of token (must match a TokenType enum name)
            text: The token text
            href: A dictionary-like object containing path and offset for UniHref
            real_line: Optional override for line number

        Raises:
            ValueError: If token_type is invalid
        """
        # Convert string token type to enum value
        try:
            pb_token_type = TokenType.Value(token_type)
        except ValueError:
            raise ValueError(f"invalid token type: {token_type}")

        # Create a new token
        tok = Token()
        tok.type = pb_token_type

        # Handle href if provided (uni_href is a oneof field in the Token message)
        if href is not None:
            uni_href = UniHref()
            # Set path and offset from the href dictionary
            uni_href.path = href.get("path", "")
            uni_href.offset = href.get("offset", 0)

            # Set the oneof field in the Token
            tok.uni_href.CopyFrom(uni_href)

        # Set real_line if it differs from calculated_line
        if real_line is not None and self.calculated_line != real_line:
            tok.real_line = real_line

        text_bytes = text.encode('utf-8')
        tok.offset = self.offset
        self.offset += len(text_bytes)
        self.text_parts.append(text_bytes)

        self.node.tokens.append(tok)
        self.calculated_line += text.count('\n')


class UimNodeWriter:
    def __init__(self, path: str):
        """
        Create a new UimNodeWriter that writes to the specified file.

        Args:
            path: The file path to write to

        Raises:
            IOError: If the file cannot be created
        """
        try:
            self.file = open(path, 'wb')
        except IOError as e:
            raise IOError(f"failed to create uim file: {e}")

    def _write_varint(self, file, value):
        """Write a variable-length integer to the file (protobuf format)."""
        while True:
            byte = value & 0x7f
            value >>= 7
            if value:
                byte |= 0x80
            file.write(bytes([byte]))
            if not value:
                break

    def begin_node(self, kind: str, path: str, start: Optional[Location] = None, nest_level: Optional[int] = 1) -> UimTokenWriter:
        """
        Begin a new node with the specified kind and path.

        Args:
            kind: The node kind (must match a NodeKind enum name)
            path: The node path
            start: Optional location information

        Returns:
            A UimTokenWriter for the new node

        Raises:
            ValueError: If the node kind is invalid
        """
        # Create a new node
        node = Node()

        # Set the node kind
        try:
            node.kind = NodeKind.Value(kind)
        except ValueError:
            raise ValueError(f"incorrect node kind: {kind}")

        # Set the path
        node.path = path
        node.uim_nest_level = nest_level

        # Set the start location if provided
        calculated_line = 0
        if start:
            node.start.CopyFrom(start)
            calculated_line = start.line
        else:
            start = Location()
            start.column = 0
            start.line = 0
            start.offset = 0
            node.start.CopyFrom(start)
            calculated_line = 0

        return UimTokenWriter(node, calculated_line)

    def write_node(self, tw: UimTokenWriter) -> None:
        """
        Write a node to the file.

        Args:
            tw: The UimTokenWriter containing the node to write

        Raises:
            IOError: If the writer is closed or an error occurs during writing
        """
        if self.file is None:
            raise IOError("attempted to write node to a closed writer")

        try:
            # Serialize the node using Protocol Buffers
            tw.node.text = b''.join(tw.text_parts)
            serialized = tw.node.SerializeToString()

            # Write length-delimited format (size + data)
            # We need to implement this manually since Python protobuf doesn't have SerializeToDelimitedString
            size = len(serialized)
            # Variable-length encoding for the size prefix (similar to how protobuf does it)
            self._write_varint(self.file, size)
            self.file.write(serialized)
            self.file.flush()
        except Exception as e:
            raise ValueError(f"failed to encode: {e}")

    def close(self) -> None:
        """Close the writer."""
        if self.file is not None:
            self.file.close()
            self.file = None


class UimSearchIndexWriter:
    def __init__(self, path: str):
        """
        Create a new UimSearchIndexWriter that writes to the specified file.

        Args:
            path: The file path to write to

        Raises:
            IOError: If the file cannot be created
        """
        try:
            self.file = open(path, 'wb')
        except IOError as e:
            raise IOError(f"failed to create uim search index file: {e}")

    def _write_varint(self, file, value):
        """Write a variable-length integer to the file (protobuf format)."""
        while True:
            byte = value & 0x7f
            value >>= 7
            if value:
                byte |= 0x80
            file.write(bytes([byte]))
            if not value:
                break

    def append(self, kind: str, key: str, href: Any, path: Optional[str] = None, typ: Optional[str] = None) -> None:
        """
        Append an index item to the file.

        Args:
            kind: The item kind (must match an IndexItemKind enum name)
            key: The item key
            href: A dictionary-like object containing path and offset for UniHref
            path: Optional path
            typ: Optional type

        Raises:
            ValueError: If the item kind is invalid
            IOError: If the writer is closed or an error occurs during writing
        """
        if self.file is None:
            raise IOError("attempted to write to a closed writer")

        # Create a new item
        item = IndexItem()
        item.key = key

        # Set the kind
        try:
            item.kind = IndexItemKind.Value(kind)
        except ValueError:
            raise ValueError(f"invalid item kind: {kind}")

        # Set optional fields
        if path is not None:
            item.path = path

        if typ is not None:
            item.type = typ

        # Set the href
        if href is not None:
            uni_href = UniHref()
            for key, value in href.items():
                if hasattr(uni_href, key):
                    setattr(uni_href, key, value)
                elif key == 'extra' and isinstance(value, dict):
                    for extra_key, extra_value in value.items():
                        uni_href.extra[extra_key] = extra_value

            # Set the uni_href oneof field in the IndexItem
            uni_href = UniHref()
            uni_href.path = href.get("path", "")
            uni_href.offset = href.get("offset", 0)

            # Set the oneof field in the IndexItem
            item.uni_href.CopyFrom(uni_href)

        try:
            # Serialize and write the item
            serialized = item.SerializeToString()
            # Write length-delimited format
            size = len(serialized)
            self._write_varint(self.file, size)
            self.file.write(serialized)
            self.file.flush()
        except Exception as e:
            raise ValueError(f"failed to encode: {e}")

    def close(self) -> None:
        """Close the writer."""
        if self.file is not None:
            self.file.close()
            self.file = None
