from ..domain import ProviderName

USAGE_MESSAGE = (
        "📖 Usage:\n"
        "/prices [options]\n"
        "        --provider NAME   | provider=NAME   (filter by provider)\n"
        "        --type otc|p2p    | type=otc|p2p    (show only OTC or P2P)\n"
        "        --volume NUM      | volume=NUM      (volume for VWAP calculation)\n"
        "        --repeat SEC      | repeat=SEC      (start auto-updates every SEC seconds)\n"
        "/list                            (list your subscriptions)\n"
        "/stop <id>                       (pause subscription by ID)\n"
        "/resume <id>                     (resume subscription by ID)\n"
        "/delete <id>                     (delete subscription by ID)\n"
        "/help                            (show this message)\n\n"
        "Valid providers: " + ", ".join([p.value for p in ProviderName])
)
