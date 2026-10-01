"""Wire up a live orchestrator from config and the environment."""

from __future__ import annotations

from lab.clients.gateway import Gateway
from lab.data.build import DEV, model_cutoff
from lab.data.schema import read_jsonl
from lab.evidence.retrieve import Retriever
from lab.orchestrator.loop import Data, Orchestrator
from lab.protocols.engine import Engine


def build(experimenter, commit: bool = True) -> Orchestrator:
    gw = Gateway.default()
    gw.cfg.require_ready([])
    engine = Engine(gw, Retriever.default(gw.cfg, gw.meter))
    dev = list(read_jsonl(DEV)) if DEV.exists() else []
    if not dev:
        raise SystemExit("No dev items. Approve sources and run `python -m lab.data.build`.")
    return Orchestrator(gw.cfg, engine, experimenter, Data(dev, post_cutoff=model_cutoff()),
                        commit=commit)
