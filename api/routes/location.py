"""Mijoz aniq joylashuvini olish — SMS pin-havola oqimi (telefon buyurtmalari uchun).

Oqim:
  1. Telefon/ovoz buyurtmasi (delivery) yaratiladi -> `start_location_capture` token
     yaratadi va mijoz raqamiga SMS yuboradi: "Aniq joyni belgilang: <link>".
  2. Mijoz havolani ochadi -> GET /loc/{token} xarita sahifasini ko'rsatadi.
  3. Mijoz pin qo'yib "Tasdiqlash" bosadi -> POST /loc/{token} {lat, lon} ->
     order.latitude/longitude saqlanadi (Yandex kuryer shu koordinatani oladi).

Bu router PUBLIC (mijoz brauzeri, login yo'q). Token tasodifiy — order'ni topadi.
"""
from __future__ import annotations

import os
import secrets
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db, AsyncSessionLocal
from database.models import Order

log = logging.getLogger("location")
router = APIRouter(tags=["location"])


def _api_base() -> str:
    return (os.getenv("API_URL") or "https://api.tursunboyev.com").rstrip("/")


async def start_location_capture(db: AsyncSession, order: Order, phone: str) -> dict:
    """Order uchun token yaratadi va mijozga SMS pin-havola yuboradi."""
    from api.services import sms
    from api.services.ai_agent import get_ai_config
    from database.models import Restaurant

    cfg = {}
    if order.restaurant_id:
        rest = (await db.execute(
            select(Restaurant).where(Restaurant.id == order.restaurant_id)
        )).scalar_one_or_none()
        if rest:
            cfg = get_ai_config(rest)

    if cfg.get("sms_location_enabled") is False:
        return {"sent": False, "skipped": True, "reason": "sms_disabled"}

    token = secrets.token_urlsafe(10)
    order.location_token = token
    await db.commit()

    link = f"{_api_base()}/loc/{token}"
    template = (cfg.get("sms_location_template") or "").strip()
    if template:
        text = (
            template
            .replace("{order_id}", str(order.id))
            .replace("{link}", link)
        )
    else:
        text = (
            f"Buyurtmangiz #{order.id} qabul qilindi. Aniq yetkazish joyini belgilang: {link}"
        )
    res = await sms.send_sms(phone, text)
    return {"sent": bool(res.get("ok")), "mock": res.get("mock", False), "link": link}


class LocationIn(BaseModel):
    lat: float
    lon: float


@router.post("/loc/{token}")
async def submit_location(token: str, body: LocationIn):
    # Koordinata oqilona chegaralarda bo'lsin
    if not (-90 <= body.lat <= 90 and -180 <= body.lon <= 180):
        raise HTTPException(400, "Noto'g'ri koordinata")
    async with AsyncSessionLocal() as db:
        order = (await db.execute(
            select(Order).where(Order.location_token == token)
        )).scalar_one_or_none()
        if not order:
            raise HTTPException(404, "Havola yaroqsiz yoki eskirgan")
        order.latitude = float(body.lat)
        order.longitude = float(body.lon)
        await db.commit()
    return {"ok": True}


_PAGE = """<!doctype html>
<html lang="uz"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Yetkazish joyini belgilang</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:-apple-system,Segoe UI,Roboto,sans-serif}
  #map{position:absolute;top:0;left:0;right:0;bottom:84px}
  .bar{position:absolute;left:0;right:0;bottom:0;height:84px;background:#fff;
       box-shadow:0 -2px 8px rgba(0,0,0,.1);display:flex;align-items:center;
       justify-content:center;padding:12px;box-sizing:border-box}
  .btn{background:#16a34a;color:#fff;border:0;border-radius:12px;font-size:17px;
       font-weight:600;padding:16px;width:100%;max-width:440px}
  .btn:disabled{background:#9ca3af}
  .hint{position:absolute;top:10px;left:10px;right:10px;background:#fff;border-radius:10px;
        padding:10px 14px;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,.12);text-align:center}
  .ok{position:absolute;inset:0;background:#fff;display:none;flex-direction:column;
      align-items:center;justify-content:center;text-align:center;padding:24px}
</style></head>
<body>
<div id="map"></div>
<div class="hint">📍 Belgini yetkazish joyiga suring, keyin «Tasdiqlash» bosing</div>
<div class="bar"><button id="go" class="btn">Tasdiqlash</button></div>
<div id="ok" class="ok"><div style="font-size:54px">✅</div>
  <h2>Rahmat! Joylashuv qabul qilindi</h2>
  <p>Bu oynani yopishingiz mumkin.</p></div>
<script>
  var TOKEN = "__TOKEN__";
  var center = [41.3111, 69.2797]; // Toshkent markazi (default)
  var map = L.map('map').setView(center, 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);
  var marker = L.marker(center, {draggable:true}).addTo(map);
  map.on('click', function(e){ marker.setLatLng(e.latlng); });
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(function(p){
      var ll = [p.coords.latitude, p.coords.longitude];
      map.setView(ll, 17); marker.setLatLng(ll);
    }, function(){}, {enableHighAccuracy:true, timeout:8000});
  }
  document.getElementById('go').onclick = function(){
    var b = this; b.disabled = true; b.textContent = 'Yuborilmoqda...';
    var ll = marker.getLatLng();
    fetch('/loc/' + TOKEN, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({lat: ll.lat, lon: ll.lng})})
    .then(function(r){ if(!r.ok) throw 0;
      document.getElementById('ok').style.display='flex'; })
    .catch(function(){ b.disabled=false; b.textContent='Tasdiqlash';
      alert('Xato. Qayta urinib ko\\'ring.'); });
  };
</script>
</body></html>"""


@router.get("/loc/{token}", response_class=HTMLResponse)
async def location_page(token: str):
    async with AsyncSessionLocal() as db:
        order = (await db.execute(
            select(Order).where(Order.location_token == token)
        )).scalar_one_or_none()
    if not order:
        return HTMLResponse("<h3 style='font-family:sans-serif;text-align:center;margin-top:40px'>"
                            "Havola yaroqsiz yoki eskirgan.</h3>", status_code=404)
    return HTMLResponse(_PAGE.replace("__TOKEN__", token))
