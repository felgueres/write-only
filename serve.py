import os
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv
import argparse
from utils import authenticate
load_dotenv()

API_KEY = os.getenv("X_API_KEY")
API_SECRET = os.getenv("X_API_SECRET")
CHAR_LIMIT = 4000 

def get_file_content(file_path: str) -> str:
    with open(file_path, 'r') as file:
        content = file.read()
        if len(content) > CHAR_LIMIT:
            raise ValueError(f"File content exceeds {CHAR_LIMIT} characters")
        return content

def post_tweet(file_path: str, access_token: str, access_token_secret: str) -> str | None:
    """Post a tweet from a file using OAuth1Session"""
    try:
        content = get_file_content(file_path)
        oauth = OAuth1Session(
            client_key=API_KEY,
            client_secret=API_SECRET,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret
        )
        response = oauth.post(
            "https://api.twitter.com/2/tweets",
            json={ "text": content }
        )
        response.raise_for_status()
        return response.json()['data']['id']

    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post tweets from text files")
    parser.add_argument("--should_auth", required=False, action="store_true", help="Authenticate new account")
    parser.add_argument("file", help="Path to file whose content will be tweeted")
    args = parser.parse_args()

    if args.should_auth: 
        access_token, access_token_secret = authenticate()
        assert access_token and access_token_secret, "Bad auth"
    else:
        access_token = os.getenv("USER_ACCESS_TOKEN")
        access_token_secret = os.getenv("USER_ACCESS_TOKEN_SECRET")
        assert access_token and access_token_secret, "auth vars not set"

    tweet_id = post_tweet(
        file_path=args.file,
        access_token=access_token,
        access_token_secret=access_token_secret
    )

    print(f"Tweet ID is: {tweet_id}")
