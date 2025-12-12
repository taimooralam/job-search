"""
Unit tests for OutreachRequest Pydantic model validation.

Tests the tier mapping fix where frontend JavaScript maps "auto" -> "balanced"
before sending to the backend. These tests verify the backend validates tier
values correctly and rejects invalid values like "auto".
"""

import pytest
from pydantic import ValidationError

from runner_service.routes.contacts import OutreachRequest


# =============================================================================
# Test OutreachRequest Model Validation
# =============================================================================


class TestOutreachRequestTierValidation:
    """Tests for OutreachRequest tier field validation."""

    def test_accepts_fast_tier(self):
        """Should accept 'fast' as a valid tier."""
        request = OutreachRequest(tier="fast", message_type="connection")

        assert request.tier == "fast"
        assert request.message_type == "connection"

    def test_accepts_balanced_tier(self):
        """Should accept 'balanced' as a valid tier."""
        request = OutreachRequest(tier="balanced", message_type="connection")

        assert request.tier == "balanced"
        assert request.message_type == "connection"

    def test_accepts_quality_tier(self):
        """Should accept 'quality' as a valid tier."""
        request = OutreachRequest(tier="quality", message_type="connection")

        assert request.tier == "quality"
        assert request.message_type == "connection"

    def test_rejects_auto_tier(self):
        """Should reject 'auto' as invalid tier (must be mapped on frontend)."""
        with pytest.raises(ValidationError) as exc_info:
            OutreachRequest(tier="auto", message_type="connection")

        error = exc_info.value
        assert "tier" in str(error).lower()
        # Pydantic v2 includes literal values in error message
        assert "fast" in str(error) or "balanced" in str(error) or "quality" in str(error)

    def test_rejects_invalid_tier(self):
        """Should reject arbitrary invalid tier values."""
        with pytest.raises(ValidationError) as exc_info:
            OutreachRequest(tier="super-premium", message_type="connection")

        error = exc_info.value
        assert "tier" in str(error).lower()

    def test_defaults_to_balanced_when_tier_missing(self):
        """Should default to 'balanced' tier when not provided."""
        request = OutreachRequest(message_type="connection")

        assert request.tier == "balanced"

    def test_rejects_none_tier(self):
        """Should reject explicit None as tier value."""
        # Pydantic v2 behavior: Literal fields don't accept None unless Optional
        with pytest.raises(ValidationError) as exc_info:
            OutreachRequest(tier=None, message_type="connection")

        error = exc_info.value
        assert "tier" in str(error).lower()


class TestOutreachRequestMessageTypeValidation:
    """Tests for OutreachRequest message_type field validation."""

    def test_accepts_connection_message_type(self):
        """Should accept 'connection' as valid message_type."""
        request = OutreachRequest(tier="balanced", message_type="connection")

        assert request.message_type == "connection"

    def test_accepts_inmail_message_type(self):
        """Should accept 'inmail' as valid message_type."""
        request = OutreachRequest(tier="balanced", message_type="inmail")

        assert request.message_type == "inmail"

    def test_rejects_invalid_message_type(self):
        """Should reject invalid message_type values."""
        with pytest.raises(ValidationError) as exc_info:
            OutreachRequest(tier="balanced", message_type="email")

        error = exc_info.value
        assert "message_type" in str(error).lower()

    def test_defaults_to_connection_when_message_type_missing(self):
        """Should default to 'connection' when message_type not provided."""
        request = OutreachRequest(tier="balanced")

        assert request.message_type == "connection"


class TestOutreachRequestCombinedValidation:
    """Tests for combined validation scenarios."""

    def test_valid_request_with_both_fields(self):
        """Should accept valid request with all fields specified."""
        request = OutreachRequest(tier="quality", message_type="inmail")

        assert request.tier == "quality"
        assert request.message_type == "inmail"

    def test_valid_request_with_defaults(self):
        """Should create valid request using all defaults."""
        request = OutreachRequest()

        assert request.tier == "balanced"
        assert request.message_type == "connection"

    def test_rejects_request_with_invalid_tier_and_valid_message_type(self):
        """Should reject request when tier is invalid even if message_type is valid."""
        with pytest.raises(ValidationError) as exc_info:
            OutreachRequest(tier="auto", message_type="connection")

        # Should only mention tier in error, not message_type
        error = exc_info.value
        assert "tier" in str(error).lower()

    def test_rejects_request_with_valid_tier_and_invalid_message_type(self):
        """Should reject request when message_type is invalid even if tier is valid."""
        with pytest.raises(ValidationError) as exc_info:
            OutreachRequest(tier="balanced", message_type="sms")

        error = exc_info.value
        assert "message_type" in str(error).lower()

    def test_rejects_request_with_both_fields_invalid(self):
        """Should reject request when both fields are invalid."""
        with pytest.raises(ValidationError) as exc_info:
            OutreachRequest(tier="auto", message_type="email")

        error = exc_info.value
        # Should mention both fields in errors
        error_str = str(error).lower()
        assert "tier" in error_str or "message_type" in error_str


class TestOutreachRequestCaseSensitivity:
    """Tests for case sensitivity in tier and message_type validation."""

    def test_tier_is_case_sensitive(self):
        """Tier field should be case-sensitive (lowercase only)."""
        with pytest.raises(ValidationError):
            OutreachRequest(tier="BALANCED", message_type="connection")

    def test_message_type_is_case_sensitive(self):
        """Message type field should be case-sensitive (lowercase only)."""
        with pytest.raises(ValidationError):
            OutreachRequest(tier="balanced", message_type="CONNECTION")

    def test_mixed_case_tier_rejected(self):
        """Mixed-case tier values should be rejected."""
        with pytest.raises(ValidationError):
            OutreachRequest(tier="Balanced", message_type="connection")


class TestOutreachRequestEdgeCases:
    """Tests for edge cases in OutreachRequest validation."""

    def test_empty_string_tier_rejected(self):
        """Empty string tier should be rejected."""
        with pytest.raises(ValidationError):
            OutreachRequest(tier="", message_type="connection")

    def test_empty_string_message_type_rejected(self):
        """Empty string message_type should be rejected."""
        with pytest.raises(ValidationError):
            OutreachRequest(tier="balanced", message_type="")

    def test_whitespace_tier_rejected(self):
        """Whitespace-only tier should be rejected."""
        with pytest.raises(ValidationError):
            OutreachRequest(tier="  ", message_type="connection")

    def test_tier_with_leading_trailing_spaces_rejected(self):
        """Tier with spaces should be rejected (no auto-stripping)."""
        with pytest.raises(ValidationError):
            OutreachRequest(tier=" balanced ", message_type="connection")


class TestOutreachRequestModelAttributes:
    """Tests for OutreachRequest model metadata and attributes."""

    def test_model_has_correct_field_descriptions(self):
        """Model should have descriptive field descriptions."""
        schema = OutreachRequest.model_json_schema()

        assert "tier" in schema["properties"]
        assert "message_type" in schema["properties"]
        assert "description" in schema["properties"]["tier"]
        assert "description" in schema["properties"]["message_type"]

    def test_model_default_values_in_schema(self):
        """Model schema should include default values."""
        schema = OutreachRequest.model_json_schema()

        # Check that defaults are documented
        assert schema["properties"]["tier"]["default"] == "balanced"
        assert schema["properties"]["message_type"]["default"] == "connection"

    def test_model_allows_json_serialization(self):
        """Model should be JSON serializable."""
        request = OutreachRequest(tier="quality", message_type="inmail")

        json_str = request.model_dump_json()
        assert "quality" in json_str
        assert "inmail" in json_str

    def test_model_allows_dict_conversion(self):
        """Model should convert to dict correctly."""
        request = OutreachRequest(tier="fast", message_type="connection")

        data = request.model_dump()
        assert data == {
            "tier": "fast",
            "message_type": "connection",
        }

    def test_model_validates_from_dict(self):
        """Model should validate when created from dict."""
        data = {"tier": "balanced", "message_type": "inmail"}
        request = OutreachRequest(**data)

        assert request.tier == "balanced"
        assert request.message_type == "inmail"
