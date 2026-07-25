from dotenv import load_dotenv
from coin_market.bot import run_bot

# Load environment variables from .env file
load_dotenv()


def main():
    run_bot()


if __name__ == "__main__":
    main()