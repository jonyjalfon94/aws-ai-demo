import logging, os, random
import boto3
from flask import Flask, redirect, render_template, request
from src.memefy import Meme
from src.meme_data import MemeData
import requests
from requests.structures import CaseInsensitiveDict
from bs4 import BeautifulSoup


# Define variables
BUCKET = os.environ.get('BUCKET', 'rekognition-demo-sela')
REGION = os.environ.get('REGION', 'eu-west-1')

# Initialize clients
db = boto3.resource('dynamodb', region_name=REGION)
s3 = boto3.resource('s3', region_name=REGION)
comprehend = boto3.client('comprehend', region_name=REGION)
rekognition = boto3.client("rekognition", region_name=REGION)
translate = boto3.client('translate', region_name=REGION)
polly = boto3.client('polly', region_name=REGION)
meme_data = MemeData()

# Initialize app
app = Flask(__name__, template_folder='src/templates')

# Render HTML template
@app.route("/")
def homepage():
    # Get all images metadata from DynamoDB
    memes = meme_data.get_all_memes()
    # Return a Jinja2 HTML template and pass in image_entities as a parameter.
    return render_template("homepage.html", memes=memes, form_error=False)  

# Submit image to S3 Bucket
@app.route("/upload_photo", methods=["GET", "POST"])
def upload_photo():
    photo = request.files["file"]
    meme_data.add_new_meme(photo.filename, photo, BUCKET, REGION)
    return redirect("/")

# Image form button handler
@app.route("/process", methods=["GET", "POST"])
def process():

    file_name = request.form['Name']
    table = db.Table('Memes')
    meme = table.get_item(Key={"Name": file_name})["Item"]

    # Make a meme with the caption given by the user
    if request.form['action'] == 'Meme':
        caption = "Put a caption next time you press me" if len(request.form['caption']) == 0 else request.form['caption']
        memefy(file_name, caption)
        return redirect("/")
    
    # Generate image caption
    elif request.form['action'] == 'Rekognition Caption':
        generate_image_caption(file_name)
        return redirect("/")

    # Return an errpr if attempting to translate or get audio to an image without caption
    if meme["caption"] == "":
        memes = meme_data.get_all_memes()
        return render_template("homepage.html", memes=memes, form_error="The image you selected does not have a caption. Please add a caption and try again.")
    
    # Translate caption to the language of the user
    if request.form['action'] == 'Translate':
        translate_target_lang = request.form['language']
        translate_text(file_name, translate_target_lang)
    
    # Generate audio from the image caption
    elif request.form['action'] == 'Polly Audio':
        text_to_mp3(file_name)

    # # Redirect to the home page.
    return redirect("/")

# Generate image caption using AWS Rekognition for collecting labels and taking a quote from brainyquote.com or icanhazdadjoke.com
def generate_image_caption(file_name):

    # Download original image
    s3.Bucket(BUCKET).download_file(file_name, 'original.jpg')
    image={"S3Object": {"Bucket": BUCKET,"Name": file_name}}
    # Get image labels from the Rekognigtion API
    labels = rekognition.detect_labels(Image=image, MaxLabels=100, MinConfidence=90)["Labels"]
    quotes = []
    headers = CaseInsensitiveDict()
    headers["Accept"] = "application/json"
    # Get quotes from brainyquote.com via scraping
    for label in labels:
        quote_list = getQuotes(label["Name"])
        for quote in quote_list:
            quotes.append({'Label' : label, 'Quote' : quote.strip('\n')})
        # Get jokes from icanhazdadjoke.com
        jokes = requests.get('https://icanhazdadjoke.com/search?term=' + label["Name"], headers=headers).json()["results"]
        for joke in jokes:
            if len(joke["joke"]) < 80:
                quotes.append({'Label' : label, 'Quote' : joke["joke"]})

    selected_quote = random.choice(quotes)
    # Make a new meme with a random quote from the list
    selected_label = "Label selected: " + selected_quote["Label"]["Name"] + ", Confidence: " + str(selected_quote["Label"]["Confidence"])
    memefy(file_name, selected_quote['Quote'], selected_label)

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

# Uses PIL to write a caption on top of the image
def memefy(file_name, caption, label=""):

    # Download original image
    s3.Bucket(BUCKET).download_file(file_name, 'original.jpg')

    # Detect caption language using Comprehend
    language = comprehend.detect_dominant_language(Text=caption)["Languages"][0]["LanguageCode"]
    # Get caption sentiment using Comprehend
    sentiment = comprehend.detect_sentiment(Text=caption, LanguageCode=language)["Sentiment"]
    caption_sentiment = "Sentiment: " + sentiment.capitalize()
    # Generate meme
    meme = Meme(caption, 'original.jpg', "en")
    img = meme.draw()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Save meme to file
    img.save('captioned_image.jpg', optimize=True, quality=80)

    # Upload meme to bucket and save its metadata in DynamoDB
    meme_data.update_meme_caption("captioned_image.jpg", file_name, caption, language, label, caption_sentiment, BUCKET, REGION)

# Translates text into the target language using AWS Translate
def translate_text(file_name, target_lang):

    # Get image metadata from DynamoDB
    table = db.Table('Memes')
    meme = table.get_item(Key={"Name": file_name})["Item"]

    # If the target language is the same as the language of the caption, return
    if meme["caption_language"] == target_lang:
        return

    # Use AWS Translate to translate caption into target language
    response = translate.translate_text(
        Text=meme["caption"],
        SourceLanguageCode=meme["caption_language"],
        TargetLanguageCode=target_lang,
    )

    # Generate meme with translated text
    memefy(file_name, response['TranslatedText'])

# Get Polly Voice ID depending on the language of the caption
def get_voice(caption_language):
    if caption_language == "fr":
        voice = "Celine"
    elif caption_language == "pt":
        voice = "Camila"
    elif caption_language == "es":
        voice = "Conchita"
    elif caption_language == "it":
        voice = "Giorgio"
    # In case the language doesn't match any of the above, chose an english voice
    else:
        voice = "Kimberly"
    return voice

# Converts text to an mp3 file using AWS Polly
def text_to_mp3(file_name):

    # Get the image caption from DynamoDB
    table = db.Table('Memes')
    meme = table.get_item(Key={"Name": file_name})["Item"]

    # Generate audio from the caption
    output = polly.synthesize_speech (Text = meme["caption"], OutputFormat = "mp3", VoiceId = get_voice(meme["caption_language"]))
    # Saave audio to S3 and update the meme metadata in DynamoDB
    meme_data.update_meme_audio(file_name, output, BUCKET, REGION)

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
    # This is used when running locally.
    app.run(host="127.0.0.1", port=8080, debug=True)
