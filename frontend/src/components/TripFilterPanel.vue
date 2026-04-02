<script setup>
import { Search, RotateCcw, ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  /** Reactive filters object */
  filters: {
    type: Object,
    required: true,
  },
  /** Level-1 departments array */
  departments1: {
    type: Array,
    default: () => [],
  },
  /** Level-2 departments array */
  departments2: {
    type: Array,
    default: () => [],
  },
  /** Available year options */
  yearOptions: {
    type: Array,
    default: () => [],
  },
  /** Loading state (disables search button while fetching) */
  loading: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits([
  'update:filters',
  'dept1Change',
  'search',
  'reset',
])

/** Segmented control options for trip type */
const tripTypeOptions = [
  { label: '全部', value: '' },
  { label: '出差', value: '出差' },
  { label: '外出', value: '外出' },
]

/**
 * Handle level-1 department selection change.
 * Resets dept2 when dept1 changes.
 */
function onDept1Change(val) {
  const deptId = val ? Number(val) : null
  emit('update:filters', { ...props.filters, dept1: deptId, dept2: null })
  emit('dept1Change', deptId)
}

/**
 * Handle level-2 department selection change
 */
function onDept2Change(val) {
  emit('update:filters', { ...props.filters, dept2: val ? Number(val) : null })
}

/**
 * Handle trip type segmented control change
 */
function onTripTypeChange(val) {
  emit('update:filters', { ...props.filters, tripType: val })
}

/**
 * Handle year selection change
 */
function onYearChange(val) {
  emit('update:filters', { ...props.filters, year: Number(val) })
}

/**
 * Handle employee name input change
 */
function onNameChange(val) {
  emit('update:filters', { ...props.filters, employeeName: val })
}
</script>

<template>
  <div class="bg-white rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
    <div class="flex flex-wrap items-end gap-3 sm:gap-4">
      <!-- Department 1 -->
      <div class="w-full sm:w-auto">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">一级部门</label>
        <div class="relative">
          <select
            class="h-10 w-full sm:w-44 appearance-none bg-white border-[1.5px] border-border-default rounded-lg px-3 pr-8 text-sm text-text-primary focus:outline-none focus:border-accent cursor-pointer"
            :value="filters.dept1 || ''"
            @change="onDept1Change($event.target.value)"
          >
            <option value="">全部部门</option>
            <option
              v-for="d in departments1.filter(d => d.dept_id !== 1)"
              :key="d.dept_id"
              :value="d.dept_id"
            >
              {{ d.name }}
            </option>
          </select>
          <ChevronDown
            :size="16"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
          />
        </div>
      </div>

      <!-- Department 2 (only visible when dept2 options are available) -->
      <div v-if="departments2.length > 0" class="w-full sm:w-auto">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">二级部门</label>
        <div class="relative">
          <select
            class="h-10 w-full sm:w-44 appearance-none bg-white border-[1.5px] border-border-default rounded-lg px-3 pr-8 text-sm text-text-primary focus:outline-none focus:border-accent cursor-pointer disabled:bg-surface disabled:text-text-tertiary"
            :value="filters.dept2 || ''"
            :disabled="!filters.dept1"
            @change="onDept2Change($event.target.value)"
          >
            <option value="">全部子部门</option>
            <option
              v-for="d in departments2"
              :key="d.dept_id"
              :value="d.dept_id"
            >
              {{ d.name }}
            </option>
          </select>
          <ChevronDown
            :size="16"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
          />
        </div>
      </div>

      <!-- Trip type segmented control (全部 / 出差 / 外出) -->
      <div class="w-full sm:w-auto">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">类型</label>
        <div class="inline-flex rounded-lg border-[1.5px] border-border-default overflow-hidden">
          <button
            v-for="opt in tripTypeOptions"
            :key="opt.value"
            class="h-10 px-4 text-sm font-medium transition-colors"
            :class="filters.tripType === opt.value
              ? 'bg-accent text-white'
              : 'bg-white text-text-secondary hover:bg-surface'"
            @click="onTripTypeChange(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <!-- Year -->
      <div class="w-full sm:w-auto">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">年份</label>
        <div class="relative">
          <select
            class="h-10 w-full sm:w-28 appearance-none bg-white border-[1.5px] border-border-default rounded-lg px-3 pr-8 text-sm text-text-primary focus:outline-none focus:border-accent cursor-pointer"
            :value="filters.year"
            @change="onYearChange($event.target.value)"
          >
            <option v-for="y in yearOptions" :key="y" :value="y">{{ y }} 年</option>
          </select>
          <ChevronDown
            :size="16"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
          />
        </div>
      </div>

      <!-- Employee name -->
      <div class="w-full sm:w-auto">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">员工姓名</label>
        <div class="relative">
          <Search
            :size="16"
            class="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
          />
          <input
            type="text"
            placeholder="搜索员工姓名..."
            class="h-10 w-full sm:w-40 pl-9 pr-3 bg-white border-[1.5px] border-border-default rounded-lg text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
            :value="filters.employeeName"
            @input="onNameChange($event.target.value)"
            @keyup.enter="emit('search')"
          />
        </div>
      </div>

      <!-- Action buttons -->
      <div class="flex items-center gap-3">
        <button
          class="flex items-center justify-center gap-1.5 h-10 px-5 bg-accent text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          :disabled="loading"
          @click="emit('search')"
        >
          <Search :size="16" />
          <span>查询</span>
        </button>
        <button
          class="flex items-center justify-center gap-1.5 h-10 px-5 border-[1.5px] border-border-default text-text-secondary text-sm font-medium rounded-lg hover:bg-surface transition-colors"
          @click="emit('reset')"
        >
          <RotateCcw :size="16" />
          <span>重置</span>
        </button>
      </div>
    </div>
  </div>
</template>
