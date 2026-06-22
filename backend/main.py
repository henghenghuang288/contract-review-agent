"""
合同/条款风险审查助手 — FastAPI 后端

接口:
  POST /api/review        传入合同文本,逐条审查,返回风险报告
  POST /api/review/upload 上传 txt/md 文件审查
  GET  /api/health        返回当前是否为在线智能模式
"""

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .llm_client import is_live
from .review import review_contract

app = FastAPI(title="合同条款风险审查助手")


class ReviewRequest(BaseModel):
    text: str


@app.get("/api/health")
def health():
    return {"status": "ok", "live_mode": is_live()}


@app.post("/api/review")
async def review(body: ReviewRequest):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="请粘贴需要审查的合同文本")
    return await review_contract(body.text)


@app.post("/api/review/upload")
async def review_upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".txt", ".md")):
        raise HTTPException(status_code=400, detail="当前演示版仅支持 txt / md 文件,请粘贴文本或上传纯文本文件")
    raw = await file.read()
    if len(raw) > 1_000_000:
        raise HTTPException(status_code=400, detail="文件过大,演示版限制 1MB 以内")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="文件编码无法识别,请用 UTF-8 或 GBK 编码的文本文件")
    if not text.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")
    return await review_contract(text)


_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
