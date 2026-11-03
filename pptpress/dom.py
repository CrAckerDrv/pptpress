"""Minimal DOM built on lxml with CSS-friendly class sets and whitespace text."""

from __future__ import annotations

import os

import lxml.etree as etree
import lxml.html as lxml_html

_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

_BLOCK_TAGS = {
    "html", "body", "div", "section", "article", "header", "footer", "main",
    "aside", "nav", "h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "li",
    "table", "thead", "tbody", "tfoot", "tr", "dl", "dt", "dd", "figure",
    "figcaption", "blockquote", "pre", "form", "fieldset", "address", "hr",
}

_SKIP = {"script", "style", "head", "title", "meta", "link", "template", "noscript"}

_WHITESPACE = " \t\r\n\f"


class Node:
    """A parsed HTML node with cached CSS-facing metadata."""

    __slots__ = (
        "element", "tag_name", "parent_node", "class_set", "child_nodes",
        "_attrs", "_element_type", "text_cache", "_order",
    )

    def __init__(self, element, element_type=None):
        self.element = element
        self.tag_name = (element.tag if isinstance(element.tag, str) else "") or ""
        self.parent_node = None
        self.child_nodes = []
        self.text_cache = None
        self._attrs = None
        self._element_type = element_type
        self._order = 0
        raw_class = element.get("class") or ""
        self.class_set = set(raw_class.split()) if raw_class else set()

    # -- attribute access -------------------------------------------------
    def attr(self, name):
        if self._attrs is None:
            self._attrs = dict(self.element.attrib)
        return self._attrs.get(name)

    @property
    def parent_tag(self):
        parent = self.parent_node
        return parent.tag_name if parent is not None and parent.tag_name else None

    @property
    def element_type(self):
        return self._element_type

    # -- tree helpers -----------------------------------------------------
    def first_element_child(self):
        for child in self.child_nodes:
            if child.tag_name:
                return child
        return None

    def element_children(self):
        return [child for child in self.child_nodes if child.tag_name]

    def prev_element_sibling(self):
        parent = self.parent_node
        if parent is None:
            return None
        previous = None
        for child in parent.child_nodes:
            if child is self:
                return previous
            if child.tag_name:
                previous = child
        return None

    def next_element_sibling(self):
        parent = self.parent_node
        if parent is None:
            return None
        seen = False
        for child in parent.child_nodes:
            if child is self:
                seen = True
                continue
            if seen and child.tag_name:
                return child
        return None

    def iter_descendants(self):
        stack = [child for child in reversed(self.child_nodes) if child.tag_name]
        while stack:
            node = stack.pop()
            yield node
            if node.child_nodes:
                stack.extend(child for child in reversed(node.child_nodes) if child.tag_name)

    def iter_elements(self):
        if self.tag_name:
            yield self
        for node in self.iter_descendants():
            if node.tag_name:
                yield node

    def find_first(self, tag_names, max_depth=8):
        """Depth-first search for the first element with a matching tag."""
        if isinstance(tag_names, str):
            tag_names = {tag_names}
        queue = [(child, 1) for child in self.element_children()]
        queue.reverse()
        while queue:
            node, depth = queue.pop()
            if node.tag_name in tag_names:
                return node
            if depth < max_depth:
                children = node.element_children()
                children.reverse()
                queue.extend((child, depth + 1) for child in children)
        return None

    def findAll(self, tag_names, max_depth=16):  # noqa: N802 - lxml-like name
        if isinstance(tag_names, str):
            tag_names = {tag_names}
        found = []
        queue = [(child, 1) for child in self.element_children()]
        queue.reverse()
        while queue:
            node, depth = queue.pop()
            if node.tag_name in tag_names:
                found.append(node)
            if depth < max_depth:
                children = node.element_children()
                children.reverse()
                queue.extend((child, depth + 1) for child in children)
        return found

    # -- text -------------------------------------------------------------
    def raw_text(self):
        if self.text_cache is None:
            parts = []
            for child in self.child_nodes:
                if child.tag_name:
                    parts.append(child.raw_text() or "")
                elif child.text:
                    parts.append(child.text)
            self.text_cache = "".join(parts)
        return self.text_cache

    def text(self):
        return collapse(self.raw_text())

    def is_block(self):
        if not self.tag_name:
            return False
        if self._element_type is not None:
            return self._element_type.is_block
        return self.tag_name in _BLOCK_TAGS

    def is_positioned(self):
        """Alignment markers set by the author (see docs/writing-guide.md)."""
        for marker in ("abs", "abs-x", "abs-y"):
            if marker in self.class_set:
                return True
        return False

    def is_abs(self):
        return "abs" in self.class_set

    def __repr__(self):
        return f"<Node {self.tag_name} .{' .'.join(sorted(self.class_set))[:40]}>"


class TextNode:
    __slots__ = ("text", "parent_node", "tag_name", "_order")

    def __init__(self, text, parent):
        self.text = text
        self.parent_node = parent
        self.tag_name = None
        self._order = 0

    def text_content(self):
        return self.text

    def __repr__(self):
        return f"<Text {self.text[:20]!r}>"


def collapse(text):
    if not text:
        return ""
    out = []
    space = False
    for char in text:
        if char in _WHITESPACE:
            space = True
            continue
        if space and out:
            out.append(" ")
        space = False
        out.append(char)
    return "".join(out)


class Document:
    """A parsed HTML document ready for CSS resolution and layout."""

    def __init__(self, source):
        self.style_texts = []
        self.root = None
        raw = source
        self.base_dir = ""
        if _looks_like_path(source):
            self.base_dir = os.path.dirname(os.path.abspath(source))
            with open(source, "r", encoding="utf-8") as handle:
                raw = handle.read()
        self.html_source = raw
        parser = lxml_html.HTMLParser(remove_comments=True, encoding="utf-8")
        try:
            document = lxml_html.document_fromstring(raw, parser=parser)
        except etree.ParserError as error:  # pragma: no cover - malformed input
            raise ValueError(f"HTML could not be parsed: {error}") from error
        body = document.find("body")
        if body is None:
            body = document
        self.raw_body = body
        self.raw_document = document
        for node in document.iter():
            if not isinstance(node.tag, str):
                continue
            if node.tag in ("style",):
                self.style_texts.append(node.text or "")
            elif node.tag == "link":
                rel = (node.get("rel") or "").lower()
                href = node.get("href") or ""
                if "stylesheet" in rel:
                    self.style_texts.append(_read_css(href, self.base_dir))
        self.root = self._build(body, None)
        self._index()

    def _build(self, element, parent):
        node = Node(element)
        node.parent_node = parent
        if node.tag_name in _SKIP:
            return node
        if element.text and element.text.strip():
            node.child_nodes.append(TextNode(element.text, node))
        for child in element:
            if not isinstance(child.tag, str) or child.tag in _SKIP:
                if isinstance(child.tag, str) and child.tail and child.tail.strip():
                    node.child_nodes.append(TextNode(child.tail, node))
                continue
            node.child_nodes.append(self._build(child, node))
            if child.tail and child.tail.strip():
                node.child_nodes.append(TextNode(child.tail, node))
        return node

    def _index(self):
        order = 0
        stack = [self.root]
        while stack:
            node = stack.pop()
            if node.tag_name:
                node._order = order
                order += 1
                stack.extend(reversed(node.child_nodes))

    def iter_elements(self):
        return self.root.iter_elements()


def _read_css(href, base_dir=""):
    """Read a local stylesheet; remote URLs are skipped (offline by design)."""
    if not href or href.startswith(("http://", "https://", "//")):
        return ""
    candidates = [href]
    if base_dir:
        candidates.insert(0, os.path.join(base_dir, href))
    for candidate in candidates:
        try:
            if os.path.exists(candidate):
                with open(candidate, "r", encoding="utf-8") as handle:
                    return handle.read()
        except OSError:
            continue
    return ""


def _looks_like_path(source):
    if not isinstance(source, str):
        return False
    if "\n" in source or "<" in source[:200]:
        return False
    return source.lower().endswith(".html") or source.lower().endswith(".htm")
