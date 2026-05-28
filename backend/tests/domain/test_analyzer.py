"""Tests for Analyzer domain model — ported from Go model/analyzer_test.go."""

from src.domain.analyzer import Analyzer, new_analyzer


class TestGetModule:
    """Ported from TestGetModule in analyzer_test.go."""

    def test_module_and_paths(self):
        analyzer = new_analyzer("id", "path")
        assert analyzer.get_module() == "id.id"
        assert analyzer.get_site_packages_path() == "path/site-packages"
        assert analyzer.get_source_packages_path() == "path/source-packages"
        assert analyzer.get_requirements_path() == "path/requirements.txt"
