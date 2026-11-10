class ScenarioError(ValueError):
    def __init__(self, message, **params):
        super().__init__(message)
        self.message = message
        self.params = params


class AuthenticationRequired(ScenarioError):
    def __init__(self):
        super().__init__('Authentication required')


class AdministratorRequired(ScenarioError):
    def __init__(self):
        super().__init__('Administrator access required')


class UserNotFound(ScenarioError):
    def __init__(self):
        super().__init__('User not found.')


class EmailRegistered(ScenarioError):
    def __init__(self):
        super().__init__('This email is already registered.')
