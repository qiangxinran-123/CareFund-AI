"""Safe in-process error types for Backend integration; no wire-schema changes."""


class AgentError(ValueError):
    code = 'agent_rejected'


class AgentConfigurationError(AgentError):
    code = 'agent_configuration_error'


class AgentContractError(AgentError):
    code = 'agent_contract_error'


class AgentTransportError(AgentError):
    code = 'agent_transport_error'
    # A timeout/disconnect is not proof that the remote generation was cancelled.
    execution_may_be_running = True


class AgentWorkflowError(AgentError):
    code = 'agent_workflow_error'


class AgentHTTPError(AgentError):
    code = 'agent_http_error'

    def __init__(self, status_code, provider_code=None):
        self.status_code = status_code
        self.provider_code = provider_code
        suffix = ' (' + provider_code + ')' if provider_code else ''
        super().__init__('Dify HTTP error: ' + str(status_code) + suffix)
