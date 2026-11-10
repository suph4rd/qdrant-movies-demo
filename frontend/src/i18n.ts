import ru from './translations.json'
import { session } from './session'
export function t(
    message: string,
    params: Record<string, string | number> = {},
) {
    const translated =
        session.lang === 'ru'
            ? (ru as Record<string, string>)[message] || message
            : message
    return translated.replace(/%\((\w+)\)s/g, (match, key: string) =>
        String(params[key] ?? match),
    )
}
