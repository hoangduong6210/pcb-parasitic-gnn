"""
planar_to_graph.py

Convert a planar transformer winding description into a PCBGraph + compute
improved trace-based PEEC labels.

This bridges a planar topology generator to the Topic 13 GNN pipeline.
"""
from __future__ import annotations

import numpy as np
from typing import Dict, List, Any

from pcb_graph import PCBGraph, Node, Edge
from trace_peec import Trace, strip_self_inductance_nh, mutual_inductance_rect_nh, trace_capacitance_pf


def _make_trace_from_spec(tr: Dict, z_layer: float) -> Trace:
    return Trace(
        x0=tr.get("x0", 0.0),
        y0=tr.get("y0", 0.0),
        z=z_layer,
        length_mm=tr["length_mm"],
        width_mm=tr["width_mm"],
        thick_mm=tr.get("thick_mm", 0.07),
        net=tr.get("net", "unknown"),
    )


def build_graph_from_planar_layout(layout: Dict[str, Any]) -> PCBGraph:
    """Build PCBGraph from a compact planar layout dict."""
    g = PCBGraph()
    n_layers = layout.get("n_layers", 8)
    g.freqs_hz = np.asarray(layout.get("freqs_hz", np.logspace(4, 8, 21)))
    g.globals = {
        "n_layers": n_layers,
        "board_w_mm": layout.get("board_w_mm", 55.0),
        "board_h_mm": layout.get("board_h_mm", 55.0),
        "cu_oz": layout.get("cu_oz", 2.0),
        "eps_r": layout.get("eps_r", 4.2),
    }

    traces = layout.get("traces", [])
    nodes_by_id: Dict[int, Node] = {}

    # Create trace nodes (one per trace segment)
    for i, tr in enumerate(traces):
        z = tr.get("z_mm", (tr["layer"] + 0.5) * 0.2)  # approx layer spacing
        node = Node(
            id=i,
            kind="trace",
            layer=tr["layer"],
            center_mm=np.array([
                tr.get("x0", 0) + tr["length_mm"] / 2,
                tr.get("y0", 0),
                z
            ]),
            dims_mm=np.array([tr["width_mm"], tr["length_mm"], tr.get("thick_mm", 0.07)]),
            material="copper",
            sigma_s_m=5.8e7,
            eps_r=layout.get("eps_r", 4.2),
        )
        g.add_node(node)
        nodes_by_id[i] = node

    # Add geometric edges (all-pairs for small boards; in real use kNN or window)
    for i, t1 in enumerate(traces):
        for j, t2 in enumerate(traces):
            if i >= j:
                continue
            z1 = t1.get("z_mm", (t1["layer"] + 0.5) * 0.2)
            z2 = t2.get("z_mm", (t2["layer"] + 0.5) * 0.2)
            dx = (t2.get("x0", 0) + t2["length_mm"]/2) - (t1.get("x0", 0) + t1["length_mm"]/2)
            dy = t2.get("y0", 0) - t1.get("y0", 0)
            dz = z2 - z1
            dist = float(np.sqrt(dx*dx + dy*dy + dz*dz))

            # TRUE geometric overlap (axis-aligned rectangle intersection in x-y),
            # not the old position-blind min(L)*min(w): C_ps depends on whether the
            # pri/sec traces actually overlap, which FastCap captures and the
            # position-blind feature hid (analytical C_ps was ~10^3x off).
            ax1, ax2 = t1.get("x0", 0.0), t1.get("x0", 0.0) + t1["length_mm"]
            bx1, bx2 = t2.get("x0", 0.0), t2.get("x0", 0.0) + t2["length_mm"]
            ay1, ay2 = t1.get("y0", 0.0), t1.get("y0", 0.0) + t1["width_mm"]
            by1, by2 = t2.get("y0", 0.0), t2.get("y0", 0.0) + t2["width_mm"]
            ox = max(0.0, min(ax2, bx2) - max(ax1, bx1))
            oy = max(0.0, min(ay2, by2) - max(ay1, by1))
            overlap = ox * oy

            is_cap = t1.get("net") != t2.get("net")
            edge = Edge(
                src=i,
                dst=j,
                kind="capacitive" if is_cap else "inductive",
                dist_mm=dist,
                overlap_area_mm2=overlap,
                rel_vec_mm=np.array([dx, dy, dz])
            )
            g.add_edge(edge)
            # undirected for now
            g.add_edge(Edge(src=j, dst=i, kind=edge.kind, dist_mm=dist,
                            overlap_area_mm2=overlap, rel_vec_mm=-edge.rel_vec_mm))

    return g


def compute_improved_labels(layout: Dict[str, Any]) -> Dict[str, np.ndarray]:
    """Compute R/L/C labels using the new trace models (better than old peec_cps)."""
    traces = layout.get("traces", [])
    freqs = np.asarray(layout.get("freqs_hz", np.logspace(4, 8, 21)))
    eps_r = layout.get("eps_r", 4.2)

    # Representative pri / sec traces (first occurrence per net)
    pri_spec = next((t for t in traces if t.get("net") == "pri"), None)
    sec_spec = next((t for t in traces if t.get("net") == "sec"), None)

    if not pri_spec or not sec_spec:
        n = len(freqs)
        return {"Cps_pF": np.zeros(n), "L_pri_nH": np.zeros(n), "L_sec_nH": np.zeros(n),
                "L_mut_nH": np.zeros(n), "freq_hz": freqs}

    t_pri = _make_trace_from_spec(pri_spec, pri_spec.get("z_mm", 0.1))
    t_sec = _make_trace_from_spec(sec_spec, sec_spec.get("z_mm", 0.3))

    L_pri = strip_self_inductance_nh(t_pri)
    L_sec = strip_self_inductance_nh(t_sec)
    L_mut = mutual_inductance_rect_nh(t_pri, t_sec)
    Cps = trace_capacitance_pf(t_pri, t_sec, eps_r)

    n = len(freqs)
    return {
        "Cps_pF": np.full(n, Cps),
        "L_pri_nH": np.full(n, L_pri),
        "L_sec_nH": np.full(n, L_sec),
        "L_mut_nH": np.full(n, L_mut),
        "freq_hz": freqs,
    }


def compute_reference_labels_allpairs(layout: Dict[str, Any]) -> Dict[str, float]:
    """
    Full O(N^2) all-pairs PEEC reference ("ground-truth" silver labels).

    This is the genuinely expensive computation the GNN aims to replace: it sums
    partial inductances/capacitances over EVERY trace pair, the way a PEEC
    extractor accumulates the partial-element matrix -- not the single
    representative-pair shortcut used by compute_improved_labels().

    Returns four extensive scalars (the GNN target vector):
      Cps_pF   = sum of pri<->sec coupling capacitance over all cross pairs
      L_pri_nH = sum of self-L (pri) + mutual-L over all pri-pri pairs
      L_sec_nH = sum of self-L (sec) + mutual-L over all sec-sec pairs
      L_mut_nH = sum of mutual-L over all pri-sec pairs
    """
    traces = layout.get("traces", [])
    eps_r = layout.get("eps_r", 4.2)

    tr = [_make_trace_from_spec(t, t.get("z_mm", (t["layer"] + 0.5) * 0.2)) for t in traces]
    pri = [t for t in tr if t.net == "pri"]
    sec = [t for t in tr if t.net == "sec"]

    Cps = 0.0
    for a in pri:
        for b in sec:
            Cps += trace_capacitance_pf(a, b, eps_r)

    def net_self_plus_mutual(group):
        tot = 0.0
        for i, a in enumerate(group):
            tot += strip_self_inductance_nh(a)
            for b in group[i + 1:]:
                tot += 2.0 * mutual_inductance_rect_nh(a, b)   # symmetric pair
        return tot

    L_pri = net_self_plus_mutual(pri)
    L_sec = net_self_plus_mutual(sec)

    L_mut = 0.0
    for a in pri:
        for b in sec:
            L_mut += mutual_inductance_rect_nh(a, b)

    return {
        "Cps_pF": float(Cps),
        "L_pri_nH": float(L_pri),
        "L_sec_nH": float(L_sec),
        "L_mut_nH": float(L_mut),
    }
