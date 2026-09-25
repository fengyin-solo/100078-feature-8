"""养护施工业务规则：状态流转、字段校验、批量派工与筛选口径都收在这里。"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "work"
REQUIRED_FIELDS = ["施工编号", "关联计划", "承接单位"]
STATUS_ORDER = ["待开工", "施工中", "待验收", "已完工"]
ACTION_RULES = {"确认开工": "施工中", "提交验收": "待验收", "确认完工": "已完工"}
NEGATIVE_ACTIONS = []

DISPATCH_STATUS = STATUS_ORDER[0]  # 只有「待开工」允许派工
ONGOING_STATUSES = {"施工中", "待验收"}  # 已经在途施工，不能重复派工
FINISHED_STATUS = STATUS_ORDER[-1]
PLAN_DATE_FIELD = "计划开工日期"
PLAN_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_plan_date(value: Any) -> tuple[str, str]:
    """校验计划开工日期，统一返回 YYYY-MM-DD 文本与不可派工原因。"""
    text = str(value or "").strip()
    if not text:
        return "", "计划开工日期不能为空"
    if not PLAN_DATE_PATTERN.match(text):
        return "", "计划开工日期格式应为 YYYY-MM-DD"
    try:
        date.fromisoformat(text)
    except ValueError:
        return "", "计划开工日期不是有效的日历日期"
    return text, ""


class WorkService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("施工编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry[PLAN_DATE_FIELD] = ""
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"施工任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于养护施工可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"施工任务已{action}"

    # ---- 派工 -------------------------------------------------------------

    def validate_assign_payload(self, values: dict[str, Any]) -> tuple[str, str, str]:
        """整组/单条派工共用的入参校验，返回承接单位、计划开工日期与错误说明。"""
        unit = str(values.get("承接单位") or "").strip()
        if not unit:
            return "", "", "承接单位不能为空"
        plan_date, error = parse_plan_date(values.get(PLAN_DATE_FIELD))
        if error:
            return "", "", error
        return unit, plan_date, ""

    def classify(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """判定一条任务能不能派工：可派时返回任务本身，否则返回可读的拦截原因。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"施工任务 {entry_id} 不存在或已归档"
        status = str(entry.get("status") or "")
        if status in ONGOING_STATUSES:
            return None, f"任务已在途施工（当前状态：{status}），不能重复派工"
        if status == FINISHED_STATUS:
            return None, "任务已完工，无需派工"
        if status != DISPATCH_STATUS:
            return None, f"当前状态「{status}」不允许派工"
        return entry, ""

    def assign_entry(
        self, entry_id: int, unit: str, plan_date: str
    ) -> tuple[dict[str, Any] | None, str]:
        """单条派工：资格判定通过后写入承接单位与计划开工日期，状态仍停在待开工。"""
        entry, reason = self.classify(entry_id)
        if entry is None:
            return None, reason
        entry["承接单位"] = unit
        entry[PLAN_DATE_FIELD] = plan_date
        return entry, ""

    def preview_assign(self, entry_ids: list[Any]) -> dict[str, Any]:
        """派工前预演：把在途/完工/不存在的任务挑出来，只留下能派的那些。"""
        dispatchable: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        seen: set[int] = set()
        for raw in entry_ids:
            try:
                entry_id = int(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                blocked.append({"id": raw, "施工编号": None, "reason": "任务编号不是有效整数"})
                continue
            if entry_id in seen:
                # 同一任务在勾选结果里重复出现时合并处理，不拦截整组提交。
                continue
            seen.add(entry_id)
            entry, reason = self.classify(entry_id)
            if entry is None:
                row = store.find(MODULE, entry_id)
                code = row.get("施工编号") if row is not None else None
                blocked.append({"id": entry_id, "施工编号": code, "reason": reason})
            else:
                dispatchable.append(entry)
        return {
            "dispatchable": dispatchable,
            "blocked": blocked,
            "dispatchable_count": len(dispatchable),
            "blocked_count": len(blocked),
            "total": len(dispatchable) + len(blocked),
        }

    def batch_assign(
        self, entry_ids: list[Any], unit: str, plan_date: str
    ) -> dict[str, Any]:
        """整组派工：逐条判定、逐条落库，某条卡住不影响同组其它任务。

        - assigned：本次成功派工的任务；
        - skipped：指派前挑出的在途/完工任务，按要求不处理；
        - failed：提交后仍派不下去的任务（如已被归档），供前端单独重试。
        """
        assigned: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        seen: set[int] = set()
        for raw in entry_ids:
            try:
                entry_id = int(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                failed.append({"id": raw, "施工编号": None, "reason": "任务编号不是有效整数"})
                continue
            if entry_id in seen:
                continue
            seen.add(entry_id)
            entry, reason = self.classify(entry_id)
            if entry is None:
                target = skipped if ("在途" in reason or "完工" in reason) else failed
                row = store.find(MODULE, entry_id)
                code = row.get("施工编号") if row is not None else None
                target.append({"id": entry_id, "施工编号": code, "reason": reason})
                continue
            entry["承接单位"] = unit
            entry[PLAN_DATE_FIELD] = plan_date
            assigned.append(entry)
        return {
            "assigned": assigned,
            "skipped": skipped,
            "failed": failed,
            "assigned_count": len(assigned),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
        }

    def workload(self) -> list[dict[str, Any]]:
        """承接单位工作量：直接从施工任务表实时汇总，保证与列表口径一致。"""
        groups: dict[str, dict[str, Any]] = {}
        for row in store.rows(MODULE):
            unit = str(row.get("承接单位") or "").strip() or "未指派"
            item = groups.setdefault(unit, {
                "承接单位": unit,
                "已派工": 0,
                "待开工": 0,
                "施工中": 0,
                "待验收": 0,
                "已完工": 0,
                "在途": 0,
            })
            item["已派工"] += 1
            status = str(row.get("status") or "")
            if status in STATUS_ORDER:
                item[status] += 1
            if status in ONGOING_STATUSES:
                item["在途"] += 1
        return sorted(groups.values(), key=lambda item: (-int(item["已派工"]), str(item["承接单位"])))
