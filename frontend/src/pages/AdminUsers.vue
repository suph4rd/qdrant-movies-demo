<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { session } from '../session'
import { t } from '../i18n'
import type { User } from '../types'

const route = useRoute()
const router = useRouter()
const users = ref<User[]>([])
const loading = ref(false)
const error = ref('')
const hasNext = ref(false)
const q = ref('')
const role = ref('')
const state = ref('')
const page = computed(() => Number(route.query.page || 1))
const allowed = computed(() => session.context?.user?.role === 'admin')
let generation = 0
function stateName(user: User) {
  return user.deleted_at ? 'Deleted' : user.blocked ? 'Blocked' : 'Active'
}
function pageLink(value: number) {
  return { path: '/admin/users', query: { ...route.query, lang: session.lang, page: String(value) } }
}
async function load() {
  const current = ++generation
  q.value = String(route.query.q || '')
  role.value = String(route.query.role || '')
  state.value = String(route.query.state || '')
  error.value = ''
  users.value = []
  hasNext.value = false
  if (!allowed.value) return
  loading.value = true
  try {
    const result = await api<{ users: User[]; has_next: boolean; page: number }>('/admin/users', {
      query: { q: q.value, role: role.value, state: state.value, page: String(route.query.page || 1) },
    })
    if (current === generation) {
      users.value = result.users
      hasNext.value = result.has_next
    }
  } catch (cause) {
    if (current === generation) error.value = cause instanceof Error ? cause.message : t('The request failed. Try again.')
  } finally {
    if (current === generation) loading.value = false
  }
}
function search() {
  router.push({ path: '/admin/users', query: { q: q.value, role: role.value, state: state.value, lang: session.lang } })
}
watch(() => [route.fullPath, session.lang, allowed.value], load, { immediate: true })
</script>

<template>
  <h1>{{ t('Users') }}</h1>
  <p v-if="!allowed" class="error" role="alert">{{ t('Administrator access required') }}</p>
  <template v-else>
    <form @submit.prevent="search">
      <label for="email-search">{{ t('Search email') }}</label>
      <input id="email-search" v-model="q" name="q" maxlength="254">
      <label for="role">{{ t('Role') }}</label>
      <select id="role" v-model="role" name="role">
        <option value="">{{ t('All') }}</option><option value="user">{{ t('User') }}</option><option value="admin">{{ t('Administrator') }}</option>
      </select>
      <label for="state">{{ t('State') }}</label>
      <select id="state" v-model="state" name="state">
        <option value="">{{ t('All') }}</option><option value="active">{{ t('Active') }}</option><option value="blocked">{{ t('Blocked') }}</option><option value="deleted">{{ t('Deleted') }}</option>
      </select>
      <button type="submit" :disabled="loading">{{ t('Search') }}</button>
    </form>
    <p v-if="loading" role="status">{{ t('Loading…') }}</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
    <template v-else>
      <div class="cards">
        <article v-for="target in users" :key="target.id">
          <h2><RouterLink :to="{path: `/admin/users/${target.id}`, query: {lang: session.lang}}">{{ target.email }}</RouterLink></h2>
          <p>{{ t(target.role === 'admin' ? 'Administrator' : 'User') }} · {{ t(stateName(target)) }}</p>
        </article>
        <p v-if="!users.length">{{ t('No users found.') }}</p>
      </div>
      <nav v-if="page > 1 || hasNext" :aria-label="t('Users')" class="pagination">
        <RouterLink v-if="page > 1" :to="pageLink(page - 1)">{{ t('Previous') }}</RouterLink>
        <RouterLink v-if="hasNext" :to="pageLink(page + 1)">{{ t('Next') }}</RouterLink>
      </nav>
    </template>
  </template>
</template>
