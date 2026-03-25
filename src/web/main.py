"""FastAPI application – routes, SSE streaming, graph analytics API, GNN endpoints."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

import config
from src.ml.risk_scorer import GNNRiskScorer
from src.osint import OSINTManager
from src.scheduler.periodic_scanner import PeriodicScanner
from src.utils.neo4j_handler import Neo4jHandler
from src.visualization.graph_generator import GraphGenerator

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

neo4j_handler: Neo4jHandler | None = None
osint_manager: OSINTManager | None = None
gnn_scorer: GNNRiskScorer | None = None
scanner: PeriodicScanner | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global neo4j_handler, osint_manager, gnn_scorer, scanner

    neo4j_handler = Neo4jHandler()
    neo4j_ok = await neo4j_handler.verify()
    if not neo4j_ok:
        logger.warning("Neo4j is not reachable – graph features will be unavailable")

    osint_manager = OSINTManager(neo4j=neo4j_handler if neo4j_ok else None)

    if config.GNN_ENABLED:
        gnn_scorer = GNNRiskScorer()
        logger.info("GNN scorer initialized (model loaded: %s)", gnn_scorer.is_ready)

    scanner = PeriodicScanner(osint_manager)
    scanner.start()

    yield

    if scanner:
        scanner.stop()
    if osint_manager:
        await osint_manager.close()
    if neo4j_handler:
        await neo4j_handler.close()


app = FastAPI(
    title="OSINT Framework – Human Trafficker Identification",
    version="2.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Pages ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/results/{phone}", response_class=HTMLResponse)
async def results_page(request: Request, phone: str):
    clean = phone.replace("+", "").replace("-", "").replace(" ", "")
    result_file = config.RESULTS_DIR / f"{clean}.json"
    data: dict = {}
    if result_file.exists():
        data = json.loads(result_file.read_text())

    gnn_data: dict = {}
    if gnn_scorer and neo4j_handler:
        gnn_data = await gnn_scorer.score(neo4j_handler, phone)

    network: dict = {}
    if neo4j_handler:
        network = await neo4j_handler.get_network(phone)

    graph_data = GraphGenerator.build_plotly_data(network) if network else {}

    return templates.TemplateResponse("results.html", {
        "request": request,
        "phone": phone,
        "data": data,
        "gnn": gnn_data,
        "graph_data": json.dumps(graph_data, default=str),
        "network": json.dumps(network, default=str),
    })


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    results = []
    for path in sorted(config.RESULTS_DIR.glob("*.json"), reverse=True):
        try:
            d = json.loads(path.read_text())
            results.append({
                "phone": d.get("phone", path.stem),
                "timestamp": d.get("timestamp", ""),
                "risk_level": d.get("summary", {}).get("risk_level", "UNKNOWN"),
                "risk_score": d.get("summary", {}).get("risk_score", 0),
            })
        except Exception:
            continue
    return templates.TemplateResponse("history.html", {"request": request, "results": results})


# ── Search ───────────────────────────────────────────────────────

@app.post("/search")
async def search(
    phone_number: str = Form(...),
    email: str = Form(None),
    include_darkweb: bool = Form(True),
):
    result = await osint_manager.investigate(phone_number, email, include_darkweb)

    if gnn_scorer and neo4j_handler and result.get("phone"):
        gnn_result = await gnn_scorer.score(neo4j_handler, result["phone"])
        result["gnn_risk"] = gnn_result

    return JSONResponse(result)


@app.post("/search/stream")
async def search_stream(
    phone_number: str = Form(...),
    email: str = Form(None),
    include_darkweb: bool = Form(True),
):
    async def event_generator():
        async for event_str in osint_manager.investigate_stream(
            phone_number, email, include_darkweb
        ):
            yield {"data": event_str}

        if gnn_scorer and neo4j_handler:
            gnn_result = await gnn_scorer.score(neo4j_handler, phone_number)
            yield {"data": json.dumps({"event": "gnn_risk", "data": gnn_result}, default=str)}

    return EventSourceResponse(event_generator())


@app.get("/download/{phone}")
async def download_results(phone: str):
    clean = phone.replace("+", "").replace("-", "").replace(" ", "")
    path = config.RESULTS_DIR / f"{clean}.json"
    if not path.exists():
        return JSONResponse({"error": "Results not found"}, status_code=404)
    data = json.loads(path.read_text())
    return JSONResponse(data, headers={
        "Content-Disposition": f"attachment; filename={clean}.json"
    })


# ── API Status ───────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    neo4j_ok = False
    if neo4j_handler:
        neo4j_ok = await neo4j_handler.verify()

    return {
        "neo4j": neo4j_ok,
        "gnn_model_loaded": gnn_scorer.is_ready if gnn_scorer else False,
        "gnn_enabled": config.GNN_ENABLED,
        "scheduler_enabled": config.SCHEDULER_ENABLED,
        "apis": {
            "numverify": bool(config.NUMVERIFY_API_KEY),
            "truecaller": bool(config.TRUECALLER_API_KEY),
            "hunter": bool(config.HUNTER_API_KEY),
            "spiderfoot": bool(config.SPIDERFOOT_API_URL),
        },
    }


# ── Graph Analytics API ─────────────────────────────────────────

@app.get("/api/graph/connections/{phone}")
async def graph_connections(phone: str):
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)
    return await neo4j_handler.get_connections(phone)


@app.get("/api/graph/clusters")
async def graph_clusters():
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)
    return await neo4j_handler.get_clusters()


@app.get("/api/graph/high-risk")
async def graph_high_risk():
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)
    return await neo4j_handler.get_high_risk()


@app.get("/api/graph/centrality")
async def graph_centrality():
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)
    return await neo4j_handler.get_centrality()


@app.get("/api/graph/network/{phone}")
async def graph_network(phone: str):
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)
    return await neo4j_handler.get_network(phone)


@app.get("/api/graph/timeline/{phone}")
async def graph_timeline(phone: str):
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)
    return await neo4j_handler.get_timeline(phone)


@app.get("/api/graph/movement/{phone}")
async def graph_movement(phone: str):
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)
    return await neo4j_handler.get_movement(phone)


# ── GNN-specific endpoints ──────────────────────────────────────

@app.get("/api/gnn/score/{phone}")
async def gnn_score_endpoint(phone: str):
    if not gnn_scorer:
        return JSONResponse({"error": "GNN not enabled"}, status_code=503)
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)
    return await gnn_scorer.score(neo4j_handler, phone)


@app.post("/api/gnn/train")
async def gnn_train():
    """Trigger model training on all existing graph data."""
    if not gnn_scorer:
        return JSONResponse({"error": "GNN not enabled"}, status_code=503)
    if not neo4j_handler:
        return JSONResponse({"error": "Neo4j not available"}, status_code=503)

    from src.ml.graph_features import build_pyg_data

    phones = await neo4j_handler.get_all_phones_for_training()
    if not phones:
        return JSONResponse({"error": "No training data in graph"}, status_code=400)

    data_list = []
    for p in phones:
        subgraph = await neo4j_handler.get_subgraph_for_gnn(p["phone"])
        if subgraph["nodes"]:
            data_list.append(build_pyg_data(subgraph))

    if not data_list:
        return JSONResponse({"error": "No valid subgraphs for training"}, status_code=400)

    metrics = gnn_scorer.train(data_list)
    return {"status": "trained", "metrics": metrics, "subgraphs_used": len(data_list)}
