import sys
import pytest

from chalice import __version__ as chalice_version
from chalice.config import Config, DeployedResources


def test_config_create_method():
    c = Config.create(app_name='foo')
    assert c.app_name == 'foo'
    # Otherwise attributes default to None meaning 'not set'.
    assert c.profile is None
    assert c.api_gateway_stage is None


def test_default_chalice_stage():
    c = Config()
    assert c.chalice_stage == 'dev'


def test_version_defaults_to_1_when_missing():
    c = Config()
    assert c.config_file_version == '1.0'


def test_default_value_of_manage_iam_role():
    c = Config.create()
    assert c.manage_iam_role


def test_manage_iam_role_explicitly_set():
    c = Config.create(manage_iam_role=False)
    assert not c.manage_iam_role
    c = Config.create(manage_iam_role=True)
    assert c.manage_iam_role


def test_can_chain_lookup():
    user_provided_params = {
        'api_gateway_stage': 'user_provided_params',
    }

    config_from_disk = {
        'api_gateway_stage': 'config_from_disk',
        'app_name': 'config_from_disk',
    }

    default_params = {
        'api_gateway_stage': 'default_params',
        'app_name': 'default_params',
        'project_dir': 'default_params',
    }

    c = Config(chalice_stage='dev',
               user_provided_params=user_provided_params,
               config_from_disk=config_from_disk,
               default_params=default_params)
    assert c.api_gateway_stage == 'user_provided_params'
    assert c.app_name == 'config_from_disk'
    assert c.project_dir == 'default_params'

    assert c.config_from_disk == config_from_disk


def test_user_params_is_optional():
    c = Config(config_from_disk={'api_gateway_stage': 'config_from_disk'},
               default_params={'api_gateway_stage': 'default_params'})
    assert c.api_gateway_stage == 'config_from_disk'


def test_can_chain_chalice_stage_values():
    disk_config = {
        'api_gateway_stage': 'dev',
        'stages': {
            'dev': {
            },
            'prod': {
                'api_gateway_stage': 'prod',
                'iam_role_arn': 'foobar',
                'manage_iam_role': False,
            }
        }
    }
    c = Config(chalice_stage='dev',
               config_from_disk=disk_config)
    assert c.api_gateway_stage == 'dev'
    assert c.manage_iam_role

    prod = Config(chalice_stage='prod',
                  config_from_disk=disk_config)
    assert prod.api_gateway_stage == 'prod'
    assert prod.iam_role_arn == 'foobar'
    assert not prod.manage_iam_role


def test_can_chain_function_values():
    disk_config = {
        'lambda_timeout': 10,
        'stages': {
            'dev': {
                'lambda_timeout': 20,
                'lambda_functions': {
                    'api_handler': {
                        'lambda_timeout': 30,
                    }
                }
            }
        }
    }
    c = Config(chalice_stage='dev',
               config_from_disk=disk_config)
    assert c.lambda_timeout == 30


def test_can_create_scope_obj_with_new_function():
    disk_config = {
        'lambda_timeout': 10,
        'stages': {
            'dev': {
                'manage_iam_role': True,
                'iam_role_arn': 'role-arn',
                'autogen_policy': True,
                'iam_policy_file': 'policy.json',
                'environment_variables': {'env': 'stage'},
                'lambda_timeout': 1,
                'lambda_memory_size': 1,
                'tags': {'tag': 'stage'},
                'lambda_functions': {
                    'api_handler': {
                        'lambda_timeout': 30,
                    },
                    'myauth': {
                        # We're purposefully using different
                        # values for everything in the stage
                        # level config to ensure we can pull
                        # from function scoped config properly.
                        'manage_iam_role': True,
                        'iam_role_arn': 'auth-role-arn',
                        'autogen_policy': True,
                        'iam_policy_file': 'function.json',
                        'environment_variables': {'env': 'function'},
                        'lambda_timeout': 2,
                        'lambda_memory_size': 2,
                        'tags': {'tag': 'function'},
                    }
                }
            }
        }
    }
    c = Config(chalice_stage='dev', config_from_disk=disk_config)
    new_config = c.scope(chalice_stage='dev',
                         function_name='myauth')
    assert new_config.manage_iam_role == True
    assert new_config.iam_role_arn == 'auth-role-arn'
    assert new_config.autogen_policy == True
    assert new_config.iam_policy_file == 'function.json'
    assert new_config.environment_variables == {'env': 'function'}
    assert new_config.lambda_timeout == 2
    assert new_config.lambda_memory_size == 2
    assert new_config.tags['tag'] == 'function'


@pytest.mark.parametrize('stage_name,function_name,expected', [
    ('dev', 'api_handler', 'dev-api-handler'),
    ('dev', 'myauth', 'dev-myauth'),
    ('beta', 'api_handler', 'beta-api-handler'),
    ('beta', 'myauth', 'beta-myauth'),
    ('prod', 'api_handler', 'prod-stage'),
    ('prod', 'myauth', 'prod-stage'),
    ('foostage', 'api_handler', 'global'),
    ('foostage', 'myauth', 'global'),
])
def test_can_create_scope_new_stage_and_function(stage_name, function_name,
                                                 expected):
    disk_config = {
        'environment_variables': {'from': 'global'},
        'stages': {
            'dev': {
                'environment_variables': {'from': 'dev-stage'},
                'lambda_functions': {
                    'api_handler': {
                        'environment_variables': {
                            'from': 'dev-api-handler',
                        }
                    },
                    'myauth': {
                        'environment_variables': {
                            'from': 'dev-myauth',
                        }
                    }
                }
            },
            'beta': {
                'environment_variables': {'from': 'beta-stage'},
                'lambda_functions': {
                    'api_handler': {
                        'environment_variables': {
                            'from': 'beta-api-handler',
                        }
                    },
                    'myauth': {
                        'environment_variables': {
                            'from': 'beta-myauth',
                        }
                    }
                }
            },
            'prod': {
                'environment_variables': {'from': 'prod-stage'},
            }
        }
    }
    c = Config(chalice_stage='dev', config_from_disk=disk_config)
    new_config = c.scope(chalice_stage=stage_name,
                         function_name=function_name)
    assert new_config.environment_variables == {'from': expected}


def test_new_scope_config_is_separate_copy():
    original = Config(chalice_stage='dev', function_name='foo')
    new_config = original.scope(chalice_stage='prod', function_name='bar')

    # The original should not have been mutated.
    assert original.chalice_stage == 'dev'
    assert original.function_name == 'foo'

    assert new_config.chalice_stage == 'prod'
    assert new_config.function_name == 'bar'


def test_can_create_deployed_resource_from_dict():
    d = DeployedResources.from_dict({
        'backend': 'api',
        'api_handler_arn': 'arn',
        'api_handler_name': 'name',
        'rest_api_id': 'id',
        'api_gateway_stage': 'stage',
        'region': 'region',
        'chalice_version': '1.0.0',
        'lambda_functions': {},
    })
    assert d.backend == 'api'
    assert d.api_handler_arn == 'arn'
    assert d.api_handler_name == 'name'
    assert d.rest_api_id == 'id'
    assert d.api_gateway_stage == 'stage'
    assert d.region == 'region'
    assert d.chalice_version == '1.0.0'
    assert d.lambda_functions == {}


def test_lambda_functions_not_required_from_dict():
    older_version = {
        # Older versions of chalice did not include the
        # lambda_functions key.
        'backend': 'api',
        'api_handler_arn': 'arn',
        'api_handler_name': 'name',
        'rest_api_id': 'id',
        'api_gateway_stage': 'stage',
        'region': 'region',
        'chalice_version': '1.0.0',
    }
    d = DeployedResources.from_dict(older_version)
    assert d.lambda_functions == {}


def test_environment_from_top_level():
    config_from_disk = {'environment_variables': {"foo": "bar"}}
    c = Config('dev', config_from_disk=config_from_disk)
    assert c.environment_variables == config_from_disk['environment_variables']


def test_environment_from_stage_level():
    config_from_disk = {
        'stages': {
            'prod': {
                'environment_variables': {"foo": "bar"}
            }
        }
    }
    c = Config('prod', config_from_disk=config_from_disk)
    assert c.environment_variables == \
            config_from_disk['stages']['prod']['environment_variables']


def test_env_vars_chain_merge():
    config_from_disk = {
        'environment_variables': {
            'top_level': 'foo',
            'shared_stage_key': 'from-top',
            'shared_stage': 'from-top',
        },
        'stages': {
            'prod': {
                'environment_variables': {
                    'stage_var': 'bar',
                    'shared_stage_key': 'from-stage',
                    'shared_stage': 'from-stage',
                },
                'lambda_functions': {
                    'api_handler': {
                        'environment_variables': {
                            'function_key': 'from-function',
                            'shared_stage': 'from-function',
                        }
                    }
                }
            }
        }
    }
    c = Config('prod', config_from_disk=config_from_disk)
    resolved = c.environment_variables
    assert resolved == {
        'top_level': 'foo',
        'stage_var': 'bar',
        'shared_stage': 'from-function',
        'function_key': 'from-function',
        'shared_stage_key': 'from-stage',
    }


def test_can_load_python_version():
    c = Config('dev')
    expected_runtime = {
        2: 'python2.7',
        3: 'python3.6',
    }[sys.version_info[0]]
    assert c.lambda_python_version == expected_runtime


class TestConfigureLambdaMemorySize(object):
    def test_not_set(self):
        c = Config('dev', config_from_disk={})
        assert c.lambda_memory_size is None

    def test_set_lambda_memory_size_global(self):
        config_from_disk = {
            'lambda_memory_size': 256
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.lambda_memory_size == 256

    def test_set_lambda_memory_size_stage(self):
        config_from_disk = {
            'stages': {
                'dev': {
                    'lambda_memory_size': 256
                }
            }
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.lambda_memory_size == 256

    def test_set_lambda_memory_size_override(self):
        config_from_disk = {
            'lambda_memory_size': 128,
            'stages': {
                'dev': {
                    'lambda_memory_size': 256
                }
            }
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.lambda_memory_size == 256


class TestConfigureLambdaTimeout(object):
    def test_not_set(self):
        c = Config('dev', config_from_disk={})
        assert c.lambda_timeout is None

    def test_set_lambda_timeout_global(self):
        config_from_disk = {
            'lambda_timeout': 120
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.lambda_timeout == 120

    def test_set_lambda_memory_size_stage(self):
        config_from_disk = {
            'stages': {
                'dev': {
                    'lambda_timeout': 120
                }
            }
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.lambda_timeout == 120

    def test_set_lambda_memory_size_override(self):
        config_from_disk = {
            'lambda_timeout': 60,
            'stages': {
                'dev': {
                    'lambda_timeout': 120
                }
            }
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.lambda_timeout == 120


class TestConfigureTags(object):
    def test_default_tags(self):
        c = Config('dev', config_from_disk={'app_name': 'myapp'})
        assert c.tags == {
            'aws-chalice': 'version=%s:stage=dev:app=myapp' % chalice_version
        }

    def test_tags_global(self):
        config_from_disk = {
            'app_name': 'myapp',
            'tags': {'mykey': 'myvalue'}
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.tags == {
            'mykey': 'myvalue',
            'aws-chalice': 'version=%s:stage=dev:app=myapp' % chalice_version
        }

    def test_tags_stage(self):
        config_from_disk = {
            'app_name': 'myapp',
            'stages': {
                'dev': {
                    'tags': {'mykey': 'myvalue'}
                }
            }
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.tags == {
            'mykey': 'myvalue',
            'aws-chalice': 'version=%s:stage=dev:app=myapp' % chalice_version
        }

    def test_tags_merge(self):
        config_from_disk = {
            'app_name': 'myapp',
            'tags': {
                'onlyglobalkey': 'globalvalue',
                'sharedkey': 'globalvalue',
                'sharedstage': 'globalvalue',
            },
            'stages': {
                'dev': {
                    'tags': {
                        'sharedkey': 'stagevalue',
                        'sharedstage': 'stagevalue',
                        'onlystagekey': 'stagevalue',
                    },
                    'lambda_functions': {
                        'api_handler': {
                            'tags': {
                                'sharedkey': 'functionvalue',
                                'onlyfunctionkey': 'functionvalue',
                            }
                        }
                    }
                }
            }
        }
        c = Config('dev', config_from_disk=config_from_disk)
        assert c.tags == {
            'onlyglobalkey': 'globalvalue',
            'onlystagekey': 'stagevalue',
            'onlyfunctionkey': 'functionvalue',
            'sharedstage': 'stagevalue',
            'sharedkey': 'functionvalue',
            'aws-chalice': 'version=%s:stage=dev:app=myapp' % chalice_version
        }

    def test_tags_specified_does_not_override_chalice_tag(self):
        c = Config.create(
            chalice_stage='dev', app_name='myapp',
            tags={'aws-chalice': 'attempted-override'})
        assert c.tags == {
            'aws-chalice': 'version=%s:stage=dev:app=myapp' % chalice_version,
        }
