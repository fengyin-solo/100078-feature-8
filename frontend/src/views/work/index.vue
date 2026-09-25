<template>
  <section class="page" data-module="work">
    <header class="page-head">
      <div>
        <h2>养护施工管理</h2>
        <p class="page-desc">维护施工任务，围绕施工编号、关联计划、承接单位、开工日期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记施工任务</button>
        <button class="btn" type="button" :disabled="!selectedIds.length" @click="openAssign()">
          整组指派{{ selectedIds.length ? `（已选 ${selectedIds.length} 条）` : '' }}
        </button>
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

    <section v-if="assignPanel.visible" class="assign-panel">
      <header class="assign-head">
        <h3>整组指派施工任务</h3>
        <button class="link" type="button" @click="closeAssign">关闭</button>
      </header>

      <template v-if="!assignPanel.results">
        <p class="assign-summary">
          可指派 {{ assignPanel.assignable.length }} 条；
          <template v-if="assignPanel.blocked.length">
            {{ assignPanel.blocked.length }} 条存在在途施工或其他原因，已自动剔除，本次不会处理
          </template>
          <template v-else>选中的任务全部可派</template>
        </p>
        <table v-if="assignPanel.assignable.length" class="data-table">
          <thead>
            <tr><th>施工编号</th><th>关联计划</th><th>当前承接单位</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in assignPanel.assignable" :key="String(row.id)">
              <td>{{ row['施工编号'] }}</td>
              <td>{{ row['关联计划'] || '—' }}</td>
              <td>{{ row['承接单位'] || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <table v-if="assignPanel.blocked.length" class="data-table blocked-table">
          <thead>
            <tr><th>施工编号</th><th>不能指派的原因</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in assignPanel.blocked" :key="String(row.id)">
              <td>{{ row['施工编号'] || `任务 ${row.id}` }}</td>
              <td>{{ row.reason }}</td>
            </tr>
          </tbody>
        </table>
        <form class="assign-form" @submit.prevent="submitAssign(assignPanel.assignable.map(row => Number(row.id)))">
          <label class="filter-item">
            <span>承接单位</span>
            <input v-model="assignPanel.contractor" placeholder="整组统一指派给该单位" />
          </label>
          <label class="filter-item">
            <span>计划开工日期</span>
            <input v-model="assignPanel.startDate" type="date" />
          </label>
          <button class="btn primary" type="submit" :disabled="!assignPanel.assignable.length || assignPanel.submitting">
            确认指派 {{ assignPanel.assignable.length }} 条
          </button>
        </form>
      </template>

      <template v-else>
        <p class="assign-summary">{{ assignPanel.message }}</p>
        <table class="data-table">
          <thead>
            <tr><th>施工编号</th><th>结果</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in assignPanel.results" :key="String(row.id)">
              <td>{{ row['施工编号'] || `任务 ${row.id}` }}</td>
              <td :class="row.ok ? 'result-ok' : 'result-fail'">{{ row.ok ? '成功' : '未成功' }}</td>
              <td>{{ row.message }}</td>
            </tr>
          </tbody>
        </table>
        <div class="assign-result-actions">
          <button v-if="failedResults.length" class="btn primary" type="button" :disabled="assignPanel.submitting" @click="retryFailed">
            仅重试未成功的 {{ failedResults.length }} 条
          </button>
          <button class="btn" type="button" @click="closeAssign">完成</button>
        </div>
      </template>
      <p v-if="assignPanel.error" class="error-text">{{ assignPanel.error }}</p>
    </section>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col"><input type="checkbox" :checked="allChecked" @change="toggleAll" /></th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input type="checkbox" :checked="selectedIds.includes(Number(row.id))" @change="toggleRow(Number(row.id))" />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openAssign([Number(row.id)])">指派</button>
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
          <td :colspan="columns.length + 2" class="empty-state">暂无养护施工数据，可先登记施工任务</td>
        </tr>
      </tbody>
    </table>

    <section class="workload">
      <h3>承接单位工作量</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>承接单位</th>
            <th v-for="status in statuses" :key="status">{{ status }}</th>
            <th>合计</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in workload" :key="String(item['承接单位'])">
            <td>{{ item['承接单位'] }}</td>
            <td v-for="status in statuses" :key="status">{{ item[status] }}</td>
            <td>{{ item['合计'] }}</td>
          </tr>
          <tr v-if="!workload.length">
            <td :colspan="statuses.length + 2" class="empty-state">暂无承接单位工作量数据</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条养护施工记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type BlockedRow = { id: number | string; 施工编号?: string | null; reason: string }
type AssignResultRow = { id: number | string; 施工编号?: string | null; ok: boolean; message: string }

const ENDPOINT = '/api/work'
const columns = ["施工编号", "关联计划", "承接单位", "开工日期", "完工日期", "完成工程量", "监理人员", "施工状态"]
const actions = ["确认开工", "提交验收", "确认完工"]
const statuses = ["待开工", "施工中", "待验收", "已完工"]
const stats = [{"label": "待开工施工", "value": 0}, {"label": "施工中单据", "value": 0}, {"label": "本月完工数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const selectedIds = ref<number[]>([])
const workload = ref<Array<Record<string, string | number>>>([])

const assignPanel = ref({
  visible: false,
  submitting: false,
  contractor: '',
  startDate: '',
  assignable: [] as Row[],
  blocked: [] as BlockedRow[],
  results: null as AssignResultRow[] | null,
  message: '',
  error: '',
})

const allChecked = computed(() => rows.value.length > 0 && rows.value.every(row => selectedIds.value.includes(Number(row.id))))
const failedResults = computed(() => (assignPanel.value.results ?? []).filter(item => !item.ok))

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

function toggleRow(id: number) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter(item => item !== id)
    : [...selectedIds.value, id]
}

function toggleAll() {
  selectedIds.value = allChecked.value ? [] : rows.value.map(row => Number(row.id))
}

async function openAssign(ids?: number[]) {
  const targets = ids ?? selectedIds.value
  if (!targets.length) {
    errorMessage.value = '请先勾选要指派的施工任务'
    return
  }
  errorMessage.value = ''
  assignPanel.value = {
    visible: true,
    submitting: false,
    contractor: '',
    startDate: '',
    assignable: [],
    blocked: [],
    results: null,
    message: '',
    error: '',
  }
  try {
    const response = await request(`${ENDPOINT}/assign/preview`, {
      method: 'POST',
      body: JSON.stringify({ ids: targets }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload?.detail ?? '指派预检失败，请稍后重试')
    }
    assignPanel.value.assignable = payload.assignable ?? []
    assignPanel.value.blocked = payload.blocked ?? []
    if (assignPanel.value.assignable.length === 1) {
      const only = assignPanel.value.assignable[0]
      assignPanel.value.contractor = String(only['承接单位'] ?? '')
      assignPanel.value.startDate = String(only['开工日期'] ?? '')
    }
  } catch (error) {
    assignPanel.value.error = error instanceof Error ? error.message : '指派预检失败'
  }
}

async function submitAssign(ids: Array<number | string>) {
  if (!ids.length || assignPanel.value.submitting) {
    return
  }
  assignPanel.value.submitting = true
  assignPanel.value.error = ''
  try {
    const response = await request(`${ENDPOINT}/assign`, {
      method: 'POST',
      body: JSON.stringify({
        ids,
        承接单位: assignPanel.value.contractor,
        开工日期: assignPanel.value.startDate,
      }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload?.detail ?? '整组指派未生效，请稍后重试')
    }
    if (payload.results?.length) {
      assignPanel.value.results = payload.results
      assignPanel.value.message = payload.message ?? ''
      await Promise.all([reload(), reloadWorkload()])
    } else {
      assignPanel.value.error = payload.message ?? '整组指派未生效'
    }
  } catch (error) {
    assignPanel.value.error = error instanceof Error ? error.message : '整组指派失败'
  } finally {
    assignPanel.value.submitting = false
  }
}

function retryFailed() {
  void submitAssign(failedResults.value.map(item => item.id))
}

function closeAssign() {
  assignPanel.value.visible = false
  selectedIds.value = []
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('养护施工动作未生效，请稍后重试')
    }
    await Promise.all([reload(), reloadWorkload()])
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

async function reloadWorkload() {
  try {
    const response = await request(`${ENDPOINT}/workload`)
    if (!response.ok) {
      throw new Error('承接单位工作量统计读取失败')
    }
    const payload = await response.json()
    workload.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '承接单位工作量统计读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadWorkload()
})
</script>
