<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useAnalyticsData } from '../composables/useAnalyticsData.js'
import apiClient from '../api/index.js'

// ECharts tree-shakable imports
import * as echarts from 'echarts/core'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  PieChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  CanvasRenderer
])

// --- Color constants ---
// Keyword-based color mapping for leave types (matches by substring)
const LEAVE_COLOR_KEYWORDS = [
  { keyword: '年假', color: '#2563EB' },
  { keyword: '事假', color: '#B45309' },
  { keyword: '病假', color: '#DC2626' },
  { keyword: '调休', color: '#059669' },
  { keyword: '婚假', color: '#7C3AED' },
  { keyword: '产假', color: '#DB2777' },
  { keyword: '育儿', color: '#0891B2' },
  { keyword: '丧假', color: '#6B7280' },
  { keyword: '生日', color: '#EA580C' },
]
const FALLBACK_PALETTE = ['#4F46E5', '#65A30D', '#0D9488', '#BE185D', '#9333EA', '#CA8A04']

/** Get color for a leave type name via keyword matching with fallback palette */
function getLeaveColor(typeName, fallbackIndex = 0) {
  const match = LEAVE_COLOR_KEYWORDS.find(k => typeName.includes(k.keyword))
  if (match) return match.color
  return FALLBACK_PALETTE[fallbackIndex % FALLBACK_PALETTE.length]
}

// --- Year options ---
const currentYear = new Date().getFullYear()
const yearOptions = [currentYear, currentYear - 1]

// --- Analytics data ---
const {
  year,
  loading,
  monthlyTrend,
  leaveTypeDistribution,
  departmentComparison,
  weekdayDistribution,
  employeeRanking,
  fetchAll,
  switchYear
} = useAnalyticsData()

// --- Department comparison metric toggle ---
const deptMetric = ref('total')

// --- Chart DOM refs ---
const trendChartRef = ref(null)
const pieChartRef = ref(null)
const deptChartRef = ref(null)
const weekdayChartRef = ref(null)
const rankingChartRef = ref(null)

// --- Chart instances ---
let trendChart = null
let pieChart = null
let deptChart = null
let weekdayChart = null
let rankingChart = null

// --- Computed: total days for pie center label ---
const pieTotal = computed(() => {
  if (!leaveTypeDistribution.value) return 0
  return leaveTypeDistribution.value.total || 0
})

// --- Chart rendering functions ---

/**
 * Ensure an ECharts instance is valid for the given DOM ref.
 * If the DOM container changed (e.g., after v-if toggle), dispose old instance and re-init.
 */
function ensureChartInstance(instance, domRef) {
  if (instance && instance.getDom() !== domRef.value) {
    instance.dispose()
    instance = null
  }
  if (!instance) {
    instance = echarts.init(domRef.value)
  }
  return instance
}

/**
 * Render the monthly trend line chart.
 */
function renderTrendChart() {
  if (!trendChartRef.value) return
  trendChart = ensureChartInstance(trendChart, trendChartRef)

  const data = monthlyTrend.value
  const currentData = data?.currentYear?.map(i => i.days) || Array(12).fill(0)
  const previousData = data?.previousYear?.map(i => i.days) || Array(12).fill(0)
  const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#fff',
      borderColor: '#E4E4E7',
      borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      valueFormatter: (value) => `${value}天`
    },
    legend: {
      data: [`${year.value}年`, `${year.value - 1}年`],
      top: 0,
      right: 0,
      textStyle: { fontSize: 12, color: '#71717A' },
      itemWidth: 16,
      itemHeight: 2
    },
    grid: {
      top: 36,
      left: 12,
      right: 12,
      bottom: 4,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: months,
      boundaryGap: false,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#F4F4F5', type: 'dashed' } },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    series: [
      {
        name: `${year.value}年`,
        type: 'line',
        data: currentData,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        showSymbol: false,
        itemStyle: { color: '#2563EB' },
        lineStyle: { width: 2.5, color: '#2563EB' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(37, 99, 235, 0.15)' },
            { offset: 1, color: 'rgba(37, 99, 235, 0.01)' }
          ])
        }
      },
      {
        name: `${year.value - 1}年`,
        type: 'line',
        data: previousData,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        showSymbol: false,
        itemStyle: { color: '#E4E4E7' },
        lineStyle: { width: 2, color: '#E4E4E7', type: 'dashed' }
      }
    ]
  }, true)
}

/**
 * Render the leave type distribution pie/doughnut chart.
 */
function renderPieChart() {
  if (!pieChartRef.value) return
  pieChart = ensureChartInstance(pieChart, pieChartRef)

  const raw = leaveTypeDistribution.value
  const data = raw?.items || []
  const total = pieTotal.value

  pieChart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: '#fff',
      borderColor: '#E4E4E7',
      borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      formatter: (params) => {
        return `${params.name}: ${params.value}天 (${params.percent}%)`
      }
    },
    graphic: [
      {
        id: 'pie-total-value',
        type: 'text',
        left: 'center',
        top: '42%',
        style: {
          text: `${total}`,
          textAlign: 'center',
          fill: '#18181B',
          fontSize: 22,
          fontWeight: 600
        }
      },
      {
        id: 'pie-total-label',
        type: 'text',
        left: 'center',
        top: '55%',
        style: {
          text: '总天数',
          textAlign: 'center',
          fill: '#A1A1AA',
          fontSize: 12
        }
      }
    ],
    series: [
      {
        type: 'pie',
        radius: ['65%', '88%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        data: data.map((item, idx) => ({
          name: item.type,
          value: item.days,
          itemStyle: { color: getLeaveColor(item.type, idx) }
        }))
      }
    ]
  }, true)
}

/**
 * Render the department comparison horizontal bar chart.
 */
function renderDeptChart() {
  if (!deptChartRef.value) return
  deptChart = ensureChartInstance(deptChart, deptChartRef)

  const raw = departmentComparison.value
  const items = raw?.departments || []
  const sortKey = deptMetric.value === 'avg' ? 'avgDays' : 'totalDays'
  // Sort descending, take top 10, then reverse for horizontal bar (top at top)
  const top = [...items].sort((a, b) => b[sortKey] - a[sortKey]).slice(0, 10)
  const sorted = [...top].reverse()
  const depts = sorted.map(d => d.name)
  const values = sorted.map(d => d[sortKey])
  const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0

  // Dynamically resize chart height based on item count
  const chartHeight = Math.max(250, sorted.length * 32 + 60)
  deptChartRef.value.style.height = `${chartHeight}px`
  deptChart.resize()

  deptChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: '#E4E4E7',
      borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      valueFormatter: (value) => `${value}天`
    },
    grid: {
      top: 36,
      left: 12,
      right: 50,
      bottom: 4,
      containLabel: true
    },
    xAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#F4F4F5', type: 'dashed' } },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    yAxis: {
      type: 'category',
      data: depts,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#71717A',
        fontSize: 12,
        width: 120,
        overflow: 'truncate',
        ellipsis: '...'
      }
    },
    series: [
      {
        type: 'bar',
        data: values,
        barMaxWidth: 22,
        barMinWidth: 12,
        itemStyle: {
          color: '#2563EB',
          borderRadius: [0, 4, 4, 0]
        },
        label: {
          show: true,
          position: 'right',
          color: '#71717A',
          fontSize: 11,
          formatter: '{c}天'
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#F59E0B', type: 'dashed', width: 1.5 },
          label: {
            position: 'insideEndTop',
            formatter: `均值: ${Math.round(avg * 10) / 10}天`,
            fontSize: 11,
            color: '#F59E0B',
            padding: [2, 6]
          },
          data: [{ xAxis: avg }]
        }
      }
    ]
  }, true)
}

/**
 * Render the weekday distribution vertical bar chart.
 */
function renderWeekdayChart() {
  if (!weekdayChartRef.value) return
  weekdayChart = ensureChartInstance(weekdayChart, weekdayChartRef)

  const data = weekdayDistribution.value?.weekdays || []
  const weekdays = data.map(d => d.label)
  const values = data.map(d => d.count)

  weekdayChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: '#E4E4E7',
      borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      valueFormatter: (value) => `${value}次`
    },
    grid: {
      top: 24,
      left: 12,
      right: 12,
      bottom: 4,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: weekdays,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#71717A', fontSize: 12 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#F4F4F5', type: 'dashed' } },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    series: [
      {
        type: 'bar',
        data: values.map((v, i) => ({
          value: v,
          // Highlight Monday (index 0) and Friday (index 4)
          itemStyle: {
            color: (i === 0 || i === 4) ? '#2563EB' : '#93BBFD',
            borderRadius: [4, 4, 0, 0]
          }
        })),
        barWidth: 32,
        label: {
          show: true,
          position: 'top',
          color: '#71717A',
          fontSize: 11,
          formatter: '{c}次'
        }
      }
    ]
  }, true)
}

/**
 * Render the employee ranking stacked horizontal bar chart.
 */
function renderRankingChart() {
  if (!rankingChartRef.value) return
  rankingChart = ensureChartInstance(rankingChart, rankingChartRef)

  const data = employeeRanking.value?.employees || []
  // Reverse so top-ranked appears on top in horizontal bar
  const reversed = [...data].reverse()
  const names = reversed.map(d => d.name)

  // Collect all unique leave types from data
  const typeSet = new Set()
  data.forEach(d => d.breakdown?.forEach(b => typeSet.add(b.type)))
  const leaveTypes = [...typeSet]

  const series = leaveTypes.map((type, idx) => ({
    name: type,
    type: 'bar',
    stack: 'total',
    barMaxWidth: 22,
    barMinWidth: 12,
    itemStyle: {
      color: getLeaveColor(type, idx),
      borderRadius: 0
    },
    label: { show: false },
    data: reversed.map(d => {
      const item = d.breakdown?.find(b => b.type === type)
      return item ? item.days : 0
    })
  }))

  rankingChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: '#E4E4E7',
      borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      formatter: (params) => {
        let result = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        let total = 0
        params.forEach(p => {
          if (p.value > 0) {
            result += `<div style="display:flex;align-items:center;gap:6px;margin:2px 0">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>
              ${p.seriesName}: ${p.value}天
            </div>`
          }
          total += p.value
        })
        result += `<div style="margin-top:4px;font-weight:600">合计: ${Math.round(total * 10) / 10}天</div>`
        return result
      }
    },
    legend: {
      data: leaveTypes,
      bottom: 0,
      left: 'center',
      type: 'scroll',
      textStyle: { fontSize: 12, color: '#71717A' },
      itemWidth: 12,
      itemHeight: 12,
      itemGap: 16
    },
    grid: {
      top: 12,
      left: 12,
      right: 50,
      bottom: 36,
      containLabel: true
    },
    xAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#F4F4F5', type: 'dashed' } },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#71717A',
        fontSize: 12,
        formatter: (value) => {
          // Show name with a circle avatar placeholder
          return `{avatar|} ${value}`
        },
        rich: {
          avatar: {
            width: 20,
            height: 20,
            borderRadius: 10,
            backgroundColor: '#E4E4E7'
          }
        }
      }
    },
    series
  }, true)
}

/**
 * Render all charts.
 */
function renderAllCharts() {
  renderTrendChart()
  renderPieChart()
  renderDeptChart()
  renderWeekdayChart()
  renderRankingChart()
}

/**
 * Resize all chart instances on window resize.
 */
function handleResize() {
  trendChart?.resize()
  pieChart?.resize()
  deptChart?.resize()
  weekdayChart?.resize()
  rankingChart?.resize()
}

/**
 * Handle department metric toggle (total vs avg).
 * Re-fetches department comparison data for the selected metric.
 */
async function handleDeptMetricChange(metric) {
  deptMetric.value = metric
  try {
    departmentComparison.value = await apiClient.getDepartmentComparison(year.value, metric)
  } catch (err) {
    console.error('[Analytics] Failed to refresh department comparison:', err)
  }
}

// --- Watch data changes to re-render charts ---
watch(monthlyTrend, () => nextTick(renderTrendChart))
watch(leaveTypeDistribution, () => nextTick(renderPieChart))
watch(departmentComparison, () => nextTick(renderDeptChart))
watch(weekdayDistribution, () => nextTick(renderWeekdayChart))
watch(employeeRanking, () => nextTick(renderRankingChart))

// --- Lifecycle ---
onMounted(() => {
  fetchAll(year.value)
  nextTick(renderAllCharts)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  pieChart?.dispose()
  deptChart?.dispose()
  weekdayChart?.dispose()
  rankingChart?.dispose()
  trendChart = null
  pieChart = null
  deptChart = null
  weekdayChart = null
  rankingChart = null
})
</script>

<template>
  <div class="p-4 sm:p-6 lg:p-8 space-y-6">
    <!-- Page header: title + year switcher -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-text-primary">数据分析</h1>
        <p class="text-sm text-text-secondary mt-1">可视化展示员工请假数据统计与趋势</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          v-for="y in yearOptions"
          :key="y"
          class="px-3.5 py-1.5 text-[13px] font-medium rounded-md transition-colors"
          :class="year === y
            ? 'bg-accent text-white font-semibold'
            : 'border border-border-default text-text-secondary hover:text-text-primary'"
          @click="switchYear(y)"
        >
          {{ y }}
        </button>
      </div>
    </div>

    <!-- Loading overlay -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="flex items-center gap-3 text-text-secondary">
        <svg class="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span class="text-sm">加载中...</span>
      </div>
    </div>

    <template v-else>
      <!-- Row 1: Monthly trend + Leave type distribution -->
      <div class="flex flex-col lg:flex-row gap-4">
        <!-- Monthly trend line chart -->
        <div class="flex-1 bg-white rounded-xl border border-border-default p-6">
          <h2 class="text-sm font-semibold text-text-primary mb-4">月度请假趋势</h2>
          <div ref="trendChartRef" class="w-full" style="height: 280px"></div>
        </div>

        <!-- Leave type distribution pie chart -->
        <div class="w-full lg:w-[380px] bg-white rounded-xl border border-border-default p-6">
          <h2 class="text-sm font-semibold text-text-primary mb-4">假期类型分布</h2>
          <div class="flex flex-col items-center">
            <div ref="pieChartRef" class="w-full" style="height: 180px"></div>
            <!-- Custom legend -->
            <div class="w-full mt-4 space-y-2">
              <div
                v-for="(item, idx) in (leaveTypeDistribution?.items || [])"
                :key="item.type"
                class="flex items-center justify-between text-sm"
              >
                <div class="flex items-center gap-2">
                  <span
                    class="inline-block w-2.5 h-2.5 rounded-full"
                    :style="{ backgroundColor: getLeaveColor(item.type, idx) }"
                  />
                  <span class="text-text-secondary">{{ item.type }}</span>
                </div>
                <div class="flex items-center gap-3">
                  <span class="font-medium text-text-primary">{{ item.days }}天</span>
                  <span class="text-text-tertiary text-xs w-10 text-right">{{ item.ratio }}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Row 2: Department comparison + Weekday distribution -->
      <div class="flex flex-col lg:flex-row gap-4">
        <!-- Department comparison horizontal bar chart -->
        <div class="flex-1 bg-white rounded-xl border border-border-default p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-text-primary">部门请假对比</h2>
            <div class="flex items-center gap-1 bg-surface rounded-md p-0.5">
              <button
                class="px-2.5 py-1 text-xs font-medium rounded transition-colors"
                :class="deptMetric === 'total'
                  ? 'bg-white text-text-primary shadow-sm'
                  : 'text-text-tertiary hover:text-text-secondary'"
                @click="handleDeptMetricChange('total')"
              >
                总天数
              </button>
              <button
                class="px-2.5 py-1 text-xs font-medium rounded transition-colors"
                :class="deptMetric === 'avg'
                  ? 'bg-white text-text-primary shadow-sm'
                  : 'text-text-tertiary hover:text-text-secondary'"
                @click="handleDeptMetricChange('avg')"
              >
                人均
              </button>
            </div>
          </div>
          <div ref="deptChartRef" class="w-full" style="min-height: 250px"></div>
        </div>

        <!-- Weekday distribution vertical bar chart -->
        <div class="w-full lg:w-[380px] bg-white rounded-xl border border-border-default p-6">
          <h2 class="text-sm font-semibold text-text-primary mb-4">请假星期分布</h2>
          <div ref="weekdayChartRef" class="w-full" style="height: 250px"></div>
        </div>
      </div>

      <!-- Row 3: Employee ranking -->
      <div class="bg-white rounded-xl border border-border-default p-6">
        <h2 class="text-sm font-semibold text-text-primary mb-4">请假排行 Top 10</h2>
        <div ref="rankingChartRef" class="w-full" style="height: 380px"></div>
      </div>
    </template>
  </div>
</template>
