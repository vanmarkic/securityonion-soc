"""Tests for app configuration loading."""

import json
from pathlib import Path

from src.config import AppConfig, load_config


class TestLoadConfig:
    def test_load_from_dict(self):
        raw = {
            "server": {
                "modules": {
                    "statickeyauth": {
                        "apiKey": "testkey",
                        "anonymousCidr": "0.0.0.0/0",
                    },
                    "filedatastore": {
                        "jobDir": "jobs",
                    },
                }
            }
        }
        cfg = AppConfig.from_dict(raw)
        assert cfg.statickeyauth.api_key == "testkey"
        assert cfg.statickeyauth.anonymous_cidr == "0.0.0.0/0"
        assert cfg.filedatastore.job_dir == "jobs"

    def test_load_from_file(self, tmp_path: Path):
        config_file = tmp_path / "sensoroni.json"
        config_file.write_text(
            json.dumps(
                {
                    "server": {
                        "modules": {
                            "statickeyauth": {
                                "apiKey": "filekey",
                                "anonymousCidr": "*",
                            },
                            "filedatastore": {"jobDir": "/tmp/jobs"},
                        }
                    }
                }
            )
        )
        cfg = load_config(str(config_file))
        assert cfg.statickeyauth.api_key == "filekey"
        assert cfg.statickeyauth.anonymous_cidr == "*"

    def test_missing_module_uses_defaults(self):
        raw = {"server": {"modules": {}}}
        cfg = AppConfig.from_dict(raw)
        assert cfg.statickeyauth.api_key == ""
        assert cfg.filedatastore.job_dir == "jobs"

    def test_staticrbac_config(self):
        raw = {
            "server": {
                "modules": {
                    "staticrbac": {
                        "roleFiles": ["rbac/roles"],
                        "userFiles": ["rbac/users"],
                        "scanIntervalMs": 30000,
                        "defaultRole": "auditor",
                    }
                }
            }
        }
        cfg = AppConfig.from_dict(raw)
        assert cfg.staticrbac.role_files == ["rbac/roles"]
        assert cfg.staticrbac.default_role == "auditor"

    def test_kratos_config(self):
        raw = {
            "server": {
                "modules": {
                    "kratos": {"hostUrl": "http://kratos:4434"}
                }
            }
        }
        cfg = AppConfig.from_dict(raw)
        assert cfg.kratos.host_url == "http://kratos:4434"
