# -*- coding: utf-8 -*-
"""
============================================================================
Normalizador de Progresso do Pipeline SONAX.

Converte etapas de execução pontuais e heterogêneas das 8 fases do pipeline
em uma escala cumulativa global contínua (0.0 a 1.0) e formata os rótulos de
contexto para visualização pelo chamador.

Pesos acumulados por fase (total 100%):
    1. scanning      0%   → 2%   (offset 0.00, peso 0.02)
    2. classifying   2%   → 5%   (offset 0.02, peso 0.03)
    3. copying       5%   → 10%  (offset 0.05, peso 0.05)
    4. transcribing  10%  → 80%  (offset 0.10, peso 0.70)
    5. inserting     80%  → 83%  (offset 0.80, peso 0.03)
    6. reviewing     83%  → 91%  (offset 0.83, peso 0.08)
    7. analyzing     91%  → 98%  (offset 0.91, peso 0.07)
    8. cleanup       98%  → 100% (offset 0.98, peso 0.02)
============================================================================
"""
from __future__ import annotations

from app.engine.events import ProgressUpdateEvent


class ProgressNormalizer:
    """Calculador de progresso normalizado e gerador de rótulos contextuais."""

    # (offset, peso, prefixo_fixo_ou_None)
    PHASE_SPECS: dict[str, tuple[float, float, str | None]] = {
        "scanning": (0.00, 0.02, "varrendo  •  "),
        "classifying": (0.02, 0.03, "classificando  •  "),
        "copying": (0.05, 0.05, "copiando  •  "),
        "transcribing": (0.10, 0.70, None),  # dinâmico: "{done}/{total} arquivos  •  "
        "inserting": (0.80, 0.03, "gravando no banco  •  "),
        "reviewing": (0.83, 0.08, None),     # dinâmico: "revisando {done}/{total}  •  "
        "analyzing": (0.91, 0.07, None),     # dinâmico: "analisando {done}/{total}  •  "
        "cleanup": (0.98, 0.02, "limpando temporários  •  "),
    }

    def normalize(
        self,
        done: float,
        total: float,
        phase: str = "",
        message: str | None = None,
    ) -> ProgressUpdateEvent:
        """Calcula o progresso global (0.0 a 1.0) e gera o evento normalizado."""
        if total <= 0:
            return ProgressUpdateEvent(
                fraction=0.0,
                label="Processando ...",
                phase=phase,
                done=done,
                total=total,
                message=message,
                is_indeterminate=True,
            )

        step_pct = max(0.0, min(1.0, done / total)) if total > 0 else 0.0
        fase = (phase or "").lower().strip()

        if fase in self.PHASE_SPECS:
            offset, peso, prefixo = self.PHASE_SPECS[fase]
            cumulativo = offset + (step_pct * peso)

            if prefixo is not None:
                contexto = prefixo
            elif fase == "transcribing":
                done_int = min(int(total), int(done) + 1 if done < total else int(total))
                total_int = int(total)
                contexto = f"{done_int}/{total_int} arquivos  •  "
            elif fase == "reviewing":
                done_int = min(int(total), int(done) + 1 if done < total else int(total))
                total_int = int(total)
                contexto = f"revisando {done_int}/{total_int}  •  "
            elif fase == "analyzing":
                done_int = min(int(total), int(done) + 1 if done < total else int(total))
                total_int = int(total)
                contexto = f"analisando {done_int}/{total_int}  •  "
            else:
                contexto = ""
        else:
            cumulativo = step_pct
            contexto = ""

        cumulativo = min(1.0, max(0.0, cumulativo))
        label = f"{contexto}{cumulativo * 100:.0f}%"

        return ProgressUpdateEvent(
            fraction=cumulativo,
            label=label,
            phase=fase,
            done=done,
            total=total,
            message=message,
            is_indeterminate=False,
        )
