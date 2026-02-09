<script setup>
import { ref, watch } from 'vue'
import { Search, ChevronDown, RotateCcw, Check } from 'lucide-vue-next'

const props = defineProps({
  /** Reactive filters object */
  filters: {
    type: Object,
    required: true
  },
  /** Level-1 departments array */
  departments1: {
    type: Array,
    default: () => []
  },
  /** Level-2 departments array */
  departments2: {
    type: Array,
    default: () => []
  },
  /** Dynamic leave type options from API */
  leaveTypeOptions: {
    type: Array,
    default: () => []
  },
  /** Available year options */
  yearOptions: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits([
  'search',
  'reset',
  'dept1-change',
  'update:filters'
])

// Debounce timer for employee name search
let debounceTimer = null

/**
 * Check if all leave types are currently selected
 */
function isAllSelected() {
  return props.leaveTypeOptions.length > 0 && props.filters.leaveTypes.length === props.leaveTypeOptions.length
}

/**
 * Check if a specific leave type is selected
 */
function isTypeSelected(name) {
  return props.filters.leaveTypes.includes(name)
}

/**
 * Toggle all leave types selection
 */
function toggleAll() {
  if (isAllSelected()) {
    props.filters.leaveTypes = []
  } else {
    props.filters.leaveTypes = props.leaveTypeOptions.map(t => t.name)
  }
}

/**
 * Toggle a single leave type selection
 */
function toggleType(name) {
  const idx = props.filters.leaveTypes.indexOf(name)
  if (idx >= 0) {
    props.filters.leaveTypes.splice(idx, 1)
  } else {
    props.filters.leaveTypes.push(name)
  }
}

/**
 * Handle level-1 department selection change
 */
function onDept1Change(event) {
  const val = event.target.value
  props.filters.deptId = val ? Number(val) : null
  props.filters.deptId2 = null
  emit('dept1-change', props.filters.deptId)
}

/**
 * Handle level-2 department selection change
 */
function onDept2Change(event) {
  const val = event.target.value
  props.filters.deptId2 = val ? Number(val) : null
}

/**
 * Handle employee name input with 300ms debounce
 */
function onNameInput(event) {
  const value = event.target.value
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    props.filters.employeeName = value
  }, 300)
}

/**
 * Handle year selection change
 */
function onYearChange(event) {
  props.filters.year = Number(event.target.value)
}
</script>

<template>
  <div class="bg-white rounded-xl border-[1.5px] border-border-default p-4 sm:p-5 lg:p-6">
    <!-- Row 1: Department, Employee name, Year -->
    <div class="flex flex-col lg:flex-row lg:items-end gap-4 mb-4">
      <!-- Department group -->
      <div class="w-full lg:flex-1">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">部门</label>
        <div class="flex gap-2">
          <!-- Level 1 department select -->
          <div class="relative flex-1">
            <select
              class="w-full h-10 appearance-none bg-white border-[1.5px] border-border-default rounded-lg px-3 pr-8 text-sm text-text-primary focus:outline-none focus:border-accent cursor-pointer"
              :value="filters.deptId || ''"
              @change="onDept1Change"
            >
              <option value="">全部部门</option>
              <option
                v-for="dept in departments1.filter(d => d.dept_id !== 1)"
                :key="dept.dept_id"
                :value="dept.dept_id"
              >
                {{ dept.name }}
              </option>
            </select>
            <ChevronDown
              :size="16"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
            />
          </div>

          <!-- Level 2 department select -->
          <div class="relative flex-1">
            <select
              class="w-full h-10 appearance-none bg-white border-[1.5px] border-border-default rounded-lg px-3 pr-8 text-sm text-text-primary focus:outline-none focus:border-accent cursor-pointer disabled:bg-surface disabled:text-text-tertiary"
              :value="filters.deptId2 || ''"
              :disabled="!filters.deptId || departments2.length === 0"
              @change="onDept2Change"
            >
              <option value="">全部子部门</option>
              <option
                v-for="dept in departments2"
                :key="dept.dept_id"
                :value="dept.dept_id"
              >
                {{ dept.name }}
              </option>
            </select>
            <ChevronDown
              :size="16"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
            />
          </div>

        </div>
      </div>

      <!-- Employee name search -->
      <div class="w-full lg:flex-1">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">员工姓名</label>
        <div class="relative">
          <Search
            :size="16"
            class="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
          />
          <input
            type="text"
            placeholder="搜索员工姓名..."
            class="w-full h-10 pl-9 pr-3 bg-white border-[1.5px] border-border-default rounded-lg text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
            :value="filters.employeeName"
            @input="onNameInput"
          />
        </div>
      </div>

      <!-- Year select -->
      <div class="w-full sm:w-48 lg:w-40">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">年份</label>
        <div class="relative">
          <select
            class="w-full h-10 appearance-none bg-white border-[1.5px] border-border-default rounded-lg px-3 pr-8 text-sm text-text-primary focus:outline-none focus:border-accent cursor-pointer"
            :value="filters.year"
            @change="onYearChange"
          >
            <option v-for="y in yearOptions" :key="y" :value="y">{{ y }} 年</option>
          </select>
          <ChevronDown
            :size="16"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
          />
        </div>
      </div>
    </div>

    <!-- Row 2: Leave type tags + action buttons -->
    <div class="flex flex-col sm:flex-row sm:items-end gap-4">
      <!-- Leave type group -->
      <div class="flex-1">
        <label class="block text-[13px] font-medium text-text-secondary mb-1.5">请假类型</label>
        <div class="flex flex-wrap items-center gap-2 min-h-[40px]">
          <!-- "All" button -->
          <button
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-[13px] font-semibold transition-all"
            :class="isAllSelected()
              ? 'bg-accent text-white'
              : 'border-[1.5px] border-border-default text-text-secondary hover:bg-surface'"
            @click="toggleAll"
          >
            <Check v-if="isAllSelected()" :size="14" />
            <span>全部</span>
          </button>

          <!-- Individual leave type tags -->
          <button
            v-for="lt in leaveTypeOptions"
            :key="lt.name"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-all"
            :class="isTypeSelected(lt.name)
              ? `${lt.bgColor} ${lt.textColor} border border-transparent ${lt.borderColor}`
              : 'border-[1.5px] border-border-default text-text-secondary hover:bg-surface'"
            @click="toggleType(lt.name)"
          >
            <Check v-if="isTypeSelected(lt.name)" :size="14" />
            <span>{{ lt.name }}</span>
          </button>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="flex items-center gap-3">
        <button
          class="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 h-10 px-5 bg-accent text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors"
          @click="emit('search')"
        >
          <Search :size="16" />
          <span>查询</span>
        </button>
        <button
          class="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 h-10 px-5 border-[1.5px] border-border-default text-text-secondary text-sm font-medium rounded-lg hover:bg-surface transition-colors"
          @click="emit('reset')"
        >
          <RotateCcw :size="16" />
          <span>重置</span>
        </button>
      </div>
    </div>
  </div>
</template>
