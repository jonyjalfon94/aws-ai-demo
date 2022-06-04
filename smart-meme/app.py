import logging, os, random
from turtle import home

import boto3
from flask import Flask, redirect, render_template, request
# from PIL import Image, ImageDraw, ImageFont
from memefy import Meme
import requests
from requests.structures import CaseInsensitiveDict
from bs4 import BeautifulSoup


# Define variables

# Get bucket name from environment variable or set to default value
BUCKET = os.environ.get('BUCKET', 'rekognition-demo-sela')
REGION = os.environ.get('REGION', 'eu-west-1')

# Initialize clients
db = boto3.resource('dynamodb', region_name=REGION)
s3 = boto3.resource('s3', region_name=REGION)
comprehend = boto3.client('comprehend', region_name=REGION)
rekognition = boto3.client("rekognition", region_name=REGION)
translate = boto3.client('translate', region_name=REGION)
polly = boto3.client('polly', region_name=REGION)

# Initialize app
app = Flask(__name__)

# Render HTML template
@app.route("/")
def homepage():
    # Get all images metadata from DynamoDB
    table = db.Table('Memes')
    response = table.scan()
    image_entities = response['Items']
    # Return a Jinja2 HTML template and pass in image_entities as a parameter.
    return render_template("homepage.html", image_entities=image_entities, form_error=False)  

# Submit image to Google Cloud Storage
@app.route("/upload_photo", methods=["GET", "POST"])
def upload_photo():
    photo = request.files["file"]
    s3.Bucket(BUCKET).upload_fileobj(photo, photo.filename, ExtraArgs={'ACL':'public-read', 'CacheControl' : 'max-age=0'})
    table = db.Table('Memes')
    response = table.put_item(
        Item={
            'Name': photo.filename,
            'processed': False,
            'original_image_public_url': f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{photo.filename}",
            'processed_image_public_url': '',
            'caption' : '',
            'caption_language':'',
            'mp3_bucket_url':''
        }
    )
    return redirect("/")

# Image form button handler
@app.route("/process", methods=["GET", "POST"])
def process():
    file_name = request.form['Name']
    table = db.Table('Memes')
    meme = table.get_item(Key={
      "Name": file_name,
    })["Item"]
    if request.form['action'] == 'Meme':
        caption = "Put a caption next time you press me" if len(request.form['caption']) == 0 else request.form['caption']
        memefy(file_name, caption)
        return redirect("/")
    elif request.form['action'] == 'Rekognition Generated Caption':
        generate_image_caption(file_name)
        return redirect("/")
    if meme["caption"] == "":
        table = db.Table('Memes')
        image_entities = table.scan()['Items']
        return render_template("homepage.html", image_entities=image_entities, form_error="The image you selected does not have a caption. Please add a caption and try again.")
    if request.form['action'] == 'Translate':
        translate_target_lang = request.form['language']
        translate_text(file_name, translate_target_lang)
    elif request.form['action'] == 'Polly Get Audio':
        text_to_mp3(file_name)

    # # Redirect to the home page.
    return redirect("/")

# Get quotes from brainyquote.com by web scraping with BeautifulSoup for a given keyword
def getQuotes(keyword):
    quoteArray = []
    base_url = "https://www.brainyquote.com/quotes/keywords/"
    url = base_url + keyword + ".html"
    response_data = requests.get(url).text[:]
    soup = BeautifulSoup(response_data, 'html.parser')
    # loop through the html source code of the website and find specific keys
    for item in soup.find_all("a", class_="b-qt"):
        quote = item.get_text().rstrip()
        if len(quote) < 80:
            quoteArray.append(quote)
    return quoteArray

# Generate image caption using Google Vision API for collecting labels and taking a quote from brainyquote.com
def generate_image_caption(file_name):
    # Download original image
    s3.Bucket(BUCKET).download_file(file_name, 'original.jpg')
    response = rekognition.detect_labels(
		Image={
			"S3Object": {
				"Bucket": BUCKET,
				"Name": file_name,
			}
		},
		MaxLabels=100,
		MinConfidence=90,
	)
    labels = response["Labels"]
    quotes = []
    for i in range(3):
        for label in labels:
            #Get quotes from the brainyquote.com for each label
            quotes.extend(getQuotes(label["Name"]))
        if  len(quotes) > 0:
            break
        if i == 2 and len(quotes) == 0:
            print(i)
            for label in labels:
                #Get quotes from icanhazdadjoke.com instead
                label_name = label["Name"]
                headers = CaseInsensitiveDict()
                headers["Accept"] = "application/json"
                jokes = requests.get(f"https://icanhazdadjoke.com/search?term={label_name}", headers=headers).json()["results"]
                for joke in jokes:
                    if len(joke["joke"]) < 80:
                        print(joke["joke"])
                        quotes.append(joke["joke"])
    memefy(file_name, random.choice(quotes))

# Uses PIL to write a caption on top of the image
def memefy(file_name, caption):
  # Download file
  s3.Bucket(BUCKET).download_file(file_name, 'original.jpg')
  # Detect caption language
  language = comprehend.detect_dominant_language(Text=caption)["Languages"][0]["LanguageCode"]
  # Generate meme
  meme = Meme(caption, 'original.jpg', "en")
  img = meme.draw()
  if img.mode in ("RGBA", "P"):   #Without this the code can break sometimes
      img = img.convert("RGB")
  img.save('captioned_image.jpg', optimize=True, quality=80)

  # Upload meme to bucket
  s3.Bucket(BUCKET).upload_file("captioned_image.jpg", f"processed/{file_name}", ExtraArgs={'ACL':'public-read', 'CacheControl' : 'max-age=0'})

  # Update image metadata
  table = db.Table('Memes')
  table.update_item(
      Key={
          'Name': file_name
      },
      UpdateExpression='SET #proc = :proc, caption = :caption, #procimg = :procimg, #captionlang = :captionlang',
      ExpressionAttributeValues={
          ':proc': True,
          ':caption': caption,
          ':captionlang' : language,
          ':procimg': f"https://{BUCKET}.s3.{REGION}.amazonaws.com/processed/{file_name}"
      },
      ExpressionAttributeNames={
        "#proc": "processed",
        "#procimg" : "processed_image_public_url",
        '#captionlang' : "caption_language"
      },
      ReturnValues="UPDATED_NEW"
  )

# Translates text into the target language using Google cloud translate API
def translate_text(file_name, target_lang):
    # Get datastore entity for image
    table = db.Table('Memes')
    meme = table.get_item(Key={
      "Name": file_name,
    })["Item"]
    if meme["caption_language"] == target_lang:
        return
    # Use Google translate API to translate caption into target language
    response = translate.translate_text(
        Text=meme["caption"],
        SourceLanguageCode=meme["caption_language"],
        TargetLanguageCode=target_lang,
    )
    # Generate meme with translated text
    memefy(file_name, response['TranslatedText'])

def get_voice(caption_language):
    if caption_language == "fr":
        voice = "Celine"
    elif caption_language == "ru":
        voice = "Maxim"
    elif caption_language == "es":
        voice = "Conchita"
    elif caption_language == "it":
        voice = "Giorgio"
    # In case the language doesn't match any of the above, chose an english voice
    else:
        voice = "Kimberly"
    return voice

# Converts text to an mp3 file using Text to Speech API
def text_to_mp3(file_name):
    # Get the image caption from its Datastore entity
    table = db.Table('Memes')
    meme = table.get_item(Key={
      "Name": file_name,
    })["Item"]
    output = polly.synthesize_speech (
        Text = meme["caption"], OutputFormat = "mp3", VoiceId = get_voice(meme["caption_language"])
    )
    print(output['AudioStream'])
    s3.Bucket(BUCKET).upload_fileobj(output['AudioStream'], f"audio/{file_name}", ExtraArgs={'ACL':'public-read', 'CacheControl' : 'max-age=0'})
    table = db.Table('Memes')
    table.update_item(
        Key={
            'Name': file_name
        },
        UpdateExpression='SET #audio = :audio',
        ExpressionAttributeValues={
            ':audio': f"https://{BUCKET}.s3.{REGION}.amazonaws.com/audio/{file_name}"
        },
        ExpressionAttributeNames={
          "#audio" : "mp3_bucket_url",
        },
        ReturnValues="UPDATED_NEW"
    )

@app.errorhandler(500)
def server_error(e):
    logging.exception("An error occurred during a request.")
    return (
        """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(
            e
        ),
        500,
    )

if __name__ == "__main__":
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)
