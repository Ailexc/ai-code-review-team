"""触发器 API"""

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

import structlog

from app.triggers.registry import trigger_registry
from app.schemas.trigger import TriggerRequest, TriggerResponse, TriggerListResponse, TriggerTypeInfo

# 确保触发器已注册（导入模块触发 @register 装饰器）
import app.triggers.local_dir  # noqa: F401
import app.triggers.paste      # noqa: F401
import app.triggers.upload     # noqa: F401
import app.triggers.cli        # noqa: F401

logger = structlog.get_logger()
router = APIRouter()


@router.get("/types", response_model=TriggerListResponse)
async def list_trigger_types():
    """列出所有可用的触发器类型"""
    return TriggerListResponse(
        triggers=[TriggerTypeInfo(**t) for t in trigger_registry.list_triggers()]
    )


@router.post("", response_model=TriggerResponse)
async def execute_trigger(data: TriggerRequest):
    """执行触发器（local_directory / code_paste）"""
    try:
        trigger = trigger_registry.create(data.trigger_type)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 构造参数
    kwargs = {}
    if data.trigger_type == "local_directory":
        if not data.path:
            raise HTTPException(status_code=400, detail="local_directory 触发器需要 path 参数")
        kwargs["path"] = data.path
    elif data.trigger_type == "code_paste":
        if not data.code:
            raise HTTPException(status_code=400, detail="code_paste 触发器需要 code 参数")
        kwargs["code"] = data.code
        kwargs["filename"] = data.filename or "pasted_code.py"
    elif data.trigger_type == "cli":
        if not data.files:
            raise HTTPException(status_code=400, detail="cli 触发器需要 files 参数")
        kwargs["files"] = data.files

    result = await trigger.execute(**kwargs)

    return TriggerResponse(
        success=result.success,
        trigger_type=result.trigger_type,
        files=result.files,
        file_count=len(result.files),
        metadata=result.metadata,
        error=result.error,
    )


@router.post("/upload", response_model=TriggerResponse)
async def upload_file(file: UploadFile = File(...)):
    """上传文件触发器"""
    # 保存上传文件到临时位置
    upload_dir = Path("./uploads")
    upload_dir.mkdir(exist_ok=True)
    tmp_path = upload_dir / file.filename

    try:
        content = await file.read()
        tmp_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    # 执行触发器
    trigger = trigger_registry.create("file_upload")
    result = await trigger.execute(file_path=str(tmp_path))

    # 清理临时文件
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass

    return TriggerResponse(
        success=result.success,
        trigger_type=result.trigger_type,
        files=result.files,
        file_count=len(result.files),
        metadata=result.metadata,
        error=result.error,
    )
