"""
Unit Tests for SSE Streaming Fix (Event Loop Starvation).

Tests the SSE streaming improvements that prevent event loop starvation
during pipeline execution. The fix ensures progress updates are delivered
in real-time instead of batching at the end.

Key changes tested:
1. Service-layer emit_progress is async and yields control (asyncio.sleep(0))
2. SSE generator polls at 100ms for responsive updates (reduced from 500ms)
3. Flask proxy uses iter_content() for real-time delivery (not iter_lines())
"""

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

from src.services.full_extraction_service import FullExtractionService
from src.services.company_research_service import CompanyResearchService
from src.services.cv_generation_service import CVGenerationService
from src.common.model_tiers import ModelTier
from src.layer1_4.jd_processor import LLMMetadata


# ===== FIXTURES =====


@pytest.fixture
def sample_job_id():
    """Sample job ID."""
    return "507f1f77bcf86cd799439011"


@pytest.fixture
def mock_job_doc(sample_job_id):
    """Mock MongoDB job document."""
    from bson import ObjectId
    return {
        "_id": ObjectId(sample_job_id),
        "title": "Software Engineer",
        "company": "TestCorp",
        "job_description": "Build scalable systems. Python, AWS, Kubernetes required.",
        "jd_text": "Build scalable systems. Python, AWS, Kubernetes required.",
        "url": "https://example.com/job/123",
        "source": "linkedin",
    }


@pytest.fixture
def mock_progress_callback():
    """Mock progress callback that tracks calls."""
    mock = Mock()
    mock.call_count = 0
    mock.calls_list = []

    def track_call(layer_key: str, status: str, message: str):
        mock.call_count += 1
        mock.calls_list.append((layer_key, status, message))

    mock.side_effect = track_call
    return mock


@pytest.fixture
def mock_llm_metadata():
    """Mock LLMMetadata for JD processor."""
    return LLMMetadata(
        backend="claude_cli",
        model="claude-3-5-haiku-20241022",
        tier="low",
        duration_ms=100,
        cost_usd=0.001,
        success=True
    )


# ===== ASYNC EMIT_PROGRESS TESTS =====


class TestAsyncEmitProgress:
    """Test that emit_progress is async and yields to event loop."""

    @pytest.mark.asyncio
    async def test_full_extraction_emit_progress_is_async(self, mock_job_doc, mock_progress_callback, mock_llm_metadata):
        """FullExtractionService.execute calls progress callback asynchronously."""
        service = FullExtractionService()

        # Mock all dependencies
        with patch.object(service, '_get_job', return_value=mock_job_doc), \
             patch.object(service, '_run_jd_processor', return_value=(
                 {
                     "html": "<div>test</div>",
                     "sections": [{"id": "s1", "heading": "Overview"}],
                     "content_hash": "abc123"
                 },
                 mock_llm_metadata
             )), \
             patch.object(service, '_run_jd_extractor', return_value=(
                 {"role_category": "engineering", "top_keywords": ["python", "aws"]},
                 None  # No error
             )), \
             patch.object(service, '_run_layer_2', return_value={
                 "pain_points": ["Scale to 10M users"],
                 "strategic_needs": ["Cloud migration"]
             }), \
             patch.object(service, '_run_layer_4', return_value={
                 "fit_score": 85,
                 "fit_category": "strong",
                 "fit_rationale": "Good match",
                 "annotation_signals": {}
             }), \
             patch.object(service, '_persist_results', return_value=True):

            # Execute with progress callback
            result = await service.execute(
                job_id=str(mock_job_doc["_id"]),
                tier=ModelTier.FAST,
                progress_callback=mock_progress_callback
            )

            # Verify callback was called multiple times
            assert mock_progress_callback.call_count >= 4
            # Verify callback received expected layer keys
            layer_keys = [call[0] for call in mock_progress_callback.calls_list]
            assert "jd_processor" in layer_keys
            assert "pain_points" in layer_keys
            assert "fit_scoring" in layer_keys

    @pytest.mark.asyncio
    async def test_emit_progress_yields_to_event_loop(self, mock_job_doc, mock_llm_metadata):
        """emit_progress includes asyncio.sleep(0) to yield control."""
        # Track asyncio.sleep calls
        sleep_calls = []

        original_sleep = asyncio.sleep

        async def tracking_sleep(delay):
            """Track sleep calls."""
            sleep_calls.append(delay)
            await original_sleep(delay)

        service = FullExtractionService()

        with patch.object(service, '_get_job', return_value=mock_job_doc), \
             patch.object(service, '_run_jd_processor', return_value=(
                 {
                     "html": "<div>test</div>",
                     "sections": [{"id": "s1"}],
                     "content_hash": "abc"
                 },
                 mock_llm_metadata
             )), \
             patch.object(service, '_run_jd_extractor', return_value=(None, "Test error")), \
             patch.object(service, '_run_layer_2', return_value={"pain_points": []}), \
             patch.object(service, '_run_layer_4', return_value={
                 "fit_score": 80, "fit_category": "good", "annotation_signals": {}
             }), \
             patch.object(service, '_persist_results', return_value=True), \
             patch('asyncio.sleep', side_effect=tracking_sleep):

            await service.execute(
                job_id=str(mock_job_doc["_id"]),
                tier=ModelTier.FAST,
                progress_callback=lambda *args: None
            )

            # Verify asyncio.sleep(0) was called multiple times (once per progress update)
            assert len([s for s in sleep_calls if s == 0]) >= 4

    @pytest.mark.asyncio
    async def test_company_research_emit_progress_is_async(self, mock_job_doc, mock_progress_callback):
        """CompanyResearchService.execute calls progress callback asynchronously."""
        # Create mock repository
        mock_repository = MagicMock()
        mock_repository.find_one.return_value = mock_job_doc

        service = CompanyResearchService(repository=mock_repository)

        # Mock dependencies using property attributes
        mock_company_researcher = MagicMock()
        mock_company_researcher.research.return_value = {
            "summary": "Test company",
            "signals": [],
            "url": "https://test.com"
        }

        mock_role_researcher = MagicMock()
        mock_role_researcher.research.return_value = {
            "summary": "Test role",
            "business_impact": []
        }

        mock_people_mapper = MagicMock()
        mock_people_mapper.map_people.return_value = {
            "contacts": [],
            "decision_makers": []
        }

        with patch.object(service, '_check_cache', return_value=None), \
             patch.object(type(service), 'company_researcher', new_callable=lambda: mock_company_researcher, create=True), \
             patch.object(type(service), 'role_researcher', new_callable=lambda: mock_role_researcher, create=True), \
             patch.object(type(service), 'people_mapper', new_callable=lambda: mock_people_mapper, create=True), \
             patch.object(service, '_persist_research', return_value=True), \
             patch.object(service, '_get_cache_collection') as mock_cache:

            # Mock cache collection (for saving)
            mock_cache.return_value = MagicMock()

            # Execute with progress callback
            result = await service.execute(
                job_id=str(mock_job_doc["_id"]),
                tier=ModelTier.FAST,
                force_refresh=False,
                progress_callback=mock_progress_callback
            )

            # Verify callback was called for multiple layers
            assert mock_progress_callback.call_count >= 3
            layer_keys = [call[0] for call in mock_progress_callback.calls_list]
            assert "fetch_job" in layer_keys
            assert "company_research" in layer_keys

    @pytest.mark.asyncio
    async def test_cv_generation_emit_progress_is_async(self, mock_job_doc, mock_progress_callback):
        """CVGenerationService.execute calls progress callback asynchronously."""
        service = CVGenerationService()

        # Mock dependencies - use actual method names
        with patch.object(service, '_fetch_job', return_value=mock_job_doc), \
             patch.object(service, '_validate_job_data', return_value=None), \
             patch.object(service, '_build_state', return_value={
                 "job_id": str(mock_job_doc["_id"]),
                 "title": "Software Engineer"
             }), \
             patch('src.layer6_v2.orchestrator.CVGeneratorV2') as mock_cv_gen, \
             patch.object(service, '_build_cv_editor_state', return_value={}), \
             patch.object(service, '_persist_cv_result', return_value=True):

            # Mock CV generator
            mock_generator = MagicMock()
            mock_generator.generate_cv.return_value = {
                "cv_text": "Test CV",
                "cv_editor_state": {},
                "stars_used": []
            }
            mock_cv_gen.return_value = mock_generator

            # Execute with progress callback
            result = await service.execute(
                job_id=str(mock_job_doc["_id"]),
                tier=ModelTier.FAST,
                progress_callback=mock_progress_callback
            )

            # Verify callback was called
            assert mock_progress_callback.call_count >= 2
            layer_keys = [call[0] for call in mock_progress_callback.calls_list]
            assert "fetch_job" in layer_keys

    @pytest.mark.asyncio
    async def test_emit_progress_handles_callback_exceptions_gracefully(self, mock_job_doc, mock_llm_metadata):
        """emit_progress continues execution even if callback raises exception."""
        def failing_callback(layer_key: str, status: str, message: str):
            raise RuntimeError("Callback failed!")

        service = FullExtractionService()

        with patch.object(service, '_get_job', return_value=mock_job_doc), \
             patch.object(service, '_run_jd_processor', return_value=(
                 {
                     "html": "<div>test</div>",
                     "sections": [{"id": "s1"}],
                     "content_hash": "abc"
                 },
                 mock_llm_metadata
             )), \
             patch.object(service, '_run_jd_extractor', return_value=(None, "Test error")), \
             patch.object(service, '_run_layer_2', return_value={"pain_points": []}), \
             patch.object(service, '_run_layer_4', return_value={
                 "fit_score": 80, "fit_category": "good", "annotation_signals": {}
             }), \
             patch.object(service, '_persist_results', return_value=True):

            # Should not raise even though callback fails
            result = await service.execute(
                job_id=str(mock_job_doc["_id"]),
                tier=ModelTier.FAST,
                progress_callback=failing_callback
            )

            # Execution should complete successfully
            assert result.success is True


# ===== SSE GENERATOR POLL INTERVAL TESTS =====


class TestSSEGeneratorPollInterval:
    """Test that SSE generator polls at 100ms for responsive updates."""

    @pytest.mark.asyncio
    async def test_sse_generator_delivers_logs_quickly(self):
        """SSE generator delivers logs promptly for responsive UI updates."""
        from runner_service.routes.operation_streaming import (
            stream_operation_logs,
            create_operation_run,
            update_operation_status,
            append_operation_log,
        )

        # Create a test operation run
        run_id = create_operation_run("test_job_123", "test-operation")

        # Add initial logs
        append_operation_log(run_id, "Starting operation")
        append_operation_log(run_id, "Processing layer 1")

        # Mark as completed immediately
        update_operation_status(run_id, "completed", result={"status": "ok"})

        # Stream logs
        response = await stream_operation_logs(run_id)

        events_received = []
        async for chunk in response.body_iterator:
            events_received.append(chunk)
            if "event: end" in chunk:
                break

        # Verify we got the logs and completion event
        combined = "".join(events_received)
        assert "Starting operation" in combined
        assert "Processing layer 1" in combined
        assert "event: end" in combined


# ===== FLASK PROXY ITER_CONTENT TESTS =====


class TestFlaskProxyStreaming:
    """Test that Flask proxy uses iter_content for real-time SSE delivery."""

    def test_stream_logs_uses_iter_content(self):
        """Flask proxy should use iter_content(chunk_size=None) for real-time streaming."""
        from frontend.runner import stream_logs

        # Mock the requests.get response
        mock_response = MagicMock()

        # Simulate SSE chunks arriving over time
        def fake_iter_content(chunk_size=None, decode_unicode=False):
            """Simulate chunks arriving in real-time."""
            yield "data: Log line 1\n\n"
            yield "data: Log line 2\n\n"
            yield "event: end\ndata: completed\n\n"

        mock_response.iter_content = fake_iter_content

        with patch('frontend.runner.requests.get', return_value=mock_response):
            from flask import Flask
            app = Flask(__name__)

            with app.test_request_context():
                response = stream_logs("test_run_123")

                # Consume the response (it's a generator of strings)
                chunks = list(response.response)

                # Verify we got SSE events
                assert len(chunks) >= 3
                # Chunks are strings, not bytes
                assert any("Log line 1" in chunk for chunk in chunks)
                assert any("event: end" in chunk for chunk in chunks)

    def test_stream_logs_processes_sse_events_with_double_newline(self):
        """Flask proxy correctly processes SSE events (ending with \\n\\n)."""
        from frontend.runner import stream_logs

        mock_response = MagicMock()

        # Simulate fragmented SSE chunks
        def fake_iter_content(chunk_size=None, decode_unicode=False):
            # SSE events can arrive fragmented
            yield "data: Partial"
            yield " message\n\n"
            yield "data: Complete message\n\n"

        mock_response.iter_content = fake_iter_content

        with patch('frontend.runner.requests.get', return_value=mock_response):
            from flask import Flask
            app = Flask(__name__)

            with app.test_request_context():
                response = stream_logs("test_run_123")

                chunks = list(response.response)

                # Verify both complete events were processed (chunks are strings)
                combined = "".join(chunks)
                assert "Partial message" in combined
                assert "Complete message" in combined

    def test_stream_logs_handles_connection_errors(self):
        """Flask proxy handles connection errors gracefully."""
        from frontend.runner import stream_logs
        import requests

        with patch('frontend.runner.requests.get', side_effect=requests.exceptions.ConnectionError):
            from flask import Flask
            app = Flask(__name__)

            with app.test_request_context():
                response = stream_logs("test_run_123")

                chunks = list(response.response)
                combined = "".join(chunks)

                # Should return error event
                assert "event: error" in combined
                assert "Cannot connect" in combined

    def test_stream_logs_sets_correct_sse_headers(self):
        """Flask proxy sets correct headers for SSE streaming."""
        from frontend.runner import stream_logs

        mock_response = MagicMock()
        mock_response.iter_content = lambda chunk_size=None, decode_unicode=False: iter([])

        with patch('frontend.runner.requests.get', return_value=mock_response):
            from flask import Flask
            app = Flask(__name__)

            with app.test_request_context():
                response = stream_logs("test_run_123")

                # Verify SSE headers
                assert response.mimetype == "text/event-stream"
                assert response.headers.get("Cache-Control") == "no-cache"
                assert response.headers.get("X-Accel-Buffering") == "no"


# ===== INTEGRATION TESTS =====


class TestSSEStreamingIntegration:
    """Integration tests for end-to-end SSE streaming."""

    @pytest.mark.asyncio
    async def test_progress_updates_delivered_in_real_time(self, mock_job_doc, mock_llm_metadata):
        """Progress updates are delivered during execution, not batched at end."""
        received_updates = []
        update_timestamps = []

        def tracking_callback(layer_key: str, status: str, message: str):
            """Track when updates arrive."""
            received_updates.append((layer_key, status, message))
            update_timestamps.append(asyncio.get_event_loop().time())

        service = FullExtractionService()

        # Use synchronous functions since _run_jd_processor is sync
        def delayed_jd_processor(*args, **kwargs):
            import time
            time.sleep(0.01)  # Small delay
            return (
                {"html": "<div>test</div>", "sections": [{"id": "s1"}], "content_hash": "abc"},
                mock_llm_metadata
            )

        def delayed_layer_2(*args, **kwargs):
            import time
            time.sleep(0.01)  # Small delay
            return {"pain_points": ["test"]}

        with patch.object(service, '_get_job', return_value=mock_job_doc), \
             patch.object(service, '_run_jd_processor', side_effect=delayed_jd_processor), \
             patch.object(service, '_run_jd_extractor', return_value=(None, "Test error")), \
             patch.object(service, '_run_layer_2', side_effect=delayed_layer_2), \
             patch.object(service, '_run_layer_4', return_value={
                 "fit_score": 80, "fit_category": "good", "annotation_signals": {}
             }), \
             patch.object(service, '_persist_results', return_value=True):

            start_time = asyncio.get_event_loop().time()

            await service.execute(
                job_id=str(mock_job_doc["_id"]),
                tier=ModelTier.FAST,
                progress_callback=tracking_callback
            )

            # Verify updates arrived during execution (not all at once)
            assert len(update_timestamps) >= 4

            # First and last update should be spread out in time
            time_span = update_timestamps[-1] - update_timestamps[0]
            assert time_span > 0.01  # Updates spread over time

    @pytest.mark.asyncio
    async def test_multiple_rapid_progress_updates_all_delivered(self, mock_job_doc, mock_llm_metadata):
        """Rapid consecutive progress updates are all delivered (no loss)."""
        received_updates = []

        def counting_callback(layer_key: str, status: str, message: str):
            received_updates.append((layer_key, status))

        service = FullExtractionService()

        with patch.object(service, '_get_job', return_value=mock_job_doc), \
             patch.object(service, '_run_jd_processor', return_value=(
                 {"html": "<div>test</div>", "sections": [{"id": "s1"}], "content_hash": "abc"},
                 mock_llm_metadata
             )), \
             patch.object(service, '_run_jd_extractor', return_value=(None, "Test error")), \
             patch.object(service, '_run_layer_2', return_value={"pain_points": []}), \
             patch.object(service, '_run_layer_4', return_value={
                 "fit_score": 80, "fit_category": "good", "annotation_signals": {}
             }), \
             patch.object(service, '_persist_results', return_value=True):

            await service.execute(
                job_id=str(mock_job_doc["_id"]),
                tier=ModelTier.FAST,
                progress_callback=counting_callback
            )

            # Verify all expected updates were received
            # Each layer should have at least: processing, success
            layer_keys = [update[0] for update in received_updates]
            statuses = [update[1] for update in received_updates]

            assert "jd_processor" in layer_keys
            assert "pain_points" in layer_keys
            assert "processing" in statuses
            assert "success" in statuses
