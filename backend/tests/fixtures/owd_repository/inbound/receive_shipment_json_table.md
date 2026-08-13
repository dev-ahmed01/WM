# SOP: Receive Shipment

## 1. Document Metadata
```json
{
  "sop_id": "WH-REC-001",
  "version": "1.1.0",
  "department": "Warehouse Operations",
  "category": "Receiving",
  "owner": "Warehouse Operations Manager",
  "roles_allowed": ["Warehouse Receiving Clerk"],
  "required_equipment": ["Barcode scanner"]
}
```

## 2. AI Retrieval Metadata
```json
{
  "keywords": ["receiving", "inbound shipment"],
  "alternative_user_phrases": ["a truck just arrived"],
  "tags": ["inbound", "warehouse-floor"]
}
```

## 3. Workflow Definition
```json
{
  "workflow_id": "WH-REC-001",
  "workflow_objective": "Receive purchased goods accurately.",
  "business_goal": "Maintain inbound inventory accuracy.",
  "entry_conditions": ["A vendor delivery arrived"],
  "exit_conditions": ["Receipt is validated"]
}
```

## 4. Workflow States
| State ID | State Name | Purpose | Entry Condition | Exit Condition | Responsible Role | Expected Duration | Business Objective |
|---|---|---|---|---|---|---|---|
| S1 | Preparation | Open the receipt. | Vehicle arrived | Receipt open | Receiving Clerk | 3 min | Prevent errors. |
| S2 | Condition Check | Check quantity and damage. | S1 complete | Outcome chosen | Receiving Clerk | 5 min | Detect discrepancies. |
| S3 | Resolve Damage | Isolate damaged goods. | Damage found | Goods isolated | Supervisor | 5 min | Contain risk. |
| S4 | Validate Receipt | Close the receipt. | Checks complete | Receipt done | Receiving Clerk | 2 min | Update stock. |

## 5. Step Definitions

### State S1 — Preparation
```json
{
  "step_id": "S1-01",
  "sequence_number": 1,
  "action": "Open the pending receipt document.",
  "next_step": "S2-01",
  "retry_allowed": true,
  "maximum_retry_count": 3,
  "completion_criteria": "Correct receipt is open."
}
```

### State S2 — Condition Check
```json
{
  "step_id": "S2-01",
  "sequence_number": 2,
  "action": "Choose whether the shipment matches or is damaged.",
  "next_step": null,
  "decision": {
    "decision_id": "D-REC-001",
    "decision_question": "Does the shipment match?",
    "possible_answers": [
      {"answer_value": "match", "label": "Matches"},
      {"answer_value": "damage", "label": "Damage found"}
    ],
    "next_state": {"match": "S4", "damage": "S3"},
    "next_step": {"match": "S4-01", "damage": "S3-01"}
  }
}
```

### State S3 — Resolve Damage
```json
{
  "step_id": "S3-01",
  "sequence_number": 3,
  "action": "Isolate the damaged goods.",
  "next_step": "S4-01",
  "retry_allowed": true,
  "maximum_retry_count": 1
}
```

### State S4 — Validate Receipt
```json
{
  "step_id": "S4-01",
  "sequence_number": 4,
  "action": "Validate the receipt.",
  "next_step": null,
  "retry_allowed": false,
  "maximum_retry_count": 0
}
```

## 8. User Context
```json
{
  "applicable_roles": ["Warehouse Receiving Clerk"],
  "department": "Warehouse Operations"
}
```

## 10. Knowledge Relationships
```json
{
  "next_sops": ["WH-REC-002"],
  "predecessor_sop": "PUR-RFQ-002",
  "escalation_sops": ["WH-REC-003"],
  "referenced_equipment": ["Barcode scanner"]
}
```

## 9. Analytics Events
| Event | Trigger | Consumed By |
|---|---|---|
| `workflow_started` | S1-01 begins | Intelligence Hub |
| `workflow_completed` | S4-01 completes | Intelligence Hub |
| **KPIs** | Receipt cycle time; discrepancy rate | Intelligence Hub |

## 11. References
| Field | Value |
|---|---|
| Primary Source | Warehouse receiving manual |
| Official Documentation URL | https://example.com/receiving |
