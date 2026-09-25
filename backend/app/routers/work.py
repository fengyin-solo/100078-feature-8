"""养护施工接口：维护施工任务，覆盖整组指派、确认开工、提交验收、确认完工等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, AssignResult, EntryPayload, PageResult
from app.services.work import WorkService

router = APIRouter(prefix="/api/work", tags=["养护施工"])

service = WorkService()

LIST_FIELDS = ["施工编号", "关联计划", "承接单位", "开工日期", "完工日期", "完成工程量", "监理人员", "施工状态"]
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


@router.get("/workload")
def contractor_workload() -> dict[str, Any]:
    """承接单位工作量统计：按承接单位汇总各状态施工任务数，与施工任务列表同源。"""
    items = service.contractor_workload()
    return {"items": items, "total": len(items)}


@router.post("/assign/preview")
def preview_assign(payload: EntryPayload) -> dict[str, Any]:
    """整组指派前预检：把存在在途施工、已完工或不存在的任务挑出来，只留能派的。"""
    return service.preview_assign(payload.values.get("ids"))


@router.post("/assign", response_model=AssignResult)
def assign_entries(payload: EntryPayload) -> AssignResult:
    """把选中的施工任务整组指派给同一承接单位，并统一计划开工日期。

    逐条处理：每条独立成功或失败，未成功的明细随 results 返回，可单独重试；
    已成功的不会回滚。ids 只传一个时就是单条派工。
    """
    results, error = service.batch_assign(
        payload.values.get("ids"),
        payload.values.get("承接单位"),
        payload.values.get("开工日期"),
    )
    if error is not None:
        return AssignResult(ok=False, message=error)
    succeeded = sum(1 for item in results if item["ok"])
    failed = len(results) - succeeded
    if failed:
        message = f"已指派 {succeeded} 条，{failed} 条未成功，可单独重试未成功的任务"
    else:
        message = f"已整组指派 {succeeded} 条施工任务"
    return AssignResult(ok=failed == 0, message=message, results=results)


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


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条施工任务执行确认开工、提交验收、确认完工；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出养护施工清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "work", "total": total, "items": items}
