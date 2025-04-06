import os
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv
import argparse
from utils import authenticate
import base64
load_dotenv()

API_KEY = os.getenv("X_API_KEY")
API_SECRET = os.getenv("X_API_SECRET")
CHAR_LIMIT = 4000 

def encode_image(image_path: str) -> str:
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def upload_media(image_path: str, oauth: OAuth1Session) -> str:
    media_endpoint = "https://upload.twitter.com/1.1/media/upload.json"
    media_data = encode_image(image_path=image_path)
    upload_params = {
        "media_data": media_data
    }
    response = oauth.post(media_endpoint, data=upload_params)
    response.raise_for_status()
    return response.json()["media_id_string"]


def get_file_content(file_path: str) -> str:
    with open(file_path, 'r') as file:
        content = file.read()
        if len(content) > CHAR_LIMIT:
            raise ValueError(f"File content exceeds {CHAR_LIMIT} characters")
        return content

def post_tweet(file_path: str, access_token: str, access_token_secret: str, image_paths: list = None) -> str | None:
    """Post a tweet from a file using OAuth1Session"""
    try:
        content = get_file_content(file_path)
        oauth = OAuth1Session(
            client_key=API_KEY,
            client_secret=API_SECRET,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret
        )
        payload = {"text": content}

        if image_paths and len(image_paths) > 0:
            media_ids = []
            for image_path in image_paths:
                media_id = upload_media(image_path=image_path, oauth=oauth)
                media_ids.append(media_id)
            payload["media"] = {"media_ids": media_ids}
        
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
    """usage for file
    python serve.py --file firsttweet.txt
    usage for images
    python serve.py --file firsttweet.txt --images image1.jpg image2.jpg image3.jpg image4.jpg
    """
    parser = argparse.ArgumentParser(description="Post tweets from text files")
    parser.add_argument("--should_auth", required=False, action="store_true", help="Authenticate new account")
    parser.add_argument("--file", help="Path to file whose content will be tweeted")
    parser.add_argument("--images", nargs="*", help="Path to file whose content will be tweeted")

    args = parser.parse_args()

    if args.should_auth: 
        access_token, access_token_secret = authenticate()
        assert access_token and access_token_secret, "Bad auth"
    else:
        access_token = os.getenv("USER_ACCESS_TOKEN")
        access_token_secret = os.getenv("USER_ACCESS_TOKEN_SECRET")
        assert access_token and access_token_secret, "auth vars not set"
    
    if args.images and len(args.images) > 4:
        print("Twitter allows maximum of 4 images, getting first 4")
        args.images = args.images[:4] 

    tweet_id = post_tweet(
        file_path=args.file,
        access_token=access_token,
        access_token_secret=access_token_secret,
        image_paths=args.images
    )

    print(f"Tweet ID is: {tweet_id}")
