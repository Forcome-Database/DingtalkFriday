<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { UserPlus, Trash2, Loader2, AlertCircle, Users, Shield, ShieldCheck, Pencil, X } from 'lucide-vue-next'
import api from '../api/index.js'

const users = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')

// New user form
const newMobile = ref('')
const newName = ref('')
const newRole = ref('user')
const formError = ref('')

// Edit modal state
const editVisible = ref(false)
const editMobile = ref('')
const editName = ref('')
const editRole = ref('user')
const editSaving = ref(false)
const editError = ref('')

const roleOptions = [
  { value: 'user', label: '普通用户' },
  { value: 'admin', label: '管理员' },
]

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
    await api.addUser({ mobile, name: newName.value.trim() || undefined, role: newRole.value })
    newMobile.value = ''
    newName.value = ''
    newRole.value = 'user'
    await loadUsers()
  } catch (e) {
    formError.value = e.response?.data?.detail || '添加用户失败'
  } finally {
    saving.value = false
  }
}

function openEdit(user) {
  editMobile.value = user.mobile
  editName.value = user.name || ''
  editRole.value = user.role || 'user'
  editError.value = ''
  editVisible.value = true
}

function closeEdit() {
  editVisible.value = false
}

async function saveEdit() {
  editSaving.value = true
  editError.value = ''
  try {
    await api.updateUser(editMobile.value, {
      name: editName.value.trim() || null,
      role: editRole.value,
    })
    editVisible.value = false
    await loadUsers()
  } catch (e) {
    editError.value = e.response?.data?.detail || '保存失败'
  } finally {
    editSaving.value = false
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

// Close edit modal on Escape key
function onEscKey(e) {
  if (e.key === 'Escape' && editVisible.value) closeEdit()
}
watch(editVisible, (visible) => {
  if (visible) window.addEventListener('keydown', onEscKey)
  else window.removeEventListener('keydown', onEscKey)
})
onUnmounted(() => window.removeEventListener('keydown', onEscKey))

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
          class="flex-1 sm:max-w-[160px] px-3 py-2 text-sm border border-border-default rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
          @keydown.enter="addUser"
        />
        <select
          v-model="newRole"
          class="sm:max-w-[130px] px-3 py-2 text-sm border border-border-default rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent bg-white"
        >
          <option v-for="opt in roleOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
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
              <th class="px-4 sm:px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase">角色</th>
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
              <td class="px-4 sm:px-6 py-3 font-medium text-text-primary">
                {{ user.mobile }}
              </td>
              <td class="px-4 sm:px-6 py-3 text-text-secondary">{{ user.name || '-' }}</td>
              <td class="px-4 sm:px-6 py-3">
                <span
                  class="inline-flex items-center gap-1 px-2 py-1 text-xs rounded font-medium"
                  :class="user.isAdmin
                    ? 'bg-amber-100 text-amber-700'
                    : 'bg-gray-100 text-gray-600'"
                >
                  <ShieldCheck v-if="user.isAdmin" :size="12" />
                  <Shield v-else :size="12" />
                  {{ user.isAdmin ? '管理员' : '普通用户' }}
                </span>
              </td>
              <td class="px-4 sm:px-6 py-3 text-text-tertiary text-xs font-mono">{{ user.userid || '-' }}</td>
              <td class="px-4 sm:px-6 py-3 text-text-tertiary text-xs">
                {{ user.created_at ? new Date(user.created_at).toLocaleString('zh-CN') : '-' }}
              </td>
              <td class="px-4 sm:px-6 py-3 text-right space-x-1">
                <button
                  class="inline-flex items-center gap-1 px-2 py-1 text-xs text-accent hover:bg-blue-50 rounded transition-colors"
                  @click="openEdit(user)"
                >
                  <Pencil :size="12" />
                  编辑
                </button>
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

    <!-- Edit user modal -->
    <Teleport to="body">
      <div v-if="editVisible" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/40" @click="closeEdit"></div>
        <!-- Modal -->
        <div class="relative bg-white rounded-xl shadow-xl border border-border-default w-full max-w-md p-6 space-y-5">
          <div class="flex items-center justify-between">
            <h3 class="text-lg font-semibold text-text-primary">编辑用户</h3>
            <button class="p-1 rounded hover:bg-gray-100 text-text-tertiary" @click="closeEdit">
              <X :size="18" />
            </button>
          </div>

          <div class="space-y-4">
            <!-- Mobile (read-only) -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1">手机号</label>
              <input
                :value="editMobile"
                disabled
                class="w-full px-3 py-2 text-sm border border-border-default rounded-lg bg-gray-50 text-text-tertiary cursor-not-allowed"
              />
            </div>
            <!-- Name -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1">姓名</label>
              <input
                v-model="editName"
                type="text"
                placeholder="输入姓名"
                class="w-full px-3 py-2 text-sm border border-border-default rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                @keydown.enter="saveEdit"
              />
            </div>
            <!-- Role -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1">角色</label>
              <select
                v-model="editRole"
                class="w-full px-3 py-2 text-sm border border-border-default rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent bg-white"
              >
                <option v-for="opt in roleOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </div>
          </div>

          <!-- Error -->
          <div v-if="editError" class="flex items-center gap-1.5 text-red-600">
            <AlertCircle :size="14" />
            <span class="text-xs">{{ editError }}</span>
          </div>

          <!-- Actions -->
          <div class="flex justify-end gap-3 pt-2">
            <button
              class="px-4 py-2 text-sm font-medium text-text-secondary border border-border-default rounded-lg hover:bg-gray-50 transition-colors"
              @click="closeEdit"
            >
              取消
            </button>
            <button
              class="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-accent rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
              :disabled="editSaving"
              @click="saveEdit"
            >
              <Loader2 v-if="editSaving" class="animate-spin" :size="14" />
              保存
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
