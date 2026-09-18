"""Request and response models the row models do not already cover.

Task 1.2 put one model per *stored* shape in :mod:`resumetailor.db.models` and
left ``response_model`` to this task (D-54). What it could not cover is
everything that is not a row:

* :mod:`~resumetailor.api.schemas.errors` -- the three error bodies this API
  actually produces, the union of them, and the ``responses=`` tables that put
  them in the OpenAPI document.
* :mod:`~resumetailor.api.schemas.health` -- the liveness body.
* :mod:`~resumetailor.api.schemas.sse` -- the frames of the three streaming
  routes, which ``response_model`` cannot describe at all.

Request models stay in their routers. Moving them here would be a wider diff
through files tasks 2.4 and 2.5 have just rewritten, for no gain: a request
model is read at exactly one place, and FastAPI already documents it.

Nothing is re-exported from this package on purpose. Import from the module
that defines it, so a reader can see which of the three concerns a name
belongs to.
"""
