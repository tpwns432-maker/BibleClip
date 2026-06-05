"""Route mixins for the pywebview JS bridge.

pywebview's ``js_api`` must be a single object, so the bridge surface is split
into mixin classes that ``webui.api.Api`` composes via multiple inheritance.
Each mixin only uses shared instance state (``self.lib``, ``self._push``, …)
established by ``Api.__init__`` — none define their own ``__init__``.
"""
from bibleclip.webui.routes.bible import BibleRoutes
from bibleclip.webui.routes.notes import NoteRoutes
from bibleclip.webui.routes.system import SystemRoutes

__all__ = ['BibleRoutes', 'NoteRoutes', 'SystemRoutes']
