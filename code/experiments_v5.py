#!/usr/bin/env python3
"""
experiments_v5.py — panel round-3 push on the FastHenry-labelled v2 corpus.
Self-contained standardization (no hidden state) so fresh-layout inference is
consistent.

(A) Multi-seed accuracy (3 seeds) on the filament-L_m corpus.
(B) L_m field-grade validation: filament convergence (5x2 vs 15x6) + GNN vs the
    refined 15x6 reference -> replaces the 63%-off Grover label.
(C) Large-N MEASURED accuracy: train on small boards, test on the LARGEST.
(D) Downstream rank-order (Spearman) of interleaving variants by L_m: reference
    vs GNN -> decision-usefulness.
Runs on a compute cluster.
"""
import json, platform, time
from pathlib import Path
import numpy as np
import torch, torch.nn as nn
from scipy.stats import spearmanr

from gnn_baseline import PCBParasiticGNN, collate
from fem_inductance_ref import fem_pair_mutual_nh
from run_research13_pipeline import load_dataset, build_samples, TARGETS
from gen_corpus_fh import filament_total_Lm, big_layout
from planar_to_graph import build_graph_from_planar_layout

ROOT = Path(__file__).resolve().parents[1]
LM = TARGETS.index("L_mut_nH")


class Norm:
    """Holds all standardization stats fit on a fixed training split."""
    def __init__(self, samples, train_idx):
        Y = np.stack([s["y"] for s in samples]); Yl = np.sign(Y)*np.log1p(np.abs(Y))
        self.ym, self.ys = Yl.mean(0), Yl.std(0)+1e-8
        nf = np.concatenate([samples[j]["node_feat"] for j in train_idx], 0)
        self.nfm, self.nfs = nf.mean(0), nf.std(0)+1e-6
        ef = [samples[j]["edge_feat"] for j in train_idx if samples[j]["edge_feat"].size]
        ef = np.concatenate(ef,0) if ef else np.zeros((1,7))
        self.efm, self.efs = ef.mean(0), ef.std(0)+1e-6
    def node(self, nf): return ((np.asarray(nf,np.float32)-self.nfm)/self.nfs).astype(np.float32)
    def edge(self, ef):
        ef=np.asarray(ef,np.float32)
        return ((ef-self.efm)/self.efs).astype(np.float32) if ef.size else ef
    def y(self, yp): return ((np.sign(yp)*np.log1p(np.abs(yp))-self.ym)/self.ys).astype(np.float32)
    def inv(self, yn): yl=yn*self.ys+self.ym; return np.sign(yl)*np.expm1(np.abs(yl))


def split(samples, seed, size_split):
    n=len(samples)
    if size_split:
        order=np.argsort([s["node_feat"].shape[0] for s in samples])
        nte=max(1,int(0.2*n)); return order[:n-nte], order[n-nte:]
    rng=np.random.default_rng(seed); idx=np.arange(n); rng.shuffle(idx)
    nte=max(1,int(0.2*n)); return idx[nte:], idx[:nte]


def mk(s, nrm):
    return {"node_feat": nrm.node(s["node_feat"]), "edge_feat": nrm.edge(s["edge_feat"]),
            "edge_index": s["edge_index"], "edge_dim": 7, "y": nrm.y(s["y"])}


def train(samples, seed, epochs=200, size_split=False):
    torch.manual_seed(seed); np.random.seed(seed)
    tr, te = split(samples, seed, size_split)
    nrm = Norm(samples, tr)
    work = [mk(s, nrm) for s in samples]
    model = PCBParasiticGNN(node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=96, n_layers=4, n_targets=4)
    opt=torch.optim.AdamW(model.parameters(),lr=2e-3,weight_decay=1e-5)
    sch=torch.optim.lr_scheduler.CosineAnnealingLR(opt,T_max=epochs); lf=nn.SmoothL1Loss()
    rng=np.random.default_rng(seed)
    for ep in range(epochs):
        model.train(); order=tr.copy(); rng.shuffle(order)
        for i in range(0,len(order),32):
            b=collate([work[j] for j in order[i:i+32]])
            opt.zero_grad(); lf(model(b),b.y).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),5.0); opt.step()
        sch.step()
    model.eval()
    preds=[]; ys=[]
    with torch.no_grad():
        for j in te:
            preds.append(nrm.inv(model(collate([work[j]])).numpy()[0]))
            ys.append(samples[j]["y"])
    preds,ys=np.stack(preds),np.stack(ys)
    r2=lambda a,b: float(1-np.sum((a-b)**2)/(np.sum((b-b.mean())**2)+1e-12))
    per={t:round(r2(preds[:,k],ys[:,k]),4) for k,t in enumerate(TARGETS)}
    test_nodes=[int(samples[j]["node_feat"].shape[0]) for j in te]
    return model, nrm, per, (min(test_nodes),max(test_nodes))


def gnn_Lm(model, nrm, nf, ef, ei):
    s={"node_feat":nrm.node(nf),"edge_feat":nrm.edge(ef),
       "edge_index":np.asarray(ei,np.int64),"edge_dim":7,"y":np.zeros(4,np.float32)}
    with torch.no_grad():
        return float(nrm.inv(model(collate([s])).numpy()[0])[LM])


def fine_Lm(layout):
    trs=layout["traces"]; pri=[t for t in trs if t["net"]=="pri"]; sec=[t for t in trs if t["net"]=="sec"]
    tot=0.0
    for a in pri:
        for b in sec:
            h=abs(b.get("z_mm",0.3)-a.get("z_mm",0.1)); ov=min(a["length_mm"],b["length_mm"])
            tot+=fem_pair_mutual_nh(a["width_mm"],b["width_mm"],a.get("thick_mm",0.07),h,ov,nw=15,nt=6)
    return tot


def main():
    layouts, labels, meta = load_dataset(ROOT/"03_datasets"/"synth_v2")
    samples = build_samples(layouts, labels)
    res={"meta":{"host":platform.node(),"n":len(samples),"avg_nodes":meta.get("avg_nodes"),
                 "max_nodes":meta.get("max_nodes"),"label_Lm":meta.get("label_Lm")}}
    print("[corpus] n=%d avg=%.1f max=%d"%(len(samples),meta.get("avg_nodes",0),meta.get("max_nodes",0)))

    # (A) multi-seed
    print("[A] multi-seed accuracy")
    pers=[]; m42=nrm42=None
    for s in [42,43,44]:
        model,nrm,per,_=train(samples,s,200)
        pers.append(per); print("  seed",s,per)
        if s==42: m42,nrm42=model,nrm
    arr=lambda t:np.array([p[t] for p in pers])
    res["accuracy_multiseed"]={t:{"mean":round(float(arr(t).mean()),4),"std":round(float(arr(t).std()),4)} for t in TARGETS}

    # (B) L_m field-grade
    print("[B] L_m field-grade validation")
    sel=[r for r in layouts if any(t["net"]=="pri" for t in r["layout"]["traces"])
         and any(t["net"]=="sec" for t in r["layout"]["traces"])][-12:]
    conv=[]; gvf=[]
    for rec in sel:
        coarse=filament_total_Lm(rec["layout"],nw=5,nt=2); fine=fine_Lm(rec["layout"])
        gnn=gnn_Lm(m42,nrm42,rec["node_feat"],rec["edge_feat"],rec["edge_index"])
        if fine>0: conv.append(abs(coarse-fine)/fine*100); gvf.append(abs(gnn-fine)/fine*100)
    res["Lm_field_grade"]={"n":len(conv),
        "filament_5x2_vs_15x6_median_pct":round(float(np.median(conv)),2),
        "gnn_vs_15x6_filament_median_pct":round(float(np.median(gvf)),2),
        "prev_grover_vs_filament_pct":62.6}
    print("  ",res["Lm_field_grade"])

    # (C) large-N measured
    print("[C] large-N measured (size split)")
    _,_,per_big,(nmin,nmax)=train(samples,42,200,size_split=True)
    res["large_N_measured"]={"test_nodes_min":nmin,"test_nodes_max":nmax,"per_target_r2":per_big}
    print("  test %d-%d nodes:"%(nmin,nmax),per_big)

    # (D) downstream rank-order
    print("[D] downstream rank-order Spearman")
    rhos=[]; rng=np.random.default_rng(7)
    for d in range(8):
        base=big_layout(99000+d,18); ref=[]; gp=[]
        for v in range(6):
            lay=json.loads(json.dumps(base)); perm=rng.permutation(8)
            for t in lay["traces"]:
                t["layer"]=int(perm[t["layer"]%8]); t["z_mm"]=t["layer"]*0.18+0.05
            g=build_graph_from_planar_layout(lay); nf,ef,ei=g.to_feature_matrices()
            ref.append(filament_total_Lm(lay))
            gp.append(gnn_Lm(m42,nrm42,nf.tolist(),ef.tolist(),ei.tolist() if ei.size else []))
        rho,_=spearmanr(ref,gp)
        if not np.isnan(rho): rhos.append(rho)
    res["downstream_rank_spearman"]={"n_designs":len(rhos),
        "mean_rho":round(float(np.mean(rhos)),3),"min_rho":round(float(np.min(rhos)),3)}
    print("  ",res["downstream_rank_spearman"])

    out=ROOT/"05_experiments"/"run_v5"; out.mkdir(parents=True,exist_ok=True)
    (out/"results_v5.json").write_text(json.dumps(res,indent=2))
    print("=== DONE ->",out/"results_v5.json")


if __name__=="__main__":
    main()
