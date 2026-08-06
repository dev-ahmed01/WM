# WorkMate AI — Modular OWD Compiler Subsystem

The **OWD Compiler** converts declarative Operational Workflow Definition (OWD) Markdown files into normalized, executable finite state machine tables in Snowflake.

---

## Compiler Architecture & Pipeline Stages

```
OWD Markdown Source Code (.md)
            │
            ▼
[ 1. Parser (parser.py) ] ──────> OWDDocument AST
            │
            ▼
[ 2. Validator (validator.py) ] ─> ValidationReport (Errors / Warnings)
            │
            ▼
[ 3. Compiler (compiler.py) ] ──> CompiledWorkflow (Relational Dict Payloads)
            │
            ▼
[ 4. Loader (loader.py) ] ──────> Snowflake Tables (KNOWLEDGE_STUDIO.*)
```

---

## Module Breakdown

| Module | Core Responsibility | External Dependencies | SQL / DB Execution |
| :--- | :--- | :--- | :--- |
| **`models.py`** | Internal compiler domain AST objects (`OWDDocument`, `Workflow`, `State`, `Step`, `Decision`, `BusinessRule`, `SafetyRule`, `ValidationRule`, `Transition`). | Pydantic | None |
| **`parser.py`** | Parses raw markdown text into `OWDDocument` AST object graph. Pure syntax parser. | `models`, `utils`, `exceptions` | None |
| **`validator.py`** | Inspects `OWDDocument` for duplicate keys, broken state transitions, reachability, and missing exit nodes. | `models`, `utils`, `exceptions` | None |
| **`compiler.py`** | Transforms validated AST into database-ready `CompiledWorkflow` entity payloads. | `models`, `utils`, `exceptions` | None |
| **`loader.py`** | Persists `CompiledWorkflow` payload into Snowflake database tables using `MERGE` SQL statements. | `models`, `database` | **Snowflake ONLY** |
| **`pipeline.py`** | High-level orchestrator wiring Parser $\rightarrow$ Validator $\rightarrow$ Compiler $\rightarrow$ Loader into a unified function. | All Compiler Modules | Indirect via Loader |
| **`exceptions.py`** | Compiler error hierarchy (`OWDParsingException`, `OWDValidationException`, `OWDCompilationException`, `OWDLoaderException`). | Python Exception | None |
| **`utils.py`** | Helper utilities for SHA-256 source hashing, ID generation, text sanitization, and graph reachability. | Standard Library | None |

---

## OWD Compiler Lifecycle Example

### 1. Markdown Source Input
```markdown
# SOP-FIN-001: Expense Authorization & Verification

::state[STATE_VERIFY_RECEIPT]{type="ATOMIC_STEP" is_initial=true}
## Verify Receipt Integrity
Verify that the uploaded receipt contains valid line items and merchant details.

- [ ] Check merchant tax ID format ::step[STEP_TAX_ID]
- [ ] Verify receipt date is within 30 days ::step[STEP_DATE_CHECK]

:::rule[RULE_VAL_01]{type="SAFETY_GUARDRAIL" enforcement="HARD_STOP"}
Receipt amount must not exceed department authorization limit of $5,000 without VP sign-off.
:::

:::evidence[EVIDENCE_RECEIPT_PDF]{type="DOCUMENT_PDF" required=true}
Must upload original PDF receipt from merchant.
:::

::transition{to="STATE_DECISION_AMOUNT" condition="ALWAYS"}
```

### 2. Compilation Execution
```python
from app.compiler.pipeline import OWDCompilerPipeline

report = OWDCompilerPipeline.process_owd(
    markdown_text=markdown_source,
    workflow_code="SOP-FIN-001",
    title="Expense Authorization & Verification",
    department_id="dept_finance",
    user_id="user_admin",
)
```

### 3. Compilation Report Response Output
```json
{
  "compilation_status": "SUCCESS",
  "validation_errors": [],
  "warnings": [],
  "number_of_states": 2,
  "number_of_steps": 2,
  "number_of_decisions": 0,
  "number_of_business_rules": 0,
  "number_of_safety_rules": 1,
  "number_of_validation_rules": 0,
  "deployment_status": "PUBLISHED",
  "snowflake_tables_updated": [
    "KNOWLEDGE_STUDIO.workflows",
    "KNOWLEDGE_STUDIO.workflow_versions",
    "KNOWLEDGE_STUDIO.workflow_states",
    "KNOWLEDGE_STUDIO.workflow_steps",
    "KNOWLEDGE_STUDIO.workflow_transitions",
    "KNOWLEDGE_STUDIO.workflow_rules",
    "KNOWLEDGE_STUDIO.workflow_evidence_specs",
    "KNOWLEDGE_STUDIO.workflow_search_metadata"
  ]
}
```
