"""Call a separately published draft workflow; never reuse the extraction key."""
import argparse
import getpass
import json
import os
from pathlib import Path

from .agent_service import AgentError, AgentService
from .dify_runner import DifyRunner, parse_object


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    parser.add_argument('--user', required=True, help='Opaque authenticated user ID')
    args = parser.parse_args()
    try:
        request = parse_object(args.request.read_bytes())
        service = AgentService(None)
        service.validate_draft_request(request)
        key = os.getenv('DIFY_DRAFT_API_KEY') or getpass.getpass('Dify draft app API key (hidden): ').strip()
        if key == os.getenv('DIFY_EXTRACT_API_KEY'):
            raise AgentError('Use a separate draft workflow API key')
        service.runner = DifyRunner(draft_api_key=key, user=args.user,
                                    base_url=os.getenv('DIFY_BASE_URL', 'https://api.dify.ai/v1'))
        result = service.draft(request)
    except (AgentError, OSError, EOFError) as exc:
        parser.exit(1, 'Draft failed: ' + str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
