<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { session } from '../session'
import { t } from '../i18n'
import type { Mark, MovieList } from '../types'
import MovieCard from '../components/MovieCard.vue'
const route = useRoute(),
    lists = ref<MovieList[]>([]),
    loading = ref(false),
    error = ref('')
let revision = 0
onUnmounted(() => {
    revision++
})
async function load() {
    const current = ++revision
    loading.value = true
    error.value = ''
    try {
        const data = await api<{
            lists: MovieList[]
            marks: Record<string, Mark>
        }>('/account', {
            query: {
                list:
                    typeof route.query.list === 'string'
                        ? route.query.list
                        : 'watched',
                page:
                    typeof route.query.page === 'string'
                        ? route.query.page
                        : '1',
            },
        })
        if (current === revision) {
            lists.value = data.lists
            if (session.context) session.context.marks = data.marks
        }
    } catch (cause) {
        if (current === revision)
            error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
        if (current === revision) loading.value = false
    }
}
watch(() => route.fullPath, load, { immediate: true })
function pageLink(list: MovieList, page: number) {
    return {
        path: '/account',
        query: { list: list.flag, page: String(page), lang: session.lang },
    }
}
</script>
<template>
    <h1>{{ t('My account') }}</h1>
    <p>{{ session.context?.user?.email }}</p>
    <p class="account-status" aria-live="polite">
        <span v-if="loading" role="status">{{ t('Loading…') }}</span>
    </p>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <section
        v-for="list in lists"
        :key="list.flag"
        :aria-labelledby="`list-${list.flag}`"
    >
        <h2 :id="`list-${list.flag}`">
            {{ t(list.label) }} ({{ list.total }})
        </h2>
        <div class="cards">
            <MovieCard
                v-for="entry in list.movies"
                :key="entry.movie.id"
                :movie="entry.movie"
                marks
                @changed="load"
            />
            <p v-if="!list.movies.length">
                {{ t('No movies in this list yet.') }}
            </p>
        </div>
        <nav
            v-if="list.page > 1 || list.has_next"
            class="pagination"
            :aria-label="t(list.label)"
        >
            <RouterLink
                v-if="list.page > 1"
                :to="pageLink(list, list.page - 1)"
                >{{ t('Previous') }}</RouterLink
            ><span>{{ t('Page %(page)s', { page: list.page }) }}</span
            ><RouterLink
                v-if="list.has_next"
                :to="pageLink(list, list.page + 1)"
                >{{ t('Next') }}</RouterLink
            >
        </nav>
    </section>
</template>
