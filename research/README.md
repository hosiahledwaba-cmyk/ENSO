# ENSO Shield: Living Research Documentation Workflow

This directory serves as the scientific core of the ENSO Shield platform. In accordance with the project's research-led engineering principles, the scientific paper and experiment records evolve continuously alongside software implementation.

---

## Directory Index

```text
research/
├── README.md                           # This index and research workflow guide
├── paper/
│   ├── manuscript.md                   # Living scientific manuscript (working Markdown)
│   ├── manuscript.tex                  # Publication manuscript in Springer LNCS LaTeX format
│   └── references.bib                  # Verified BibTeX bibliography
├── protocol/
│   └── research_protocol.md            # Questions, hypotheses, target math, splits, and threat models
├── experiments/
│   ├── experiment_log.md               # Chronological log of executed empirical runs
│   └── claims_and_evidence.md          # Scientific claims register and evidence matrix
└── decisions/
    └── research_decisions.md           # Formal architectural and climatological decision records
```

---

## The Co-Evolution Workflow

```
+-------------------------------------------------------------------------------+
|                        IMPLEMENTATION MILESTONE CYCLE                         |
|                                                                               |
|  1. Software Implementation ---> 2. Automated Experiments & Artifact Logging  |
|       (ml/, security/, api/)     (Run tests, export metrics to experiment_log)|
|                                                        |                      |
|                                                        v                      |
|  4. Publication Sync        <--- 3. Manuscript & Evidence Update              |
|     (Sync manuscript.tex         (Update manuscript.md & claims_and_evidence) |
|      with BibTeX citations)                                                   |
+-------------------------------------------------------------------------------+
```

### Protocol for Every Implementation Milestone
1. **No Phantom Claims:** Never write results or novelty claims into the manuscript until code has executed, automated tests pass, and metrics are recorded in `experiment_log.md`.
2. **Update on Completion:** When a milestone prompt completes:
   * Record the experiment configuration and actual numbers in `experiments/experiment_log.md`.
   * Update the corresponding empirical tables in `paper/manuscript.md` and `paper/manuscript.tex`.
   * Cross-reference new verified claims in `experiments/claims_and_evidence.md`.
3. **Immutability of History:** Never overwrite historical experiment runs in `experiment_log.md`. If a protocol is altered, document the decision in `decisions/research_decisions.md` and append a new experiment entry.

---

## Compiling the Scientific Manuscript

The scientific manuscript is maintained as Markdown (`manuscript.md`) for version control readability, with a twin Springer LNCS LaTeX template (`manuscript.tex`).

### Compiling to PDF via LaTeX (Local or Docker)
If LaTeX is installed locally:
```powershell
cd research/paper
pdflatex -interaction=nonstopmode manuscript.tex
bibtex manuscript
pdflatex -interaction=nonstopmode manuscript.tex
pdflatex -interaction=nonstopmode manuscript.tex
```

Alternatively, compile using an unprivileged Docker container:
```powershell
docker run --rm -v "C:\myworkspaces\projects\ENSO\research\paper:/work" -w /work texlive/texlive:latest sh -c "pdflatex manuscript.tex && bibtex manuscript && pdflatex manuscript.tex"
```

The files are also fully compatible with Overleaf (upload `manuscript.tex`, `references.bib`, and the Springer `llncs.cls` class file).

---

## Summary of Active Research Decisions

* **RD-001:** Lookahead climatology leakage resolved by freezing training-period normal parameters ($\mu, \sigma, \tau_{20}$) over 1981–2005.
* **RD-002:** Seasonal target defined as core austral summer (DJF) indexed by calendar year of January/February ($Y$). Forecast issued November 1st with 1-to-3 month lead time.
* **RD-003:** Bounding box focused on Limpopo Basin & South African Maize Quadrangle ($22^\circ\text{S} - 30^\circ\text{S}, 25^\circ\text{E} - 32^\circ\text{E}$).
* **RD-004:** Threat model formalized around False Data Injection (FDI) and sensor telemetry replay, defended via cryptographic SHA-256 provenance and dynamic Mahalanobis anomaly screening.
