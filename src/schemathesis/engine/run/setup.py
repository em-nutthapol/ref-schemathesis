"""Setup phase: one-time preparation of a test run before any test case is generated."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from schemathesis.core import SpecificationFeature
from schemathesis.core.errors import HookExecutionError
from schemathesis.engine import Status, events
from schemathesis.hooks import dispatch_setup

if TYPE_CHECKING:
    from schemathesis.engine.context import EngineContext
    from schemathesis.engine.events import EventGenerator
    from schemathesis.engine.run import Phase
    from schemathesis.engine.run.auth_bootstrap import AuthBootstrapPayload
    from schemathesis.engine.run.cache import CacheReport
    from schemathesis.engine.run.probes import ProbeRun


@dataclass(slots=True)
class SetupPayload:
    probes: list[ProbeRun]
    cache: CacheReport | None = None
    # `None` when the specification does not support signing up.
    auth: AuthBootstrapPayload | None = None


def execute(ctx: EngineContext, phase: Phase) -> EventGenerator:
    from schemathesis.engine.run import analysis, auth_bootstrap, probes

    specification = ctx.schema.specification
    payload = SetupPayload(probes=probes.probe(ctx), cache=ctx.cache.run())
    hook_failed = False
    # A run that has to stop, e.g. because probing spent the time budget, skips the remaining steps.
    if specification.supports_feature(SpecificationFeature.SCHEMA_ANALYSIS) and not ctx.has_to_stop:
        hook_failed = yield from analysis.analyze(ctx, phase)
    if specification.supports_feature(SpecificationFeature.AUTH_BOOTSTRAP) and not ctx.has_to_stop:
        payload.auth = yield from auth_bootstrap.bootstrap(ctx)
    if not ctx.has_to_stop:
        try:
            dispatch_setup(ctx.schema)
        except HookExecutionError as exc:
            hook_failed = True
            yield events.hook_error(phase.name, exc)
    failed = hook_failed or (payload.auth is not None and payload.auth.status == Status.ERROR)
    yield events.PhaseFinished(phase=phase, status=Status.ERROR if failed else Status.SUCCESS, payload=payload)
