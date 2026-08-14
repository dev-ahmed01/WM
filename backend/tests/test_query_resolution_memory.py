from unittest.mock import patch

from app.services.query_resolution_memory import QueryResolutionMemoryService


def test_confirmed_similar_query_maps_only_to_current_published_workflow():
    QueryResolutionMemoryService._cache.clear()
    memories = [{
        "id": "qres_1",
        "normalized_query": "barcode not scanning",
        "original_query": "barcode isnt scanning what should i do",
        "translated_query": "barcode is not scanning what should I do",
        "workflow_version_id": "ver_barcode",
        "workflow_code": "WH_REC_004",
        "hit_count": 2,
    }]
    catalog = [{
        "workflow_version_id": "ver_barcode",
        "workflow_code": "WH_REC_004",
        "title": "Barcode Registration",
        "description": "Register product barcodes during receiving.",
    }]
    with (
        patch(
            "app.services.query_resolution_memory.QueryResolutionRepository.list_confirmed",
            return_value=memories,
        ),
        patch(
            "app.services.query_resolution_memory.QueryResolutionRepository.record_hit"
        ) as record_hit,
    ):
        match = QueryResolutionMemoryService.match(
            "the barcode isnt scaning", "dept_ops", catalog
        )

    assert match is not None
    assert match["workflow_version_id"] == "ver_barcode"
    assert match["matched_from_memory"] is True
    record_hit.assert_called_once_with("qres_1")


def test_memory_never_returns_an_unpublished_or_removed_workflow():
    QueryResolutionMemoryService._cache.clear()
    with patch(
        "app.services.query_resolution_memory.QueryResolutionRepository.list_confirmed",
        return_value=[{
            "id": "qres_old", "normalized_query": "damaged package",
            "original_query": "damaged package", "translated_query": "damaged package",
            "workflow_version_id": "retired_version", "workflow_code": "OLD_1",
        }],
    ):
        assert QueryResolutionMemoryService.match(
            "damaged package", "dept_ops", []
        ) is None
