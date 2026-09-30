import test from 'node:test'
import assert from 'node:assert/strict'
import axios from 'axios'
import { effectScope, nextTick, ref } from 'vue'
import { formatBusinessTimestamp } from '../src/utils/date.js'

globalThis.localStorage = { getItem: () => null, removeItem: () => {} }
const requests = []
let adapterResponse = () => ({})
axios.defaults.adapter = async config => {
  requests.push(config)
  return { data: await adapterResponse(config), status: 200, headers: {}, config }
}
const { default: api, waitForSyncCompletion } = await import('../src/api/index.js')
const { useLeaveData } = await import('../src/composables/useLeaveData.js')
const { useTripData } = await import('../src/composables/useTripData.js')
const { useAnalyticsData } = await import('../src/composables/useAnalyticsData.js')
const { useTripAnalyticsData } = await import('../src/composables/useTripAnalyticsData.js')

function deferred() {
  let resolve
  let reject
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}

function summary(label) {
  return { stats: { totalCount: label }, list: [label], summary: {}, pagination: { total: 1, page: 1, pageSize: 10 } }
}

test('empty leave type selections stay distinct from all types in API queries', async () => {
  await api.getMonthlySummary({ year: 2026, leaveTypes: [] })
  assert.equal(requests.at(-1).params.leaveTypes, '')
  await api.getMonthlySummary({ year: 2026, leaveTypes: null })
  assert.equal(requests.at(-1).params.leaveTypes, undefined)
  await api.getDailyDetail('one', 2026, 9, ['年假'])
  assert.equal(requests.at(-1).params.leaveTypes, '年假')
  await api.getTripDailyDetail({ employeeId: 'one', year: 2026, month: 9, tripType: '外出' })
  assert.equal(requests.at(-1).params.tripType, '外出')
})

test('initial leave fetch treats types as all until options finish loading', async () => {
  const original = api.getMonthlySummary
  let selection
  api.getMonthlySummary = async params => { selection = params.leaveTypes; return summary('initial') }
  const data = useLeaveData()
  await data.fetchData()
  assert.equal(selection, null)
  api.getMonthlySummary = original
})

test('null leave selection still means all after options are loaded', async () => {
  const methods = ['getLeaveTypes', 'getMonthlySummary']
  const originals = methods.map(name => api[name])
  let selection
  api.getLeaveTypes = async () => [{ leave_name: '年假' }]
  api.getMonthlySummary = async params => { selection = params.leaveTypes; return summary('all') }
  try {
    const data = useLeaveData()
    await data.loadLeaveTypes()
    data.filters.leaveTypes = null
    await data.fetchData()
    assert.equal(selection, null)
  } finally {
    methods.forEach((name, i) => { api[name] = originals[i] })
  }
})

test('sync timestamps use Shanghai time, including UTC records without an offset', () => {
  assert.equal(formatBusinessTimestamp('2026-12-31T16:30:15+00:00'), '2027-01-01 00:30:15')
  assert.equal(formatBusinessTimestamp('2026-12-31T16:30:15'), '2027-01-01 00:30:15')
  assert.equal(formatBusinessTimestamp('invalid'), '')
})

test('older trip table response cannot overwrite a newer filter result', async () => {
  const original = api.getTripMonthlySummary
  const old = deferred()
  const fresh = deferred()
  api.getTripMonthlySummary = params => params.year === 2025 ? old.promise : fresh.promise
  const data = useTripData()
  data.filters.year = 2025
  const first = data.fetchData()
  data.filters.year = 2026
  const second = data.fetchData()
  fresh.resolve(summary('fresh'))
  await second
  old.resolve(summary('old'))
  await first
  assert.deepEqual(data.tableData.value, ['fresh'])
  assert.equal(data.stats.value.totalCount, 'fresh')
  api.getTripMonthlySummary = original
})

test('trip heatmap follows the selected year and rejects obsolete detail responses', async () => {
  const countOriginal = api.getTripDailyCount
  const detailOriginal = api.getTripToday
  let requestedYear
  api.getTripDailyCount = async params => { requestedYear = params.year; return { days: {} } }
  const data = useTripData()
  data.filters.year = 2024
  await data.fetchDailyTripCount()
  assert.equal(requestedYear, 2024)
  const old = deferred()
  const fresh = deferred()
  api.getTripToday = params => params.date === '2026-09-29' ? old.promise : fresh.promise
  const first = data.fetchTodayTripDetail('2026-09-29')
  const second = data.fetchTodayTripDetail('2026-09-30')
  fresh.resolve({ list: ['fresh'] })
  await second
  old.resolve({ list: ['old'] })
  await first
  assert.deepEqual(data.todayTripDetail.value, ['fresh'])
  api.getTripDailyCount = countOriginal
  api.getTripToday = detailOriginal
})

test('business today is Shanghai date and is recalculated on each open', async () => {
  const OriginalDate = Date
  const original = api.getTripToday
  let now = '2026-12-31T16:30:00Z'
  globalThis.Date = class extends OriginalDate {
    constructor(...args) { super(...(args.length ? args : [now])) }
    static now() { return new OriginalDate(now).valueOf() }
  }
  api.getTripToday = async () => ({ list: [] })
  try {
    const data = useTripData()
    await data.fetchTodayTripDetail('出差')
    assert.equal(data.todayTripDate.value, '2027-01-01')
    now = '2027-01-01T16:30:00Z'
    await data.fetchTodayTripDetail('出差')
    assert.equal(data.todayTripDate.value, '2027-01-02')
  } finally {
    globalThis.Date = OriginalDate
    api.getTripToday = original
  }
})

test('analytics publish only the most recently requested year', async () => {
  for (const [make, methods, field] of [
    [() => useAnalyticsData(), ['getMonthlyTrend', 'getLeaveTypeDistribution', 'getDepartmentComparison', 'getWeekdayDistribution', 'getEmployeeRanking'], 'leaveTypeDistribution'],
    [() => useTripAnalyticsData(ref(2026)), ['getTripMonthlyTrend', 'getTripTypeDistribution', 'getTripDepartmentComparison', 'getTripWeekdayDistribution', 'getTripEmployeeRanking'], 'typeDistribution']
  ]) {
    const originals = methods.map(name => api[name])
    const old = deferred()
    methods.forEach(name => { api[name] = year => year === 2025 ? old.promise : Promise.resolve({ year }) })
    const data = make()
    const first = data.fetchAll(2025)
    await data.fetchAll(2026)
    old.resolve({ year: 2025 })
    await first
    await nextTick()
    assert.equal(data.monthlyTrend.value.year, 2026)
    assert.equal(data[field].value.year, 2026)
    methods.forEach((name, i) => { api[name] = originals[i] })
  }
})

test('leave summary, daily count and modal reject responses for older selections', async () => {
  const names = ['getMonthlySummary', 'getDailyLeaveCount', 'getTodayLeaveDetail']
  const originals = names.map(name => api[name])
  const old = deferred()
  api.getMonthlySummary = params => params.year === 2025 ? old.promise : Promise.resolve(summary('fresh'))
  api.getDailyLeaveCount = async () => ({ todayCount: 7, days: [] })
  const data = useLeaveData()
  data.filters.year = 2025
  const first = data.fetchData()
  data.filters.year = 2026
  await data.fetchData()
  old.resolve(summary('old'))
  await first
  assert.deepEqual(data.tableData.value, ['fresh'])
  assert.equal(data.todayLeaveCount.value, 7)

  const oldDetail = deferred()
  api.getTodayLeaveDetail = params => params.date === '2026-09-29' ? oldDetail.promise : Promise.resolve({ date: params.date, count: 1 })
  const firstDetail = data.fetchTodayLeaveDetail('2026-09-29')
  await data.fetchTodayLeaveDetail('2026-09-30')
  oldDetail.resolve({ date: '2026-09-29', count: 99 })
  await firstDetail
  assert.equal(data.todayLeaveDetail.value.date, '2026-09-30')
  assert.equal(data.todayLeaveDetail.value.count, 1)
  names.forEach((name, i) => { api[name] = originals[i] })
})

test('a changed department metric cannot be overwritten by the initial dashboard batch', async () => {
  for (const [make, methods] of [
    [() => useAnalyticsData(), ['getMonthlyTrend', 'getLeaveTypeDistribution', 'getDepartmentComparison', 'getWeekdayDistribution', 'getEmployeeRanking']],
    [() => useTripAnalyticsData(ref(2026)), ['getTripMonthlyTrend', 'getTripTypeDistribution', 'getTripDepartmentComparison', 'getTripWeekdayDistribution', 'getTripEmployeeRanking']]
  ]) {
    const originals = methods.map(name => api[name])
    const old = deferred()
    methods.forEach(name => { api[name] = async () => ({ year: 2026 }) })
    api[methods[2]] = (year, metric) => metric === 'total' ? old.promise : Promise.resolve({ metric, average: 3 })
    const data = make()
    const batch = data.fetchAll(2026)
    await data.fetchDepartmentComparison('avg')
    old.resolve({ metric: 'total', average: 999 })
    await batch
    assert.equal(data.departmentComparison.value.metric, 'avg')
    assert.equal(data.departmentComparison.value.average, 3)
    methods.forEach((name, i) => { api[name] = originals[i] })
  }
})

test('trip sync stays locked through an old success and the new task running, then reports failure', async () => {
  const originalTrigger = api.triggerTripSync
  const originalSummary = api.getTripMonthlySummary
  const originalDaily = api.getTripDailyCount
  const originalTimeout = globalThis.setTimeout
  const delays = []
  const statuses = [
    { latest: { trip: { id: 10, status: 'success' } }, running: { trip: false } },
    { latest: { trip: { id: 10, status: 'success' } }, running: { trip: false } },
    { latest: { trip: { id: 11, status: 'running' } }, running: { trip: true } },
    { latest: { trip: { id: 11, status: 'failed', message: '上游失败' } }, running: { trip: false } }
  ]
  adapterResponse = config => config.url === '/sync/status' ? statuses.shift() : {}
  api.triggerTripSync = async () => ({ success: true })
  api.getTripMonthlySummary = async () => summary('synced')
  api.getTripDailyCount = async () => ({ days: {} })
  globalThis.setTimeout = callback => { delays.push(callback); return 1 }
  const flushUntilDelay = async () => {
    for (let i = 0; i < 30 && !delays.length; i++) await Promise.resolve()
    assert.equal(delays.length, 1)
  }
  try {
    const data = useTripData()
    const task = data.triggerTripSync()
    await flushUntilDelay()
    assert.equal(data.syncing.value, true)
    delays.shift()()
    await flushUntilDelay()
    assert.equal(data.syncing.value, true)
    delays.shift()()
    assert.equal(await task, false)
    assert.equal(data.syncing.value, false)
    assert.match(data.syncMessage.value, /同步失败.*上游失败/)
  } finally {
    api.triggerTripSync = originalTrigger
    api.getTripMonthlySummary = originalSummary
    api.getTripDailyCount = originalDaily
    globalThis.setTimeout = originalTimeout
    adapterResponse = () => ({})
  }
})

test('rejected sync startup and polling failures are explicit instead of reporting success', async () => {
  const originalStatus = api.getSyncStatus
  const originalTrigger = api.triggerSync
  api.getSyncStatus = async () => ({ latest: { full: { id: 1, status: 'success' } }, running: { full: false } })
  try {
    const data = useLeaveData()
    api.triggerSync = async () => ({ success: false, message: '任务已在执行' })
    assert.equal(await data.triggerSync(2026), false)
    assert.equal(data.syncMessage.value, '任务已在执行')
    assert.equal(data.syncing.value, false)

    api.triggerSync = async () => ({ success: true })
    adapterResponse = () => { throw new Error('poll unavailable') }
    assert.equal(await data.triggerSync(2026), false)
    assert.match(data.syncMessage.value, /状态未知/)
    assert.equal(data.syncing.value, false)
  } finally {
    api.getSyncStatus = originalStatus
    api.triggerSync = originalTrigger
    adapterResponse = () => ({})
  }
})

test('late initial sync status cannot unlock a newly started manual sync', async () => {
  for (const [make, domain, triggerMethod, fetchMethods] of [
    [useLeaveData, 'full', 'triggerSync', ['getMonthlySummary', 'getDailyLeaveCount']],
    [useTripData, 'trip', 'triggerTripSync', ['getTripMonthlySummary', 'getTripDailyCount']]
  ]) {
    const methods = ['getSyncStatus', triggerMethod, ...fetchMethods]
    const originals = methods.map(name => api[name])
    const initial = deferred()
    const startup = deferred()
    let calls = 0
    const baseline = { latest: { [domain]: { id: 10, status: 'success' } }, running: { [domain]: false } }
    api.getSyncStatus = () => ++calls === 1 ? initial.promise : Promise.resolve(baseline)
    api[triggerMethod] = () => startup.promise
    api[fetchMethods[0]] = async () => summary('synced')
    api[fetchMethods[1]] = async () => ({ days: [], todayCount: 0 })
    adapterResponse = () => ({ latest: { [domain]: { id: 11, status: 'success' } }, running: { [domain]: false } })
    try {
      const data = make()
      const init = data.refreshSyncStatus()
      const manual = data[triggerMethod](2026)
      initial.resolve({ latest: { [domain]: { id: 9, status: 'success' } }, running: { [domain]: false } })
      await init
      assert.equal(data.syncing.value, true)
      assert.equal(data.syncStatus.value.latest[domain].id, 10)
      startup.resolve({ success: true })
      assert.equal(await manual, true)
      assert.equal(data.syncing.value, false)
    } finally {
      methods.forEach((name, i) => { api[name] = originals[i] })
      adapterResponse = () => ({})
    }
  }
})

test('disposing the page cancels sync polling instead of leaving a background loop', async () => {
  const originalStatus = api.getSyncStatus
  const originalTrigger = api.triggerTripSync
  const originalTimeout = globalThis.setTimeout
  let delayScheduled = false
  api.getSyncStatus = async () => ({ latest: { trip: { id: 10, status: 'success' } }, running: { trip: false } })
  api.triggerTripSync = async () => ({ success: true })
  adapterResponse = () => ({ latest: { trip: { id: 11, status: 'running' } }, running: { trip: true } })
  globalThis.setTimeout = () => { delayScheduled = true; return 1 }
  const scope = effectScope()
  try {
    const data = scope.run(useTripData)
    const task = data.triggerTripSync()
    for (let i = 0; i < 30 && !delayScheduled; i++) await Promise.resolve()
    assert.equal(delayScheduled, true)
    scope.stop()
    assert.equal(await task, false)
  } finally {
    scope.stop()
    api.getSyncStatus = originalStatus
    api.triggerTripSync = originalTrigger
    globalThis.setTimeout = originalTimeout
    adapterResponse = () => ({})
  }
})

test('full sync follows its task ID even when another year is running or later fails', async () => {
  const originalTimeout = globalThis.setTimeout
  const firstRequest = requests.length
  const statuses = [
    { task: { task_id: 'full:other', status: 'success' }, latest: { full: { id: 20, status: 'success' } }, running: { full: false } },
    { task: { task_id: 'full:wanted', status: 'running' }, latest: { full: { id: 21, status: 'failed' } }, running: { full: false } },
    { task: { task_id: 'full:wanted', status: 'success' }, latest: { full: { id: 21, status: 'failed' } }, running: { full: true } }
  ]
  adapterResponse = () => statuses.shift()
  globalThis.setTimeout = callback => { queueMicrotask(callback); return 1 }
  try {
    const result = await waitForSyncCompletion('full', 10, () => {}, undefined, 'full:wanted')
    assert.equal(result.task_id, 'full:wanted')
    assert.equal(result.status, 'success')
    assert.equal(statuses.length, 0)
    assert.equal(requests.length - firstRequest, 3)
    assert.ok(requests.slice(firstRequest).every(request => request.params.taskId === 'full:wanted'))
  } finally {
    globalThis.setTimeout = originalTimeout
    adapterResponse = () => ({})
  }
})

test('manual full sync can enqueue another year and follow a merged same-year task', async () => {
  const methods = ['getSyncStatus', 'triggerSync', 'getMonthlySummary', 'getDailyLeaveCount']
  const originals = methods.map(name => api[name])
  const startupResponses = [
    { success: true, taskId: 'full:2025' },
    { success: false, taskId: 'full:2026' }
  ]
  const years = []
  api.getSyncStatus = async () => ({ latest: { full: { id: 30, status: 'running' } }, running: { full: true } })
  api.triggerSync = async year => { years.push(year); return startupResponses.shift() }
  api.getMonthlySummary = async () => summary('synced')
  api.getDailyLeaveCount = async () => ({ days: [], todayCount: 0 })
  adapterResponse = config => ({
    task: { task_id: config.params.taskId, status: 'success' },
    latest: { full: { id: 31, status: 'failed' } }, running: { full: true }
  })
  try {
    const data = useLeaveData()
    assert.equal(await data.triggerSync(2025), true)
    assert.equal(data.syncMessage.value, '同步完成')
    assert.equal(data.syncing.value, false)
    assert.equal(await data.triggerSync(2026), true)
    assert.deepEqual(years, [2025, 2026])
    assert.equal(data.syncStatus.value.task.task_id, 'full:2026')
  } finally {
    methods.forEach((name, i) => { api[name] = originals[i] })
    adapterResponse = () => ({})
  }
})
