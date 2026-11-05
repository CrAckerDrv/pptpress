"""Native PowerPoint animation and slide transitions.

Nothing here runs in a browser: the deck *declares* intent with ``data-*``
attributes and this module writes the same ``p:timing`` tree PowerPoint itself
produces when you pick an effect in the Animation Pane. The result stays fully
editable — you can open the pane, retime an effect, or delete it.

Attributes
----------
On a slide (``<section class="slide" data-transition="push-left">``):

===================  ==========================================================
``data-transition``  ``fade`` ``push`` ``push-left`` ``wipe`` ``wipe-left``
                     ``cover`` ``split`` ``cut``
``data-transition-speed``  ``slow`` ``med`` ``fast``
===================  ==========================================================

On any element (``<div data-anim="fade-up" data-anim-delay="0.3">``):

===================  ==========================================================
``data-anim``        effect name (see :data:`EFFECTS`)
``data-anim-delay``  seconds before this effect starts (default ``0``)
``data-anim-dur``    seconds the effect runs (default ``0.5``)
``data-anim-group``  integer; effects sharing a group start on the same click
``data-anim-trigger````click`` (default) starts a new click, ``with`` joins the
                     previous click, ``after`` starts right after it
===================  ==========================================================
"""

from __future__ import annotations

import math
from lxml import etree
from pptx.oxml.ns import qn

__all__ = ["EFFECTS", "TRANSITIONS", "parse_spec", "build_timing", "set_transition"]

# --------------------------------------------------------------------------
# effect grammar
# --------------------------------------------------------------------------
# presetID/presetSubtype only drive the label in PowerPoint's Animation Pane;
# what actually renders is the behaviour list built below.
EFFECTS = {
    # name          preset  class    subtype  what happens
    "fade":         (10, "entr", 0),
    "fade-up":      (42, "entr", 0),
    "fade-down":    (42, "entr", 4),
    "fade-left":    (42, "entr", 8),
    "fade-right":   (42, "entr", 2),
    "fly-left":     (2, "entr", 8),
    "fly-right":    (2, "entr", 2),
    "fly-up":       (2, "entr", 4),
    "fly-down":     (2, "entr", 1),
    "zoom":         (23, "entr", 16),
    "wipe":         (22, "entr", 4),
    "wipe-left":    (22, "entr", 8),
    "wipe-up":      (22, "entr", 1),
    "fade-out":     (10, "exit", 0),
    "fly-out":      (2, "exit", 8),
    "zoom-out":     (23, "exit", 16),
    "pulse":        (6, "emph", 0),
    "spin":         (18, "emph", 0),
}

TRANSITIONS = {
    "fade": "p:fade",
    "push": "p:push",
    "push-left": "p:push",
    "wipe": "p:wipe",
    "wipe-left": "p:wipe",
    "cover": "p:cover",
    "split": "p:split",
    "cut": "p:cut",
}

# Directional payloads for the transition elements that take one.
TRANSITION_DIRECTION = {
    "push": "u",
    "push-left": "l",
    "wipe": "u",
    "wipe-left": "l",
    "cover": "u",
}

DEFAULT_DURATION = 0.5


class Anim:
    """One declared effect, resolved to concrete timing values."""

    __slots__ = ("effect", "delay", "duration", "group", "trigger", "order")

    def __init__(self, effect, delay=0.0, duration=DEFAULT_DURATION, group=None,
                 trigger="click", order=0):
        self.effect = effect
        self.delay = delay
        self.duration = duration
        self.group = group
        self.trigger = trigger
        self.order = order

    def __repr__(self):
        return (f"<Anim {self.effect} delay={self.delay} dur={self.duration} "
                f"group={self.group} trigger={self.trigger}>")


def _seconds(raw, default):
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if not text:
        return default
    try:
        if text.endswith("ms"):
            return max(0.0, float(text[:-2]) / 1000.0)
        if text.endswith("s"):
            return max(0.0, float(text[:-1]))
        value = float(text)
    except ValueError:
        return default
    # A bare number is milliseconds only when it is obviously too large to be
    # seconds ("500" reads as 0.5 s, "0.6" reads as 0.6 s).
    return value / 1000.0 if value > 20 else value


def parse_spec(node, order=0):
    """Read ``data-anim*`` attributes into an :class:`Anim`, or ``None``."""
    if node is None or not hasattr(node, "attr"):
        return None
    effect = (node.attr("data-anim") or "").strip().lower()
    if not effect:
        return None
    if effect not in EFFECTS:
        return None
    delay = _seconds(node.attr("data-anim-delay"), 0.0)
    duration = _seconds(node.attr("data-anim-dur"), DEFAULT_DURATION)
    group_raw = node.attr("data-anim-group")
    group = None
    if group_raw not in (None, ""):
        try:
            group = int(group_raw)
        except ValueError:
            group = None
    trigger = (node.attr("data-anim-trigger") or "click").strip().lower()
    if trigger not in ("click", "with", "after"):
        trigger = "click"
    return Anim(effect, delay=delay, duration=max(0.05, duration), group=group,
                trigger=trigger, order=order)


def parse_stagger(node):
    """Read ``data-anim-stagger`` — the per-child delay in seconds, or ``None``.

    ``data-anim="fade-up" data-anim-stagger="0.12"`` on a grid animates each of
    its direct children 0.12 s after the previous one, so "these four cards come
    in one by one" is one attribute instead of four hand-tuned delays.
    """
    if node is None or not hasattr(node, "attr"):
        return None
    raw = node.attr("data-anim-stagger")
    if raw is None or str(raw).strip() == "":
        # A bare `data-anim-stagger` means "yes, with the default step".
        return 0.12 if raw is not None else None
    value = _seconds(raw, 0.12)
    return max(0.0, value)


def with_delay(anim, delay):
    """Copy ``anim`` with a new delay, keeping every other declaration."""
    return Anim(anim.effect, delay=max(0.0, delay), duration=anim.duration,
                group=anim.group, trigger=anim.trigger, order=anim.order)


# --------------------------------------------------------------------------
# timing tree
# --------------------------------------------------------------------------
class _Ids:
    def __init__(self, start=2):
        self.value = start

    def next(self):
        self.value += 1
        return self.value


def _ctn(parent, ids, dur="indefinite", **attributes):
    element = etree.SubElement(parent, qn("p:cTn"))
    element.set("id", str(ids.next()))
    element.set("dur", dur)
    for key, value in attributes.items():
        element.set(key, str(value))
    return element


def _st_cond(parent, delay_ms=0):
    conditions = etree.SubElement(parent, qn("p:stCondLst"))
    cond = etree.SubElement(conditions, qn("p:cond"))
    cond.set("delay", str(int(round(delay_ms))))
    return conditions


def _target(parent, shape_id):
    target = etree.SubElement(parent, qn("p:tgtEl"))
    sp_tgt = etree.SubElement(target, qn("p:spTgt"))
    sp_tgt.set("spid", str(shape_id))
    return sp_tgt


def _attr_names(parent, names):
    holder = etree.SubElement(parent, qn("p:attrNameLst"))
    for name in names:
        etree.SubElement(holder, qn("p:attrName")).text = name


def _behaviour(parent, ids, shape_id, duration_ms, attributes=None):
    behaviour = etree.SubElement(parent, qn("p:cBhvr"))
    if attributes:
        for key, value in attributes.items():
            behaviour.set(key, str(value))
    timing = _ctn(behaviour, ids, dur=str(int(round(duration_ms))), fill="hold")
    _st_cond(timing, 0)
    _target(behaviour, shape_id)
    return behaviour


def _visibility_set(parent, ids, shape_id, visible):
    element = etree.SubElement(parent, qn("p:set"))
    behaviour = etree.SubElement(element, qn("p:cBhvr"))
    timing = _ctn(behaviour, ids, dur="1", fill="hold")
    _st_cond(timing, 0)
    _target(behaviour, shape_id)
    _attr_names(behaviour, ["style.visibility"])
    to = etree.SubElement(element, qn("p:to"))
    etree.SubElement(to, qn("p:strVal")).set("val", "visible" if visible else "hidden")


def _anim_effect(parent, ids, shape_id, duration_ms, fade_in):
    effect = etree.SubElement(parent, qn("p:animEffect"))
    effect.set("transition", "in" if fade_in else "out")
    effect.set("filter", "fade")
    behaviour = etree.SubElement(effect, qn("p:cBhvr"))
    _ctn(behaviour, ids, dur=str(int(round(duration_ms))))
    _target(behaviour, shape_id)


def _motion(parent, ids, shape_id, duration_ms, attribute, start_value, end_value):
    """Animate one ppt_* property from ``start_value`` to ``end_value``.

    PowerPoint expresses relative motion with formula strings (``#ppt_y+0.08``),
    which is exactly how its own Float Up / Fly In effects are stored.
    """
    element = etree.SubElement(parent, qn("p:anim"))
    element.set("calcmode", "lin")
    element.set("valueType", "num")
    behaviour = etree.SubElement(element, qn("p:cBhvr"))
    behaviour.set("additive", "base")
    _ctn(behaviour, ids, dur=str(int(round(duration_ms))), fill="hold")
    _target(behaviour, shape_id)
    _attr_names(behaviour, [attribute])
    track = etree.SubElement(element, qn("p:tavLst"))
    for position, value in ((0, start_value), (100000, end_value)):
        tav = etree.SubElement(track, qn("p:tav"))
        tav.set("tm", str(position))
        val = etree.SubElement(tav, qn("p:val"))
        etree.SubElement(val, qn("p:strVal")).set("val", value)


def _rotate(parent, ids, shape_id, duration_ms, degrees):
    element = etree.SubElement(parent, qn("p:animRot"))
    element.set("by", str(int(round(degrees * 60000))))
    behaviour = etree.SubElement(element, qn("p:cBhvr"))
    _ctn(behaviour, ids, dur=str(int(round(duration_ms))), fill="hold")
    _target(behaviour, shape_id)


_PIXEL = 1.0 / 540.0  # one 720p-ish pixel as a fraction of slide height


def _movement(effect):
    """Distance/direction for the motion effects, as (attribute, from, to)."""
    offset = 0.06
    table = {
        "fade-up": ("ppt_y", f"#ppt_y+{offset}", "#ppt_y"),
        "fade-down": ("ppt_y", f"#ppt_y-{offset}", "#ppt_y"),
        "fade-left": ("ppt_x", f"#ppt_x+{offset}", "#ppt_x"),
        "fade-right": ("ppt_x", f"#ppt_x-{offset}", "#ppt_x"),
        "fly-left": ("ppt_x", "#ppt_x-0.35", "#ppt_x"),
        "fly-right": ("ppt_x", "#ppt_x+0.35", "#ppt_x"),
        "fly-up": ("ppt_y", "#ppt_y+0.35", "#ppt_y"),
        "fly-down": ("ppt_y", "#ppt_y-0.35", "#ppt_y"),
        "fly-out": ("ppt_y", "#ppt_y", "#ppt_y-0.35"),
    }
    return table.get(effect)


def _effect_body(parent, ids, shape_id, anim):
    """Write the behaviour list for one shape/effect pair."""
    duration_ms = anim.duration * 1000.0
    preset_id, preset_class, _subtype = EFFECTS[anim.effect]
    entry = etree.SubElement(parent, qn("p:par"))
    timing = _ctn(
        entry, ids, fill="hold",
        presetID=preset_id,
        presetClass=preset_class,
        presetSubtype=_subtype,
        grpId=0,
    )
    _st_cond(timing, anim.delay * 1000.0)
    body = etree.SubElement(timing, qn("p:childTnLst"))

    if preset_class == "entr":
        _visibility_set(body, ids, shape_id, True)
        if anim.effect in ("fade", "fade-up", "fade-down", "fade-left", "fade-right",
                           "zoom"):
            _anim_effect(body, ids, shape_id, duration_ms, True)
        movement = _movement(anim.effect)
        if movement:
            attribute, start, end = movement
            _motion(body, ids, shape_id, duration_ms, attribute, start, end)
        if anim.effect == "zoom":
            _motion(body, ids, shape_id, duration_ms, "ppt_w", "#ppt_w*0.45", "#ppt_w")
            _motion(body, ids, shape_id, duration_ms, "ppt_h", "#ppt_h*0.45", "#ppt_h")
        if anim.effect.startswith("wipe"):
            effect = etree.SubElement(body, qn("p:animEffect"))
            direction = {"wipe-left": "wipe(left)", "wipe-up": "wipe(up)"}.get(
                anim.effect, "wipe(right)")
            effect.set("transition", "in")
            effect.set("filter", direction)
            behaviour = etree.SubElement(effect, qn("p:cBhvr"))
            _ctn(behaviour, ids, dur=str(int(round(duration_ms))))
            _target(behaviour, shape_id)
    elif preset_class == "exit":
        if anim.effect in ("fade-out", "zoom-out"):
            _anim_effect(body, ids, shape_id, duration_ms, False)
        movement = _movement(anim.effect)
        if movement:
            attribute, start, end = movement
            _motion(body, ids, shape_id, duration_ms, attribute, start, end)
        if anim.effect == "zoom-out":
            _motion(body, ids, shape_id, duration_ms, "ppt_w", "#ppt_w", "#ppt_w*0.2")
            _motion(body, ids, shape_id, duration_ms, "ppt_h", "#ppt_h", "#ppt_h*0.2")
        _visibility_set(body, ids, shape_id, False)
    else:  # emphasis
        if anim.effect == "spin":
            _rotate(body, ids, shape_id, duration_ms, 360)
        else:  # pulse
            _motion(body, ids, shape_id, duration_ms, "ppt_w", "#ppt_w", "#ppt_w*1.12")
            _motion(body, ids, shape_id, duration_ms, "ppt_h", "#ppt_h", "#ppt_h*1.12")
    return entry


def _group(entries, anims):
    """Split effects into click groups: ``(start, [index, …])``.

    ``start`` is ``("click", delay)`` for a group that waits for the presenter,
    ``("after", delay)`` for one that follows the previous group, and
    ``("auto", delay)`` for the very first group when it has a delay.
    """
    groups: list[tuple[tuple[str, float], list[int]]] = []
    previous_key = None
    for index, anim in enumerate(anims):
        key = anim.group if anim.group is not None else index
        if anim.trigger == "with" and groups:
            groups[-1][1].append(index)
        elif anim.group is not None and previous_key is not None and anim.group == previous_key:
            # An explicit group number only joins when it repeats the previous one.
            groups[-1][1].append(index)
        elif anim.trigger == "after" and groups:
            groups.append((("after", anim.delay), [index]))
        else:
            start = ("click", anim.delay) if groups or anim.delay <= 0 else ("auto", anim.delay)
            groups.append((start, [index]))
        previous_key = key
    return groups


def build_timing(slide, entries, trigger_sequence=True):
    """Append a ``p:timing`` element to ``slide``.

    ``entries`` is a list of ``(anim, [shape_id, …])`` in document order.
    """
    if not entries:
        return None
    anims = [entry[0] for entry in entries]
    ids = _Ids(2)

    sld = slide._element
    for existing in sld.findall(qn("p:timing")):
        sld.remove(existing)
    timing_root = etree.SubElement(sld, qn("p:timing"))
    tn_lst = etree.SubElement(timing_root, qn("p:tnLst"))
    root_par = etree.SubElement(tn_lst, qn("p:par"))
    root_ctn = _ctn(root_par, ids, dur="indefinite", restart="never", nodeType="tmRoot")
    root_children = etree.SubElement(root_ctn, qn("p:childTnLst"))
    seq = etree.SubElement(root_children, qn("p:seq"))
    seq.set("concurrent", "1")
    seq.set("nextAc", "seek")
    main = _ctn(seq, ids, dur="indefinite", nodeType="mainSeq")
    main_children = etree.SubElement(main, qn("p:childTnLst"))

    groups = _group(entries, anims)
    previous_id = None
    for (kind, delay_seconds), indices in groups:
        per_click = etree.SubElement(main_children, qn("p:par"))
        click = _ctn(per_click, ids, fill="hold")
        conditions = etree.SubElement(click, qn("p:stCondLst"))
        cond = etree.SubElement(conditions, qn("p:cond"))
        if kind == "click":
            # Every click group waits for the presenter, and PowerPoint re-arms
            # it whenever the main sequence begins (its own two-condition form).
            cond.set("delay", "indefinite")
            begin = etree.SubElement(conditions, qn("p:cond"))
            begin.set("evt", "onBegin")
            begin.set("delay", "0")
            etree.SubElement(begin, qn("p:tn")).set("val", str(main.get("id")))
        elif kind == "after" and previous_id is not None:
            # Chain onto the previous group's end instead of a click.
            cond.set("evt", "onEnd")
            cond.set("delay", str(int(round(delay_seconds * 1000.0))))
            etree.SubElement(cond, qn("p:tn")).set("val", str(previous_id))
        else:
            cond.set("delay", str(int(round(delay_seconds * 1000.0))))
            begin = etree.SubElement(conditions, qn("p:cond"))
            begin.set("evt", "onBegin")
            begin.set("delay", "0")
            etree.SubElement(begin, qn("p:tn")).set("val", str(main.get("id")))
        click_children = etree.SubElement(click, qn("p:childTnLst"))

        inner = etree.SubElement(click_children, qn("p:par"))
        inner_ctn = _ctn(inner, ids, fill="hold")
        _st_cond(inner_ctn, 0)
        inner_children = etree.SubElement(inner_ctn, qn("p:childTnLst"))

        emitted = 0

        for index in indices:
            anim = anims[index]
            for shape_id in entries[index][1]:
                entry = _effect_body(inner_children, ids, shape_id, anim)
                ctn = entry.find(qn("p:cTn"))
                # Within a click group the very first targeted shape is the
                # "on click" effect; every other shape runs with it. Counting
                # per shape (not per anim) keeps a multi-shape card from
                # spawning several clicks for one author-declared effect.
                ctn.set("nodeType", "clickEffect" if emitted == 0 else "withEffect")
                emitted += 1
        previous_id = click.get("id")

    prev = etree.SubElement(seq, qn("p:prevCondLst"))
    prev_cond = etree.SubElement(prev, qn("p:cond"))
    prev_cond.set("evt", "onPrev")
    prev_cond.set("delay", "0")
    prev_target = etree.SubElement(prev_cond, qn("p:tgtEl"))
    etree.SubElement(prev_target, qn("p:sldTgt"))
    nxt = etree.SubElement(seq, qn("p:nextCondLst"))
    next_cond = etree.SubElement(nxt, qn("p:cond"))
    next_cond.set("evt", "onNext")
    next_cond.set("delay", "0")
    next_target = etree.SubElement(next_cond, qn("p:tgtEl"))
    etree.SubElement(next_target, qn("p:sldTgt"))
    return timing_root


# --------------------------------------------------------------------------
# slide transitions
# --------------------------------------------------------------------------
def set_transition(slide, transition, speed=None):
    """Write a ``p:transition`` element (must precede ``p:timing``)."""
    if not transition:
        return None
    key = str(transition).strip().lower()
    tag = TRANSITIONS.get(key)
    if tag is None:
        return None
    sld = slide._element
    for existing in sld.findall(qn("p:transition")):
        sld.remove(existing)

    element = etree.Element(qn("p:transition"))
    if speed:
        element.set("spd", str(speed).strip().lower())
    effect = etree.SubElement(element, qn(tag))
    direction = TRANSITION_DIRECTION.get(key)
    if direction:
        effect.set("dir", direction)

    timing = sld.find(qn("p:timing"))
    if timing is not None:
        timing.addprevious(element)
    else:
        sld.append(element)
    return element
