"""养护施工接口：维护施工任务，覆盖派工、确认开工、提交验收、确认完工等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    BatchAssignPayload,
    BatchAssignPreviewResult,
    BatchAssignResult,
    EntryPayload,
    PageResult,
)
from app.services.work import WorkService

router = APIRouter(prefix="/api/work", tags=["养护施工"])

service = WorkService()

LIST_FIELDS = ["施工编号", "关联计划", "承接单位", "计划开工日期", "开工日期", "完工日期", "完成工程量", "监理人员", "施工状态"]
STATUSES = ["待开工", "施工中", "待验收", "已完工"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按施工编号检索"),
    status: str | None = Query(default=None, description="待开工、施工中、待验收、已完工"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按施工编号与状态过滤养护施工列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/assign-preview", response_model=BatchAssignPreviewResult)
def assign_preview(payload: BatchAssignPayload) -> BatchAssignPreviewResult:
    """整组派工前预演：先挑出在途施工/已完工/不存在的任务，只让能派的进入下一步。"""
    ids = list(dict.fromkeys(payload.entry_ids))
    if not ids:
        raise HTTPException(status_code=400, detail="请至少勾选一条施工任务")
    result = service.preview_assign(ids)
    message = f"可派工 {result['dispatchable_count']} 条；另有 {result['blocked_count']} 条无法派工，将被跳过"
    return BatchAssignPreviewResult(message=message, **result)


@router.post("/batch-assign", response_model=BatchAssignResult)
def batch_assign(payload: BatchAssignPayload) -> BatchAssignResult:
    """整组派工：多条任务统一指派给同一承接单位、统一计划开工日期。

    逐条判定逐条落库，部分卡住不影响其它条目；卡住的条目带原因返回，可单独重试。
    """
    if not payload.entry_ids:
        raise HTTPException(status_code=400, detail="请至少勾选一条施工任务")
    unit, plan_date, error = service.validate_assign_payload(
        {"承接单位": payload.承接单位, "计划开工日期": payload.计划开工日期}
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    result = service.batch_assign(list(dict.fromkeys(payload.entry_ids)), unit, plan_date)
    if result["assigned_count"]:
        message = (
            f"成功派工 {result['assigned_count']} 条"
            + (f"，跳过 {result['skipped_count']} 条" if result["skipped_count"] else "")
            + (f"，失败 {result['failed_count']} 条" if result["failed_count"] else "")
        )
    else:
        message = "没有任何任务派工成功，请按失败原因调整后重试"
    return BatchAssignResult(ok=bool(result["assigned_count"]), message=message, **result)


@router.get("/workload")
def workload() -> dict[str, Any]:
    """承接单位工作量统计：与施工任务列表同源实时汇总，派工完成后口径同步更新。"""
    items = service.workload()
    return {"items": items, "total": len(items)}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出养护施工清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "work", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条施工任务明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"施工任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条施工任务，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="施工任务已登记", entry=entry)


@router.post("/{entry_id}/assign", response_model=ActionResult)
def assign_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """单条派工（也用于整组派工后对卡住任务的单独重试），不影响其它任务。"""
    unit, plan_date, error = service.validate_assign_payload(payload.values)
    if error:
        return ActionResult(ok=False, message=error)
    entry, message = service.assign_entry(entry_id, unit, plan_date)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="施工任务已派工", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条施工任务执行确认开工、提交验收、确认完工；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
