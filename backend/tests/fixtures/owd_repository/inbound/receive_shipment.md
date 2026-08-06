# SOP-INB-001: Inbound Shipment Receiving Procedure

::state[STATE_INIT]{type="ATOMIC_STEP" is_initial=true}
# Step 1: Shipment Arrival Inspection
Verify delivery vehicle seal and inspect physical condition of outer shipping containers before unloading.

- [ ] Verify seal number matches bill of lading ::step[STEP_CHECK_SEAL]
- [ ] Inspect outer carton integrity for physical damage ::step[STEP_INSPECT_CARTONS]
- [ ] Record ambient temperature reading for cold-chain shipments ::step[STEP_READ_TEMP]

:::rule[RULE_SEAL_01]{type="SAFETY_GUARDRAIL" enforcement="HARD_STOP"}
Seal mismatch or broken tamper band requires immediate supervisor hold.
:::

:::rule[RULE_TEMP_01]{type="BUSINESS_RULE" enforcement="WARNING_CONFIRM"}
Temperature readings outside 2C-8C must be flagged for quality review.
:::

:::evidence[EVIDENCE_BOL_PDF]{type="DOCUMENT_PDF" required=true}
Attach scanned bill of lading with driver signature.
:::

::transition{to="STATE_UNLOAD" condition="ALWAYS"}

::state[STATE_UNLOAD]{type="ATOMIC_STEP"}
# Step 2: Pallet Unloading & Staging
Unload pallets from trailer using electric pallet jack and transport to staging bay A1-A4.

- [ ] Scan staging bay barcode ::step[STEP_SCAN_BAY]
- [ ] Count total pallet units received ::step[STEP_PALLET_COUNT]

::transition{to="STATE_DECISION_DAMAGE" condition="ALWAYS"}

::state[STATE_DECISION_DAMAGE]{type="DECISION"}
# Step 3: Damage Assessment Decision
Determine if any shipping containers or pallets exhibit visible damage.

::transition{to="STATE_HOLD_INSPECTION" condition="DECISION_OPTION"}
::transition{to="STATE_RECEIVE_SYSTEM" condition="DECISION_OPTION"}

::state[STATE_HOLD_INSPECTION]{type="ESCALATION"}
# Step 4: Quality Inspection Hold
Place damaged shipment on quarantine hold and notify Quality Assurance supervisor.

- [ ] Apply physical quarantine tape to pallets ::step[STEP_APPLY_TAPE]
- [ ] File damaged goods report ::step[STEP_FILE_REPORT]

::transition{to="STATE_END" condition="ALWAYS"}

::state[STATE_RECEIVE_SYSTEM]{type="ATOMIC_STEP"}
# Step 5: System Receiving Entry
Enter PO number and line item quantities into warehouse management system.

- [ ] Enter PO number in system ::step[STEP_ENTER_PO]
- [ ] Confirm item counts match packing slip ::step[STEP_CONFIRM_COUNTS]

::transition{to="STATE_END" condition="ALWAYS"}

::state[STATE_END]{type="END" is_terminal=true}
# Step 6: Receiving Completed
Shipment receiving process complete. Pallets released for putaway.
