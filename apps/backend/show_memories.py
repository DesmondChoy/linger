"""Print an account's saved memories on the server, for developers.

Inspect shows only memory IDs. Resolve them here, where the store lives:

    uv run python -m apps.backend.show_memories <username> [memory_id ...]

With no IDs, every active original and the curated retrieval view are listed.
"""

import argparse

from src.linger.services.memory import AccountContext, MemoryPolicyService

from .auth import account_id_for
from .config import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username")
    parser.add_argument("memory_ids", nargs="*", help="only these memories (IDs from Inspect)")
    args = parser.parse_args()

    service = MemoryPolicyService(REPO_ROOT / "memories")
    account = AccountContext(account_id_for(args.username))
    wanted = set(args.memory_ids)
    originals = [
        record for record in service.list_active(account)
        if not wanted or record.memory_id in wanted
    ]
    curated = [
        memory for memory in service.list_for_retrieval(account)
        if not wanted or memory.memory_id in wanted
    ]

    print(f"Originals ({len(originals)})")
    for record in originals:
        print(f"  {record.memory_id}  {record.created_at}  {record.capture_type}")
        print(f"    {record.text}")
    print(f"Retrieval view ({len(curated)})")
    for memory in curated:
        print(f"  {memory.memory_id}  {memory.kind}  from {', '.join(memory.source_memory_ids)}")
        print(f"    {memory.text}")
    missing = wanted - {record.memory_id for record in originals} - {memory.memory_id for memory in curated}
    for memory_id in sorted(missing):
        print(f"Not found for {args.username}: {memory_id}")


if __name__ == "__main__":
    main()
