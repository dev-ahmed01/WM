"""Deterministic workflow intent and noisy-query regression tests."""

import pytest

from app.core.text_matching import fuzzy_relevance_score
from app.services.copilot_reasoning import CopilotReasoningService
from app.services.workflow_intent import WorkflowIntentService


CATALOG = [
    {
        "workflow_id": "workflow_1",
        "workflow_code": "SOP_INB_101",
        "title": "receive_shipment_v1_1",
        "description": "Inbound receiving, seal verification, temperature logging, and inventory intake.",
        "workflow_version_id": "ver_1",
        "version_number": 4,
    }
]


@pytest.mark.parametrize(
    "message",
    [
        "get me receive shipment",
        "get me receive shipment sop",
        "I need the receive shipment sop",
        "please fetch the recive shipmnt procedure",
        "receive shipment",
    ],
)
def test_catalog_match_understands_equivalent_workflow_requests(message):
    match = WorkflowIntentService.match_published_workflow(message, CATALOG)
    assert match is not None
    assert match["workflow_version_id"] == "ver_1"


def test_operational_damage_question_is_not_mistaken_for_workflow_selection():
    assert (
        WorkflowIntentService.match_published_workflow(
            "package is damaged what should I do", CATALOG
        )
        is None
    )


def test_problem_descriptions_can_propose_a_confirmable_sop():
    catalog = CATALOG + [
        {
            "workflow_code": "WH_REC_003", "title": "Damage Inspection",
            "description": "Inspect damaged packages and record their condition.",
            "workflow_version_id": "ver_damage",
        },
        {
            "workflow_code": "WH_REC_004", "title": "Barcode Registration On Receipt",
            "description": "Register and scan received product barcodes.",
            "workflow_version_id": "ver_barcode",
        },
    ]
    damage = WorkflowIntentService.match_published_workflow(
        "The packages are damaged what should I do", catalog, proposal_mode=True
    )
    barcode = WorkflowIntentService.match_published_workflow(
        "the barcode isn't scanning what should I do", catalog, proposal_mode=True
    )

    assert damage and damage["workflow_code"] == "WH_REC_003"
    assert barcode and barcode["workflow_code"] == "WH_REC_004"


def test_ambiguous_query_returns_ranked_real_catalog_options():
    catalog = CATALOG + [
        {
            "workflow_code": "WH_REC_002",
            "title": "Verify Goods Against Purchase Order",
            "description": "Confirm received goods match the purchase order.",
            "workflow_version_id": "ver_verify",
        },
        {
            "workflow_code": "WH_PICK_001",
            "title": "Pick Order",
            "description": "Retrieve products to fulfill an order.",
            "workflow_version_id": "ver_pick",
        },
    ]

    ranked = WorkflowIntentService.rank_published_workflows(
        "tell me the process of getting goods", catalog
    )

    assert len(ranked) <= 3
    assert "ver_1" in {item["workflow_version_id"] for item in ranked}
    assert all(item["match_score"] > 0 for item in ranked)


@pytest.mark.parametrize(
    "message",
    [
        "i dont know if it is damage inspection i dont know what is in it",
        "what does this procedure cover?",
        "tell me about it",
        "I'm not sure, explain it",
    ],
)
def test_pending_confirmation_information_questions_are_recognized(message):
    assert WorkflowIntentService.is_confirmation_information_request(message)


def test_unrelated_new_problem_is_not_a_confirmation_information_request():
    assert not WorkflowIntentService.is_confirmation_information_request(
        "the barcode is not scanning"
    )


def test_noisy_damage_query_keeps_enough_verified_relevance():
    focused = CopilotReasoningService.focus_operational_query(
        "turn all this the package is damaged what should I do"
    )
    assert focused == "package is damaged what should i do"
    score = fuzzy_relevance_score(
        focused,
        "Container Damage Evaluation. Yes, damaged cartons detected.",
    )
    assert score >= 0.90


def test_all_steps_completion_requires_an_attestation_not_a_question():
    assert WorkflowIntentService.is_all_steps_completion("all the steps are done")
    assert WorkflowIntentService.is_all_steps_completion("the entire workflow is complete")
    assert WorkflowIntentService.is_all_steps_completion("I finished every step")
    assert WorkflowIntentService.is_all_steps_completion("everything is completed")
    assert not WorkflowIntentService.is_all_steps_completion("are all the steps done?")
