import { reactive } from 'vue'
import { api } from './api'
import type { SearchTask } from './types'

export const searchTasks = reactive<{ tasks: SearchTask[]; error: string }>({ tasks: [], error: '' })
let generation = 0
let request = 0

export function resetTasks() {
    generation++
    searchTasks.tasks = []
    searchTasks.error = ''
}
export function rememberTask(task: SearchTask) {
    request++
    const index = searchTasks.tasks.findIndex(item => item.task_id === task.task_id)
    if (index < 0) searchTasks.tasks.push(task)
    else searchTasks.tasks[index] = { ...searchTasks.tasks[index], ...task }
}
export async function refreshTasks() {
    const current = generation
    const revision = ++request
    try {
        const data = await api<{ tasks: SearchTask[] }>('/search-tasks')
        if (current === generation && revision === request) {
            searchTasks.tasks = data.tasks
            searchTasks.error = ''
        }
    } catch (error) {
        if (current === generation && revision === request)
            searchTasks.error = error instanceof Error ? error.message : String(error)
    }
}
export async function readTask(task_id: string) {
    const current = generation
    await api(`/search-tasks/${encodeURIComponent(task_id)}/read`, { method: 'POST', body: {} })
    if (current === generation)
        searchTasks.tasks = searchTasks.tasks.filter(task => task.task_id !== task_id || ['queued', 'running'].includes(task.status))
}
