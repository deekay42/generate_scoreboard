import numpy as np
from cassiopeia import *
from cassiopeia.datastores.common import HTTPError


config = get_default_config()
config['pipeline']['ChampionGG'] = {
    "package": "cassiopeia_championgg",
    "api_key": "496b4c2f287421a51a41aeb51a808f74"  # Your api.champion.gg API key (or an env var containing it)
}

config['pipeline']['RiotAPI'] = {
    "api_key": "RGAPI-39e77a14-355a-4826-8cfb-6f5cc68bdc7c",
    "limiting_share": 1.0,
    "request_error_handling": {
        "404": {
            "strategy": "throw"
        },
        "429": {
            "service": {
                "strategy": "exponential_backoff",
                "initial_backoff": 1.0,
                "backoff_factor": 2.0,
                "max_attempts": 4
            },
            "method": {
                "strategy": "retry_from_headers",
                "max_attempts": 5
            },
            "application": {
                "strategy": "retry_from_headers",
                "max_attempts": 5
            }
        },
        "500": {
            "strategy": "exponential_backoff",
            "initial_backoff": 1.0,
            "backoff_factor": 2.0,
            "max_attempts": 4
        },
        "503": {
            "strategy": "exponential_backoff",
            "initial_backoff": 1.0,
            "backoff_factor": 2.0,
            "max_attempts": 4
        },
        "timeout": {
            "strategy": "exponential_backoff",
            "initial_backoff": 1.0,
            "backoff_factor": 2.0,
            "max_attempts": 4
        },
        "403": {
            "strategy": "throw"
        }
    }
}


set_default_region("KR")
apply_settings(config)