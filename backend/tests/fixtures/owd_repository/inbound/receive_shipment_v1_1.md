---
spec_version: "1.1"
sop_id: "SOP-INB-101"
version: "1.1.0"
department: "dept_inbound"
category: "OPERATIONAL_SOP"
owner: "Logistics Operations Lead"
priority: "HIGH"
difficulty: "INTERMEDIATE"
estimated_duration: "45 mins"
roles_allowed:
  - "Warehouse Operator"
  - "Receiving Supervisor"
  - "Logistics Manager"
required_equipment:
  - "Barcode Scanner"
  - "Electric Pallet Jack"
  - "Digital Thermometer Probe"
dependencies:
  - "SOP-SAF-001"
related_sops:
  - "SOP-INB-002"
  - "SOP-QA-001"
review_cycle: "BI_ANNUAL"
effective_date: "2026-02-01"
---

# 1 Document Metadata
sop_id: SOP-INB-101
version: 1.1.0
department: dept_inbound
category: OPERATIONAL_SOP
owner: Logistics Operations Lead
priority: HIGH
difficulty: INTERMEDIATE
estimated_duration: 45 mins
roles_allowed: Warehouse Operator, Receiving Supervisor, Logistics Manager
required_equipment: Barcode Scanner, Electric Pallet Jack, Digital Thermometer Probe
dependencies: SOP-SAF-001
related_sops: SOP-INB-002, SOP-QA-001
review_cycle: BI_ANNUAL
effective_date: 2026-02-01

# 2 AI Retrieval Metadata
keywords: inbound, shipment, receiving, bill_of_lading, pallet, tamper_seal, temperature_log
synonyms: intake, delivery, cargo_acceptance, goods_receipt
search_phrases: how to receive inbound trailer, bill of lading seal verification, damaged shipment hold procedure
search_queries: receive shipment SOP, trailer unloading steps, temperature probe calibration
business_process: Inbound Freight Logistics & Receiving
equipment: Barcode Scanner, Electric Pallet Jack, Digital Thermometer Probe
workflow_tags: inbound, logistics, high_priority, cold_chain

# 3 Workflow Definition
workflow_objective: Execute end-to-end inbound freight receiving, seal verification, temperature logging, and WMS inventory intake.
business_goal: Guarantee 100% PO matching precision and zero uninspected damaged stock entry.
entry_conditions: Freight trailer backed into dock door A1-A6 with manifest.
exit_conditions: Goods received into WMS, pallets staged, receiving log signed.
previous_workflow: None
next_workflow: SOP-INB-002
blocking_workflows: SOP-SAF-001
optional_workflows: SOP-QA-001
expected_business_outcome: Inbound freight safely received and logged into WMS within 45 minutes of arrival.

# 4 Workflow States & Steps

::state[STATE_INIT]{type="ATOMIC_STEP" is_initial=true purpose="Verify trailer seal and physical outer cartons" entry_condition="Trailer docked" exit_condition="Seal verified" responsible_role="Receiving Operator" expected_duration="10 mins"}
## State 1: Dock Arrival & Seal Inspection

:::step[STEP_CHECK_SEAL]
sequence_number: 1
instruction: Verify physical trailer door seal number against Bill of Lading manifest.
action: Match seal number and inspect tamper band integrity.
expected_outcome: Seal matches BOL exactly with no signs of tampering.
safety_note: Wear protective gloves and eye protection when cutting metal drum seal bands.
estimated_time: 3 mins
retry_policy: MAX_RETRIES_1
completion_criteria: Seal barcode scanned and numbers verified match.
common_failure: Seal number mismatch or missing driver signature.
recovery_action: Halt unloading and trigger supervisor escalation hold.
:::ai_conversation
question_ai_should_ask: Does the physical seal number match the Bill of Lading manifest?
expected_user_responses: Yes match, No mismatch, Broken seal
clarification_questions: Can you read the last 4 digits of the seal tag?
fallback_prompt: Please enter the exact numeric seal string printed on the tag.
coaching_prompt: Refer to Section 2 of BOL manifest for primary seal barcode string.
escalation_trigger: SEAL_MISMATCH
confidence_requirements: 0.95
citation_source: SOP-INB-101 Section 4.1
:::
:::

:::rule[RULE_SEAL_HARD_STOP]{type="SAFETY_GUARDRAIL" enforcement="HARD_STOP"}
Broken seal or tag mismatch requires immediate driver hold and QA escalation.
:::

:::evidence[EVIDENCE_BOL_PDF]{type="DOCUMENT_PDF" required=true}
Attach scanned signed copy of Bill of Lading manifest PDF.
:::

::transition{to="STATE_TEMPERATURE_LOG" condition="ALWAYS"}

::state[STATE_TEMPERATURE_LOG]{type="ATOMIC_STEP" purpose="Log ambient and internal temperature for cold-chain goods" entry_condition="Seal cut approved" exit_condition="Temp within range" responsible_role="Receiving Operator" expected_duration="10 mins"}
## State 2: Cold-Chain Temperature Check

:::step[STEP_LOG_TEMP]
sequence_number: 2
instruction: Insert calibrated digital thermometer probe between pallet packages and log temp.
action: Record reading on temperature display probe.
expected_outcome: Temperature reading logged between 2C and 8C.
safety_note: Ensure probe is disinfected before insertion.
estimated_time: 5 mins
retry_policy: MAX_RETRIES_3
completion_criteria: Numeric temperature recorded in WMS.
common_failure: Temp out of range (> 8C).
recovery_action: Place cold-chain pallet in temporary cooler and notify QA manager.
:::ai_conversation
question_ai_should_ask: What is the current temperature reading in degrees Celsius?
expected_user_responses: Numeric C reading, Out of range
clarification_questions: Is the thermal logger probe LED flashing green?
fallback_prompt: Re-insert probe and wait 30 seconds for stable reading.
coaching_prompt: Temperature must remain strictly between 2.0C and 8.0C.
escalation_trigger: TEMP_EXCURSION
confidence_requirements: 0.90
citation_source: Cold Chain Compliance Standard CC-2025
:::
:::

::transition{to="STATE_DECISION_DAMAGE" condition="ALWAYS"}

::state[STATE_DECISION_DAMAGE]{type="DECISION" purpose="Evaluate container damage" entry_condition="Temp log complete" exit_condition="Decision made" responsible_role="Receiving Supervisor"}
## State 3: Container Damage Evaluation

:::decision[DEC_DAMAGE_CHECK]
question: Do any pallets or cartons exhibit crushed boxes, wet stains, or physical damage?
alternative_path: STATE_RECEIVE_SYSTEM
business_rule: RULE_ZERO_DAMAGE_ENTRY
escalation_workflow: SOP-QA-001
options:
  - option_code: OPT_DAMAGED
    option_label: Yes, damaged cartons detected
    next_state: STATE_HOLD_INSPECTION
  - option_code: OPT_INTACT
    option_label: No, all cartons intact
    next_state: STATE_RECEIVE_SYSTEM
:::

::state[STATE_HOLD_INSPECTION]{type="ESCALATION" purpose="Quarantine damaged goods" is_terminal=false}
## State 4: Quality Quarantine Hold

:::step[STEP_APPLY_TAPE]
sequence_number: 3
instruction: Apply physical red quarantine tape to damaged pallet and transport to Bay Q-1.
action: Wrap quarantine tape and affix warning placard.
expected_outcome: Damaged goods isolated in quarantine bay.
estimated_time: 10 mins
retry_policy: NO_RETRY
completion_criteria: Bay Q-1 barcode scanned.
:::

::transition{to="STATE_END" condition="ALWAYS"}

::state[STATE_RECEIVE_SYSTEM]{type="ATOMIC_STEP" purpose="System PO receiving entry" exit_condition="PO closed"}
## State 5: WMS Inventory Receipt

:::step[STEP_POST_WMS]
sequence_number: 4
instruction: Enter PO number and confirm received carton counts in WMS portal.
action: Post WMS receiving transaction.
expected_outcome: Purchase Order receipt status updated to COMPLETED.
estimated_time: 7 mins
retry_policy: MAX_RETRIES_3
completion_criteria: WMS receipt confirmation ID generated.
:::

::transition{to="STATE_END" condition="ALWAYS"}

::state[STATE_END]{type="END" is_terminal=true purpose="Receiving process completed"}
## State 6: Receiving Completed
Inbound shipment receiving process complete. Pallets released for storage putaway.

# 8 User Context
roles: Warehouse Operator, Receiving Supervisor, Logistics Manager
permissions: receiving.read, receiving.write, quarantine.override
experience_levels: INTERMEDIATE, SENIOR
certifications: FORKLIFT_CERTIFIED, COLD_CHAIN_CERTIFIED
supported_languages: en-US, es-ES
department: dept_inbound

# 9 Analytics Events
events:
  - name: workflow_started
    trigger: TRAILER_DOCK_SCAN
    kpis: dock_dwell_time_start
  - name: temperature_logged
    trigger: PROBE_READING_SUBMITTED
    kpis: temperature_compliance_rate
  - name: damage_quarantine_triggered
    trigger: DECISION_DAMAGED_SELECTED
    kpis: damage_incident_rate
  - name: workflow_completed
    trigger: WMS_RECEIPT_POSTED
    kpis: total_receiving_cycle_time
kpis: first_pass_yield, temperature_excursion_rate, dock_to_stock_time

# 10 Knowledge Relationships
parent_sop: None
child_sops: SOP-INB-002
related_sops: SOP-QA-001, SOP-INV-001
previous_sop: None
next_sop: SOP-INB-002
escalation_sop: SOP-QA-001
exception_sop: SOP-SAF-001
referenced_equipment: Barcode Scanner, Electric Pallet Jack, Digital Thermometer Probe
referenced_documents: Bill of Lading Manifest, WMS Purchase Order
referenced_policies: Global Inbound Cold Chain Policy

# 11 References
primary_source: Enterprise Logistics Compliance Manual Section 4
supporting_sources: OSHA Dock Safety Guidelines (29 CFR 1910)
official_documentation_url: https://docs.workmate.ai/sops/inbound/receive-shipment
compliance_standards: ISO 9001:2015 Clause 8.5.2, Cold Chain Standard CC-2025
documentation_sections: Section 4.1 Trailer Inspection, Section 4.2 Cold Chain Logging
