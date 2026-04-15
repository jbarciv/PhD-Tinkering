#!/usr/bin/env python3
"""
Fetch unread arXiv digest emails, filter/categorize papers, send one HTML summary.
Configure via environment variables (optional overrides for same defaults as before).
"""

from __future__ import annotations

import email
import html
import imaplib
import os
import re
import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any, Callable

# --- Connection settings (env overrides keep cron working if vars unset) ---
IMAP_SSL_HOST = os.environ.get("MY_MAIL_CHECKER_IMAP_HOST", "imap.gmail.com")
IMAP_SSL_PORT = int(os.environ.get("MY_MAIL_CHECKER_IMAP_PORT", "993"))
SMTP_SSL_HOST = os.environ.get("MY_MAIL_CHECKER_SMTP_HOST", "smtp.gmail.com")
SMTP_SSL_PORT = int(os.environ.get("MY_MAIL_CHECKER_SMTP_PORT", "465"))

USERNAME = os.environ.get("MY_MAIL_CHECKER_USERNAME", 'mailToCheck@gmail.com')
PASSWORD = os.environ.get("MY_MAIL_CHECKER_PASSWORD", 'yourAppEmailPassword')
SENDER = os.environ.get("MY_MAIL_CHECKER_SENDER", USERNAME)
RECEIVER = os.environ.get("MY_MAIL_CHECKER_RECEIVER", 'receiverEmail@gmail.com')

# Lines that start a new field (order matters for regex choice)
_FIELD_TITLE = re.compile(
    r"^(arXiv:|Date:|Title:|Authors:|Categories:|Comments:)(.*)$", re.I
)
_ABSTRACT_MARKER = re.compile(r"^\\+")  # one or more backslashes (digest format)


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def get_plain_text_body(msg: email.message.Message) -> str:
    """Prefer text/plain; decode charset; walk multipart."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() != "text":
                continue
            if part.get_content_subtype() != "plain":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_maintype() == "text":
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        if msg.get_content_maintype() == "text":
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
            return str(payload)
    return ""


def _normalize_newlines(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\\r\\n" in t:
        t = t.replace("\\r\\n", "\n")
    return t


def split_digest_into_articles(text: str) -> list[str]:
    """Split raw digest into one string per paper (blocks starting with arXiv:)."""
    lines = _normalize_newlines(text).split("\n")
    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("arXiv:"):
            if current:
                chunks.append("\n".join(current))
            current = [line]
        else:
            if current:
                current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def parse_arxiv_block(raw: str) -> dict[str, Any]:
    """
    Parse one paper block. Handles multi-line Title, Authors, Comments, Abstract.
    """
    lines = [ln.rstrip() for ln in _normalize_newlines(raw).split("\n")]
    arxiv_id = ""
    title_parts: list[str] = []
    author_parts: list[str] = []
    categories = ""
    date = ""
    comment_parts: list[str] = []
    abstract_parts: list[str] = []
    link = ""

    state: str | None = None  # title | authors | comments
    in_abstract = False

    def flush_continuation_if_needed(stripped: str) -> bool:
        """Return True if this line was consumed as continuation."""
        nonlocal state, in_abstract
        if _FIELD_TITLE.match(stripped):
            return False
        if _ABSTRACT_MARKER.match(stripped):
            return False
        if stripped.startswith("---"):
            return False
        if state == "title":
            title_parts.append(stripped)
            return True
        if state == "authors":
            author_parts.append(stripped)
            return True
        if state == "comments":
            comment_parts.append(stripped)
            return True
        if in_abstract:
            if "------------------------------------------------------------------------------" in stripped:
                return True
            if "\\ (" in stripped:
                return True
            abstract_parts.append(stripped)
            return True
        return False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if flush_continuation_if_needed(stripped):
            continue

        if stripped.startswith("arXiv:"):
            arxiv_id = stripped.split()[0]
            state = None
            continue

        if stripped.lower().startswith("date:"):
            date = re.sub(r" \(.*\)", "", stripped[5:].strip()).strip()
            continue

        if stripped.startswith("Title:"):
            state = "title"
            title_parts = [stripped[6:].strip()]
            continue

        if stripped.startswith("Authors:"):
            state = "authors"
            author_parts = [stripped[8:].strip()]
            continue

        if stripped.startswith("Categories:"):
            state = None
            categories = stripped[11:].strip()
            continue

        if stripped.startswith("Comments:"):
            state = "comments"
            comment_parts = [stripped[9:].strip()]
            continue

        if _ABSTRACT_MARKER.match(stripped):
            if in_abstract:
                m = re.search(r"https://arxiv\.org/abs/[\d.]+", stripped)
                if m:
                    link = m.group(0)
                in_abstract = False
            else:
                in_abstract = True
            state = None
            continue

        if "------------------------------------------------------------------------------" in stripped:
            in_abstract = False
            continue

    title = " ".join(title_parts).strip()
    authors = re.sub(r"\s+", " ", " ".join(author_parts)).strip()
    comments = " ".join(comment_parts).strip()
    abstract = " ".join(abstract_parts).strip()

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": authors,
        "categories": categories,
        "abstract": abstract,
        "link": link,
        "date": date,
        "comments": comments,
    }


def _title_and_abstract_text(block: str) -> str:
    info = parse_arxiv_block(block)
    return f"{info.get('title', '')} {info.get('abstract', '')}"


def _haystack(block: str) -> str:
    return _title_and_abstract_text(block).lower()


# ---------------------------------------------------------------------------
# Hard exclusions — title + abstract only. VTOL may pass if clearly road-AV.
# ---------------------------------------------------------------------------

EXCLUDE_TERMS: tuple[str, ...] = (
    "uav",
    "uavs",
    "unmanned aerial",
    "unmanned-aerial",
    "micro aerial",
    "micro-aerial",
    "multirotor",
    "quadrotor",
    "quadcopter",
    "hexacopter",
    "octocopter",
    "tricopter",
    "fixed-wing uav",
    "fixed wing uav",
    "aerial robot",
    "aerial robotics",
    "aerial vehicle",
    "aerial vehicles",
    "drone",
    "drones",
    "rotorcraft",
    "vtol",
    "evtol",
    "tiltrotor",
    "ducted fan",
    "underwater",
    "under water",
    "submarine",
    "auv",
    "auvs",
    "unmanned surface vessel",
    "unmanned surface vehicle",
    "unmanned underwater",
    "usv",
    "remotely operated vehicle",
    "surgical robot",
    "surgical robotics",
    "endoscope",
    "endoscopic",
    "laparoscop",
    "catheter robot",
    "medical robot",
    "medical robotics",
    "intraoperative",
    "satellite",
    "satellites",
    "spacecraft",
    "orbital",
    "low earth orbit",
    "space robot",
    "humanoid locomotion",
    "bipedal walking",
    "biped walking",
    "harvesting robot",
    "harvest robot",
    "crop monitoring",
    "crop row",
    "agricultural field robot",
    "orchard robot",
    "vineyard robot",
)

EXCLUDE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\buav\b", re.I),
    re.compile(r"\bdrone\b", re.I),
    re.compile(r"\bauv\b", re.I),
    re.compile(r"\busv\b", re.I),
    re.compile(r"\bvtol\b", re.I),
    re.compile(r"\bevtol\b", re.I),
    re.compile(r"\bquadrotor(s)?\b", re.I),
    re.compile(r"\bquadcopter(s)?\b", re.I),
    re.compile(r"\bmulti-?rotor(s)?\b", re.I),
    re.compile(r"\bhexacopter(s)?\b", re.I),
    re.compile(r"\boctocopter(s)?\b", re.I),
    re.compile(r"\btricopter(s)?\b", re.I),
    re.compile(r"\brotorcraft\b", re.I),
    re.compile(r"\bunderwater\s+(robot|vehicle|navigation|slam)\b", re.I),
    re.compile(r"\bsubmarine\s+(robot|vehicle|navigation)\b", re.I),
    re.compile(r"\b(surgical|medical)\s+robot(s|ics)?\b", re.I),
    re.compile(r"\bendoscop(ic|y)\b", re.I),
    re.compile(r"\bspace\s+robot(s|ics)?\b", re.I),
    re.compile(r"\borbital\s+(mechanics|robot)\b", re.I),
]

_GROUND_VEHICLE_EXCEPTION_TERMS: tuple[str, ...] = (
    "autonomous vehicle",
    "autonomous vehicles",
    "autonomous driving",
    "self-driving",
    "self driving",
    "driverless car",
    "road vehicle",
    "on-road",
    "onroad",
    "highway driving",
    "urban driving",
    "traffic scene",
    "lane change",
    "intersection",
    "adas",
    "advanced driver-assistance",
    "advanced driver assistance",
    "vehicle-to-everything",
    "vehicle to everything",
    "v2x",
    "v2v",
    "v2i",
    "car following",
    "ego vehicle",
    "host vehicle",
)

_AGRICULTURAL_EXCLUDE_TERMS: tuple[str, ...] = (
    "harvest",
    "harvesting",
    "crop",
    "crops",
    "orchard",
    "vineyard",
    "agricultural robot",
    "field robot",
    "farm robot",
)

_HUMANOID_EXCLUDE_TERMS: tuple[str, ...] = (
    "humanoid",
    "bipedal",
    "biped",
    "legged locomotion",
    "walking robot",
)

_VTOL_TERMS: frozenset[str] = frozenset(("vtol", "evtol", "tiltrotor"))


def _vtol_term_hit(hay: str) -> bool:
    return any(t in hay for t in _VTOL_TERMS)


def _ground_vehicle_exception(hay: str) -> bool:
    return any(e in hay for e in _GROUND_VEHICLE_EXCEPTION_TERMS)


def _is_excluded(block: str) -> bool:
    hay = _haystack(block)

    if any(t in hay for t in _HUMANOID_EXCLUDE_TERMS) and not _has_av_driving_context(hay):
        return True

    if any(t in hay for t in _AGRICULTURAL_EXCLUDE_TERMS):
        if not _ground_vehicle_exception(hay):
            return True

    for term in EXCLUDE_TERMS:
        if term not in hay:
            continue
        if term in _VTOL_TERMS and _ground_vehicle_exception(hay):
            continue
        return True

    for pat in EXCLUDE_PATTERNS:
        if not pat.search(hay):
            continue
        if _vtol_term_hit(hay) and _ground_vehicle_exception(hay):
            continue
        return True

    return False


_ODD_WORD = re.compile(r"\bodd\b", re.I)

# Colloquial / math “odd” — suppress acronym read unless domain signals also present
_ODD_COLLOQUIAL_PHRASES: tuple[str, ...] = (
    "odd number",
    "odd numbers",
    "odd one out",
    "odd behavior",
    "odd behaviour",
    "odd behaviors",
    "odd behaviours",
    "odd result",
    "odd results",
    "odd way",
    "odd ways",
    "odd property",
    "odd properties",
)

# ISO / SUT-related names for functional safety & intended-functionality (also used in ODD bucket)
_ODD_FULL_PHRASES: tuple[str, ...] = (
    "operational design domain",
    "operational-design domain",
    "operational design domains",
    "operational-design domains",
    "design domain for operation",
    "driving operational design",
)

_ODD_DOMAIN_SIGNALS: tuple[str, ...] = (
    "odd specification",
    "odd specifications",
    "odd definition",
    "odd definitions",
    "odd characterization",
    "odd characterisation",
    "odd taxonomy",
    "odd taxonomies",
    "odd classification",
    "odd label",
    "odd labeling",
    "odd labelling",
    "odd description",
    "odd modeling",
    "odd modelling",
    "odd model",
    "odd models",
    "odd database",
    "odd knowledge",
    "odd representation",
    "odd ontology",
    "odd coverage",
    "odd monitor",
    "odd monitoring",
    "odd boundary",
    "odd boundaries",
    "boundary of the odd",
    "outside the odd",
    "within the odd",
    "odd mismatch",
    "odd gap",
    "odd transition",
    "odd expansion",
    "odd extension",
    "odd update",
    "odd evolution",
    "odd maintenance",
    "odd lifecycle",
    "odd life cycle",
    "odd management",
    "odd validation",
    "odd verification",
    "odd assessment",
    "odd certification",
    "odd compliance",
    "odd-compliant",
    "odd compliant",
    "odd scenario",
    "odd scenarios",
    "scenario classification",
    "scenario taxonomy",
    "corner case",
    "corner cases",
    "edge case",
    "edge cases",
    "long-tail scenario",
    "long tail scenario",
    "rare event",
    "rare events",
    "domain adaptation",
    "domain shift",
    "distribution shift",
    "deployment",
    "deployability",
    "operational envelope",
    "design envelope",
    "known-unknown",
    "unknown-unknown",
    "unknown unknown",
    "out-of-distribution",
    "out of distribution",
    "ood detection",
    "odd-aware",
    "odd aware",
    "risk assessment",
    "hazard analysis",
    "safety of the intended functionality",
    "sotif",
    "iso 21448",
    "iso21448",
)

_AV_DRIVING_CONTEXT_TERMS: tuple[str, ...] = (
    "autonomous vehicle",
    "autonomous vehicles",
    "autonomous driving",
    "automated driving",
    "autonomous car",
    "autonomous cars",
    "self-driving",
    "self driving",
    "driverless",
    "driverless car",
    "intelligent vehicle",
    "intelligent vehicles",
    "connected vehicle",
    "connected vehicles",
    "automotive",
    "road safety",
    "traffic safety",
    "vehicle safety",
    "active safety",
    "passive safety",
    "advanced driver-assistance",
    "advanced driver assistance",
    "driver assistance",
    "adas",
    "lane keeping",
    "lane-keeping",
    "lane change",
    "lane-change",
    "highway",
    "freeway",
    "motorway",
    "urban intersection",
    "intersection",
    "roundabout",
    "merge maneuver",
    "merge manoeuvre",
    "car following",
    "cut-in",
    "cut in",
    "ego vehicle",
    "host vehicle",
    "traffic participant",
    "traffic participants",
    "vulnerable road user",
    "vulnerable road users",
    "vru",
    "on-road",
    "onroad",
    "street scene",
    "driving scene",
    "traffic scene",
    "driving context",
    "driving environment",
    "driving task",
    "driving behaviour",
    "driving behavior",
    "steering wheel",
    "brake system",
    "throttle",
    "longitudinal",
    "lateral dynamics",
    "vehicle dynamics",
    "ground vehicle",
    "road user",
    "road users",
    "wheeled robot",
    "wheeled mobile robot",
    "mobile robot",
    "ugv",
    "unmanned ground vehicle",
    "unmanned ground vehicles",
    "automobile",
    "automotive industry",
    "oem",
    "tier-1",
    "tier 1",
    "nuplan",
    "nuscenes",
    "waymo",
    "kitti",
    "argoverse",
    "highd",
    "interaction dataset",
    "driving dataset",
    "naturalistic driving",
)


def _has_av_driving_context(hay: str) -> bool:
    return any(t in hay for t in _AV_DRIVING_CONTEXT_TERMS)


def _odd_acronym_usable(hay: str) -> bool:
    if any(p in hay for p in _ODD_FULL_PHRASES):
        return True
    if not _ODD_WORD.search(hay):
        return False
    if any(p in hay for p in _ODD_COLLOQUIAL_PHRASES) and not _has_av_driving_context(hay):
        return False
    if any(p in hay for p in _ODD_COLLOQUIAL_PHRASES) and not any(
        s in hay for s in _ODD_DOMAIN_SIGNALS
    ):
        return False
    return any(s in hay for s in _ODD_DOMAIN_SIGNALS)


def is_operational_design_domain_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not _has_av_driving_context(hay):
        return False
    return _odd_acronym_usable(hay)


# --- ISO 26262 / IEC 61508 / SOTIF / formal methods / runtime assurance ---
_SAFETY_FORMAL_SIGNALS: tuple[str, ...] = (
    "iso 26262",
    "iso26262",
    "iec 61508",
    "iec61508",
    "iso 21448",
    "iso21448",
    "sotif",
    "functional safety",
    "safety of the intended functionality",
    "asil",
    "hara",
    "hazard analysis",
    "fault tree",
    "fault-tree",
    "fta",
    "fmea",
    "fmeca",
    "failure mode",
    "safety case",
    "safety argument",
    "gsn",
    "goal structuring notation",
    "stpa",
    "stamp",
    "formal verification",
    "formally verify",
    "formally verified",
    "formal method",
    "formal methods",
    "formal specification",
    "formal model",
    "theorem proving",
    "interactive theorem",
    "model checking",
    "smt solver",
    "sat solver",
    "timed automata",
    "timed automaton",
    "hybrid automata",
    "hybrid automaton",
    "reachability analysis",
    "reachable set",
    "reachable sets",
    "barrier certificate",
    "control barrier function",
    "cbf",
    "inductive invariant",
    "invariant synthesis",
    "assume-guarantee",
    "assume guarantee",
    "contract-based design",
    "contracts for",
    "runtime verification",
    "runtime assurance",
    "runtime monitor",
    "runtime monitoring",
    "shield",
    "shielding",
    "least restrictive",
    "simplex architecture",
    "probabilistic safety",
    "risk assessment",
    "collision avoidance",
    "collision-free",
    "collision free",
    "rss",
    "responsibility-sensitive safety",
    "responsibility sensitive safety",
    "safe corridor",
    "safety envelope",
    "safe set",
    "forward invariant",
    "controlled invariant",
    "chance constraint",
    "chance-constrained",
    "probabilistic reachability",
    "uppaal",
    "spaceex",
    "flowstar",
)


def is_av_safety_formal_verification_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not _has_av_driving_context(hay):
        return False
    # Concrete standards / formalisms only — the tuple omits bare “safety”.
    return any(s in hay for s in _SAFETY_FORMAL_SIGNALS)


_DECISION_PHRASES: tuple[str, ...] = (
    "decision making",
    "decision-making",
    "decision process",
    "decision processes",
    "decision module",
    "decision modules",
    "decision framework",
    "decision frameworks",
    "decision support",
    "behavioral decision",
    "behavioural decision",
    "driving decision",
    "driving decisions",
    "lane-change decision",
    "lane change decision",
    "lane-selection",
    "lane selection",
    "intersection negotiation",
    "merge decision",
    "gap acceptance",
    "gap-acceptance",
    "tactical decision",
    "tactical decisions",
    "strategic decision",
    "strategic decisions",
    "high-level decision",
    "high level decision",
    "behavior planning",
    "behaviour planning",
    "behavioral planning",
    "behavioural planning",
    "option selection",
    "maneuver selection",
    "manoeuvre selection",
    "task selection",
    "intent recognition",
    "intention recognition",
    "pomdp",
    "partially observable markov",
    "mdp",
    "markov decision process",
    "semi-markov",
    "semi markov",
    "game-theoretic",
    "game theoretic",
    "stackelberg",
    "level-k",
    "level k",
    "nested logit",
    "discrete choice",
    "utility maximization",
    "utility maximisation",
    "behavior cloning",
    "behaviour cloning",
    "bc policy",
    "policy for driving",
    "driving policy",
    "negotiation strategy",
)

_AV_DECISION_CONTEXT: tuple[str, ...] = _AV_DRIVING_CONTEXT_TERMS + (
    "autonomous",
    "automated",
    "vehicle",
    "vehicles",
    "driving",
    "driver",
    "traffic",
    "road",
    "car",
    "cars",
    "truck",
    "trucks",
    "bus",
    "buses",
)


def is_autonomous_vehicle_decision_making_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not any(p in hay for p in _DECISION_PHRASES):
        return False
    if not any(c in hay for c in _AV_DECISION_CONTEXT):
        return False
    return True


_MOTION_PLAN_SIGNALS: tuple[str, ...] = (
    "motion planning",
    "motion planner",
    "path planning",
    "path planner",
    "trajectory planning",
    "trajectory planner",
    "trajectory generation",
    "trajectory optimization",
    "trajectory optimisation",
    "trajectory tracking",
    "spatiotemporal planning",
    "spatio-temporal planning",
    "kinodynamic planning",
    "kinodynamic trajectory",
    "sampling-based planning",
    "sampling based planning",
    "lattice planner",
    "lattice planning",
    "optimization-based planning",
    "optimisation-based planning",
    "spline",
    "splines",
    "b\u00e9zier",
    "bezier",
    "b-spline",
    "bspline",
    "b spline",
    "polynomial trajectory",
    "minimum jerk",
    "minimum-snap",
    "minimum snap",
    "rrt",
    "rrt*",
    "rrt-star",
    "prm",
    "prm*",
    "prm-star",
    "fmt*",
    "bit*",
    "chomp",
    "stomp",
    "ilqr",
    "i-lqr",
    "ilqg",
    "ddp",
    "differential dynamic programming",
    "sequential convex",
    "homotopy class",
    "corridor planning",
    "frenet",
    "curvilinear",
    "time-optimal",
    "time optimal",
    "mpc",
    "model predictive control",
    "tube mpc",
    "shrinking horizon",
    "real-time iteration",
    "sequential quadratic",
)

_MOTION_CONTEXT: tuple[str, ...] = _AV_DRIVING_CONTEXT_TERMS

# Deliberately omit bare “planning” / “planner” — require concrete motion/path/optimizer cues.
_PLANNING_ANCHOR_TERMS: tuple[str, ...] = (
    "trajectory",
    "path",
    "motion",
    "route",
    "spatiotemporal",
    "spatio-temporal",
    "frenet",
    "corridor",
    "mpc",
    "rrt",
    "prm",
    "spline",
    "optimization",
    "optimisation",
    "jerk",
    "snap",
    "kinodynamic",
    "lattice",
    "sampling-based",
    "sampling based",
)


def is_motion_planning_trajectory_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not any(m in hay for m in _MOTION_PLAN_SIGNALS):
        return False
    if not any(c in hay for c in _MOTION_CONTEXT):
        return False
    if "planning" in hay and not any(a in hay for a in _PLANNING_ANCHOR_TERMS):
        return False
    return True


_RL_SIGNALS: tuple[str, ...] = (
    "reinforcement learning",
    "deep reinforcement learning",
    "deep rl",
    "offline reinforcement",
    "offline rl",
    "batch reinforcement",
    "batch rl",
    "multi-agent reinforcement",
    "multiagent reinforcement",
    "marl",
    "multi-agent rl",
    "multiagent rl",
    "inverse reinforcement learning",
    "inverse rl",
    "irl",
    "imitation learning",
    "behavior cloning",
    "behaviour cloning",
    "policy gradient",
    "actor-critic",
    "actor critic",
    "proximal policy",
    "ppo",
    "soft actor-critic",
    "td3",
    "ddpg",
    "dqn",
    "a3c",
    "reward shaping",
    "reward function",
    "curriculum learning",
    "gail",
    "generative adversarial imitation",
)

_RL_DRIVING_CONTEXT: tuple[str, ...] = _AV_DRIVING_CONTEXT_TERMS + (
    "driving",
    "driver",
    "vehicle",
    "vehicles",
    "traffic",
    "carla",
    "sumo",
    "metadrive",
    "highway-env",
    "highway env",
    "lane",
    "intersection",
    "autonomous racing",
    "racing simulator",
    "driving simulator",
    "simulation-based",
    "simulation based",
)


def is_reinforcement_learning_driving_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not any(r in hay for r in _RL_SIGNALS):
        return False
    if not any(c in hay for c in _RL_DRIVING_CONTEXT):
        return False
    return True


_PREDICTION_SIGNALS: tuple[str, ...] = (
    "trajectory prediction",
    "trajectory forecasting",
    "motion prediction",
    "motion forecasting",
    "behavior prediction",
    "behaviour prediction",
    "behavior forecasting",
    "behaviour forecasting",
    "intent prediction",
    "intention prediction",
    "intent estimation",
    "intention estimation",
    "occupancy prediction",
    "occupancy forecasting",
    "occupancy grid",
    "occupancy map",
    "occupancy flow",
    "interaction-aware",
    "interaction aware",
    "interaction prediction",
    "social force",
    "social forces",
    "social lstm",
    "social pooling",
    "graph neural",
    "scene-centric",
    "scene centric",
    "agent-centric",
    "agent centric",
    "multi-agent prediction",
    "pedestrian prediction",
    "cyclist prediction",
    "vehicle trajectory",
    "kinematic prediction",
)

_PREDICTION_SCENE_CONTEXT: tuple[str, ...] = (
    "traffic",
    "pedestrian",
    "pedestrians",
    "cyclist",
    "cyclists",
    "vehicle",
    "vehicles",
    "car",
    "cars",
    "road",
    "highway",
    "intersection",
    "lane",
    "urban scene",
    "driving",
    "driver",
    "vulnerable road user",
    "vru",
    "crowd",
    "crosswalk",
    "crosswalks",
    "zebra crossing",
)


def is_prediction_behavior_modeling_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not any(p in hay for p in _PREDICTION_SIGNALS):
        return False
    if not any(c in hay for c in _PREDICTION_SCENE_CONTEXT):
        return False
    return True


_HDMAP_PERCEPTION_SIGNALS: tuple[str, ...] = (
    "hd map",
    "hd-map",
    "high-definition map",
    "high definition map",
    "high-resolution map",
    "high resolution map",
    "semantic map",
    "semantic mapping",
    "vector map",
    "vectorized map",
    "lane graph",
    "road graph",
    "road topology",
    "lane topology",
    "lane-level",
    "lane level",
    "centimetre-level",
    "centimeter-level",
    "centimetre level",
    "centimeter level",
    "map construction",
    "map updating",
    "map update",
    "map fusion",
    "localization map",
    "localisation map",
    "semantic segmentation",
    "panoptic segmentation",
    "instance segmentation",
    "drivable area",
    "drivable space",
    "free space",
    "freespace",
    "lane detection",
    "lane marking",
    "lane markings",
    "road marking",
    "road markings",
    "curb detection",
    "curb segmentation",
    "3d object detection",
    "3-d object detection",
    "monocular depth",
    "stereo depth",
    "depth estimation",
    "bird's eye view",
    "birds eye view",
    "bird eye view",
    "bev ",
    "bev-based",
    "bev based",
    "inverse perspective",
    "lidar",
    "light detection and ranging",
    "camera-lidar",
    "camera lidar",
    "lidar-camera",
    "lidar camera",
    "radar fusion",
    "camera fusion",
    "sensor fusion",
    "multi-modal perception",
    "multimodal perception",
    "occupancy network",
    "occupancy networks",
    "hd map priors",
)

_HDMAP_CONTEXT: tuple[str, ...] = _AV_DRIVING_CONTEXT_TERMS + (
    "road",
    "lane",
    "urban",
    "highway",
    "scene understanding",
    "driving perception",
    "perception for autonomous",
)


def is_hd_maps_environment_perception_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not any(s in hay for s in _HDMAP_PERCEPTION_SIGNALS):
        return False
    if not any(c in hay for c in _HDMAP_CONTEXT):
        return False
    if re.search(r"\bmap\b", hay) or "mapping" in hay:
        if not any(
            k in hay
            for k in (
                "hd map",
                "high-definition",
                "high definition",
                "semantic map",
                "vector map",
                "lane graph",
                "occupancy",
                "segmentation",
                "lane detection",
                "bev",
                "bird",
                "lidar",
                "radar fusion",
                "3d object",
                "drivable",
                "localization map",
                "localisation map",
            )
        ):
            return False
    return True


_SIM_SCENARIO_SIGNALS: tuple[str, ...] = (
    "traffic simulation",
    "microscopic simulation",
    "macroscopic simulation",
    "traffic flow model",
    "traffic flow modeling",
    "traffic flow modelling",
    "cellular automata",
    "car-following model",
    "car following model",
    "scenario generation",
    "scenario-based testing",
    "scenario based testing",
    "scenario mining",
    "adversarial scenario",
    "adversarial testing",
    "critical scenario",
    "corner-case generation",
    "corner case generation",
    "synthetic scenario",
    "synthetic scenarios",
    "naturalistic driving",
    "naturalistic dataset",
    "driving dataset",
    "sumo",
    "simulation of urban mobility",
    "carla",
    "metadrive",
    "lgsvl",
    "prescan",
    "vissim",
    "aimsun",
    "paramics",
    "anylogic",
    "agent-based traffic",
    "agent based traffic",
    "traffic microsimulation",
    "traffic micro-simulation",
    "scenario catalog",
    "scenario catalogue",
    "test case generation",
    "coverage-based testing",
    "coverage based testing",
)

_SIM_CONTEXT: tuple[str, ...] = _AV_DRIVING_CONTEXT_TERMS + (
    "traffic",
    "vehicle",
    "vehicles",
    "driving",
    "road network",
    "road-network",
)


def is_traffic_simulation_scenario_generation_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not any(s in hay for s in _SIM_SCENARIO_SIGNALS):
        return False
    if not any(c in hay for c in _SIM_CONTEXT):
        return False
    return True


_CONTROL_SIGNALS: tuple[str, ...] = (
    "longitudinal control",
    "lateral control",
    "steering control",
    "steering angle",
    "steer-by-wire",
    "steer by wire",
    "brake control",
    "throttle control",
    "traction control",
    "yaw control",
    "yaw rate",
    "yaw stability",
    "roll stability",
    "sideslip",
    "side-slip",
    "slip angle",
    "tire model",
    "tyre model",
    "pacejka",
    "magic formula",
    "bicycle model",
    "single-track",
    "single track",
    "double-track",
    "vehicle dynamics",
    "chassis control",
    "suspension model",
    "powertrain",
    "driveline",
    "drivetrain",
    "electronic stability",
    "anti-lock",
    "anti lock",
    "pid control",
    "pid controller",
    "lqr",
    "linear quadratic regulator",
    "gain scheduling",
    "low-level control",
    "low level control",
    "actuator control",
    "torque vectoring",
    "wheel slip",
    "road friction",
    "friction estimation",
    "cornering stiffness",
)

_CONTROL_ANCHOR = re.compile(
    r"longitudinal|lateral|steering|yaw|sideslip|slip\s*angle|tire\s+model|tyre\s+model|bicycle\s+model|vehicle\s+dynamics|chassis|powertrain|traction\s+control|electronic\s+stability|wheel\s+slip|torque\s+vectoring|pacejka|actuator",
    re.I,
)


def is_vehicle_control_dynamics_relevant(block: str) -> bool:
    hay = _haystack(block)
    if not _has_av_driving_context(hay):
        return False
    if not any(s in hay for s in _CONTROL_SIGNALS):
        return False
    if re.search(r"\bcontrol\b", hay) and not _CONTROL_ANCHOR.search(hay):
        if not any(x in hay for x in ("mpc", "lqr", "pid")):
            return False
    return True


_OTHER_VEHICLE_TERMS: tuple[str, ...] = _AV_DRIVING_CONTEXT_TERMS + (
    "vehicle",
    "vehicles",
    "automotive",
    "car",
    "cars",
    "truck",
    "trucks",
    "bus",
    "driving",
    "driver",
    "traffic",
    "road",
)


def is_other_relevant_vehicles(block: str) -> bool:
    hay = _haystack(block)
    return any(t in hay for t in _OTHER_VEHICLE_TERMS)


def prioritize_articles(article_texts: list[str]) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {
        "Operational Design Domain (ODD)": [],
        "AV Safety & Formal Verification": [],
        "Autonomous Vehicle Decision Making": [],
        "Motion Planning & Trajectory Optimization": [],
        "Reinforcement Learning for Driving": [],
        "Prediction & Behavior Modeling": [],
        "HD Maps & Environment Perception": [],
        "Traffic Simulation & Scenario Generation": [],
        "Vehicle Control & Lateral/Longitudinal Dynamics": [],
        "Other Relevant (Vehicles)": [],
    }

    checks: tuple[tuple[str, Callable[[str], bool]], ...] = (
        ("Operational Design Domain (ODD)", is_operational_design_domain_relevant),
        ("AV Safety & Formal Verification", is_av_safety_formal_verification_relevant),
        ("Autonomous Vehicle Decision Making", is_autonomous_vehicle_decision_making_relevant),
        ("Motion Planning & Trajectory Optimization", is_motion_planning_trajectory_relevant),
        ("Reinforcement Learning for Driving", is_reinforcement_learning_driving_relevant),
        ("Prediction & Behavior Modeling", is_prediction_behavior_modeling_relevant),
        ("HD Maps & Environment Perception", is_hd_maps_environment_perception_relevant),
        ("Traffic Simulation & Scenario Generation", is_traffic_simulation_scenario_generation_relevant),
        ("Vehicle Control & Lateral/Longitudinal Dynamics", is_vehicle_control_dynamics_relevant),
        ("Other Relevant (Vehicles)", is_other_relevant_vehicles),
    )

    filtered: list[str] = []
    for block in article_texts:
        if _is_excluded(block):
            continue
        filtered.append(block)

    for block in filtered:
        for name, fn in checks:
            if fn(block):
                categories[name].append(block)
                break

    return categories




def build_html_email(categorized: dict[str, list[str]]) -> str:
    total = sum(len(v) for v in categorized.values())
    parts = [
        "<html><head><style>",
        "body { font-family: Arial, sans-serif; }",
        "h3 { color: #007BFF; }",
        "hr { border: 1px solid #ddd; }",
        ".article { margin-bottom: 20px; word-wrap: break-word; }",
        ".title { font-weight: bold; display: block; margin-bottom: 6px; }",
        "</style></head><body>",
        f"<h3>Master, I have found {total} articles for you today.</h3>",
    ]

    for category, article_list in categorized.items():
        if not article_list:
            continue
        parts.append(f"<h3>📜 {html.escape(category.upper())} 📜</h3><hr>")
        for block in article_list:
            info = parse_arxiv_block(block)
            title = html.escape(info["title"] or "(no title)")
            date = html.escape(info["date"])
            authors = html.escape(info["authors"])
            comments = html.escape(info["comments"])
            abstract = html.escape(info["abstract"])
            link = html.escape(info["link"])

            parts.append('<div class="article">')
            parts.append(f'<span class="title">{title}</span><br>')
            parts.append(f"<i>📅 Date: {date}</i><br>")
            parts.append(f"<i>✍️ Authors: {authors}</i><br>")
            if comments:
                parts.append(f"💬 Comments: {comments}<br>")
            parts.append(f"📝 <b>Abstract:</b> {abstract}<br>")
            if link:
                parts.append(f'🔗 <a href="{link}" target="_blank" rel="noopener">Read more</a><br>')
            parts.append("</div><hr>")

    parts.append(
        "<br><br><p>Your humble assistant,<br>🤖 <b>ArxivBot</b></p></body></html>"
    )
    return "\n".join(parts)


def send_email(body: str) -> None:
    start = time.time()
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = "Your Daily ArXiv Articles... Master"
    msg["From"] = SENDER
    msg["To"] = RECEIVER
    try:
        with smtplib.SMTP_SSL(SMTP_SSL_HOST, SMTP_SSL_PORT) as server:
            server.login(USERNAME, PASSWORD)
            server.sendmail(SENDER, RECEIVER, msg.as_string())
        log(f"Email sent to {RECEIVER} | Time taken: {time.time() - start:.2f}s")
    except Exception as e:
        log(f"Failed to send email: {e}")


def process_unread_emails() -> None:
    articles: list[str] = []

    with imaplib.IMAP4_SSL(IMAP_SSL_HOST, IMAP_SSL_PORT) as server:
        server.login(USERNAME, PASSWORD)
        server.select("INBOX")

        log("Checking for unread emails in inbox...")
        _status, data = server.search(None, "UNSEEN")
        if not data or not data[0]:
            unread_uids: list[int] = []
        else:
            unread_uids = [int(s) for s in data[0].split() if s]
        log(f"Unread emails found: {len(unread_uids)}")

        for uid in unread_uids:
            start = time.time()
            _f, fdata = server.fetch(str(uid), "(RFC822)")
            if not fdata or fdata[0] is None:
                continue
            msg = email.message_from_bytes(fdata[0][1])
            text = get_plain_text_body(msg)
            articles.extend(split_digest_into_articles(text))
            log(f"Processed mail | Time taken: {time.time() - start:.2f}s")

    categorized = prioritize_articles(articles)

    if not any(categorized.values()):
        log("No relevant articles found.")
        return

    send_email(build_html_email(categorized))


def main() -> None:
    process_unread_emails()


if __name__ == "__main__":
    main()

