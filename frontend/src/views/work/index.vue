<template>
  <section class="page" data-module="work">
    <header class="page-head">
      <div>
        <h2>养护施工管理</h2>
        <p class="page-desc">维护施工任务，围绕施工编号、关联计划、承接单位、开工日期做登记、筛选与状态流转；支持整组派工与承接单位工作量统计。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记施工任务</button>
        <button class="btn" type="button" @click="exportRows">导出养护施工清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="selectedIds.size" class="batch-bar">
      <span>已勾选 <strong>{{ selectedIds.size }}</strong> 条施工任务</span>
      <button class="btn primary" type="button" @click="openBatchDialog">整组指派</button>
      <button class="btn ghost" type="button" @click="selectedIds.clear()">清空选择</button>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="col-check"><input type="checkbox" :checked="allChecked" :indeterminate.prop="someChecked" @change="toggleAll" /></th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="col-check">
            <input type="checkbox" :checked="selectedIds.has(Number(row.id))" @change="toggleOne(Number(row.id))" />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
          <td><span class="status-tag" :data-status="row.status">{{ row.status }}</span></td>
          <td class="row-actions">
            <button
              v-if="row.status === '待开工'"
              class="link"
              type="button"
              @click="openSingleDialog(row)"
            >
              派工
            </button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 3" class="empty-state">暂无养护施工数据，可先登记施工任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条养护施工记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="workload-panel">
      <header class="workload-head">
        <h3>承接单位工作量</h3>
        <button class="btn ghost" type="button" @click="loadWorkload">刷新统计</button>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th>承接单位</th>
            <th>已派工合计</th>
            <th>待开工</th>
            <th>施工中</th>
            <th>待验收</th>
            <th>在途合计</th>
            <th>已完工</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in workload" :key="item['承接单位']">
            <td>{{ item['承接单位'] }}</td>
            <td>{{ item['已派工'] }}</td>
            <td>{{ item['待开工'] }}</td>
            <td>{{ item['施工中'] }}</td>
            <td>{{ item['待验收'] }}</td>
            <td><strong>{{ item['在途'] }}</strong></td>
            <td>{{ item['已完工'] }}</td>
          </tr>
          <tr v-if="!workload.length">
            <td colspan="7" class="empty-state">暂无工作量数据</td>
          </tr>
        </tbody>
      </table>
      <p class="workload-tip">统计与施工任务列表同源实时汇总，派工成功后立即同步。</p>
    </section>

    <!-- 派工弹窗：整组与单条共用 -->
    <div v-if="dialogVisible" class="modal-overlay" @click.self="closeDialog">
      <div class="modal">
        <header class="modal-head">
          <h3>{{ dialogMode === 'batch' ? '整组指派承接单位' : '派工给承接单位' }}</h3>
          <button class="modal-close" type="button" @click="closeDialog">×</button>
        </header>

        <!-- 第一步：预览 + 填写统一信息 -->
        <div v-if="dialogStep === 'form'" class="modal-body">
          <div v-if="dialogMode === 'batch'" class="preview-block">
            <p v-if="previewLoading" class="muted">正在核对勾选任务的施工状态…</p>
            <template v-else>
              <p class="preview-line">
                <span class="dot ok"></span>可派工 <strong>{{ preview.dispatchable_count }}</strong> 条
                <span class="dot skip"></span>在途/完工等不可派 <strong>{{ preview.blocked_count }}</strong> 条，将自动跳过
              </p>
              <ul v-if="preview.blocked.length" class="reason-list">
                <li v-for="item in preview.blocked" :key="String(item.id)">
                  <span class="reason-code">{{ item['施工编号'] || `任务#${item.id}` }}</span>
                  <span class="reason-text">{{ item.reason }}</span>
                </li>
              </ul>
            </template>
          </div>
          <div v-else class="preview-block">
            <p class="preview-line">
              <span class="muted">施工编号：</span>{{ singleRow && singleRow['施工编号'] }}
              <span class="muted">｜当前承接单位：</span>{{ (singleRow && singleRow['承接单位']) || '—' }}
            </p>
          </div>

          <form class="assign-form" @submit.prevent="submitAssign">
            <label class="filter-item">
              <span>承接单位 <i>*</i></span>
              <input v-model="assignForm.unit" list="unit-options" placeholder="统一指派给该承接单位" />
              <datalist id="unit-options">
                <option v-for="unit in unitOptions" :key="unit" :value="unit" />
              </datalist>
            </label>
            <label class="filter-item">
              <span>计划开工日期 <i>*</i></span>
              <input v-model="assignForm.planDate" type="date" />
            </label>
            <p v-if="formError" class="error-text">{{ formError }}</p>
            <div class="modal-actions">
              <button class="btn ghost" type="button" @click="closeDialog">取消</button>
              <button
                class="btn primary"
                type="submit"
                :disabled="submitLoading || (dialogMode === 'batch' && !preview.dispatchable_count)"
              >
                {{ submitLoading ? '提交中…' : (dialogMode === 'batch' ? `确认派工（${preview.dispatchable_count || 0} 条）` : '确认派工') }}
              </button>
            </div>
          </form>
        </div>

        <!-- 第二步：逐条结果，卡住的可单独重试 -->
        <div v-else class="modal-body">
          <p class="result-summary">{{ resultMessage }}</p>

          <section v-if="resultRows.assigned.length" class="result-group">
            <h4 class="result-title ok">成功 {{ resultRows.assigned.length }} 条</h4>
            <ul class="reason-list">
              <li v-for="item in resultRows.assigned" :key="String(item.id)">
                <span class="reason-code">{{ item['施工编号'] }}</span>
                <span class="reason-text">已指派给 {{ item['承接单位'] }}，计划开工 {{ item['计划开工日期'] }}</span>
              </li>
            </ul>
          </section>

          <section v-if="resultRows.skipped.length" class="result-group">
            <h4 class="result-title skip">跳过 {{ resultRows.skipped.length }} 条（在途施工，未处理）</h4>
            <ul class="reason-list">
              <li v-for="item in resultRows.skipped" :key="String(item.id)">
                <span class="reason-code">{{ item['施工编号'] || `任务#${item.id}` }}</span>
                <span class="reason-text">{{ item.reason }}</span>
              </li>
            </ul>
          </section>

          <section v-if="resultRows.failed.length" class="result-group">
            <h4 class="result-title fail">未成功 {{ resultRows.failed.length }} 条（可单独重试，不影响已成功的任务）</h4>
            <ul class="reason-list">
              <li v-for="item in resultRows.failed" :key="String(item.id)">
                <span class="reason-code">{{ item['施工编号'] || `任务#${item.id}` }}</span>
                <span class="reason-text">{{ item.reason }}</span>
                <button class="link retry-link" type="button" :disabled="item.retrying" @click="retryOne(item)">
                  {{ item.retrying ? '重试中…' : '单独重试' }}
                </button>
              </li>
            </ul>
          </section>

          <div class="modal-actions">
            <button class="btn primary" type="button" @click="finishDialog">完成</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type ReasonRow = {
  id: number | string
  ['施工编号']: string | null
  reason: string
  retrying?: boolean
}

const ENDPOINT = '/api/work'
const columns = ["施工编号", "关联计划", "承接单位", "计划开工日期", "开工日期", "完工日期", "完成工程量", "监理人员", "施工状态"]
const actions = ["确认开工", "提交验收", "确认完工"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const workload = ref<Array<Record<string, number | string>>>([])

const stats = computed(() => {
  let waiting = 0
  let ongoing = 0
  let finished = 0
  for (const item of workload.value) {
    waiting += Number(item['待开工']) || 0
    ongoing += Number(item['在途']) || 0
    finished += Number(item['已完工']) || 0
  }
  return [
    { label: "待开工施工", value: waiting },
    { label: "在途施工（施工中+待验收）", value: ongoing },
    { label: "已完工数", value: finished },
  ]
})

const unitOptions = computed(() => {
  const units = new Set<string>()
  for (const item of workload.value) units.add(String(item['承接单位']))
  for (const row of rows.value) {
    const unit = String(row['承接单位'] || '').trim()
    if (unit) units.add(unit)
  }
  return [...units]
})

// ---- 勾选 ----
const selectedIds = reactive(new Set<number>())
const allChecked = computed(() => rows.value.length > 0 && rows.value.every((row) => selectedIds.has(Number(row.id))))
const someChecked = computed(() => !allChecked.value && rows.value.some((row) => selectedIds.has(Number(row.id))))

function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  for (const row of rows.value) {
    const id = Number(row.id)
    if (checked) selectedIds.add(id)
    else selectedIds.delete(id)
  }
}

function toggleOne(id: number) {
  if (selectedIds.has(id)) selectedIds.delete(id)
  else selectedIds.add(id)
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '施工任务登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '养护施工动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadWorkload()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护施工操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('施工任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护施工列表读取失败'
  }
}

async function loadWorkload() {
  try {
    const response = await request(`${ENDPOINT}/workload`)
    if (!response.ok) return
    const payload = await response.json()
    workload.value = payload.items ?? []
  } catch {
    // 统计读取失败不阻断派工主流程
  }
}

// ---- 派工弹窗 ----
const dialogVisible = ref(false)
const dialogStep = ref<'form' | 'result'>('form')
const dialogMode = ref<'batch' | 'single'>('batch')
const singleRow = ref<Row | null>(null)
const previewLoading = ref(false)
const submitLoading = ref(false)
const formError = ref('')
const resultMessage = ref('')
const assignForm = reactive({ unit: '', planDate: '' })
const preview = reactive({
  dispatchable: [] as Row[],
  blocked: [] as ReasonRow[],
  dispatchable_count: 0,
  blocked_count: 0,
})
const resultRows = reactive({
  assigned: [] as Row[],
  skipped: [] as ReasonRow[],
  failed: [] as ReasonRow[],
})

function todayISO() {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function resetDialogState() {
  dialogStep.value = 'form'
  formError.value = ''
  resultMessage.value = ''
  preview.dispatchable = []
  preview.blocked = []
  preview.dispatchable_count = 0
  preview.blocked_count = 0
  resultRows.assigned = []
  resultRows.skipped = []
  resultRows.failed = []
}

async function openBatchDialog() {
  if (!selectedIds.size) return
  resetDialogState()
  dialogMode.value = 'batch'
  singleRow.value = null
  assignForm.unit = ''
  assignForm.planDate = todayISO()
  dialogVisible.value = true
  previewLoading.value = true
  try {
    const response = await request(`${ENDPOINT}/assign-preview`, {
      method: 'POST',
      body: JSON.stringify({ entry_ids: [...selectedIds] }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail || '派工预演失败')
    }
    Object.assign(preview, {
      dispatchable: payload.dispatchable ?? [],
      blocked: (payload.blocked ?? []).map((item: ReasonRow) => ({ ...item })),
      dispatchable_count: payload.dispatchable_count ?? 0,
      blocked_count: payload.blocked_count ?? 0,
    })
    if (preview.dispatchable[0]) {
      assignForm.unit = String(preview.dispatchable[0]['承接单位'] || '')
    }
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '派工预演失败'
  } finally {
    previewLoading.value = false
  }
}

function openSingleDialog(row: Row) {
  resetDialogState()
  dialogMode.value = 'single'
  singleRow.value = row
  assignForm.unit = String(row['承接单位'] || '')
  assignForm.planDate = String(row['计划开工日期'] || '') || todayISO()
  dialogVisible.value = true
}

function closeDialog() {
  dialogVisible.value = false
}

async function submitAssign() {
  formError.value = ''
  if (!assignForm.unit.trim()) {
    formError.value = '请填写承接单位'
    return
  }
  if (!assignForm.planDate) {
    formError.value = '请选择计划开工日期'
    return
  }
  submitLoading.value = true
  try {
    if (dialogMode.value === 'batch') {
      const ids = preview.dispatchable.map((item) => item.id)
      const response = await request(`${ENDPOINT}/batch-assign`, {
        method: 'POST',
        body: JSON.stringify({
          entry_ids: ids,
          承接单位: assignForm.unit.trim(),
          计划开工日期: assignForm.planDate,
        }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(payload?.detail || '整组派工未提交成功')
      }
      resultRows.assigned = payload.assigned ?? []
      resultRows.skipped = payload.skipped ?? []
      resultRows.failed = (payload.failed ?? []).map((item: ReasonRow) => ({ ...item }))
      resultMessage.value = payload.message || ''
    } else if (singleRow.value) {
      const id = singleRow.value.id
      const response = await request(`${ENDPOINT}/${id}/assign`, {
        method: 'POST',
        body: JSON.stringify({
          values: { 承接单位: assignForm.unit.trim(), 计划开工日期: assignForm.planDate },
        }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(payload?.detail || '派工未提交成功')
      }
      if (payload.ok) {
        resultRows.assigned = payload.entry ? [payload.entry] : []
        resultMessage.value = payload.message || '派工成功'
      } else {
        resultRows.failed = [{ id: Number(id), '施工编号': String(singleRow.value['施工编号'] || ''), reason: payload.message || '派工失败' }]
        resultMessage.value = '该任务未派工成功，可调整后单独重试'
      }
    }
    dialogStep.value = 'result'
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '派工提交失败，请稍后重试'
  } finally {
    submitLoading.value = false
  }
}

async function retryOne(item: ReasonRow) {
  item.retrying = true
  try {
    const response = await request(`${ENDPOINT}/${item.id}/assign`, {
      method: 'POST',
      body: JSON.stringify({
        values: { 承接单位: assignForm.unit.trim(), 计划开工日期: assignForm.planDate },
      }),
    })
    const payload = await response.json().catch(() => null)
    if (payload?.ok && payload.entry) {
      const index = resultRows.failed.findIndex((row) => String(row.id) === String(item.id))
      if (index >= 0) resultRows.failed.splice(index, 1)
      resultRows.assigned.push(payload.entry as Row)
      resultMessage.value = `重试成功：${payload.entry['施工编号']} 已派工；其余任务未受影响`
    } else {
      item.reason = payload?.message || '重试仍未成功'
    }
  } catch (error) {
    item.reason = error instanceof Error ? error.message : '重试请求失败'
  } finally {
    item.retrying = false
  }
}

async function finishDialog() {
  dialogVisible.value = false
  selectedIds.clear()
  await Promise.all([reload(), loadWorkload()])
}

onMounted(() => {
  void reload()
  void loadWorkload()
})
</script>
