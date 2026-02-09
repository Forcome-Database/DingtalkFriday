<script setup>
import { onMounted, ref } from 'vue'
import { UserPlus, Trash2, Loader2, AlertCircle, Users } from 'lucide-vue-next'
import api from '../api/index.js'

const users = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')

// New user form
const newMobile = ref('')
const newName = ref('')
const formError = ref('')

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    users.value = await api.getUsers()
  } catch (e) {
    error.value = '加载用户列表失败'
  } finally {
    loading.value = false
  }
}

async function addUser() {
  const mobile = newMobile.value.trim()
  if (!mobile) {
    formError.value = '请输入手机号'
    return
  }
  if (!/^1\d{10}$/.test(mobile)) {
    formError.value = '请输入正确的手机号'
    return
  }

  saving.value = true
  formError.value = ''
  try {
    await api.addUser({ mobile, name: newName.value.trim() || undefined })
    newMobile.value = ''
    newName.value = ''
    await loadUsers()
  } catch (e) {
    formError.value = e.response?.data?.detail || '添加用户失败'
  } finally {
    saving.value = false
  }
}

async function removeUser(mobile) {
  if (!confirm(`确定移除用户 ${mobile} 的访问权限？`)) return

  try {
    await api.removeUser(mobile)
    await loadUsers()
  } catch (e) {
    error.value = e.response?.data?.detail || '移除用户失败'
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="p-4 sm:p-6 lg:p-8 space-y-6">
    <!-- Page title -->
    <div>
      <h1 class="text-2xl font-semibold text-text-primary">用户管理</h1>
      <p class="text-sm text-text-secondary mt-1">管理可访问系统的用户手机号</p>
    </div>

    <!-- Add user form -->
    <div class="bg-white rounded-xl border border-border-default p-4 sm:p-6">
      <h2 class="text-base font-semibold text-text-primary mb-4 flex items-center gap-2">
        <UserPlus :size="18" class="text-accent" />
        添加授权用户
      </h2>
      <div class="flex flex-col sm:flex-row gap-3">
        <input
          v-model="newMobile"
          type="tel"
          maxlength="11"
          placeholder="手机号"
          class="flex-1 px-3 py-2 text-sm border border-border-default rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
          @keydown.enter="addUser"
        />
        <input
          v-model="newName"
          type="text"
          placeholder="姓名（选填）"
          class="flex-1 sm:max-w-[200px] px-3 py-2 text-sm border border-border-default rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
          @keydown.enter="addUser"
        />
        <button
          class="flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-accent rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
          :disabled="saving"
          @click="addUser"
        >
          <Loader2 v-if="saving" class="animate-spin" :size="14" />
          <UserPlus v-else :size="14" />
          添加
        </button>
      </div>
      <div v-if="formError" class="flex items-center gap-1.5 text-red-600 mt-2">
        <AlertCircle :size="14" />
        <span class="text-xs">{{ formError }}</span>
      </div>
    </div>

    <!-- User list -->
    <div class="bg-white rounded-xl border border-border-default">
      <div class="px-4 sm:px-6 py-4 border-b border-border-default flex items-center justify-between">
        <h2 class="text-base font-semibold text-text-primary flex items-center gap-2">
          <Users :size="18" class="text-text-secondary" />
          已授权用户
          <span class="text-xs font-normal text-text-tertiary">({{ users.length }})</span>
        </h2>
      </div>

      <!-- Error -->
      <div v-if="error" class="px-4 sm:px-6 py-3 text-sm text-red-600 flex items-center gap-2">
        <AlertCircle :size="14" />
        {{ error }}
      </div>

      <!-- Loading -->
      <div v-if="loading" class="px-4 sm:px-6 py-8 text-center text-text-tertiary">
        <Loader2 class="animate-spin mx-auto mb-2" :size="20" />
        <span class="text-sm">加载中...</span>
      </div>

      <!-- Empty state -->
      <div v-else-if="users.length === 0" class="px-4 sm:px-6 py-8 text-center text-text-tertiary text-sm">
        暂无授权用户
      </div>

      <!-- Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-surface">
              <th class="px-4 sm:px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase">手机号</th>
              <th class="px-4 sm:px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase">姓名</th>
              <th class="px-4 sm:px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase">钉钉ID</th>
              <th class="px-4 sm:px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase">添加时间</th>
              <th class="px-4 sm:px-6 py-3 text-right text-xs font-medium text-text-secondary uppercase">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="user in users"
              :key="user.id"
              class="border-t border-border-default hover:bg-surface/50 transition-colors"
            >
              <td class="px-4 sm:px-6 py-3 font-medium text-text-primary">{{ user.mobile }}</td>
              <td class="px-4 sm:px-6 py-3 text-text-secondary">{{ user.name || '-' }}</td>
              <td class="px-4 sm:px-6 py-3 text-text-tertiary text-xs font-mono">{{ user.userid || '-' }}</td>
              <td class="px-4 sm:px-6 py-3 text-text-tertiary text-xs">
                {{ user.created_at ? new Date(user.created_at).toLocaleString('zh-CN') : '-' }}
              </td>
              <td class="px-4 sm:px-6 py-3 text-right">
                <button
                  class="inline-flex items-center gap-1 px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded transition-colors"
                  @click="removeUser(user.mobile)"
                >
                  <Trash2 :size="12" />
                  移除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
