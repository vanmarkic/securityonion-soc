"""Tests for Repo domain model — ported from Go model/repo_test.go."""

from src.domain.repo import Repo, get_repos_default


class TestGetRepos:
    """Ported from TestGetRepos in repo_test.go."""

    def _default_repos(self):
        return [
            Repo(
                repo_url="https://github.com/Security-Onion-Solutions/securityonion-resources",
                license="DRL",
            ),
        ]

    def test_valid(self):
        config = {
            "rulesRepos": [
                {"repo": "repo1", "license": "MIT", "community": "1"},
                {"repo": "repo2", "license": "GPL2", "folder": "sigma/stable", "community": 0},
                {"repo": "repo3", "license": "DRL", "community": True},
                {"repo": "repo4", "license": "DRL", "community": "no"},
            ],
        }
        repos, err = get_repos_default(config, "rulesRepos", True, self._default_repos())
        assert err is None
        assert len(repos) == 4

        assert repos[0].repo_url == "repo1"
        assert repos[0].license == "MIT"
        assert repos[0].community is True

        assert repos[1].repo_url == "repo2"
        assert repos[1].license == "GPL2"
        assert repos[1].folder == "sigma/stable"
        assert repos[1].community is False

        assert repos[2].repo_url == "repo3"
        assert repos[2].license == "DRL"
        assert repos[2].community is True

        assert repos[3].repo_url == "repo4"
        assert repos[3].license == "DRL"
        assert repos[3].community is False

    def test_empty_config_returns_defaults(self):
        dflt = self._default_repos()
        repos, err = get_repos_default({}, "rulesRepos", True, dflt)
        assert err is None
        assert repos == dflt

    def test_missing_license(self):
        config = {
            "rulesRepos": [
                {"repo": "repo1"},
            ],
        }
        repos, err = get_repos_default(config, "rulesRepos", True, self._default_repos())
        assert err is not None
        assert 'missing "license" from "rulesRepos" entry' in err

    def test_missing_repo(self):
        config = {
            "rulesRepos": [
                {"license": "DRL"},
            ],
        }
        repos, err = get_repos_default(config, "rulesRepos", True, self._default_repos())
        assert err is not None
        assert 'missing "repo" link from "rulesRepos" entry' in err

    def test_wrong_structure_a(self):
        config = {"rulesRepos": "repo"}
        repos, err = get_repos_default(config, "rulesRepos", True, self._default_repos())
        assert err is not None
        assert 'top level config value "rulesRepos" is not an array of objects' in err

    def test_wrong_structure_b(self):
        config = {"rulesRepos": ["github"]}
        repos, err = get_repos_default(config, "rulesRepos", True, self._default_repos())
        assert err is not None
        assert '"rulesRepos" entry is not an object' in err
