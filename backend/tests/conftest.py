import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lekha.tables import build  # noqa: E402

SCALE = 0.12


@pytest.fixture(scope="session")
def built():
    t, truth, stg, q, log = build(42, SCALE)
    return {"t": t, "truth": truth, "stg": stg, "q": q, "log": log}


@pytest.fixture(scope="session")
def pipeline_out(tmp_path_factory):
    from lekha import pipeline
    out = tmp_path_factory.mktemp("results")
    pipeline.run(seed=42, scale=SCALE, out=out, sim_runs=1000, quick=True)
    return out
