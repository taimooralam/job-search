"""
Unit tests for InMail/Connection button onclick handler fix.

Tests the fix where InMail and Connection buttons in job_detail.html were
updated to use generateOutreach() with contact indices instead of
generateContactMessage() with contact names.

The bug occurred because contact names with special characters (apostrophes,
ampersands, quotes) broke the onclick handler when passed as strings.

Fix: Changed from:
  onclick="generateContactMessage('{{ job._id }}', '{{ contact.name | e }}', ...)"
To:
  onclick="generateOutreach('primary', {{ loop.index0 }}, 'inmail', this)"

This ensures proper parameter passing and avoids JavaScript injection issues.
"""

import pytest
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock


class TestOutreachButtonOnclickHandlers:
    """Tests for InMail/Connection button onclick handlers in job_detail.html."""

    def test_primary_contact_inmail_button_uses_generateoutreach_with_index(
        self, authenticated_client, mock_db
    ):
        """Should render InMail button with generateOutreach('primary', index, 'inmail') handler."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Senior Engineer",
            "company": "TechCorp",
            "status": "not processed",
            "score": 85,
            "primary_contacts": [
                {
                    "name": "Jane Doe",
                    "role": "Hiring Manager",
                    "linkedin_url": "https://linkedin.com/in/janedoe"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use generateOutreach with index-based parameters
        assert "generateOutreach('primary', 0, 'inmail', this)" in html

    def test_primary_contact_connection_button_uses_generateoutreach_with_index(
        self, authenticated_client, mock_db
    ):
        """Should render Connection button with generateOutreach('primary', index, 'connection') handler."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Staff Engineer",
            "company": "StartupCo",
            "status": "not processed",
            "score": 90,
            "primary_contacts": [
                {
                    "name": "John Smith",
                    "role": "Recruiter",
                    "linkedin_url": "https://linkedin.com/in/johnsmith"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use generateOutreach with index-based parameters
        assert "generateOutreach('primary', 0, 'connection', this)" in html

    def test_secondary_contact_inmail_button_uses_generateoutreach_with_index(
        self, authenticated_client, mock_db
    ):
        """Should render InMail button for secondary contacts with correct type and index."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Principal Engineer",
            "company": "BigTech",
            "status": "not processed",
            "score": 92,
            "secondary_contacts": [
                {
                    "name": "Alice Johnson",
                    "role": "Team Lead",
                    "linkedin_url": "https://linkedin.com/in/alicejohnson"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use generateOutreach with 'secondary' type
        assert "generateOutreach('secondary', 0, 'inmail', this)" in html

    def test_secondary_contact_connection_button_uses_generateoutreach_with_index(
        self, authenticated_client, mock_db
    ):
        """Should render Connection button for secondary contacts with correct type and index."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Lead Engineer",
            "company": "Innovation Inc",
            "status": "not processed",
            "score": 88,
            "secondary_contacts": [
                {
                    "name": "Bob Wilson",
                    "role": "Engineering Manager",
                    "linkedin_url": "https://linkedin.com/in/bobwilson"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use generateOutreach with 'secondary' type
        assert "generateOutreach('secondary', 0, 'connection', this)" in html

    def test_multiple_primary_contacts_each_get_correct_index(
        self, authenticated_client, mock_db
    ):
        """Should render buttons for multiple contacts with correct loop indices."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Senior Developer",
            "company": "DevCorp",
            "status": "not processed",
            "score": 80,
            "primary_contacts": [
                {
                    "name": "First Contact",
                    "role": "Hiring Manager",
                    "linkedin_url": "https://linkedin.com/in/first"
                },
                {
                    "name": "Second Contact",
                    "role": "Recruiter",
                    "linkedin_url": "https://linkedin.com/in/second"
                },
                {
                    "name": "Third Contact",
                    "role": "Tech Lead",
                    "linkedin_url": "https://linkedin.com/in/third"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Each contact should have its own index (0, 1, 2)
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 1, 'inmail', this)" in html
        assert "generateOutreach('primary', 2, 'inmail', this)" in html

        assert "generateOutreach('primary', 0, 'connection', this)" in html
        assert "generateOutreach('primary', 1, 'connection', this)" in html
        assert "generateOutreach('primary', 2, 'connection', this)" in html

    def test_multiple_secondary_contacts_each_get_correct_index(
        self, authenticated_client, mock_db
    ):
        """Should render buttons for multiple secondary contacts with correct loop indices."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Backend Engineer",
            "company": "CloudCo",
            "status": "not processed",
            "score": 75,
            "secondary_contacts": [
                {
                    "name": "Secondary One",
                    "role": "Engineer",
                    "linkedin_url": "https://linkedin.com/in/sec1"
                },
                {
                    "name": "Secondary Two",
                    "role": "Manager",
                    "linkedin_url": "https://linkedin.com/in/sec2"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Each secondary contact should have its own index (0, 1)
        assert "generateOutreach('secondary', 0, 'inmail', this)" in html
        assert "generateOutreach('secondary', 1, 'inmail', this)" in html

        assert "generateOutreach('secondary', 0, 'connection', this)" in html
        assert "generateOutreach('secondary', 1, 'connection', this)" in html


class TestOutreachButtonSpecialCharacterHandling:
    """Tests that special characters in contact names don't break button handlers."""

    def test_contact_name_with_apostrophe_renders_safely(
        self, authenticated_client, mock_db
    ):
        """Should handle contact names with apostrophes without breaking JavaScript."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Software Engineer",
            "company": "TestCorp",
            "status": "not processed",
            "score": 82,
            "primary_contacts": [
                {
                    "name": "O'Brien",  # Apostrophe in name
                    "role": "Hiring Manager",
                    "linkedin_url": "https://linkedin.com/in/obrien"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use index-based approach (no name in onclick)
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html

        # The old buggy approach would have broken here:
        # onclick="generateContactMessage('...', 'O'Brien', ...)" would cause JS error
        # New approach avoids this by using index instead of name

    def test_contact_name_with_quotes_renders_safely(
        self, authenticated_client, mock_db
    ):
        """Should handle contact names with quotes without breaking JavaScript."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Frontend Engineer",
            "company": "WebCo",
            "status": "not processed",
            "score": 78,
            "primary_contacts": [
                {
                    "name": 'Jane "Jay" Doe',  # Quotes in name
                    "role": "Tech Lead",
                    "linkedin_url": "https://linkedin.com/in/janedoe"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use index-based approach (no name in onclick)
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html

    def test_contact_name_with_ampersand_renders_safely(
        self, authenticated_client, mock_db
    ):
        """Should handle contact names with ampersands without breaking JavaScript."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Data Engineer",
            "company": "Analytics & Co",
            "status": "not processed",
            "score": 83,
            "primary_contacts": [
                {
                    "name": "Smith & Associates",  # Ampersand in name
                    "role": "Partner",
                    "linkedin_url": "https://linkedin.com/in/smith"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use index-based approach (no name in onclick)
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html

    def test_contact_name_with_backslash_renders_safely(
        self, authenticated_client, mock_db
    ):
        """Should handle contact names with backslashes without breaking JavaScript."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "DevOps Engineer",
            "company": "Infrastructure Inc",
            "status": "not processed",
            "score": 86,
            "primary_contacts": [
                {
                    "name": "Back\\slash",  # Backslash in name
                    "role": "SRE",
                    "linkedin_url": "https://linkedin.com/in/backslash"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use index-based approach (no name in onclick)
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html

    def test_contact_name_with_html_tags_renders_safely(
        self, authenticated_client, mock_db
    ):
        """Should handle contact names with HTML-like content without breaking template."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Security Engineer",
            "company": "SecureCo",
            "status": "not processed",
            "score": 91,
            "primary_contacts": [
                {
                    "name": "<script>alert('xss')</script>",  # XSS attempt
                    "role": "Security Lead",
                    "linkedin_url": "https://linkedin.com/in/security"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should use index-based approach (no name in onclick)
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html

        # The onclick handler should not contain the malicious script
        # Index-based approach prevents injection


class TestOutreachButtonEdgeCases:
    """Edge case tests for outreach button rendering."""

    def test_contact_with_none_name_field(
        self, authenticated_client, mock_db
    ):
        """Should handle contacts with None name gracefully."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "QA Engineer",
            "company": "TestCo",
            "status": "not processed",
            "score": 70,
            "primary_contacts": [
                {
                    "name": None,  # None name
                    "role": "Recruiter",
                    "linkedin_url": "https://linkedin.com/in/unknown"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should still render buttons with index-based handlers
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html

    def test_contact_with_empty_string_name(
        self, authenticated_client, mock_db
    ):
        """Should handle contacts with empty string name."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "ML Engineer",
            "company": "AI Labs",
            "status": "not processed",
            "score": 89,
            "primary_contacts": [
                {
                    "name": "",  # Empty string name
                    "role": "Research Lead",
                    "linkedin_url": "https://linkedin.com/in/researcher"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should still render buttons with index-based handlers
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html

    def test_no_contacts_no_buttons_rendered(
        self, authenticated_client, mock_db
    ):
        """Should not render outreach buttons when no contacts exist."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Platform Engineer",
            "company": "CloudCorp",
            "status": "not processed",
            "score": 77,
            # No primary_contacts or secondary_contacts
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should not contain any generateOutreach calls
        assert "generateOutreach" not in html

    def test_empty_contacts_arrays_no_buttons_rendered(
        self, authenticated_client, mock_db
    ):
        """Should not render outreach buttons when contact arrays are empty."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Systems Engineer",
            "company": "InfraCo",
            "status": "not processed",
            "score": 81,
            "primary_contacts": [],
            "secondary_contacts": []
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should not contain any generateOutreach calls
        assert "generateOutreach" not in html

    def test_contact_with_contact_name_fallback(
        self, authenticated_client, mock_db
    ):
        """Should work when contact uses 'contact_name' instead of 'name'."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Full Stack Engineer",
            "company": "WebApp Inc",
            "status": "not processed",
            "score": 84,
            "primary_contacts": [
                {
                    "contact_name": "Alternative Name Field",  # Using contact_name
                    "role": "Engineering Manager",
                    "linkedin_url": "https://linkedin.com/in/altname"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Should still render buttons with index-based handlers
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html


class TestOutreachButtonBothContactTypes:
    """Tests with both primary and secondary contacts present."""

    def test_both_primary_and_secondary_contacts_render_correctly(
        self, authenticated_client, mock_db
    ):
        """Should render buttons for both primary and secondary contacts with correct types."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Architect",
            "company": "Enterprise Corp",
            "status": "not processed",
            "score": 93,
            "primary_contacts": [
                {
                    "name": "Primary Contact 1",
                    "role": "VP Engineering",
                    "linkedin_url": "https://linkedin.com/in/primary1"
                },
                {
                    "name": "Primary Contact 2",
                    "role": "Director",
                    "linkedin_url": "https://linkedin.com/in/primary2"
                }
            ],
            "secondary_contacts": [
                {
                    "name": "Secondary Contact 1",
                    "role": "Senior Engineer",
                    "linkedin_url": "https://linkedin.com/in/secondary1"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Primary contacts should use 'primary' type
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 1, 'inmail', this)" in html
        assert "generateOutreach('primary', 0, 'connection', this)" in html
        assert "generateOutreach('primary', 1, 'connection', this)" in html

        # Secondary contacts should use 'secondary' type
        assert "generateOutreach('secondary', 0, 'inmail', this)" in html
        assert "generateOutreach('secondary', 0, 'connection', this)" in html

    def test_indices_are_independent_for_primary_and_secondary(
        self, authenticated_client, mock_db
    ):
        """Should use independent indices for primary and secondary contacts."""
        # Arrange
        job_id = ObjectId()
        mock_db.find_one.return_value = {
            "_id": job_id,
            "title": "Tech Lead",
            "company": "Innovation Labs",
            "status": "not processed",
            "score": 87,
            "primary_contacts": [
                {
                    "name": "Primary 1",
                    "role": "Manager",
                    "linkedin_url": "https://linkedin.com/in/p1"
                },
                {
                    "name": "Primary 2",
                    "role": "Lead",
                    "linkedin_url": "https://linkedin.com/in/p2"
                }
            ],
            "secondary_contacts": [
                {
                    "name": "Secondary 1",
                    "role": "Engineer",
                    "linkedin_url": "https://linkedin.com/in/s1"
                },
                {
                    "name": "Secondary 2",
                    "role": "Developer",
                    "linkedin_url": "https://linkedin.com/in/s2"
                }
            ]
        }

        # Act
        response = authenticated_client.get(f"/job/{str(job_id)}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Primary contacts: indices 0, 1
        assert "generateOutreach('primary', 0, 'inmail', this)" in html
        assert "generateOutreach('primary', 1, 'inmail', this)" in html

        # Secondary contacts: also indices 0, 1 (independent from primary)
        assert "generateOutreach('secondary', 0, 'inmail', this)" in html
        assert "generateOutreach('secondary', 1, 'inmail', this)" in html
