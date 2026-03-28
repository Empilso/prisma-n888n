from fastapi import APIRouter, Request
import os, json

router = APIRouter()

STAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "stage_config.json")

@router.post("/api/stage/save")
async def save_stage(req: Request):
    data = await req.json()
    with open(STAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"status": "ok"}

@router.get("/api/stage/load")
async def load_stage():
    if os.path.exists(STAGE_FILE):
        with open(STAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@router.get("/api/agent-logs/{agent_id}")
async def get_agent_logs(agent_id: str):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs")
    if not os.path.exists(log_dir):
        return {"logs": []}
    
    import glob
    files = glob.glob(os.path.join(log_dir, f"agent_{agent_id}_*.log"))
    if not files:
        return {"logs": []}
        
    files.sort(key=os.path.getmtime)
    with open(files[-1], "r", encoding="utf-8") as f:
        lines = f.readlines()
        return {"logs": [l.strip() for l in lines[-150:]]}
