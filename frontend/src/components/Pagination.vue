<script setup>
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

const props = defineProps({
  /** Current page number (1-based) */
  page: {
    type: Number,
    required: true
  },
  /** Number of items per page */
  pageSize: {
    type: Number,
    default: 10
  },
  /** Total number of items */
  total: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['page-change', 'page-size-change'])

/** Available page size options */
const pageSizeOptions = [10, 50, 100]

/** Total number of pages */
const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

/** Start index of current page (1-based) */
const startItem = computed(() => {
  if (props.total === 0) return 0
  return (props.page - 1) * props.pageSize + 1
})

/** End index of current page */
const endItem = computed(() => Math.min(props.page * props.pageSize, props.total))

/**
 * Generate visible page numbers with ellipsis markers.
 * Shows at most 7 page buttons with "..." for gaps.
 */
const visiblePages = computed(() => {
  const total = totalPages.value
  const current = props.page
  const pages = []

  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i)
    return pages
  }

  // Always show first page
  pages.push(1)

  if (current > 3) {
    pages.push('...')
  }

  // Pages around current
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  if (current < total - 2) {
    pages.push('...')
  }

  // Always show last page
  if (total > 1) pages.push(total)

  return pages
})

function goTo(page) {
  if (page < 1 || page > totalPages.value || page === props.page) return
  emit('page-change', page)
}
</script>

<template>
  <div class="flex flex-col sm:flex-row items-center justify-center sm:justify-between gap-2 px-4 py-3">
    <!-- Left: info + page size selector -->
    <div class="flex items-center gap-3">
      <span class="text-[13px] text-text-secondary">
        <template v-if="total > 0">
          <span class="hidden sm:inline">显示 {{ startItem }}-{{ endItem }} / </span>共 {{ total }} 条
        </template>
        <template v-else>暂无数据</template>
      </span>
      <select
        class="h-7 appearance-none border border-border-default rounded-md px-2 pr-6 text-[13px] text-text-secondary bg-white focus:outline-none focus:border-accent cursor-pointer"
        :value="pageSize"
        @change="emit('page-size-change', Number($event.target.value))"
      >
        <option v-for="s in pageSizeOptions" :key="s" :value="s">{{ s }} 条/页</option>
      </select>
    </div>

    <!-- Page controls -->
    <div class="flex items-center justify-center sm:justify-end gap-1" v-if="total > 0">
      <!-- Previous page -->
      <button
        class="w-9 h-9 sm:w-8 sm:h-8 flex items-center justify-center rounded-md text-text-secondary hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        :disabled="page <= 1"
        @click="goTo(page - 1)"
      >
        <ChevronLeft :size="16" />
      </button>

      <!-- Page numbers -->
      <template v-for="(p, idx) in visiblePages" :key="idx">
        <span
          v-if="p === '...'"
          class="w-9 h-9 sm:w-8 sm:h-8 flex items-center justify-center text-[13px] text-text-tertiary"
        >
          ...
        </span>
        <button
          v-else
          class="w-9 h-9 sm:w-8 sm:h-8 flex items-center justify-center rounded-md text-[13px] font-medium transition-colors"
          :class="p === page
            ? 'bg-accent text-white'
            : 'text-text-secondary hover:bg-surface'"
          @click="goTo(p)"
        >
          {{ p }}
        </button>
      </template>

      <!-- Next page -->
      <button
        class="w-9 h-9 sm:w-8 sm:h-8 flex items-center justify-center rounded-md text-text-secondary hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        :disabled="page >= totalPages"
        @click="goTo(page + 1)"
      >
        <ChevronRight :size="16" />
      </button>
    </div>
  </div>
</template>
