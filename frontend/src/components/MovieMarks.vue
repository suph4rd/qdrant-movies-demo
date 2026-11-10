<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import { session } from '../session'
import { t } from '../i18n'
import type { Flag, Mark, Movie } from '../types'
const props = defineProps<{ movie: Movie }>()
const emit = defineEmits<{ changed: [] }>()
const busy = ref(false),
    error = ref('')
const flags: { flag: Flag; label: string }[] = [
    { flag: 'watched', label: 'Watched' },
    { flag: 'liked', label: 'Liked' },
    { flag: 'watchlist', label: 'Watchlist' },
]
async function update(flag: Flag) {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
        const result = await api<{ marks: Record<string, Mark> }>(
            '/account/marks',
            {
                method: 'POST',
                body: {
                    movie_id: props.movie.id,
                    flag,
                    state: !session.context?.marks[props.movie.id]?.[flag],
                    reference: props.movie.mark_reference || '',
                },
            },
        )
        if (session.context) session.context.marks = result.marks
        emit('changed')
    } catch (cause) {
        error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
        busy.value = false
    }
}
</script>
<template>
    <div
        v-if="session.context?.user"
        class="movie-marks"
        :aria-label="t('My account')"
    >
        <button
            v-for="item in flags"
            :key="item.flag"
            type="button"
            :disabled="busy"
            :aria-pressed="!!session.context.marks[movie.id]?.[item.flag]"
            @click="update(item.flag)"
        >
            {{
                t(
                    session.context.marks[movie.id]?.[item.flag]
                        ? 'Remove from %(list)s'
                        : 'Add to %(list)s',
                    { list: t(item.label) },
                )
            }}
        </button>
        <p v-if="error" role="alert" class="error">{{ error }}</p>
    </div>
</template>
