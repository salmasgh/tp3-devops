"""order-api (Service A) : point d'entrée POST /order.

Valide la commande, interroge pricing-engine (Service B) en HTTP puis
consolide la réponse. Aucune bibliothèque d'observabilité n'est importée :
toute la télémétrie est collectée par les sondes eBPF de Beyla.
"""
import asyncio
import os
import uuid

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PRICING_URL = os.getenv("PRICING_URL", "http://pricing-engine:8080")
# Temps de traitement interne simulé (validation, persistance...).
PROCESSING_MS = float(os.getenv("PROCESSING_MS", "5"))

app = FastAPI(title="order-api")
client: httpx.AsyncClient | None = None


class Order(BaseModel):
    product: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=100)
    customer: str = Field(min_length=1, max_length=64)


@app.on_event("startup")
async def startup() -> None:
    global client
    client = httpx.AsyncClient(
        base_url=PRICING_URL,
        timeout=httpx.Timeout(30.0),
        limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    if client:
        await client.aclose()


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.post("/order", status_code=201)
async def create_order(order: Order) -> dict:
    await asyncio.sleep(PROCESSING_MS / 1000)
    try:
        resp = await client.get(
            "/price", params={"product": order.product, "quantity": order.quantity}
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"pricing-engine unreachable: {exc}")
    if resp.status_code >= 500:
        raise HTTPException(status_code=502, detail="pricing-engine error")
    price = resp.json()
    return {
        "order_id": str(uuid.uuid4()),
        "customer": order.customer,
        "product": order.product,
        "quantity": order.quantity,
        "unit_price": price["unit_price"],
        "total": price["total"],
        "currency": price["currency"],
        "status": "CONFIRMED",
    }
