from . import operators, preferences, panel


def register():
    preferences.register()
    operators.register()
    panel.register()


def unregister():
    panel.unregister()
    operators.unregister()
    preferences.unregister()
