from web.presentation import pages


async def render_form(request, registration=False, error=None, email='', status_code=200):
    return await pages.render(request, 'auth.html', {
        'registration': registration, 'error': error, 'email': email,
        'heading': 'Register' if registration else 'Log in'}, status_code=status_code)


