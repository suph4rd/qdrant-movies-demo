<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { readTask, rememberTask, searchTasks } from '../searchTasks'
import { ApiError, api } from '../api'
import { session } from '../session'
import { t } from '../i18n'
import type { SearchTask, SearchSubmission, Mark, SearchResult } from '../types'
import MovieCard from '../components/MovieCard.vue'
import MovieMarks from '../components/MovieMarks.vue'
const route = useRoute(),
    router = useRouter()
const query = ref(''),
    mode = ref('movie'),
    limit = ref('10'),
    busy = ref(false),
    loading = ref(false),
    error = ref(''),
    result = ref<SearchResult | null>(null)
let revision = 0
onUnmounted(() => {
    revision++
})
function value(key: string, fallback: string) {
    const raw = route.query[key]
    return typeof raw === 'string' ? raw : fallback
}
watch(
    [() => route.fullPath, () => searchTasks.tasks.find(task => task.task_id === value('task', ''))?.status],
    async () => {
        const current = ++revision
        query.value = value('q', '')
        mode.value = value('mode', session.context?.default_mode || 'movie')
        limit.value = value('limit', session.context?.default_limit || '10')
        result.value = null
        error.value = ''
        loading.value = false
        if (value('task', '')) {
            loading.value = true
            try {
                const data = await api<{ task: SearchTask; marks: Record<string, Mark>; movie_count?: number | null }>(`/search-tasks/${encodeURIComponent(value('task', ''))}`)
                if (current !== revision) return
                query.value = data.task.params.q
                mode.value = data.task.params.mode
                limit.value = data.task.params.limit
                result.value = data.task.result || null
                error.value = data.task.error || ''
                if (session.context) {
                    session.context.marks = data.marks
                    if (data.movie_count !== undefined) session.context.movie_count = data.movie_count
                }
                if (data.task.status === 'succeeded' || data.task.status === 'failed') {
                    await readTask(data.task.task_id).catch(cause => { searchTasks.error = cause instanceof Error ? cause.message : String(cause) })
                } else {
                    rememberTask(data.task)
                }
            } catch (cause) {
                if (current === revision) error.value = cause instanceof Error ? cause.message : String(cause)
            } finally { if (current === revision) loading.value = false }
            return
        }
        if (!Object.hasOwn(route.query, 'q')) return
        loading.value = true
        try {
            const data = await api<{
                result: SearchResult | null
                marks: Record<string, Mark>
                movie_count?: number | null
            }>('/search', {
                query: {
                    q: query.value,
                    mode: mode.value,
                    limit: limit.value,
                    result: value('result', ''),
                },
            })
            if (current === revision) {
                result.value = data.result
                if (session.context) {
                    session.context.marks = data.marks
                    if (data.movie_count !== undefined)
                        session.context.movie_count = data.movie_count
                }
            }
        } catch (cause) {
            if (current === revision)
                error.value =
                    cause instanceof Error ? cause.message : String(cause)
        } finally {
            if (current === revision) loading.value = false
        }
    },
    { immediate: true },
)
const conflictTask = ref('')
async function submit() {
    if (busy.value) return
    busy.value = true
    error.value = ''
    conflictTask.value = ''
    const current = revision
    const params = { q: query.value, mode: mode.value, limit: limit.value }
    try {
        const data = await api<SearchSubmission>('/search', {
            method: 'POST',
            body: params,
        })
        if (current !== revision) return
        if ('task_id' in data) {
            rememberTask({ ...data, params })
            return
        }
        await router.push({
            path: '/',
            query: { ...params, result: data.token, lang: session.lang },
        })
    } catch (cause) {
        if (cause instanceof ApiError && cause.task_id) conflictTask.value = cause.task_id
        error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
        busy.value = false
    }
}
</script>
<template>
    <header>
        <p class="eyebrow">
            {{
                session.context?.movie_count == null
                    ? t('MOVIE CATALOG · Count unavailable')
                    : t('MOVIE CATALOG · MOVIES: %(count)s', {
                          count: session.context.movie_count,
                      })
            }}
        </p>
        <h1>{{ t('What to watch next?') }}</h1>
        <p>
            {{
                t(
                    'Choose a movie or describe what you want to watch in English or Russian.',
                )
            }}
        </p>
    </header>
    <form @submit.prevent="submit" :aria-busy="busy">
        <label for="mode">{{ t('Search mode') }}</label
        ><select id="mode" v-model="mode">
            <option value="movie">{{ t('By movie') }}</option>
            <option value="description">{{ t('By description') }}</option>
        </select>
        <label for="query">{{ t('Movie title, ID, or description') }}</label>
        <div class="search">
            <input
                id="query"
                v-model="query"
                :list="mode === 'movie' ? 'titles' : undefined"
                :placeholder="
                    t(
                        'For example, The Matrix, 1, or an astronaut stranded on Mars',
                    )
                "
                aria-describedby="hint"
            /><button :disabled="busy || loading">
                {{ t('Find similar movies') }}
            </button>
        </div>
        <label for="limit">{{ t('Number of similar movies') }}</label
        ><select id="limit" v-model="limit">
            <option
                v-for="option in session.context?.limit_options"
                :key="option"
                :value="option"
            >
                {{ option }}
            </option>
        </select>
        <datalist id="titles">
            <option
                v-for="movie in session.context?.catalog"
                :key="movie.id"
                :value="movie.title"
            />
        </datalist>
        <p id="hint" class="muted">
            {{
                t(
                    'In movie mode, enter a title or ID. In description mode, describe a plot or mood in English or Russian.',
                )
            }}
        </p>
    </form>
    <p v-if="busy || loading" role="status">{{ t('Loading…') }}</p>
    <p v-if="error" role="alert" class="error">{{ error }}
        <RouterLink v-if="conflictTask" :to="{ path: '/', query: { task: conflictTask, lang: session.lang } }">{{ t('View search task') }}</RouterLink>
    </p>
    <template v-else-if="result">
        <p
            v-for="(message, index) in result.messages"
            :key="index"
            role="status"
        >
            {{ message }}
        </p>
        <section
            v-for="(group, index) in result.groups"
            :key="index"
            :aria-labelledby="`results-${index}`"
        >
            <h2 :id="`results-${index}`">
                {{
                    group.source
                        ? t('Similar to “%(title)s”', {
                              title: group.source.title,
                          }) + ` (${group.source.year})`
                        : t('Movies matching your description')
                }}<template v-if="group.source?.original_title">
                    · {{ group.source.original_title }}</template
                ><template v-if="group.source?.wikidata_id">
                    · {{ group.source.wikidata_id }}</template
                ><template v-else-if="group.source?.tmdb_id">
                    · TMDB {{ group.source.tmdb_id }}</template
                >
            </h2>
            <template v-if="group.source?.wikidata_id"
                ><p>
                    <a
                        :href="`https://www.wikidata.org/wiki/${encodeURIComponent(group.source.wikidata_id)}`"
                        >{{ t('Source: Wikidata') }}</a
                    >
                </p>
                <p class="muted">
                    {{
                        t(
                            'Wikidata provides a short description, not a plot summary. Plot-based recommendations may be less precise.',
                        )
                    }}
                </p></template
            >
            <p v-else-if="group.source?.tmdb_id">
                <a
                    :href="`https://www.themoviedb.org/movie/${encodeURIComponent(group.source.tmdb_id)}`"
                    >{{ t('Source: TMDB') }}</a
                >
            </p>
            <MovieMarks
                v-if="group.source?.mark_reference"
                :movie="group.source"
            />
            <p class="muted">
                {{
                    t(
                        'Cosine similarity measures vector similarity, not the probability that you will like a movie.',
                    )
                }}
            </p>
            <div class="cards">
                <MovieCard
                    v-for="point in group.recommendations"
                    :key="point.id"
                    :movie="point.payload"
                    :score="point.score"
                    :marks="!!point.payload.mark_reference"
                />
                <p v-if="!group.recommendations.length">
                    {{ t('No similar movies yet.') }}
                </p>
            </div>
        </section>
    </template>
    <p v-else-if="!loading && !busy && !error" class="initial">
        {{
            t('Start with a favorite movie. Recommendations will appear here.')
        }}
    </p>
</template>
