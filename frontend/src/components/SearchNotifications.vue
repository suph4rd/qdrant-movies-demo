<script setup lang="ts">
import { onUnmounted, watch } from 'vue'
import { session } from '../session'
import { t } from '../i18n'
import { readTask, refreshTasks, resetTasks, searchTasks } from '../searchTasks'
import type { SearchTask } from '../types'
let stop = () => {}
watch(() => [session.context?.csrf_token, session.context?.user?.id, session.lang], () => {
    stop()
    resetTasks()
    if (!session.context) return
    let disposed = false
    let socket: WebSocket | undefined
    let timer: ReturnType<typeof setTimeout> | undefined
    function connect() {
        if (disposed) return
        void refreshTasks()
        socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/notifications/ws`)
        socket.onopen = () => { void refreshTasks() }
        socket.onmessage = event => {
            try {
                const data = JSON.parse(event.data)
                if (data.event === 'search.completed' || data.event === 'heartbeat') void refreshTasks()
            } catch { /* Ignore malformed transport messages and recover on reconnect. */ }
        }
        socket.onclose = () => {
            if (!disposed) timer = setTimeout(connect, 2000)
        }
        socket.onerror = () => socket?.close()
    }
    stop = () => {
        disposed = true
        clearTimeout(timer)
        socket?.close()
    }
    connect()
}, { immediate: true })
onUnmounted(() => stop())
function label(task: SearchTask) {
    if (task.status === 'succeeded') return t('External search completed')
    if (task.status === 'failed') return t('External search failed')
    return t('External search in progress')
}
async function dismiss(id: string) {
    try { await readTask(id) }
    catch (error) { searchTasks.error = error instanceof Error ? error.message : String(error) }
}
</script>
<template>
    <aside v-if="searchTasks.tasks.length || searchTasks.error" :aria-label="t('Search notifications')" class="search-notifications">
        <p v-if="searchTasks.error" role="alert">{{ searchTasks.error }} <button @click="refreshTasks">{{ t('Retry') }}</button></p>
        <div v-for="task in searchTasks.tasks" :key="task.task_id" role="status">
            <RouterLink :to="{ path: '/', query: { task: task.task_id, lang: session.lang } }">{{ label(task) }}: {{ task.params.q }}</RouterLink>
            <button v-if="task.status === 'succeeded' || task.status === 'failed'" @click="dismiss(task.task_id)">{{ t('Mark as read') }}</button>
        </div>
    </aside>
</template>
