import { createRouter, createWebHistory } from 'vue-router'
import { getToken, removeToken, removeUser } from '../utils/auth.js'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    name: 'Main',
    component: () => import('../views/MainView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // Catch-all redirect to home
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

/**
 * Check if a JWT token is expired by decoding the payload.
 */
function isTokenExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 < Date.now()
  } catch {
    return true
  }
}

// Navigation guard: redirect to /login if no token or expired token
router.beforeEach((to, from, next) => {
  const token = getToken()

  if (to.meta.requiresAuth !== false) {
    if (!token || isTokenExpired(token)) {
      removeToken()
      removeUser()
      next({ name: 'Login' })
      return
    }
  }

  if (to.name === 'Login' && token && !isTokenExpired(token)) {
    next({ name: 'Main' })
    return
  }

  next()
})

export default router
