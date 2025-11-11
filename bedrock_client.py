"""Deprecated Nova Sonic client interface.

The original helper based on the AWS console samples is no longer used after
migrating to the real-time session utilities. This module remains only to avoid
import errors for legacy code; new integrations should import
``NovaSonicRealtimeSession`` from ``nova_sonic_realtime`` instead.
"""

from __future__ import annotations

import warnings

__all__ = ["NovaSonicClient"]


class NovaSonicClient:  # pylint: disable=too-few-public-methods
    """Compatibility wrapper that points developers to the new helper."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401
        warnings.warn(
            (
                "`NovaSonicClient` fue reemplazado por `NovaSonicRealtimeSession`. "
                "Actualiza tus importaciones a `nova_sonic_realtime` para acceder al "
                "flujo oficial bidireccional."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        raise RuntimeError(
            "NovaSonicClient está deprecado. Usa NovaSonicRealtimeSession en "
            "`nova_sonic_realtime.py`."
        )
