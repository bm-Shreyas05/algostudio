"""The engine, assembled for a browser instead of a server.

Everything here runs inside Pyodide. There is no sandbox module in this
package and there is no need for one: the browser tab *is* the boundary, and
it is a far better one than anything CPython could enforce on itself. The code
a visitor types executes on the visitor's own machine, under the same origin
policy as every other page they have open, and never reaches this project's
server at all.

That is what makes the public deployment able to offer arbitrary code while
``ALGOSTUDIO_ALLOW_ARBITRARY_CODE`` stays 0: the server continues to refuse to
execute anything it did not ship. See docs/21-pyodide-spike.md.
"""

from .engine import analytics, meta, run, views  # noqa: F401
