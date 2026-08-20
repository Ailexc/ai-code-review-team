"""项目管理 API"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.core.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse

router = APIRouter()


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    language: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = Query(None, description="搜索项目名称或描述"),
    db: AsyncSession = Depends(get_db),
):
    """获取项目列表"""
    query = select(Project)
    count_query = select(func.count(Project.id))

    # 搜索条件
    if search:
        like_pattern = f"%{search}%"
        query = query.where(
            (Project.name.ilike(like_pattern)) | (Project.description.ilike(like_pattern))
        )
        count_query = count_query.where(
            (Project.name.ilike(like_pattern)) | (Project.description.ilike(like_pattern))
        )
    # 筛选条件
    if language:
        query = query.where(Project.language == language)
        count_query = count_query.where(Project.language == language)
    if is_active is not None:
        query = query.where(Project.is_active == is_active)
        count_query = count_query.where(Project.is_active == is_active)

    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Project.created_at.desc())

    # 执行查询
    result = await db.execute(query)
    projects = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建项目"""
    # 检查路径是否已存在
    existing = await db.execute(select(Project).where(Project.path == data.path))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="项目路径已存在")

    project = Project(**data.model_dump())
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取项目详情"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return ProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新项目"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.flush()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除项目"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    await db.delete(project)
