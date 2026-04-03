<script setup>
import { computed } from 'vue'
import { X, Clock, Briefcase, Download, ChevronLeft, ChevronRight } from 'lucide-vue-next'

const props = defineProps({
  /** Whether the modal is visible */
  visible: {
    type: Boolean,
    default: false
  },
  /** Trip/outing detail list from API */
  detail: {
    type: Array,
    default: () => []
  },
  /** Whether data is loading */
  loading: {
    type: Boolean,
    default: false
  },
  /** Trip type filter: '出差', '外出', or '' for all */
  tripType: {
    type: String,
    default: ''
  },
  /** Currently selected date (YYYY-MM-DD) */
  selectedDate: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close', 'date-change', 'export'])

const todayStr = new Date().toISOString().slice(0, 10)

const isToday = computed(() => props.selectedDate === todayStr)

const displayDate = computed(() => {
  if (!props.selectedDate || isToday.value) return '今日'
  const [y, m, d] = props.selectedDate.split('-')
  return `${parseInt(m)}月${parseInt(d)}日`
})

/** Unique person count (deduplicated by employeeId) */
const uniqueCount = computed(() => {
  return new Set(props.detail.map(d => d.employeeId)).size
})

/** Dynamic title based on tripType */
const title = computed(() => {
  if (props.tripType === '出差') return '出差详情'
  if (props.tripType === '外出') return '外出详情'
  return '外出/出差详情'
})

function prevDay() {
  const d = new Date(props.selectedDate)
  d.setDate(d.getDate() - 1)
  emit('date-change', d.toISOString().slice(0, 10))
}

function nextDay() {
  const d = new Date(props.selectedDate)
  d.setDate(d.getDate() + 1)
  emit('date-change', d.toISOString().slice(0, 10))
}

function onDateInput(event) {
  emit('date-change', event.target.value)
}

function goToday() {
  emit('date-change', todayStr)
}

function getTagConfig(tagName) {
  if (tagName === '出差') return { bgColor: 'bg-orange-50', textColor: 'text-orange-600' }
  if (tagName === '外出') return { bgColor: 'bg-blue-50', textColor: 'text-blue-600' }
  return { bgColor: 'bg-gray-100', textColor: 'text-gray-600' }
}

function getInitial(name) {
  return name ? name.charAt(0) : '?'
}

function onOverlayClick(event) {
  if (event.target === event.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="visible"
        class="fixed inset-0 bg-black/40 z-50"
        @click="onOverlayClick"
      >
        <Transition name="slide">
          <div
            v-if="visible"
            class="absolute right-0 top-0 bottom-0 w-full sm:w-[480px] max-w-full bg-white shadow-2xl flex flex-col"
            @click.stop
          >
            <!-- Panel header -->
            <div class="p-4 sm:p-6 pb-4 border-b border-border-default">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                  <div class="w-10 h-10 rounded-lg bg-orange-50 flex items-center justify-center flex-shrink-0">
                    <Briefcase :size="20" class="text-orange-500" />
                  </div>
                  <div>
                    <div class="text-base font-semibold text-text-primary">{{ title }}</div>
                    <div class="text-[13px] text-text-secondary mt-0.5">
                      共 <span class="font-medium text-text-primary">{{ uniqueCount }}</span> 人
                    </div>
                  </div>
                </div>
                <button
                  class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface text-text-tertiary hover:text-text-primary transition-colors"
                  @click="emit('close')"
                >
                  <X :size="20" />
                </button>
              </div>

              <!-- Date selector row -->
              <div class="flex items-center justify-between mt-3">
                <div class="flex items-center gap-1.5">
                  <button
                    class="w-7 h-7 flex items-center justify-center rounded-md hover:bg-surface text-text-tertiary hover:text-text-primary transition-colors"
                    @click="prevDay"
                  >
                    <ChevronLeft :size="16" />
                  </button>
                  <label class="relative cursor-pointer">
                    <span
                      class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-sm font-medium border border-border-default hover:bg-surface transition-colors"
                    >
                      {{ displayDate }}
                      <span class="text-text-tertiary text-[12px]">{{ selectedDate }}</span>
                    </span>
                    <input
                      type="date"
                      :value="selectedDate"
                      class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      @input="onDateInput"
                    />
                  </label>
                  <button
                    class="w-7 h-7 flex items-center justify-center rounded-md hover:bg-surface text-text-tertiary hover:text-text-primary transition-colors"
                    @click="nextDay"
                  >
                    <ChevronRight :size="16" />
                  </button>
                  <button
                    v-if="!isToday"
                    class="ml-1 px-2 py-0.5 text-[12px] font-medium text-accent bg-accent/10 rounded hover:bg-accent/20 transition-colors"
                    @click="goToday"
                  >
                    今天
                  </button>
                </div>

                <button
                  class="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium text-text-secondary rounded-lg border border-border-default hover:bg-surface hover:text-text-primary transition-colors"
                  :disabled="detail.length === 0"
                  @click="emit('export')"
                >
                  <Download :size="14" />
                  导出
                </button>
              </div>
            </div>

            <!-- Panel body -->
            <div class="flex-1 overflow-y-auto p-4 sm:p-6">
              <!-- Loading skeleton -->
              <div v-if="loading" class="space-y-3">
                <div v-for="i in 3" :key="i" class="rounded-xl border-[1.5px] border-border-default p-4 animate-pulse">
                  <div class="flex items-center gap-3 mb-3">
                    <div class="w-8 h-8 rounded-full bg-gray-200" />
                    <div class="flex-1">
                      <div class="h-4 bg-gray-200 rounded w-24 mb-1.5" />
                      <div class="h-3 bg-gray-100 rounded w-32" />
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="h-5 bg-gray-100 rounded w-12" />
                    <div class="h-4 bg-gray-100 rounded w-28" />
                  </div>
                </div>
              </div>

              <template v-else>
                <!-- Empty state -->
                <div
                  v-if="detail.length === 0"
                  class="flex flex-col items-center justify-center py-16 text-text-tertiary"
                >
                  <Briefcase :size="48" class="mb-3 opacity-30" />
                  <span class="text-sm">{{ isToday ? '今日无外出/出差记录' : '当日无外出/出差记录' }}</span>
                </div>

                <!-- Records list -->
                <div v-else class="space-y-3">
                  <div
                    v-for="(record, idx) in detail"
                    :key="idx"
                    class="rounded-xl border-[1.5px] border-border-default p-3 sm:p-4"
                  >
                    <div class="flex items-start justify-between mb-2">
                      <div class="flex items-center gap-2.5">
                        <div
                          class="w-8 h-8 rounded-full bg-accent text-white text-sm font-semibold flex items-center justify-center flex-shrink-0"
                        >
                          {{ getInitial(record.employeeName) }}
                        </div>
                        <div>
                          <div class="text-sm font-medium text-text-primary">{{ record.employeeName }}</div>
                          <div class="text-[12px] text-text-tertiary">{{ record.deptName }}</div>
                        </div>
                      </div>
                      <span
                        class="inline-flex items-center px-2 py-0.5 rounded text-[12px] font-medium flex-shrink-0"
                        :class="[getTagConfig(record.tagName).bgColor, getTagConfig(record.tagName).textColor]"
                      >
                        {{ record.tagName }}
                      </span>
                    </div>

                    <div class="flex items-center gap-2 flex-wrap">
                      <div class="flex items-center gap-1 text-[13px] text-text-secondary">
                        <Clock :size="13" class="text-text-tertiary" />
                        <span>{{ record.beginTime }} ~ {{ record.endTime }}</span>
                      </div>
                      <span class="text-[13px] text-text-tertiary">
                        {{ record.durationHours }}小时
                      </span>
                    </div>
                  </div>
                </div>
              </template>
            </div>

            <!-- Panel footer -->
            <div
              v-if="detail.length > 0"
              class="border-t border-border-default px-4 sm:px-6 py-4 bg-surface"
            >
              <div class="flex items-center justify-between">
                <span class="text-[13px] font-medium text-text-secondary">{{ displayDate }}{{ title }}</span>
                <span class="text-sm font-semibold text-text-primary">
                  共 {{ uniqueCount }} 人
                </span>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
