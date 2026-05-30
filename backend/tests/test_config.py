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

    def test_salt_config_full_block(self):
        raw = {
            "server": {
                "modules": {
                    "salt": {
                        "timeoutMs": 15000,
                        "longRelayTimeoutMs": 60000,
                        "saltstackDir": "/srv/saltstack",
                        "queueDir": "/srv/queue",
                        "bypassErrors": True,
                    }
                }
            }
        }
        cfg = AppConfig.from_dict(raw)
        assert cfg.salt is not None
        assert cfg.salt.timeout_ms == 15000
        assert cfg.salt.long_relay_timeout_ms == 60000
        assert cfg.salt.saltstack_dir == "/srv/saltstack"
        assert cfg.salt.queue_dir == "/srv/queue"
        assert cfg.salt.bypass_errors is True

    def test_salt_config_absent_is_none(self):
        raw = {"server": {"modules": {}}}
        cfg = AppConfig.from_dict(raw)
        assert cfg.salt is None

    def test_salt_config_missing_keys_use_defaults(self):
        raw = {"server": {"modules": {"salt": {"timeoutMs": 5000}}}}
        cfg = AppConfig.from_dict(raw)
        assert cfg.salt is not None
        assert cfg.salt.timeout_ms == 5000
        assert cfg.salt.long_relay_timeout_ms == 120_000
        assert cfg.salt.saltstack_dir == "/opt/so/saltstack"
        assert cfg.salt.queue_dir == "/opt/so/conf/soc/queue"
        assert cfg.salt.bypass_errors is False
