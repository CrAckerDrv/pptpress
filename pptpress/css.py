"""A compact CSS engine: parse stylesheets and resolve the cascade.

Scope is deliberately bounded to what a slide deck needs: type/class/id/attribute
selectors, descendant and child combinators, the ``:first-child``/``:last-child``/
``:nth-child()``/``:not()``/``:root``/``:empty`` pseudo classes, inline styles,
``!important`` and the usual specificity ordering. Anything outside that scope is
ignored rather than crashing the build, which keeps generated decks robust.
"""

from __future__ import annotations

import re

import tinycss2

_INHERITABLE = {
    "color", "font-family", "font-size", "font-weight", "font-style",
    "line-height", "letter-spacing", "text-align", "text-transform",
    "visibility", "list-style-type", "white-space", "font-variant-numeric",
}

_DEFAULT_INHERITED = {
    "color": "#111111",
    "font-family": "Inter, sans-serif",
    "font-size": "16px",
    "font-weight": "400",
    "font-style": "normal",
    "line-height": "normal",
    "letter-spacing": "0px",
    "text-align": "left",
    "text-transform": "none",
    "visibility": "visible",
    "white-space": "normal",
}

_SHORTHAND_ALIASES = {
    "gap": ("row-gap", "column-gap"),
    "grid-gap": ("row-gap", "column-gap"),
}

# The browser-equivalent defaults. They must live in the cascade rather than in
# Python fallbacks: ``font-size``/``font-weight``/``font-style`` are inheritable,
# so ``_DEFAULT_INHERITED`` always supplies a value and any ``computed.get(...)``
# fallback is dead code. Author rules are appended after this sheet and win at
# equal specificity, which is exactly how a real UA sheet behaves.
UA_STYLESHEET = """
h1{font-size:32pt;font-weight:700}
h2{font-size:24pt;font-weight:700}
h3{font-size:19pt;font-weight:600}
h4{font-size:16pt;font-weight:600}
h5{font-size:14pt;font-weight:600}
h6{font-size:12pt;font-weight:600}
b,strong,th{font-weight:700}
i,em,cite,dfn{font-style:italic}
small{font-size:0.85em}
s,del{text-decoration:line-through}
u,ins{text-decoration:underline}
ol{list-style-type:decimal}
ul{list-style-type:disc}
sub,sup{font-size:0.75em}
"""


class Compound:
    __slots__ = ("tag", "ids", "classes", "attrs", "pseudos", "not_selectors")

    def __init__(self):
        self.tag = None
        self.ids = []
        self.classes = []
        self.attrs = []          # (name, op, value)
        self.pseudos = []        # (name, argument)
        self.not_selectors = []  # list of Selector

    @property
    def quick_key(self):
        return self.ids[0] if self.ids else None

    def describe(self):
        parts = [self.tag or ""]
        parts += [f"#{i}" for i in self.ids]
        parts += [f".{c}" for c in self.classes]
        parts += [f"[{a[0]}{a[1] or ''}{a[2] or ''}]" for a in self.attrs]
        parts += [f":{p[0]}" for p in self.pseudos]
        return "".join(parts) or "*"

    def specificity(self):
        classes = len(self.classes) + len(self.attrs) + len(self.pseudos)
        classes += sum(sel.specificity()[1] for sel in self.not_selectors)
        return (len(self.ids), classes, 1 if self.tag and self.tag != "*" else 0)


class Selector:
    """A complex selector: ``compounds`` joined by combinators (right-last)."""

    __slots__ = ("parts", "pseudo_element")

    def __init__(self, parts, pseudo_element=None):
        self.parts = parts  # list[(combinator, Compound)]; first combinator ignored
        self.pseudo_element = pseudo_element

    def specificity(self):
        ids = classes = tags = 0
        for _, compound in self.parts:
            a, b, c = compound.specificity()
            ids += a
            classes += b
            tags += c
        if self.pseudo_element in ("before", "after", "marker", "placeholder"):
            tags += 1
        return (ids, classes, tags)


_TOKEN = re.compile(
    r"""
    (?P<combinator>\s*[>+~]\s*|\s+)
    |(?P<element>::?(?:[a-zA-Z-]+)(?:\([^)]*\))?)
    |(?P<id>\#[-\w]+)
    |(?P<class>\.[-\w\\]+)
    |(?P<attr>\[[^\]]*\])
    |(?P<universal>\*)
    |(?P<tag>[-\w]+)
    """,
    re.VERBOSE,
)

_ATTR_RE = re.compile(r"^\[\s*([-\w]+)\s*(?:([~^$*|]?=)\s*(['\"]?)(.*?)\3\s*)?(i)?\s*\]$")
_ELEMENT_RE = re.compile(r"^(::?)([a-zA-Z-]+)(?:\((.*)\))?$")

def _parse_compound_token(text, tokens, index):
    compound = Compound()
    result = index
    while result < len(tokens):
        kind, value = tokens[result]
        if kind == "combinator":
            break
        if kind == "tag":
            compound.tag = value.lower()
        elif kind == "universal":
            compound.tag = "*"
        elif kind == "id":
            compound.ids.append(value[1:])
        elif kind == "class":
            compound.classes.append(value[1:])
        elif kind == "attr":
            match = _ATTR_RE.match(value)
            if match:
                name, op, _quote, target, _flag = match.groups()
                compound.attrs.append((name.lower(), op, target))
        elif kind == "element":
            match = _ELEMENT_RE.match(value)
            if not match:
                result += 1
                continue
            double, name, argument = match.groups()
            if double == "::":
                if name not in ("before", "after", "marker", "placeholder", "first-line", "first-letter"):
                    result += 1
                    continue
                compound.pseudos.append(("__pseudo_element__", name))
            else:
                if name == "not":
                    for inner in _split_selector_list(argument or ""):
                        parsed = parse_selector(inner)
                        if parsed:
                            compound.not_selectors.append(parsed)
                else:
                    compound.pseudos.append((name, argument))
        result += 1
    return compound, result


def _tokenize(selector_text):
    tokens = []
    position = 0
    text = selector_text.strip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match or match.end() == position:
            position += 1
            continue
        kind = match.lastgroup
        value = match.group()
        tokens.append((kind, value))
        position = match.end()
    return tokens


def _split_selector_list(text):
    parts = []
    depth = 0
    current = []
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def parse_selector(selector_text):
    tokens = _tokenize(selector_text)
    if not tokens:
        return None
    parts = []
    combinator = " "
    index = 0
    while index < len(tokens):
        kind, value = tokens[index]
        if kind == "combinator":
            combinator = value.strip() or " "
            index += 1
            continue
        compound, index = _parse_compound_token(selector_text, tokens, index)
        parts.append((combinator, compound))
        combinator = " "
    if not parts:
        return None
    selector = Selector(parts)
    pseudo_element = None
    for _, compound in parts:
        for name, argument in compound.pseudos:
            if name == "__pseudo_element__":
                pseudo_element = argument
    selector.pseudo_element = pseudo_element
    return selector


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------
def _element_index(element):
    parent = element.parent_node
    if parent is None:
        return 1, 1
    siblings = [c for c in parent.child_nodes if getattr(c, "tag_name", None)]
    index = siblings.index(element) + 1 if element in siblings else 1
    return index, len(siblings)


def _match_pseudo(compound_pseudo, element, resolver):
    name, argument = compound_pseudo
    if name == "__pseudo_element__":
        return True
    if name == "root":
        root = element
        while root.parent_node is not None and getattr(root.parent_node, "tag_name", None) is not None:
            root = root.parent_node
        return root is element or element.parent_tag == "body"
    if name == "first-child":
        return _element_index(element)[0] == 1
    if name == "last-child":
        index, total = _element_index(element)
        return index == total
    if name == "only-child":
        return _element_index(element)[1] == 1
    if name == "empty":
        return not any(getattr(c, "tag_name", None) or getattr(c, "text", "").strip() for c in element.child_nodes)
    if name in ("nth-child", "nth-of-type"):
        raw = (argument or "").strip().lower()
        index, _total = _element_index(element)
        if raw == "odd":
            return index % 2 == 1
        if raw == "even":
            return index % 2 == 0
        if re.fullmatch(r"\d+", raw):
            return index == int(raw)
        match = re.fullmatch(r"(-?\d*)n\s*([+-]\s*\d+)?", raw)
        if match:
            step_text, offset_text = match.groups()
            step = -1 if step_text == "-" else 1 if step_text in ("", "+") else int(step_text)
            offset = int(offset_text.replace(" ", "")) if offset_text else 0
            if step == 0:
                return index == offset
            return (index - offset) % step == 0 and (index - offset) // step >= 0
        return False
    if name in ("hover", "focus", "active"):
        return False
    if name == "is":
        return any(
            resolver.matches(element, parse_selector(part))
            for part in _split_selector_list(argument or "")
            if parse_selector(part)
        )
    if name == "has":
        return False
    # Unknown pseudo classes are treated as non-matching to avoid false positives.
    return False


def match_compound(compound, element, resolver):
    if compound.tag and compound.tag != "*" and element.tag_name != compound.tag:
        return False
    for identifier in compound.ids:
        if element.attr("id") != identifier:
            return False
    for class_name in compound.classes:
        if class_name not in element.class_set:
            return False
    for name, op, expected in compound.attrs:
        actual = element.attr(name)
        if actual is None:
            return False
        if not op:
            continue
        if op == "=" and actual != expected:
            return False
        if op == "~=" and expected not in actual.split():
            return False
        if op == "^=" and not actual.startswith(expected):
            return False
        if op == "$=" and not actual.endswith(expected):
            return False
        if op == "*=" and expected not in actual:
            return False
        if op == "|=" and not (actual == expected or actual.startswith(expected + "-")):
            return False
    for pseudo in compound.pseudos:
        if not _match_pseudo(pseudo, element, resolver):
            return False
    for not_selector in compound.not_selectors:
        if resolver.matches(element, not_selector):
            return False
    return True


class Declaration:
    __slots__ = ("prop", "value", "important")

    def __init__(self, prop, value, important=False):
        self.prop = prop
        self.value = value
        self.important = important


class Rule:
    __slots__ = ("selector", "declarations", "order", "specificity", "selector_text")

    def __init__(self, selector, declarations, order, selector_text):
        self.selector = selector
        self.declarations = declarations
        self.order = order
        self.specificity = selector.specificity()
        self.selector_text = selector_text


def _declarations_from(nodes, resolver, element):
    declarations = []
    for node in nodes:
        if node.type == "declaration":
            prop = node.lower_name
            value = resolver.rewrite_values(tinycss2.serialize(node.value).strip()) if node.value else ""
            declarations.append(Declaration(prop, value, node.important))
        elif node.type == "at-rule" and node.lower_at_keyword == "apply":
            for token in tinycss2.serialize(node.prelude).split():
                declarations.append(Declaration("__apply__", token.strip(), False))
    return declarations


class StyleSheet:
    def __init__(self):
        self.rules = []
        self.order = 0

    def add_css_text(self, css_text):
        if not css_text:
            return
        rules = tinycss2.parse_stylesheet(css_text, skip_comments=True, skip_whitespace=True)
        self._add_rules(rules, resolver=None)

    def add_rule(self, selector_text, declarations):
        selector = parse_selector(selector_text)
        if selector is None:
            return
        self.order += 1
        self.rules.append(Rule(selector, declarations, self.order, selector_text))

    def _add_rules(self, nodes, resolver):
        for node in nodes:
            if node.type == "qualified-rule":
                selector_text = tinycss2.serialize(node.prelude).strip()
                declarations = _declarations_from(node.content, resolver, None) if resolver else []
                if resolver is None:
                    declarations = []
                    for item in tinycss2.parse_declaration_list(
                        node.content, skip_comments=True, skip_whitespace=True
                    ):
                        if item.type == "declaration":
                            declarations.append(
                                Declaration(item.lower_name, tinycss2.serialize(item.value).strip(), item.important)
                            )
                for single in _split_selector_list(selector_text):
                    self.add_rule(single, declarations)
            elif node.type == "at-rule" and node.lower_at_keyword == "media":
                content = getattr(node, "content", None) or tinycss2.parse_rule_list(
                    getattr(node, "content", None) or []
                )
                if node.content is not None:
                    self._add_rules([n for n in node.content if n.type in ("qualified-rule", "at-rule")], resolver)
            elif node.type == "at-rule" and node.lower_at_keyword == "supports":
                if node.content is not None:
                    self._add_rules([n for n in node.content if n.type == "qualified-rule"], resolver)

    def matching_rules(self, element, resolver, state=None):
        applicable = []
        for rule in self.rules:
            if state and rule.selector.pseudo_element:
                continue
            if resolver.matches(element, rule.selector):
                applicable.append(rule)
        applicable.sort(key=lambda r: (r.specificity, r.order))
        return applicable


class Resolver:
    """Resolves the computed value of any CSS property for an element."""

    def __init__(self, sheets, variables=None, fonts=None):
        self.sheets = sheets
        self.variables = dict(variables or {})
        self.fonts = fonts or {}
        self._cache = {}
        self._inherited_cache = {}

    # -- helpers ---------------------------------------------------------
    def rewrite_values(self, text):
        if "$" not in text and "var(" not in text:
            return text
        text = re.sub(r"\$([A-Za-z_][-\w]*)", lambda m: self._variable_text(m.group(1)), text)
        return self._expand_vars(text)

    def _variable_text(self, name):
        value = self.variables.get(name)
        if value is None:
            return f"var(--{name})"
        return str(value)

    def _expand_vars(self, text, depth=0):
        if depth > 6 or "var(" not in text:
            return text

        def replace(match):
            body = match.group(1).strip()
            name, _, fallback = body.partition(",")
            name = name.strip()
            key = name[2:] if name.startswith("--") else name
            value = self.variables.get(key)
            if value is None:
                return fallback.strip() if fallback else ""
            return self._expand_vars(str(value), depth + 1)

        return self._expand_vars(re.sub(r"var\(([^()]*)\)", replace, text), depth + 1)

    def matches(self, element, selector):
        if selector is None:
            return False
        return self._match_from(element, selector, len(selector.parts) - 1)

    def _match_from(self, element, selector, index):
        combinator, compound = selector.parts[index]
        if not match_compound(compound, element, self):
            return False
        if index == 0:
            return True
        previous_combinator = combinator
        if previous_combinator == ">":
            parent = element.parent_node
            return parent is not None and getattr(parent, "tag_name", None) is not None and self._match_from(
                parent, selector, index - 1
            )
        if previous_combinator == "+":
            sibling = element.prev_element_sibling()
            return sibling is not None and self._match_from(sibling, selector, index - 1)
        ancestor = element.parent_node
        while ancestor is not None and getattr(ancestor, "tag_name", None) is not None:
            if self._match_from(ancestor, selector, index - 1):
                return True
            ancestor = ancestor.parent_node
        return False

    # -- cascade ---------------------------------------------------------
    def declarations_for(self, element, state="normal"):
        """Ordered declaration map (later wins, respecting !important)."""
        key = (id(element), state)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        inline = parse_inline_style(element.attr("style") or "")
        result = {}
        entries = []
        for sheet in self.sheets:
            for rule in sheet.matching_rules(element, self, state=state):
                for decl in rule.declarations:
                    entries.append((rule.specificity, 0, rule.order, decl))
        for index, (prop, value) in enumerate(inline.items()):
            entries.append(((1, 0, 0), 1, 10 ** 6 + index, Declaration(prop, value)))
        entries.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
        for _spec, _inline_rank, _order, decl in entries:
            prop = decl.prop
            value = decl.value
            important = decl.important or value.replace(" ", "").lower().endswith("!important")
            if important:
                value = re.sub(r"\s*!\s*important\s*$", "", value, flags=re.I)
            existing = result.get(prop)
            if existing is not None and existing[1] and not important:
                continue
            result[prop] = (value.strip(), important)
        self._cache[key] = result
        return result

    def computed(self, element, state="normal"):
        key = (id(element), state)
        cached = self._inherited_cache.get(key)
        if cached is not None:
            return cached
        declarations = self.declarations_for(element, state)
        parent = element.parent_node
        parent_values = None
        computed = {}
        if parent is not None and getattr(parent, "tag_name", None) is not None:
            parent_values = self.computed(parent)
        if parent_values is None:
            parent_values = dict(_DEFAULT_INHERITED)
        for prop, value in parent_values.items():
            if prop in _INHERITABLE or prop.startswith("--"):
                computed[prop] = value
        if element.tag_name:
            if element.element_type is not None:
                computed.update(element.element_type.default_style())
        for prop, (value, _important) in declarations.items():
            if prop.startswith("__"):
                continue
            if value == "var(--slide-pt)":
                value = "1pt"
            elif value == "-var(--slide-pt)" or value == "calc(-1 * var(--slide-pt))":
                value = "-1pt"
            elif "$" in value or "var(" in value:
                value = self.rewrite_values(value)
            if value in ("inherit", "unset"):
                if prop in parent_values:
                    computed[prop] = parent_values[prop]
                continue
            if value == "initial":
                computed[prop] = _DEFAULT_INHERITED.get(prop, "")
                continue
            prop, value = self._expand_declaration(prop, value, element)
            if prop is None:
                continue
            if prop == "font-family":
                value = self.fonts.get("resolve", lambda s: s)(value)
            computed[prop] = value
        if element.element_type is not None:
            computed.update(element.element_type.after_cascade(computed))
        self._inherited_cache[key] = computed
        return computed

    # -- declaration expansion ------------------------------------------
    def _expand_declaration(self, prop, value, element):
        if prop == "font":
            return self._font_shorthand(value)
        if prop == "flex":
            return "flex", value
        if prop == "background":
            return "background", value
        if prop == "border":
            return "border", value
        if prop == "text-shadow":
            return "text-shadow", value
        if prop == "__apply__":
            return None, None
        return prop, value

    def _font_shorthand(self, value):
        match = re.match(
            r"^\s*(?:(?P<style>italic|oblique|normal)\s+)?(?:(?P<weight>bold|bolder|lighter|[1-9]00)\s+)?"
            r"(?P<size>[\d.]+(?:px|pt|em|rem)?)\s*(?:/\s*(?P<lh>[\d.]+(?:px|pt|em|rem)?))?\s+(?P<family>.+)$",
            value,
        )
        if not match:
            return "font-family", value
        return "font-family", match.group("family").strip()

    def font_family_for(self, element):
        computed = self.computed(element)
        stack = computed.get("font-family", "")
        return self.fonts.get("resolve", lambda s: "Inter")(stack)


def parse_inline_style(text):
    cleaned = (text or "").strip()
    if not cleaned:
        return {}
    cleaned = re.sub(r"(?<!:)//.*?(?=;|$)", "", cleaned)
    parts = [p.strip() for p in cleaned.split(";") if p.strip()]
    result = {}
    for part in parts:
        if ":" not in part:
            continue
        prop, value = part.split(":", 1)
        result[prop.strip().lower()] = value.strip()
    return result


def parse_stylesheets(document):
    sheet = StyleSheet()
    # UA defaults first: author rules come later and win ties by source order.
    sheet.add_css_text(UA_STYLESHEET)
    for node in document.style_texts:
        sheet.add_css_text(node)
    return sheet
