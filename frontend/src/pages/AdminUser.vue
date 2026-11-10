<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { session } from '../session'
import { t } from '../i18n'
import type { User, MovieList } from '../types'

const route = useRoute()
const detail = ref<{ user: User; lists: MovieList[]; page: number; has_next: boolean } | null>(null)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const confirmation = ref('')
const allowed = computed(() => session.context?.user?.role === 'admin')
const target = computed(() => detail.value?.user)
const page = computed(() => Number(route.query.page || 1))
const isSelf = computed(() => target.value?.id === session.context?.user?.id)
let generation = 0
function pageLink(value: number) {
  return { path: route.path, query: { ...route.query, lang: session.lang, page: String(value) } }
}
function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}
async function load() {
  const current = ++generation
  error.value = ''
  detail.value = null
  confirmation.value = ''
  if (!allowed.value) return
  loading.value = true
  try {
    const result = await api<{ user: User; lists: MovieList[]; page: number; has_next: boolean }>(`/admin/users/${route.params.id}`, {
      query: { page: String(route.query.page || 1) },
    })
    if (current === generation) detail.value = result
  } catch (cause) {
    if (current === generation) error.value = cause instanceof Error ? cause.message : t('The request failed. Try again.')
  } finally {
    if (current === generation) loading.value = false
  }
}
async function change(action: string) {
  if (submitting.value || !target.value) return
  const path = `/admin/users/${target.value.id}`
  const email = confirmation.value
  submitting.value = true
  error.value = ''
  try {
    await api(path, { method: 'POST', body: { action, confirmation_email: email } })
    if (path === route.path) await load()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('The request failed. Try again.')
  } finally {
    submitting.value = false
  }
}
watch(() => [route.fullPath, session.lang, allowed.value], load, { immediate: true })
</script>

<template>
  <p v-if="!allowed" class="error" role="alert">{{ t('Administrator access required') }}</p>
  <p v-else-if="loading" role="status">{{ t('Loading…') }}</p>
  <template v-else>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="target && detail">
      <h1>{{ target.email }}</h1>
      <p>{{ t(target.role === 'admin' ? 'Administrator' : 'User') }} · {{ t(target.deleted_at ? 'Deleted' : target.blocked ? 'Blocked' : 'Active') }}</p>
      <p>{{ t('Created') }}: <time :datetime="target.created_at">{{ formatDate(target.created_at) }}</time></p>
      <p v-if="target.deleted_at">{{ t('Deleted at') }}: {{ formatDate(target.deleted_at) }}</p>
      <form v-if="target.deleted_at" class="admin-actions" @submit.prevent="change('restore')">
        <button type="submit" :disabled="submitting">{{ t('Restore as blocked') }}</button>
      </form>
      <template v-else-if="!isSelf">
        <div class="admin-actions">
          <button type="button" :disabled="submitting" @click="change(target.blocked ? 'unblock' : 'block')">{{ t(target.blocked ? 'Unblock' : 'Block') }}</button>
          <button type="button" :disabled="submitting" @click="change(target.role === 'admin' ? 'demote' : 'promote')">{{ t(target.role === 'admin' ? 'Remove administrator role' : 'Make administrator') }}</button>
        </div>
        <form class="admin-actions" @submit.prevent="change('delete')">
          <label for="confirmation-email">{{ t('Confirm deletion by entering the user email.') }}</label>
          <input id="confirmation-email" v-model="confirmation" type="email" name="confirmation_email" required autocomplete="off" :disabled="submitting">
          <p class="muted">{{ t('Deletion preserves the email and movie lists.') }}</p>
          <button class="button-danger" type="submit" :disabled="submitting">{{ t('Delete user') }}</button>
        </form>
      </template>
      <p class="muted">{{ t('Movie lists are read-only for administrators.') }}</p>
      <section v-for="group in detail.lists" :key="group.flag">
        <h2>{{ t(group.label) }}</h2>
        <div class="cards">
          <article v-for="item in group.movies" :key="item.movie.id">
            <h3>{{ item.movie.title }}</h3><p>{{ item.movie.year }} · {{ item.movie.genres.join(' / ') }}</p><p>{{ item.movie.description }}</p>
          </article>
          <p v-if="!group.movies.length">{{ t('This list is empty.') }}</p>
        </div>
      </section>
      <nav v-if="page > 1 || detail.has_next" :aria-label="t('Users')" class="pagination">
        <RouterLink v-if="page > 1" :to="pageLink(page - 1)">{{ t('Previous') }}</RouterLink>
        <RouterLink v-if="detail.has_next" :to="pageLink(page + 1)">{{ t('Next') }}</RouterLink>
      </nav>
    </template>
  </template>
</template>
