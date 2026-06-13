from . import operators, preferences


def register():
    preferences.register()
    operators.register()


def unregister():
    operators.unregister()
    preferences.unregister()
