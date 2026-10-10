from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import asyncio
import json
import os
from typing import List, Dict

from app.core.config import settings
from app.core.database import engine, Base, init_db
from app.api.v1.zones import router as zones_router
from app.api.v1.telemetry import router as telemetry_router
from app.api.v1.control import router as control_router
from app.api.v1.ai_vision import router as ai_vision_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.admin import router as admin_router
from app.api.v1.mobile import router as mobile_router

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, zone_id: str, websocket: WebSocket):
        await websocket.accept()
        if zone_id not in self.active_connections:
            self.active_connections[zone_id] = []
        self.active_connections[zone_id].append(websocket)

    def disconnect(self, zone_id: str, websocket: WebSocket):
        if zone_id in self.active_connections:
            if websocket in self.active_connections[zone_id]:
                self.active_connections[zone_id].remove(websocket)

    async def broadcast_to_zone(self, zone_id: str, message: dict):
        if zone_id in self.active_connections:
            for connection in self.active_connections[zone_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception:
                    pass

manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist
    await init_db()
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="SaaS Multi-Tenant IoT & AI Backend for Kluai Hom Thong (กล้วยหอมทอง) Fruit Weight Maximization",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(zones_router, prefix=settings.API_V1_STR)
app.include_router(telemetry_router, prefix=settings.API_V1_STR)
app.include_router(control_router, prefix=settings.API_V1_STR)
app.include_router(ai_vision_router, prefix=settings.API_V1_STR)
app.include_router(alerts_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(mobile_router, prefix=settings.API_V1_STR)

@app.websocket("/ws/telemetry/{zone_id}")
async def websocket_telemetry_endpoint(websocket: WebSocket, zone_id: str):
    await manager.connect(zone_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(zone_id, websocket)

@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "multi_tenancy": "ENABLED",
        "admin_portal": "/admin",
        "mobile_liff_portal": "/mobile"
    }

# Template Helpers
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_portal():
    """
    Enterprise Admin Web Console (สำหรับแอดมิน / เจ้าของสหกรณ์ / ผู้จัดการระบบ)
    """
    file_path = os.path.join(TEMPLATES_DIR, "admin.html")
    with open(file_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/mobile", response_class=HTMLResponse)
@app.get("/liff", response_class=HTMLResponse)
async def serve_mobile_liff_app():
    """
    Farmer Mobile Web App / LINE LIFF (สำหรับเกษตรกรเจ้าของสวน สั่งการและถ่ายรูป)
    """
    file_path = os.path.join(TEMPLATES_DIR, "mobile.html")
    with open(file_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/", response_class=HTMLResponse)
async def serve_portal_landing():
    """
    Landing Switcher: ให้เลือกเข้าระหว่าง Admin Web หรือ Mobile Farmer (LINE LIFF)
    """
    html = """
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Smart Banana IoT & AI Platform | Gateway</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600;700&display=swap');
            body { font-family: 'Kanit', sans-serif; }
        </style>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4">
        <div class="max-w-2xl w-full bg-slate-900 border border-slate-800 rounded-3xl p-6 md:p-10 shadow-2xl space-y-8 text-center">
            
            <div class="space-y-3">
                <div class="text-6xl animate-bounce">🍌</div>
                <h1 class="text-2xl md:text-3xl font-extrabold bg-gradient-to-r from-amber-400 via-yellow-300 to-emerald-400 bg-clip-text text-transparent">
                    Smart Banana IoT & AI Platform
                </h1>
                <p class="text-sm text-slate-400 max-w-lg mx-auto">
                    ระบบเพิ่มผลผลิตและน้ำหนักผลกล้วยหอมทอง (Fruit Weight Maximization)<br>
                    สถาปัตยกรรม SaaS Multi-Tenant แยกระบบแอดมินและแอปชาวสวนตามมาตรฐาน Production
                </p>
            </div>

            <!-- Portal Selection Cards -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-left">
                <!-- Admin Web Card -->
                <a href="/admin" class="group p-5 bg-slate-950 hover:bg-slate-800/80 rounded-2xl border border-slate-800 hover:border-amber-500/50 transition-all duration-200 flex flex-col justify-between space-y-4">
                    <div>
                        <div class="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 text-lg group-hover:scale-110 transition">
                            <i class="fa-solid fa-desktop"></i>
                        </div>
                        <h3 class="text-base font-bold text-white mt-3 group-hover:text-amber-300 transition">
                            หน้าเว็บแอดมิน (Admin Web)
                        </h3>
                        <p class="text-xs text-slate-400 mt-1 leading-relaxed">
                            สำหรับผู้จัดการฟาร์ม/สหกรณ์ ดูภาพรวมฟาร์ม คุม Fleet อุปกรณ์ ESP32 วิเคราะห์กราฟ TimescaleDB และปรับแต่งเกณฑ์ Rule Engine
                        </p>
                    </div>
                    <div class="text-xs font-bold text-amber-400 flex items-center group-hover:translate-x-1 transition">
                        เข้าสู่คอนโซลแอดมิน <i class="fa-solid fa-arrow-right ml-1.5"></i>
                    </div>
                </a>

                <!-- Mobile Farmer App (LINE LIFF) Card -->
                <a href="/mobile" class="group p-5 bg-slate-950 hover:bg-slate-800/80 rounded-2xl border border-slate-800 hover:border-emerald-500/50 transition-all duration-200 flex flex-col justify-between space-y-4">
                    <div>
                        <div class="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-lg group-hover:scale-110 transition">
                            <i class="fa-solid fa-mobile-screen-button"></i>
                        </div>
                        <h3 class="text-base font-bold text-white mt-3 group-hover:text-emerald-300 transition">
                            แอปชาวสวน (LINE LIFF Mobile)
                        </h3>
                        <p class="text-xs text-slate-400 mt-1 leading-relaxed">
                            สำหรับเกษตรกรใช้งานบนมือถือ สั่งเปิด-ปิดน้ำ/ปุ๋ยด้วยปุ่มขนาดใหญ่ ดูความชื้นดิน และถ่ายรูปต้นกล้วยส่ง AI วิเคราะห์ระยะและสูตรปุ๋ย
                        </p>
                    </div>
                    <div class="text-xs font-bold text-emerald-400 flex items-center group-hover:translate-x-1 transition">
                        เปิดแอปมือถือ (LINE LIFF) <i class="fa-solid fa-arrow-right ml-1.5"></i>
                    </div>
                </a>
            </div>

            <div class="pt-2 border-t border-slate-800 flex items-center justify-center space-x-6 text-xs text-slate-500">
                <a href="/docs" target="_blank" class="hover:text-slate-300 transition"><i class="fa-solid fa-book mr-1"></i> Swagger API Docs</a>
                <span>&bull;</span>
                <span class="text-emerald-500 font-semibold"><i class="fa-solid fa-circle-check mr-1"></i> Production Ready</span>
            </div>

        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
