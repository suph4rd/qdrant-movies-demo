import { createRouter, createWebHistory } from 'vue-router'
import Search from './pages/Search.vue'
import Auth from './pages/Auth.vue'
import Account from './pages/Account.vue'
import AdminUsers from './pages/AdminUsers.vue'
import AdminUser from './pages/AdminUser.vue'
import NotFound from './pages/NotFound.vue'
export const router = createRouter({
    history: createWebHistory(),
    routes: [
        { path: '/', component: Search },
        { path: '/login', component: Auth },
        { path: '/register', component: Auth },
        { path: '/account', component: Account },
        { path: '/admin/users', component: AdminUsers },
        { path: '/admin/users/:id', component: AdminUser },
        { path: '/:pathMatch(.*)*', component: NotFound },
    ],
    scrollBehavior: (to, from, saved) => {
        if (saved) return saved
        if (to.path === '/account' && from.path === '/account') return false
        return { top: 0 }
    },
})
