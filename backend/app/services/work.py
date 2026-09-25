"""养护施工业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "work"
REQUIRED_FIELDS = ["施工编号", "关联计划", "承接单位"]
STATUS_ORDER = ["待开工", "施工中", "待验收", "已完工"]
ACTION_RULES = {"确认开工": "施工中", "提交验收": "待验收", "确认完工": "已完工"}
NEGATIVE_ACTIONS = []

ASSIGNABLE_STATUS = "待开工"
IN_FLIGHT_STATUSES = {"施工中", "待验收"}
UNASSIGNED_LABEL = "（未指派）"


def normalize_ids(raw_ids: Any) -> tuple[list[int], list[str]]:
    """把前端提交的 id 列表拆成可解析的整数 id 与无法识别的原始值。"""
    if raw_ids is None:
        return [], []
    items = raw_ids if isinstance(raw_ids, (list, tuple)) else [raw_ids]
    ids: list[int] = []
    invalid: list[str] = []
    for item in items:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            invalid.append(str(item))
    return ids, invalid


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

    @staticmethod
    def _assign_block_reason(entry: dict[str, Any] | None, entry_id: int) -> str | None:
        """该任务当前不能指派的原因；可以指派时返回 None。"""
        if entry is None:
            return f"施工任务 {entry_id} 不存在或已归档"
        status = str(entry.get("status") or "")
        if status in IN_FLIGHT_STATUSES:
            return f"已存在在途施工（{status}），不能重复指派"
        if status == STATUS_ORDER[-1]:
            return "施工任务已完工，不能再指派"
        if status != ASSIGNABLE_STATUS:
            return f"当前状态「{status or '未知'}」不允许指派"
        return None

    @staticmethod
    def _assign_values_error(contractor: str, start_date: str) -> str | None:
        if not contractor:
            return "承接单位不能为空"
        if not start_date:
            return "计划开工日期不能为空"
        try:
            date.fromisoformat(start_date)
        except ValueError:
            return f"计划开工日期「{start_date}」不是有效的 YYYY-MM-DD 日期"
        return None

    def preview_assign(self, raw_ids: Any) -> dict[str, Any]:
        """指派前预检：把可指派的与卡在门外的（含原因）分开，不改动任何数据。"""
        ids, invalid = normalize_ids(raw_ids)
        assignable: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = [
            {"id": item, "施工编号": None, "reason": f"任务标识「{item}」无法识别"}
            for item in invalid
        ]
        for entry_id in dict.fromkeys(ids):
            entry = store.find(MODULE, entry_id)
            reason = self._assign_block_reason(entry, entry_id)
            if reason is None and entry is not None:
                assignable.append(entry)
            else:
                blocked.append({
                    "id": entry_id,
                    "施工编号": (entry or {}).get("施工编号"),
                    "reason": reason,
                })
        return {"assignable": assignable, "blocked": blocked}

    def batch_assign(
        self,
        raw_ids: Any,
        contractor: Any,
        start_date: Any,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """整组指派：逐条校验、逐条落库；单条失败只影响自己，已成功的照常生效。"""
        ids, invalid = normalize_ids(raw_ids)
        if not ids and not invalid:
            return [], "请先选择要指派的施工任务"
        contractor_text = str(contractor or "").strip()
        start_date_text = str(start_date or "").strip()
        values_error = self._assign_values_error(contractor_text, start_date_text)
        if values_error is not None:
            return [], values_error
        results: list[dict[str, Any]] = [
            {"id": item, "施工编号": None, "ok": False, "message": f"任务标识「{item}」无法识别"}
            for item in invalid
        ]
        for entry_id in dict.fromkeys(ids):
            entry = store.find(MODULE, entry_id)
            reason = self._assign_block_reason(entry, entry_id)
            if reason is None and entry is not None:
                entry["承接单位"] = contractor_text
                entry["开工日期"] = start_date_text
                results.append({
                    "id": entry_id,
                    "施工编号": entry.get("施工编号"),
                    "ok": True,
                    "message": "指派成功",
                })
            else:
                results.append({
                    "id": entry_id,
                    "施工编号": (entry or {}).get("施工编号"),
                    "ok": False,
                    "message": reason,
                })
        return results, None

    def contractor_workload(self) -> list[dict[str, Any]]:
        """按承接单位汇总工作量；与施工任务列表读同一份数据，指派后两边同步变化。"""
        buckets: dict[str, dict[str, Any]] = {}
        for row in store.rows(MODULE):
            contractor = str(row.get("承接单位") or "").strip() or UNASSIGNED_LABEL
            bucket = buckets.setdefault(
                contractor,
                {"承接单位": contractor, "合计": 0, **{status: 0 for status in STATUS_ORDER}},
            )
            status = str(row.get("status") or "")
            if status in STATUS_ORDER:
                bucket[status] += 1
            bucket["合计"] += 1
        return sorted(buckets.values(), key=lambda item: (-int(item["合计"]), str(item["承接单位"])))
