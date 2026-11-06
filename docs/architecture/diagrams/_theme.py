"""Shared light/high-contrast theme + labelled-edge helpers for IKIP diagrams.

Quality bar (from the diagram-as-code rules):
- light background, dark text, bold edges, >=11pt — dark themes hide dashed edges
- every edge carries a VERB; solid = principal flow, dashed = backing dependency
- model each component with the closest real node; the LABEL is authoritative
"""
from diagrams import Edge

PRIMARY = "#1f4e94"   # principal flow
BACKING = "#8a8a8a"   # backing dependency

graph_attr = {
    "bgcolor": "white",
    "pad": "0.5",
    "fontname": "Helvetica",
    "fontsize": "22",
    "fontcolor": "#14213d",
    "splines": "spline",
    "nodesep": "0.55",
    "ranksep": "0.85",
    "labelloc": "t",
}

node_attr = {
    "fontname": "Helvetica",
    "fontsize": "12",
    "fontcolor": "#1a1a1a",
}

edge_attr = {
    "fontname": "Helvetica",
    "fontsize": "11",
    "fontcolor": "#333333",
    "color": BACKING,
    "penwidth": "1.5",
}


def principal(label: str = "") -> Edge:
    """A principal data/control flow (solid, dark blue, bold)."""
    return Edge(label=label, color=PRIMARY, penwidth="2.1", fontcolor="#14213d")


def backing(label: str = "") -> Edge:
    """A backing dependency (dashed, grey)."""
    return Edge(label=label, color=BACKING, style="dashed", fontcolor="#666666")


def cluster(bg: str) -> dict:
    """graph_attr for a Cluster (a layer / trust boundary)."""
    return {
        "bgcolor": bg,
        "fontname": "Helvetica",
        "fontsize": "13",
        "fontcolor": "#14213d",
        "style": "rounded",
        "pencolor": "#b0b8c4",
    }
