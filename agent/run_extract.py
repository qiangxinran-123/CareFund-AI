"""Run a published Dify extraction workflow against a local JSON request."""
import argparse
import getpass
import json
from pathlib import Path
from .agent_service import AgentService, AgentError
from .dify_runner import DifyRunner, parse_object


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('request', type=Path)
    parser.add_argument('--user', required=True, help='Opaque per-user ID; do not use a name or phone number')
    args = parser.parse_args()
    try:
        request = parse_object(args.request.read_bytes())
        import os
        key = os.getenv('DIFY_EXTRACT_API_KEY') or getpass.getpass('Dify app API key (hidden): ')
        runner = DifyRunner(extract_api_key=key, user=args.user,
                            base_url=os.getenv('DIFY_BASE_URL', 'https://api.dify.ai/v1'))
        result = AgentService(runner).extract(request)
    except (AgentError, OSError) as exc:
        parser.exit(1, 'Extraction failed: ' + str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
