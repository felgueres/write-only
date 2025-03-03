from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("X_API_KEY")
API_SECRET = os.getenv("X_API_SECRET")

def authenticate() -> tuple[str, str]:
    """Complete the OAuth 1.0a authentication flow to get access tokens"""
    print("Authenticating...")
    request_token_url = "https://api.twitter.com/oauth/request_token?oauth_callback=oob&x_auth_access_type=write"
    oauth = OAuth1Session(API_KEY, client_secret=API_SECRET)

    try:
        fetch_response = oauth.fetch_request_token(request_token_url)
    except ValueError:
        return None, None
    resource_owner_key = fetch_response.get("oauth_token")
    resource_owner_secret = fetch_response.get("oauth_token_secret")
    print("Got OAuth token: %s" % resource_owner_key)

    base_authorization_url = "https://api.twitter.com/oauth/authorize"
    authorization_url = oauth.authorization_url(base_authorization_url)
    print("Please go here and authorize: %s" % authorization_url)
    verifier = input("Paste the PIN here: ")

    access_token_url = "https://api.twitter.com/oauth/access_token"
    oauth = OAuth1Session(
        API_KEY,
        client_secret=API_SECRET,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
    )
    
    try:
        oauth_tokens = oauth.fetch_access_token(access_token_url)
    except ValueError as e:
        print(f"Error obtaining access token: {e}")
        return None, None
    
    access_token = oauth_tokens["oauth_token"]
    access_token_secret = oauth_tokens["oauth_token_secret"]
    print(f"Access token: {access_token}")
    print(f"Access token secret: {access_token_secret}")
    
    with open(".env", "a") as f:
        f.write(f"USER_ACCESS_TOKEN={access_token}\nUSER_ACCESS_TOKEN_SECRET={access_token_secret}\n")
    
    return access_token, access_token_secret