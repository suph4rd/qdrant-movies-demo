<script setup lang="ts">
import type { Movie } from '../types'
import { t } from '../i18n'
import MovieMarks from './MovieMarks.vue'
defineProps<{ movie: Movie; score?: number; marks?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
</script>
<template>
    <article>
        <p class="muted">{{ movie.year }} · {{ movie.genres.join(' / ') }}</p>
        <h3>{{ movie.title }}</h3>
        <p>{{ movie.description }}</p>
        <p v-if="movie.description_language" class="muted">
            {{
                t('Description language: %(language)s', {
                    language: movie.description_language.toUpperCase(),
                })
            }}
        </p>
        <template v-if="movie.wikidata_id"
            ><p class="muted">{{ t('Short description from Wikidata') }}</p>
            <a
                :href="`https://www.wikidata.org/wiki/${encodeURIComponent(movie.wikidata_id)}`"
                >{{ t('Source: Wikidata') }}</a
            ></template
        >
        <a
            v-else-if="movie.tmdb_id"
            :href="`https://www.themoviedb.org/movie/${encodeURIComponent(movie.tmdb_id)}`"
            >{{ t('Source: TMDB') }}</a
        >
        <MovieMarks v-if="marks" :movie="movie" @changed="emit('changed')" />
        <p v-if="score !== undefined" class="score">
            {{ t('Cosine similarity') }}: {{ score.toFixed(4) }}
        </p>
    </article>
</template>
