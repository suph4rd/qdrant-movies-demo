export type Language = 'en' | 'ru'
export type Flag = 'watched' | 'liked' | 'watchlist'
export interface User {
    id: number
    email: string
    role: string
    blocked: boolean
    created_at: string
    deleted_at: string | null
}
export interface Movie {
    id: string
    title: string
    year: number
    genres: string[]
    description: string
    original_title?: string
    wikidata_id?: string
    tmdb_id?: string
    description_language?: string
    mark_reference?: string
}
export interface Mark {
    movie_id: string
    watched: boolean
    liked: boolean
    watchlist: boolean
}
export interface MovieList {
    flag: Flag
    label: string
    page: number
    total: number
    has_next: boolean
    movies: { movie: Movie; mark: Mark }[]
}
export interface Context {
    user: User | null
    lang: Language
    csrf_token: string
    catalog: Movie[]
    search_modes: string[]
    limit_options: string[]
    default_mode: string
    default_limit: string
    movie_count: number | null
    marks: Record<string, Mark>
}
export interface SearchResult {
    messages: string[]
    groups: {
        source: Movie | null
        recommendations: { id: string; score: number; payload: Movie }[]
    }[]
}
